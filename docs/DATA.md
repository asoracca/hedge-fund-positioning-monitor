# Data contract and sources

## Tables

| Table | Key / fields | Meaning |
|---|---|---|
| filings | accession; cik, manager, report_date, filing_date, amendment | Immutable disclosure metadata; amendment ∈ original/restatement/addition |
| positions | accession + security_id; shares, value_usd | Aggregated long share entries, values normalized to dollars |
| prices | session-date index, permanent security-ID columns | Positive total-return-adjusted index; missing prices remain NaN |
| mappings | security_id, ticker, sector, valid_from, valid_to, known_at | Historical identifier/classification mapping; open-ended valid_to allowed |
| manifest | kind, sources, license and price provenance | Distinguishes synthetic from public observations |

Identifiers are strings: preserve CUSIP leading zeros. Never guess a CUSIP from
a ticker or apply today's mapping to all history. Unknown mappings remain visible
as identifiers. Real trading joins use security_id, not presentation tickers.
Mergers, share classes and identifiers that change require a curated permanent
security history and licensed corporate-action-adjusted prices. Mapping history
alone is not a corporate-action engine.

## SEC ingestion

- [Official quarterly Form 13F datasets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets)
- [Bulk table schema](https://www.sec.gov/files/form_13f.pdf)
- [Developer / fair-access guidance](https://www.sec.gov/about/developer-resources)
- [13F FAQ](https://www.sec.gov/rules-regulations/staff-guidance/frequently-asked-questions-about-form-13f)
- [Company facts and submissions APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)

Set an identifying `SEC_USER_AGENT` with your actual contact address. The client
serializes requests at fewer than five per second within one process, below the
SEC's ten-request/second ceiling. Coordinate multiple processes/IP users yourself.
It retries transport errors and 429/5xx responses with bounded backoff, respects
numeric Retry-After values up to 60 seconds, and fails on access blocks instead
of bypassing them. Raw bytes are cached by URL with SHA-256 manifests; corrupted
cache entries fail validation. Refresh is explicit.

The bulk archive's calendar quarter is the **filing** window, not necessarily the
holdings quarter. Fetch enough adjacent archives to include late filings and all
amendment bases. `sec-archive` downloads a selected official URL and parses TSVs.
Use accession metadata to inspect original filings when anomalies arise.

Official filings before January 3, 2023 use thousands of dollars; later filings
use dollars under the updated form. `--value-unit auto` applies this policy by
filing date. `usd` and `thousands` overrides are recorded for verified exceptions.
Real filer unit mistakes still need external quality review; the code cannot
reliably infer them. Options and principal-amount instruments are excluded, but
share entries can include ETFs, ADRs and preferred securities, not only common
stocks. Filter the research universe deliberately.

Company-facts observations retain their accession/filing vintages and are filtered
by filed date. They are not silently reduced to the latest restated financial
history. Issuer/manager CIKs differ; verify the issuer before using fundamentals.

## Prices and rights

The offline repository contains **only generated prices and holdings**, under
CC0-1.0. No real vendor price dataset is bundled. SEC public filings are reusable;
that does not automatically license prices from another provider or every
security identifier master. No PitchBook scraping or redistribution occurs.

For real research, supply CSV columns `date,security_id,adjusted_close` plus JSON:

```json
{
  "provider": "Name of the public or otherwise authorized source",
  "source_url": "https://provider.example/dataset",
  "license": "Exact license or terms URL and permitted use",
  "retrieved_at": "2026-11-18T00:00:00Z",
  "adjustment": "total_return",
  "redistribution_allowed": false
}
```

The importer enforces the metadata contract, not a legal judgment about the
license's validity. The example URL is a placeholder, not a claimed price source.
No automatic Yahoo/Stooq download is provided because accessibility alone does
not establish redistribution rights or complete delisting coverage. A verified
provider adapter is still required for unattended real-price refresh.

Do not commit real price files without confirmed redistribution rights. Real data
and caches are gitignored. The demo uses business weekdays rather than a real
exchange calendar and has no delistings, splits, dividends, or real economic
relationships. None of its statistics are empirical evidence.
