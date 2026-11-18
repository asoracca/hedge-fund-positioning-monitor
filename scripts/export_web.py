"""Publish reproducible synthetic research outputs for the static Vercel viewer."""

from pathlib import Path
import json
import shutil
import pandas as pd
import plotly
from crowding.storage import load_dataset
from crowding.normalization.holdings import snapshot, position_changes
from crowding.analytics.crowding import crowding_score, manager_network
from crowding.backtesting.engine import Config, walk_forward, regime_analysis
from crowding.backtesting.attribution import sector_attribution

ROOT = Path(__file__).resolve().parents[1]


def records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso", double_precision=10))


def export():
    d = load_dataset(ROOT / "data/demo")
    assert d["manifest"]["kind"] == "synthetic", "Do not publish licensed datasets with this exporter"
    f, p, prices, mappings = (d[k] for k in ["filings", "positions", "prices", "mappings"])
    dates = sorted(set(f.groupby("report_date").filing_date.max().tolist() + [prices.index.max()]))
    result = {
        "manifest": d["manifest"],
        "securities": records(mappings),
        "snapshots": {},
        "research": {},
        "price_dates": prices.index.strftime("%Y-%m-%d").tolist(),
        "prices": {c: prices[c].round(6).tolist() for c in prices},
        "managers": records(f[["cik", "manager"]].drop_duplicates()),
    }
    for date in dates:
        current = snapshot(f, p, date)
        previous = snapshot(f, p, date - pd.DateOffset(months=3))
        sim, clusters = manager_network(current)
        # Changes compare exact adjacent reporting quarters at the same information cutoff.
        changes = []
        for cik, g in current.groupby("cik"):
            old = snapshot(f, p, date, g.report_date.max() - pd.offsets.QuarterEnd(), max_age_days=36500)
            changes.extend(records(position_changes(g, old[old.cik == cik])))
        result["snapshots"][date.strftime("%Y-%m-%d")] = {
            "holdings": records(current),
            "scores": records(crowding_score(current, previous)),
            "manager_ids": sim.index.tolist(),
            "similarity": sim.values.round(8).tolist(),
            "clusters": clusters.tolist(),
            "changes": changes,
        }
    bench = (1 + prices.pct_change(fill_method=None).mean(axis=1).fillna(0)).cumprod()
    for signal in ["ownership_change", "score"]:
        for n in [1, 5, 10]:
            r = walk_forward(f, p, prices, Config(signal=signal, top_n=n))
            result["research"][f"{signal}-{n}"] = {
                "metrics": r["metrics"],
                "daily": records(r["daily"].reset_index()),
                "ic": records(r["ic"]),
                "folds": records(r["folds"]),
                "sectors": records(sector_attribution(r["contributions"], mappings)),
                "regimes": records(regime_analysis(r["daily"], bench).reset_index()),
            }
            print(f"Exported {signal}, {n} holdings", flush=True)
    output = ROOT / "web/assets/research.json"
    output.write_text(json.dumps(result, separators=(",", ":"), allow_nan=False))
    shutil.copyfile(
        Path(plotly.__file__).parent / "package_data/plotly.min.js", ROOT / "web/assets/plotly.min.js"
    )
    print(f"Exported {len(dates)} snapshots to {output}", flush=True)


if __name__ == "__main__":
    export()
