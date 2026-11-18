"""Parquet is canonical; DuckDB provides local analytical views."""

import json
from pathlib import Path
import duckdb
import pandas as pd
from crowding.normalization.holdings import validate


def save_dataset(path, filings, positions, prices, mappings, manifest):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    filings, positions = validate(filings, positions)
    for name, frame in [
        ("filings", filings),
        ("positions", positions),
        ("prices", prices),
        ("mappings", mappings),
    ]:
        temp = path / (name + ".tmp.parquet")
        frame.to_parquet(temp, index=(name == "prices"))
        temp.replace(path / (name + ".parquet"))
    (path / "manifest.json").write_text(json.dumps(manifest, indent=2))


def load_dataset(path):
    path = Path(path)
    frames = {
        n: pd.read_parquet(path / (n + ".parquet")) for n in ["filings", "positions", "prices", "mappings"]
    }
    frames["filings"], frames["positions"] = validate(frames["filings"], frames["positions"])
    frames["manifest"] = json.loads((path / "manifest.json").read_text())
    return frames


def connect(path):
    conn = duckdb.connect(":memory:")
    for name in ["filings", "positions", "prices", "mappings"]:
        file = str((Path(path) / (name + ".parquet")).resolve()).replace("'", "''")
        conn.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{file}')")
    return conn
