"""Point-in-time sector attribution; contributions are arithmetic, not CAGR."""

import pandas as pd


def sector_attribution(contributions, mappings):
    if contributions.empty:
        return pd.DataFrame(columns=["sector", "gross_contribution_sum", "asset_days"])
    m = mappings.copy()
    for col in ["valid_from", "valid_to", "known_at"]:
        m[col] = pd.to_datetime(m[col])
    mapped = (
        contributions.reset_index(drop=True).reset_index(names="_row").merge(m, on="security_id", how="left")
    )
    cutoff = mapped.date - pd.Timedelta(days=1)
    known = mapped[
        (mapped.known_at <= cutoff)
        & (mapped.valid_from <= cutoff)
        & (mapped.valid_to.isna() | (mapped.valid_to >= cutoff))
    ]
    known = known.sort_values("known_at").drop_duplicates("_row", keep="last")
    original = contributions.reset_index(drop=True).copy()
    original["sector"] = original.index.to_series().map(known.set_index("_row").sector).fillna("Unmapped")
    return original.groupby("sector", as_index=False).agg(
        gross_contribution_sum=("gross_contribution", "sum"), asset_days=("gross_contribution", "size")
    )
