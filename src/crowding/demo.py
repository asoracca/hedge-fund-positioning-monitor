"""Seeded synthetic fixture. No real managers, holdings, prices or performance."""

import numpy as np
import pandas as pd
from crowding.storage import save_dataset


MANAGERS = [
    "Alder Ridge",
    "Northstar Systematic",
    "Tidal Research",
    "Meridian Equity",
    "Cedar Grove",
    "Arcstone Partners",
    "Harbor Quant",
    "Lattice Capital",
    "Juniper Value",
    "Orion Strategies",
    "Slate River",
    "Cobalt Investments",
]
SECTORS = ["Technology", "Health Care", "Financials", "Industrials", "Consumer", "Energy"]


def generate(path="data/demo", seed=441):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-01", "2025-12-31")
    securities = [f"DEMO{i:05d}" for i in range(30)]
    market = rng.normal(0.00022, 0.010, len(dates))
    sectors = rng.normal(0, 0.006, (len(dates), 6))
    values = np.column_stack(
        [
            60 * np.exp(np.cumsum(0.85 * market + sectors[:, i % 6] + rng.normal(0, 0.012, len(dates))))
            for i in range(30)
        ]
    )
    prices = pd.DataFrame(values, index=dates, columns=securities)
    prices.index.name = "date"
    filings, positions = [], []
    for q, report in enumerate(pd.date_range("2020-03-31", "2025-09-30", freq="QE")):
        for j, name in enumerate(MANAGERS):
            accession = f"DEMO-{q:03d}-{j:02d}"
            filed = report + pd.Timedelta(days=int(rng.integers(20, 51)))
            filings.append(
                dict(
                    accession=accession,
                    cik=str(9000000000 + j),
                    manager=name + " [DEMO]",
                    report_date=report,
                    filing_date=filed,
                    amendment="original",
                )
            )
            preference = np.ones(30)
            preference[(np.arange(30) % 3) == (j % 3)] = 4
            selection = rng.choice(30, size=12, replace=False, p=preference / preference.sum())
            for s in selection:
                shares = int(rng.integers(50000, 1500000))
                positions.append(
                    dict(
                        accession=accession,
                        security_id=securities[s],
                        shares=shares,
                        value_usd=shares * prices.loc[:report, securities[s]].iloc[-1],
                    )
                )
    # A late restatement and an additive amendment exercise historical reconstruction.
    base = filings[48].copy()
    restated = dict(
        base,
        accession="DEMO-RESTATED",
        filing_date=base["filing_date"] + pd.Timedelta(days=40),
        amendment="restatement",
    )
    filings.append(restated)
    for row in list(positions):
        if row["accession"] == base["accession"]:
            positions.append(
                dict(
                    row,
                    accession="DEMO-RESTATED",
                    shares=row["shares"] * 0.9,
                    value_usd=row["value_usd"] * 0.9,
                )
            )
    base = filings[60].copy()
    filings.append(
        dict(
            base,
            accession="DEMO-ADDITION",
            filing_date=base["filing_date"] + pd.Timedelta(days=25),
            amendment="addition",
        )
    )
    positions.append(
        dict(accession="DEMO-ADDITION", security_id=securities[0], shares=10000, value_usd=600000)
    )
    mappings = pd.DataFrame(
        [
            dict(
                security_id=s,
                ticker=f"SYN{i:02d}",
                sector=SECTORS[i % 6],
                valid_from=pd.Timestamp("2020-01-01"),
                valid_to=pd.NaT,
                known_at=pd.Timestamp("2020-01-01"),
            )
            for i, s in enumerate(securities)
        ]
    )
    save_dataset(
        path,
        pd.DataFrame(filings),
        pd.DataFrame(positions),
        prices,
        mappings,
        {
            "kind": "synthetic",
            "seed": seed,
            "license": "CC0-1.0",
            "description": "Generated demonstration only; no empirical investment evidence.",
            "price_adjustment": "Synthetic total-return index",
            "benchmark": "Equal-weight synthetic universe",
            "generator_version": 1,
        },
    )
