# Running and deployment

## Local (Python 3.11 or 3.12 recommended)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
streamlit run app.py
```

The committed Parquet demo works without network access after dependency
installation. To regenerate: `python -m crowding.cli demo`. For research artifacts:
`python -m crowding.cli research --output outputs/research`.

## Streamlit Community Cloud

Push this repository to your GitHub account, then create a Community Cloud app
using `app.py` as the entry point. Choose Python 3.12. The root requirements file
installs the package. The demo needs no secrets or API keys. Community Cloud is a
suitable free-tier option subject to its current service limits. No deployment
or public repository is created by these instructions.

For real datasets, run ingestion outside the web app and mount curated Parquet
files; set `CROWDING_DATA_DIR` to the directory. Never let unauthenticated visitors
trigger SEC crawling or upload unrestricted SQL/data. Use your own authentication
and hosting controls before exposing non-public or licensed datasets.

## Docker / low-cost host

```bash
docker build -t crowding-monitor .
docker run --rm -p 8501:8501 crowding-monitor
```

The Docker image exposes Streamlit, with a health check. Persist data externally
if using ephemeral hosting. Streamlit is a research interface, not a multi-tenant
trading execution service. Container execution and hosted deployment are not
covered by the local UI smoke tests.

## Real-data pipeline

1. Export SEC_USER_AGENT from `.env.example` after replacing the placeholder.
2. Select actual archive links from the SEC dataset page; do not infer coverage
   from the archive name alone.
3. Download each archive, normalize, review units and amendment coverage:

```bash
crowding sec-archive --url "$SEC_ARCHIVE_URL" --output data/real/q1
crowding sec-archive --url "$SEC_NEXT_ARCHIVE_URL" --output data/real/q2
crowding assemble --holdings data/real/q1 data/real/q2 \
  --prices /path/to/authorized_prices.csv \
  --price-provenance /path/to/price_provenance.json \
  --mappings /path/to/historical_mappings.csv --output data/real/research
CROWDING_DATA_DIR=data/real/research streamlit run app.py
crowding company-facts --cik 320193 --output data/real/research/facts/CIK0000320193.json
```

4. Check raw SEC totals against normalized totals; excluded options/non-share
   lines explain differences. Resolve missing amendment bases.
5. Audit mapping coverage, stale filings, universe membership, delistings and
   session coverage before interpreting backtests.
6. Freeze configuration and retain a future holdout; dashboard experimentation
   does not certify out-of-sample predictive performance.

The company page requires an optional `issuer_cik` column in historical mappings.
The example facts command fetches Apple; only securities mapped to that issuer
will display that payload. The page validates issuer CIK before displaying facts.

Hosting reference: https://docs.streamlit.io/deploy/streamlit-community-cloud

## Vercel interactive viewer

Import this GitHub repository and set Root Directory to `web`, framework to
Other, build command to `node verify.mjs`, and output directory to `.`. The
committed JSON contains Python-computed synthetic snapshots and backtests; the
build checks disclosure boundaries and agreement between browser and Python
metrics. No Python server, API key, live data service or paid storage is needed.

The deployed viewer is not the Streamlit server. It exposes six precomputed
highest-signal presets (ownership change/crowding; 1/5/10 holdings), default
backtest weights, and the full study window. Explorer weights do not alter
backtests. Costs are recalculated using the same proportional-cost formula.
To publish changed research results, run `python scripts/export_web.py`, validate
with `node web/verify.mjs`, commit the generated assets and push.
