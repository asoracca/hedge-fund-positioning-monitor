"""Validated, immutable filings and point-in-time reconstruction."""

import numpy as np
import pandas as pd

FILING_COLUMNS = ["accession", "cik", "manager", "report_date", "filing_date", "amendment"]
POSITION_COLUMNS = ["accession", "security_id", "shares", "value_usd"]


def validate(filings, positions):
    f, p = filings.copy(), positions.copy()
    for frame, columns in [(f, FILING_COLUMNS), (p, POSITION_COLUMNS)]:
        missing = set(columns) - set(frame.columns)
        if missing:
            raise ValueError(f"Missing columns: {sorted(missing)}")
        if frame[columns].isna().any().any():
            raise ValueError("Null required fields")
    for col in ["report_date", "filing_date"]:
        f[col] = pd.to_datetime(f[col]).dt.normalize()
    f["cik"] = f.cik.astype(str).str.zfill(10)
    if f.accession.duplicated().any():
        raise ValueError("Duplicate accession")
    if (f.filing_date < f.report_date).any():
        raise ValueError("Filing precedes reporting period")
    if not f.amendment.isin(["original", "restatement", "addition"]).all():
        raise ValueError("Unknown amendment type; inspect source filing")
    if not p.accession.isin(f.accession).all():
        raise ValueError("Orphan positions")
    for col in ["shares", "value_usd"]:
        p[col] = pd.to_numeric(p[col], errors="raise")
        if not np.isfinite(p[col]).all() or (p[col] < 0).any():
            raise ValueError("Positions must be finite and nonnegative")
    # Multiple share-class/discretion rows for one CUSIP are summed, never dropped.
    p = p.groupby(["accession", "security_id"], as_index=False)[["shares", "value_usd"]].sum()
    return f, p


def snapshot(filings, positions, as_of, report_date=None, max_age_days=200):
    """Known by date, inclusive. Trading engine separately imposes next-session execution.

    Additive amendments sum new entries; restatements replace the whole table.
    Missing original reports cannot be reconstructed from additions alone.
    """
    cutoff = pd.Timestamp(as_of).normalize()
    f = filings.loc[filings.filing_date <= cutoff].copy()
    if report_date is not None:
        f = f[f.report_date == pd.Timestamp(report_date)]
    f = f[(cutoff - f.report_date).dt.days <= max_age_days]
    out = []
    for (cik, period), group in f.groupby(["cik", "report_date"]):
        state = None
        last = None
        for row in group.sort_values(["filing_date", "accession"]).itertuples():
            part = positions[positions.accession == row.accession].set_index("security_id")[
                ["shares", "value_usd"]
            ]
            if row.amendment in ("original", "restatement"):
                state = part.copy()
            elif state is not None:
                state = state.add(part, fill_value=0)
            else:
                raise ValueError(f"Addition without base filing: {row.accession}")
            last = row
        if state is not None:
            state = state.reset_index().assign(
                cik=cik,
                manager=last.manager,
                report_date=period,
                filing_date=last.filing_date,
                accession=last.accession,
            )
            out.append(state)
    columns = [
        "security_id",
        "shares",
        "value_usd",
        "cik",
        "manager",
        "report_date",
        "filing_date",
        "accession",
        "weight",
    ]
    if not out:
        return pd.DataFrame(columns=columns)
    result = pd.concat(out, ignore_index=True)
    if report_date is None:
        latest = f.groupby("cik").report_date.max()
        result = result[result.report_date == result.cik.map(latest)]
    total = result.groupby("cik").value_usd.transform("sum")
    result["weight"] = result.value_usd.div(total.replace(0, np.nan)).fillna(0)
    return result[columns]


def map_securities(holdings, mappings, as_of):
    """Use only mappings known at cutoff and valid for the reporting period."""
    required = ["security_id", "ticker", "sector", "valid_from", "valid_to", "known_at"]
    if not set(required).issubset(mappings):
        raise ValueError("Incomplete mapping history")
    m = mappings.copy()
    for c in ["valid_from", "valid_to", "known_at"]:
        m[c] = pd.to_datetime(m[c])
    m = m[m.known_at <= pd.Timestamp(as_of)]
    rows = []
    for row in holdings.to_dict("records"):
        match = m[
            (m.security_id == row["security_id"])
            & (m.valid_from <= row["report_date"])
            & (m.valid_to.isna() | (m.valid_to >= row["report_date"]))
        ]
        if len(match):
            latest = match[match.known_at == match.known_at.max()]
            if len(latest) != 1:
                raise ValueError("Ambiguous historical mapping")
            row.update(latest.iloc[0][["ticker", "sector"]].to_dict())
            if "issuer_cik" in latest:
                row["issuer_cik"] = latest.iloc[0]["issuer_cik"]
            row["mapping_status"] = "mapped"
        else:
            row.update(ticker=row["security_id"], sector="Unmapped", mapping_status="unmapped")
        rows.append(row)
    return pd.DataFrame(rows)


def position_changes(current, previous):
    """Compare only managers with both reports; raw shares are NOT split adjusted."""
    common = set(current.cik) & set(previous.cik)
    cols = ["cik", "security_id", "shares", "value_usd", "weight"]
    a, b = current[current.cik.isin(common)][cols], previous[previous.cik.isin(common)][cols]
    change = a.merge(b, on=["cik", "security_id"], how="outer", suffixes=("_new", "_old")).fillna(0)
    change["shares_delta"] = change.shares_new - change.shares_old
    change["weight_delta"] = change.weight_new - change.weight_old
    change["change"] = np.select(
        [
            change.shares_old.eq(0) & change.shares_new.gt(0),
            change.shares_new.eq(0) & change.shares_old.gt(0),
            change.shares_delta.gt(0),
            change.shares_delta.lt(0),
        ],
        ["New disclosure", "Exit", "Increase", "Decrease"],
        default="Unchanged",
    )
    return change
