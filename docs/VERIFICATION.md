# Local verification — 2026-11-18

- Python 3.12 isolated environment; dependency versions recorded in requirements-lock.txt.
- `ruff check .`: passed.
- `pytest -q`: 27 tests passed, including all seven Streamlit pages.
- CLI demo generation: passed; deterministic Parquet data saved.
- CLI research: passed; actual computed metrics summarized in README.
- Research notebook: executed successfully, including disclosure-boundary assertions
  and 0/15/50-bps cost sensitivity; executed outputs included in the notebook.
- Browser: overview and signal-research views rendered; screenshots saved in docs/screenshots.
- GitHub Actions and Docker configuration supplied; hosted CI, container build and
  remote deployment have not been run.
- SEC parsing tested with schema-conforming fixtures, not claimed as a validated
  live-universe ingestion. No empirical financial performance is claimed.
