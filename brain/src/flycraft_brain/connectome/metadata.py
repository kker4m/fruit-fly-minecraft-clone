from __future__ import annotations

from pathlib import Path
from typing import Collection, Mapping

import pandas as pd


class CodexMetadata:
    """Local, queryable view of the public FlyWire Codex FAFB v783 tables."""

    VERSION = "783"
    REQUIRED_FILES = (
        "classification.csv.gz",
        "consolidated_cell_types.csv.gz",
        "neurons.csv.gz",
    )
    SEARCH_COLUMNS = (
        "primary_type",
        "additional_type(s)",
        "flow",
        "super_class",
        "class",
        "sub_class",
        "hemilineage",
        "side",
        "nerve",
        "group",
        "nt_type",
        "labels",
    )

    def __init__(
        self,
        data_dir: str | Path = "data/fly-brain",
        *,
        load_labels: bool = False,
    ) -> None:
        self.data_dir = Path(data_dir).expanduser().resolve()
        self.metadata_dir = self.data_dir / f"codex-{self.VERSION}"
        self._validate_files(load_labels=load_labels)
        self.table = self._load_table(load_labels=load_labels)

    def _validate_files(self, *, load_labels: bool) -> None:
        required = list(self.REQUIRED_FILES)
        if load_labels:
            required.append("labels.csv.gz")
        missing = [
            name for name in required if not (self.metadata_dir / name).is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"Missing Codex v{self.VERSION} metadata in {self.metadata_dir}: "
                f"{', '.join(missing)}. Run scripts/fetch_flywire_metadata.py."
            )

    def _load_table(self, *, load_labels: bool) -> pd.DataFrame:
        classification = pd.read_csv(
            self.metadata_dir / "classification.csv.gz", dtype={"root_id": "int64"}
        )
        cell_types = pd.read_csv(
            self.metadata_dir / "consolidated_cell_types.csv.gz",
            dtype={"root_id": "int64"},
        )
        neurons = pd.read_csv(
            self.metadata_dir / "neurons.csv.gz", dtype={"root_id": "int64"}
        )
        table = classification.merge(cell_types, on="root_id", how="left").merge(
            neurons, on="root_id", how="left"
        )

        completeness_path = self.data_dir / "2025_Completeness_783.csv"
        if completeness_path.is_file():
            modeled_ids = pd.read_csv(completeness_path, index_col=0).index.astype(
                "int64"
            )
            table["modeled"] = table["root_id"].isin(modeled_ids)
        else:
            table["modeled"] = False

        if load_labels:
            labels = pd.read_csv(
                self.metadata_dir / "labels.csv.gz",
                usecols=["root_id", "label"],
                dtype={"root_id": "int64", "label": "string"},
            )
            labels = (
                labels.dropna(subset=["label"])
                .groupby("root_id", sort=False)["label"]
                .agg(lambda values: " | ".join(dict.fromkeys(values)))
                .rename("labels")
            )
            table = table.merge(labels, on="root_id", how="left")
        else:
            table["labels"] = pd.NA

        return table.sort_values("root_id", kind="stable").reset_index(drop=True)

    def search(
        self,
        *,
        text: str | None = None,
        filters: Mapping[str, str | Collection[str]] | None = None,
        root_ids: Collection[int] | None = None,
        modeled_only: bool = True,
    ) -> pd.DataFrame:
        result = self.table
        mask = pd.Series(True, index=result.index)
        if modeled_only:
            mask &= result["modeled"]
        if root_ids is not None:
            mask &= result["root_id"].isin([int(value) for value in root_ids])

        for field, expected in (filters or {}).items():
            if field == "cell_type":
                mask &= self._cell_type_mask(result, expected)
                continue
            if field not in result.columns:
                raise ValueError(f"Unknown metadata field: {field}")
            values = self._as_values(expected)
            normalized = {value.casefold() for value in values}
            mask &= result[field].astype("string").str.casefold().isin(normalized)

        if text:
            text_mask = pd.Series(False, index=result.index)
            for column in self.SEARCH_COLUMNS:
                text_mask |= (
                    result[column]
                    .astype("string")
                    .str.contains(text, case=False, regex=False, na=False)
                )
            mask &= text_mask

        return result.loc[mask].copy()

    @classmethod
    def _cell_type_mask(
        cls, table: pd.DataFrame, expected: str | Collection[str]
    ) -> pd.Series:
        values = {value.casefold() for value in cls._as_values(expected)}
        primary = table["primary_type"].astype("string").str.casefold().isin(values)
        additional = (
            table["additional_type(s)"]
            .astype("string")
            .map(
                lambda cell_types: bool(
                    values
                    & {
                        token.strip().casefold()
                        for token in str(cell_types).split(",")
                        if token.strip() and token != "<NA>"
                    }
                )
            )
        )
        return primary | additional

    @staticmethod
    def _as_values(value: str | Collection[str]) -> list[str]:
        if isinstance(value, str):
            return [value]
        return [str(item) for item in value]

    def inspect_cell_type(
        self, cell_type: str, *, modeled_only: bool = True
    ) -> pd.DataFrame:
        return self.search(filters={"cell_type": cell_type}, modeled_only=modeled_only)
