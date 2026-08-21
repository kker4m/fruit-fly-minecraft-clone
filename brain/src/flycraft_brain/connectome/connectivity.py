from __future__ import annotations

from pathlib import Path
from typing import Collection, Literal

import pandas as pd
import pyarrow.compute as pc
import pyarrow.dataset as ds

Direction = Literal["inputs", "outputs", "both"]


class ConnectivityStore:
    """Predicate-filtered access to Eon's FAFB v783 connectivity parquet."""

    COLUMNS = (
        "Presynaptic_ID",
        "Postsynaptic_ID",
        "Connectivity",
        "Excitatory",
        "Excitatory x Connectivity",
    )

    def __init__(self, data_dir: str | Path = "data/fly-brain") -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.path = self.data_dir / "2025_Connectivity_783.parquet"
        if not self.path.is_file():
            raise FileNotFoundError(
                f"Missing connectivity file: {self.path}. "
                "Run scripts/fetch_fly_brain_data.py."
            )
        self.dataset = ds.dataset(self.path, format="parquet")

    def neighbors(
        self,
        root_id: int,
        *,
        direction: Direction = "both",
        min_synapses: int = 1,
    ) -> pd.DataFrame:
        if direction not in {"inputs", "outputs", "both"}:
            raise ValueError("direction must be 'inputs', 'outputs', or 'both'")
        if min_synapses < 1:
            raise ValueError("min_synapses must be positive")

        frames = []
        if direction in {"outputs", "both"}:
            outputs = self._scan(pc.field("Presynaptic_ID") == int(root_id))
            outputs["direction"] = "output"
            outputs["partner_id"] = outputs["Postsynaptic_ID"]
            frames.append(outputs)
        if direction in {"inputs", "both"}:
            inputs = self._scan(pc.field("Postsynaptic_ID") == int(root_id))
            inputs["direction"] = "input"
            inputs["partner_id"] = inputs["Presynaptic_ID"]
            frames.append(inputs)

        if not frames:
            return self._empty_neighbors()
        result = pd.concat(frames, ignore_index=True)
        result = result[result["Connectivity"] >= min_synapses]
        return result.sort_values(
            ["Connectivity", "direction", "partner_id"],
            ascending=[False, True, True],
            kind="stable",
        ).reset_index(drop=True)

    def between(
        self,
        source_ids: Collection[int],
        target_ids: Collection[int],
        *,
        min_synapses: int = 1,
    ) -> pd.DataFrame:
        if min_synapses < 1:
            raise ValueError("min_synapses must be positive")
        sources = [int(value) for value in source_ids]
        targets = [int(value) for value in target_ids]
        if not sources or not targets:
            return pd.DataFrame(columns=self.COLUMNS)
        predicate = pc.field("Presynaptic_ID").isin(sources) & pc.field(
            "Postsynaptic_ID"
        ).isin(targets)
        result = self._scan(predicate)
        result = result[result["Connectivity"] >= min_synapses]
        return result.sort_values(
            "Connectivity", ascending=False, kind="stable"
        ).reset_index(drop=True)

    def _scan(self, predicate: pc.Expression) -> pd.DataFrame:
        return self.dataset.to_table(
            columns=list(self.COLUMNS), filter=predicate
        ).to_pandas()

    @classmethod
    def _empty_neighbors(cls) -> pd.DataFrame:
        return pd.DataFrame(columns=[*cls.COLUMNS, "direction", "partner_id"])
