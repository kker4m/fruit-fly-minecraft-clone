from __future__ import annotations

import pandas as pd

from flycraft_brain.connectome import (
    CodexMetadata,
    ConnectivityStore,
    PopulationCatalog,
)


def write_metadata(data_dir):
    metadata_dir = data_dir / "codex-783"
    metadata_dir.mkdir()
    classification = pd.DataFrame(
        {
            "root_id": [101, 102, 103, 104],
            "flow": ["afferent", "efferent", "efferent", "intrinsic"],
            "super_class": ["sensory", "descending", "descending", "central"],
            "class": ["gustatory", pd.NA, pd.NA, pd.NA],
            "sub_class": ["sugar/water", pd.NA, pd.NA, pd.NA],
            "hemilineage": [pd.NA, "PSp2", "PSp2", "X"],
            "side": ["left", "left", "right", "right"],
            "nerve": ["AN", "CV", "CV", pd.NA],
        }
    )
    classification.to_csv(metadata_dir / "classification.csv.gz", index=False)
    cell_types = pd.DataFrame(
        {
            "root_id": [101, 102, 103, 104],
            "primary_type": ["GRN", "MDN", "DNp71", "CB1"],
            "additional_type(s)": [pd.NA, pd.NA, "DNp09", "aSP9"],
        }
    )
    cell_types.to_csv(metadata_dir / "consolidated_cell_types.csv.gz", index=False)
    neurons = pd.DataFrame(
        {
            "root_id": [101, 102, 103, 104],
            "group": ["SEZ", "DN", "DN", "CB"],
            "nt_type": ["ACH", "GABA", "ACH", "GLUT"],
            "nt_type_score": [0.9, 0.8, 0.7, 0.6],
            "da_avg": [0.0] * 4,
            "ser_avg": [0.0] * 4,
            "gaba_avg": [0.0, 0.8, 0.0, 0.0],
            "glut_avg": [0.0, 0.0, 0.0, 0.6],
            "ach_avg": [0.9, 0.0, 0.7, 0.0],
            "oct_avg": [0.0] * 4,
        }
    )
    neurons.to_csv(metadata_dir / "neurons.csv.gz", index=False)
    labels = pd.DataFrame(
        {
            "root_id": [102, 104],
            "label": ["backward locomotion", "unrelated label"],
        }
    )
    labels.to_csv(metadata_dir / "labels.csv.gz", index=False)
    pd.DataFrame(
        {"Completed": [True, True, True]}, index=pd.Index([101, 102, 103])
    ).to_csv(data_dir / "2025_Completeness_783.csv")


def write_connectivity(data_dir):
    pd.DataFrame(
        {
            "Presynaptic_ID": [101, 101, 102, 103],
            "Postsynaptic_ID": [102, 103, 101, 101],
            "Presynaptic_Index": [0, 0, 1, 2],
            "Postsynaptic_Index": [1, 2, 0, 0],
            "Connectivity": [10, 2, 7, 12],
            "Excitatory": [1, 1, -1, 1],
            "Excitatory x Connectivity": [10, 2, -7, 12],
        }
    ).to_parquet(data_dir / "2025_Connectivity_783.parquet")


def test_metadata_filters_modeled_ids_and_exact_additional_types(tmp_path):
    write_metadata(tmp_path)
    metadata = CodexMetadata(tmp_path)

    dnp09 = metadata.inspect_cell_type("DNp09")
    sensory = metadata.search(filters={"super_class": "sensory", "class": "gustatory"})

    assert dnp09["root_id"].tolist() == [103]
    assert sensory["root_id"].tolist() == [101]
    assert not metadata.table.loc[metadata.table.root_id.eq(104), "modeled"].item()


def test_metadata_optional_label_search(tmp_path):
    write_metadata(tmp_path)
    metadata = CodexMetadata(tmp_path, load_labels=True)

    result = metadata.search(text="backward")

    assert result["root_id"].tolist() == [102]


def test_default_population_catalog_resolves_metadata_filters(tmp_path):
    write_metadata(tmp_path)
    metadata = CodexMetadata(tmp_path)
    catalog = PopulationCatalog.load()

    result = catalog.resolve(metadata, "motor_backward_mdn")

    assert result["root_id"].tolist() == [102]


def test_connectivity_neighbors_and_between(tmp_path):
    write_connectivity(tmp_path)
    store = ConnectivityStore(tmp_path)

    neighbors = store.neighbors(101, direction="both", min_synapses=5)
    between = store.between([101], [102, 103], min_synapses=5)

    assert neighbors[["direction", "partner_id", "Connectivity"]].to_dict(
        orient="records"
    ) == [
        {"direction": "input", "partner_id": 103, "Connectivity": 12},
        {"direction": "output", "partner_id": 102, "Connectivity": 10},
        {"direction": "input", "partner_id": 102, "Connectivity": 7},
    ]
    assert between[["Postsynaptic_ID", "Connectivity"]].to_dict(orient="records") == [
        {"Postsynaptic_ID": 102, "Connectivity": 10}
    ]
