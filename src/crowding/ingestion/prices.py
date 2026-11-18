"""Provider-neutral price import; no redistribution rights assumed."""

import json
from pathlib import Path
import pandas as pd
from crowding.backtesting.engine import validate_prices


def import_prices(csv_path, provenance_path):
    meta = json.loads(Path(provenance_path).read_text())
    required = {"provider", "source_url", "license", "retrieved_at", "adjustment", "redistribution_allowed"}
    if not required.issubset(meta) or not all(meta[k] for k in required - {"redistribution_allowed"}):
        raise ValueError("Price provenance and license declaration required")
    if meta["adjustment"] != "total_return":
        raise ValueError("Research requires total-return adjusted prices, including corporate actions")
    p = pd.read_csv(csv_path, dtype={"security_id": str}, parse_dates=["date"])
    if p.duplicated(["date", "security_id"]).any():
        raise ValueError("Duplicate security/session price")
    result = p.pivot(index="date", columns="security_id", values="adjusted_close").sort_index()
    validate_prices(result)
    return result, meta
