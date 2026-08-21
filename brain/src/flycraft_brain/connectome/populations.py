from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Iterable

import pandas as pd

from .metadata import CodexMetadata


@dataclass(frozen=True, slots=True)
class PopulationDefinition:
    name: str
    role: str
    filters: dict[str, str]
    evidence: str
    source: str


class PopulationCatalog:
    """Versioned biological candidate definitions resolved against Codex."""

    def __init__(
        self,
        definitions: Iterable[PopulationDefinition],
        *,
        dataset: str,
        license_notice: str,
        boundary: str,
    ) -> None:
        definitions_by_name = {
            definition.name: definition for definition in definitions
        }
        if len(definitions_by_name) == 0:
            raise ValueError("Population catalog cannot be empty")
        self.definitions = definitions_by_name
        self.dataset = dataset
        self.license_notice = license_notice
        self.boundary = boundary

    @classmethod
    def load(cls, path: str | Path | None = None) -> PopulationCatalog:
        if path is None:
            resource = files("flycraft_brain.connectome").joinpath("populations.json")
            payload = json.loads(resource.read_text(encoding="utf-8"))
        else:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        definitions = [
            PopulationDefinition(
                name=item["name"],
                role=item["role"],
                filters=dict(item["filters"]),
                evidence=item["evidence"],
                source=item["source"],
            )
            for item in payload["populations"]
        ]
        return cls(
            definitions,
            dataset=payload["dataset"],
            license_notice=payload["license"],
            boundary=payload["boundary"],
        )

    def resolve(
        self,
        metadata: CodexMetadata,
        name: str,
        *,
        modeled_only: bool = True,
    ) -> pd.DataFrame:
        try:
            definition = self.definitions[name]
        except KeyError as error:
            available = ", ".join(sorted(self.definitions))
            raise KeyError(
                f"Unknown population '{name}'. Available: {available}"
            ) from error
        return metadata.search(
            filters=definition.filters,
            modeled_only=modeled_only,
        )

    def manifest(
        self,
        metadata: CodexMetadata,
        names: Iterable[str] | None = None,
        *,
        modeled_only: bool = True,
    ) -> dict[str, object]:
        selected_names = list(names) if names is not None else list(self.definitions)
        populations = []
        for name in selected_names:
            definition = self.definitions[name]
            neurons = self.resolve(metadata, name, modeled_only=modeled_only)
            populations.append(
                {
                    "name": definition.name,
                    "role": definition.role,
                    "filters": definition.filters,
                    "evidence": definition.evidence,
                    "source": definition.source,
                    "modeled_only": modeled_only,
                    "count": int(len(neurons)),
                    "root_ids": [int(value) for value in neurons["root_id"]],
                }
            )
        return {
            "dataset": self.dataset,
            "codex_version": metadata.VERSION,
            "license": self.license_notice,
            "boundary": self.boundary,
            "populations": populations,
        }
