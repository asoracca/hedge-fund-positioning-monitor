import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
from crowding.demo import generate
from crowding.storage import load_dataset, save_dataset
from crowding.ingestion.sec import SECClient
from crowding.ingestion.archives import parse_archive
from crowding.ingestion.prices import import_prices
from crowding.backtesting.engine import walk_forward


def main():
    parser = argparse.ArgumentParser(description="Institutional holdings research pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo")
    demo.add_argument("--output", default="data/demo")
    research = sub.add_parser("research")
    research.add_argument("--data", default="data/demo")
    research.add_argument("--output", default="outputs/research")
    sec = sub.add_parser("sec-archive")
    sec.add_argument("--url", required=True)
    sec.add_argument("--output", required=True)
    sec.add_argument("--value-unit", choices=["auto", "usd", "thousands"], default="auto")
    facts = sub.add_parser("company-facts")
    facts.add_argument("--cik", required=True)
    facts.add_argument("--output", required=True)
    assemble = sub.add_parser("assemble")
    assemble.add_argument("--holdings", nargs="+", required=True)
    assemble.add_argument("--prices", required=True)
    assemble.add_argument("--price-provenance", required=True)
    assemble.add_argument("--mappings", required=True)
    assemble.add_argument("--output", required=True)
    args = parser.parse_args()
    if args.command == "demo":
        generate(args.output)
        print(f"Synthetic demo written to {args.output}")
    elif args.command == "research":
        d = load_dataset(args.data)
        result = walk_forward(d["filings"], d["positions"], d["prices"])
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        for key, value in result.items():
            if isinstance(value, pd.DataFrame):
                value.to_csv(out / (key + ".csv"), index=(key == "daily"))
        (out / "metrics.json").write_text(
            json.dumps(dict(result["metrics"], data_kind=d["manifest"]["kind"]), indent=2)
        )
        print((out / "metrics.json").read_text())
    elif args.command in ["sec-archive", "company-facts"]:
        client = SECClient()
        try:
            out = Path(args.output)
            if args.command == "company-facts":
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(json.dumps(client.company_facts(args.cik)))
            else:
                payload = client.get(args.url)
                f, p = parse_archive(payload, args.value_unit)
                out.mkdir(parents=True, exist_ok=True)
                f.to_parquet(out / "filings.parquet", index=False)
                p.to_parquet(out / "positions.parquet", index=False)
                (out / "source.json").write_text(
                    json.dumps(
                        {
                            "url": args.url,
                            "sha256": hashlib.sha256(payload).hexdigest(),
                            "value_unit_policy": args.value_unit,
                        },
                        indent=2,
                    )
                )
                print(
                    f"Loaded {len(f)} filings and {len(p)} positions. Review units and mappings before research."
                )
        finally:
            client.close()
    else:
        filings = pd.concat(
            [pd.read_parquet(Path(h) / "filings.parquet") for h in args.holdings]
        ).drop_duplicates()
        positions = pd.concat(
            [pd.read_parquet(Path(h) / "positions.parquet") for h in args.holdings]
        ).drop_duplicates()
        prices, provenance = import_prices(args.prices, args.price_provenance)
        mappings = pd.read_csv(args.mappings, dtype={"security_id": str})
        sources = [json.loads((Path(h) / "source.json").read_text()) for h in args.holdings]
        save_dataset(
            args.output,
            filings,
            positions,
            prices,
            mappings,
            {"kind": "public", "sources": sources, "price_provenance": provenance},
        )
        print(f"Public dataset assembled at {args.output}. Set CROWDING_DATA_DIR to this directory.")


if __name__ == "__main__":
    main()
