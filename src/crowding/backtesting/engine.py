"""Fixed-signal walk-forward evaluation with monthly close execution."""

from dataclasses import dataclass
import numpy as np
import pandas as pd
from crowding.normalization.holdings import snapshot
from crowding.analytics.crowding import crowding_score
from crowding.backtesting.metrics import performance, forward_returns, information_coefficient


@dataclass(frozen=True)
class Config:
    top_n: int = 5
    cost_bps: float = 15.0
    warmup_months: int = 6
    signal: str = "ownership_change"
    direction: int = 1
    max_age_days: int = 200


def validate_prices(prices):
    if (
        prices.empty
        or not isinstance(prices.index, pd.DatetimeIndex)
        or not prices.index.is_monotonic_increasing
    ):
        raise ValueError("Prices require ordered DatetimeIndex")
    if prices.index.duplicated().any() or prices.columns.duplicated().any():
        raise ValueError("Duplicate price dates or securities")
    values = prices.to_numpy(dtype=float)
    if np.isinf(values).any() or (values[~np.isnan(values)] <= 0).any():
        raise ValueError("Prices must be positive; missing observations must be NaN")


def walk_forward(filings, positions, prices, config=Config(), weights=None):
    validate_prices(prices)
    if (
        not isinstance(config.top_n, int)
        or config.top_n < 1
        or not np.isfinite(config.cost_bps)
        or config.cost_bps < 0
        or config.cost_bps >= 5000
        or not isinstance(config.warmup_months, int)
        or config.warmup_months < 1
        or config.max_age_days < 1
    ):
        raise ValueError("Invalid research configuration")
    if config.direction not in [-1, 1] or config.signal not in ["score", "ownership_change"]:
        raise ValueError("Unsupported signal or direction")
    # First observed session of each month. Cutoff is prior calendar day, so every
    # contributing filing predates execution, including releases after market close.
    schedule = prices.groupby(prices.index.to_period("M")).head(1).index
    if len(schedule) <= config.warmup_months:
        raise ValueError("Insufficient history for walk-forward warmup")
    schedule = set(schedule[config.warmup_months :])
    w = pd.Series(0.0, index=prices.columns)
    cash = 1.0
    records, allocations, signals, folds, contributions = [], [], [], [], []
    start = None
    for i, date in enumerate(prices.index):
        gross = 0.0
        if i and w.sum() > 0:
            held = w[w > 1e-12].index
            a, b = prices.iloc[i - 1][held], prices.iloc[i][held]
            if a.isna().any() or b.isna().any():
                raise ValueError(
                    f"Missing held-asset price at {date.date()}; supply delisting/total-return data"
                )
            ret = b / a - 1
            gross = float((w[held] * ret).sum())
            contributions.extend(
                {
                    "date": date,
                    "security_id": security,
                    "weight_before_return": float(w[security]),
                    "gross_contribution": float(w[security] * ret[security]),
                }
                for security in held
            )
            w.loc[held] = w[held] * (1 + ret) / (1 + gross)
            cash /= 1 + gross
        traded = 0.0
        if date in schedule:
            cutoff = date - pd.Timedelta(days=1)
            current = snapshot(filings, positions, cutoff, max_age_days=config.max_age_days)
            prior = snapshot(
                filings, positions, cutoff - pd.DateOffset(months=3), max_age_days=config.max_age_days
            )
            scores = crowding_score(current, prior, weights)
            target = pd.Series(0.0, index=w.index)
            if not scores.empty:
                eligible = scores[scores.security_id.isin(prices.columns)].copy()
                eligible = eligible[eligible.security_id.map(prices.loc[date].notna()).fillna(False)]
                eligible = eligible.sort_values(
                    [config.signal, "security_id"], ascending=[config.direction < 0, True]
                )
                chosen = eligible.head(config.top_n).security_id
                if len(chosen):
                    target.loc[chosen] = 1 / len(chosen)
                signals.extend(eligible.assign(date=date).to_dict("records"))
            # Gross notional traded: sum absolute asset-weight changes. Entry costs
            # one notional; full rotation costs two. Cash is not charged separately.
            traded = float((target - w).abs().sum())
            w = target
            cash = 1 - w.sum()
            if start is None:
                start = date
            allocations.extend(
                {"date": date, "security_id": s, "weight": val} for s, val in w.items() if val > 0
            )
            folds.append(
                {
                    "train_start": prices.index[0],
                    "train_end": cutoff,
                    "test_start": date,
                    "latest_filing": current.filing_date.max() if not current.empty else pd.NaT,
                    "eligible_securities": len(scores),
                    "held_securities": int((w > 0).sum()),
                }
            )
        if start is not None:
            cost = traded * config.cost_bps / 10000
            records.append(
                {
                    "date": date,
                    "gross_return": gross,
                    "net_return": (1 + gross) * (1 - cost) - 1,
                    "traded_notional": traded,
                    "cost_fraction": cost,
                    "hhi": float((w * w).sum()),
                    "cash_weight": cash,
                }
            )
    daily = pd.DataFrame(records).set_index("date")
    signal_frame = pd.DataFrame(signals)
    labels = forward_returns(prices, sorted(schedule))
    ic_rows = []
    if not signal_frame.empty:
        merged = signal_frame.merge(labels, on=["date", "security_id"])
        for (date, months), g in merged.groupby(["date", "months"]):
            ic_rows.append(
                {
                    "date": date,
                    "months": months,
                    "ic": information_coefficient(g[config.signal], g.forward_return),
                    "n": int(g.forward_return.notna().sum()),
                }
            )
    return {
        "daily": daily,
        "allocations": pd.DataFrame(allocations),
        "signals": signal_frame,
        "labels": labels,
        "ic": pd.DataFrame(ic_rows),
        "folds": pd.DataFrame(folds),
        "metrics": performance(daily.net_return),
        "contributions": pd.DataFrame(contributions),
    }


def regime_analysis(daily, benchmark):
    # Regime at t uses benchmark prices only through t-1.
    trend = benchmark.shift(1) / benchmark.shift(1).rolling(126, min_periods=126).mean() - 1
    regime = pd.Series(
        np.where(trend >= 0, "Above trailing 126-day mean", "Below trailing 126-day mean"),
        index=benchmark.index,
    )
    regime[trend.isna()] = "Insufficient history"
    joined = daily.join(regime.rename("regime"))
    return pd.DataFrame(
        [
            dict(regime=name, sessions=len(group), **performance(group.net_return))
            for name, group in joined.groupby("regime")
        ]
    ).set_index("regime")
