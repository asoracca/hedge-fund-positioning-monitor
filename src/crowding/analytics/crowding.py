"""Transparent cross-sectional heuristic, not an established industry measure."""

import numpy as np
import pandas as pd
from sklearn.cluster import AgglomerativeClustering

DEFAULT_WEIGHTS = {
    "breadth": 0.30,
    "value": 0.20,
    "holder_hhi": 0.15,
    "ownership_change": 0.20,
    "overlap": 0.15,
}


def manager_network(holdings, n_clusters=3):
    matrix = holdings.pivot_table(
        index="cik", columns="security_id", values="weight", aggfunc="sum", fill_value=0
    )
    if matrix.empty:
        return pd.DataFrame(), pd.Series(dtype=int)
    values = matrix.to_numpy(dtype=float)
    norms = np.sqrt(np.einsum("ij,ij->i", values, values))
    unit = np.divide(values, norms[:, None], out=np.zeros_like(values), where=norms[:, None] > 0)
    # einsum avoids platform BLAS floating-point warning artifacts on small matrices.
    sim = pd.DataFrame(
        np.clip(np.einsum("ik,jk->ij", unit, unit), 0, 1), index=matrix.index, columns=matrix.index
    )
    k = min(n_clusters, len(matrix))
    labels = (
        (
            AgglomerativeClustering(n_clusters=k, metric="precomputed", linkage="average").fit_predict(
                np.clip(1 - sim.values, 0, 2)
            )
        )
        if len(matrix) > 1
        else [0]
    )
    return sim, pd.Series(labels, index=matrix.index, name="cluster")


def weighted_overlap(holdings, manager_a, manager_b):
    m = holdings.pivot_table(index="security_id", columns="cik", values="weight", aggfunc="sum", fill_value=0)
    return float(np.minimum(m[manager_a], m[manager_b]).sum())


def percentile(series):
    if len(series) < 2 or series.nunique() == 1:
        return pd.Series(0.5, index=series.index)
    return (series.rank(method="average") - 1) / (len(series) - 1)


def crowding_score(current, previous=None, weights=None):
    weights = DEFAULT_WEIGHTS if weights is None else weights
    if (
        set(weights) != set(DEFAULT_WEIGHTS)
        or any(not np.isfinite(w) or w < 0 for w in weights.values())
        or sum(weights.values()) <= 0
    ):
        raise ValueError("Provide five finite, nonnegative weights with positive sum")
    h = current[current.value_usd > 0].copy()
    if h.empty:
        return pd.DataFrame()
    h["holder_fraction"] = h.value_usd / h.groupby("security_id").value_usd.transform("sum")
    result = h.groupby("security_id").agg(
        breadth=("cik", "nunique"),
        value=("value_usd", "sum"),
        holder_hhi=("holder_fraction", lambda s: (s * s).sum()),
    )
    # Ownership change uses a matched manager cohort, preventing arrivals from posing as buys.
    result["ownership_change"] = 0.0
    if previous is not None and not previous.empty:
        common = set(current.cik) & set(previous.cik)
        if common:
            new = (
                current[current.cik.isin(common) & current.value_usd.gt(0)]
                .groupby("security_id")
                .cik.nunique()
            )
            old = (
                previous[previous.cik.isin(common) & previous.value_usd.gt(0)]
                .groupby("security_id")
                .cik.nunique()
            )
            result["ownership_change"] = new.subtract(old, fill_value=0).reindex(result.index).fillna(
                0
            ) / len(common)
    sim, _ = manager_network(h)
    result["overlap"] = 0.0
    for security, group in h.groupby("security_id"):
        holders = group.cik.unique()
        if len(holders) > 1:
            sub = sim.loc[holders, holders].values
            result.loc[security, "overlap"] = sub[np.triu_indices(len(sub), 1)].mean()
    result["score"] = 0.0
    for name, weight in weights.items():
        result[name + "_rank"] = percentile(result[name])
        result["score"] += 100 * weight / sum(weights.values()) * result[name + "_rank"]
    return result.reset_index().sort_values(["score", "security_id"], ascending=[False, True])
