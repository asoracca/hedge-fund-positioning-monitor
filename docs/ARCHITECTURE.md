# Architecture and implementation plan

1. **Immutable ingestion** — SEC quarterly TSV archives, submissions and company-facts JSON. Cache raw bytes by URL, SHA-256 provenance, bounded retries, explicit contact User-Agent and a serialized five-request/second ceiling. No proprietary data.
2. **Normalization** — separate filings from positions; dollar units explicit; exclude options and non-share positions. Version security mappings by validity and knowledge dates. Retain unmapped CUSIPs. Reconstruct amendments only when public.
3. **Storage** — typed Parquet tables with DuckDB views. Filings remain immutable. No overwrite of historical snapshots with later amendments.
4. **Analytics** — reported-share changes, holdings weights, overlap, cosine similarity, deterministic clusters and a configurable cross-sectional crowding heuristic.
5. **Research** — monthly expanding walk-forward evaluation of fixed crowding signals. Next-session-close execution after filing dates; calendar-month forward labels; no imputation of missing return endpoints; drift-aware turnover and costs.
6. **Interface** — Streamlit terminal: overview, crowding, holdings, network, research and company pages. Offline generated observations are explicitly synthetic everywhere.
7. **Verification** — unit tests for financial identities, disclosure timing, restatements/additions, mapping history, missing prices, costs and UI smoke tests. Reproducible notebook and CI.

## Repository

```
src/crowding/
  ingestion/       SEC client, archive adapter, licensed price import
  normalization/   schema validation, historical mapping, amendments
  analytics/       crowding, holdings changes, manager networks
  backtesting/     metrics, labels and walk-forward portfolio simulation
  ui/              dashboard and chart styling
  demo.py          deterministic offline dataset
  storage.py       Parquet/DuckDB access
  cli.py           reproducible pipelines
app.py             Streamlit entry point
tests/             correctness and integration tests
notebooks/         reproducible signal study
docs/              methods, data contract, deployment, screenshots
```

## Boundaries

13F managers are not necessarily hedge funds. Reported positions are a partial,
lagged view of long holdings, not AUM or current ownership. No signal is trained
on future labels. Research refuses missing held-asset prices instead of silently
assuming zero returns. Real-price imports require provenance and rights metadata;
no bundled vendor prices or guessed CUSIP-to-ticker mappings.
