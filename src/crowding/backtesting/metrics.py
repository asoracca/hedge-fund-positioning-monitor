import numpy as np
import pandas as pd
from scipy.stats import spearmanr


def performance(returns, periods=252, annual_risk_free=0.0):
    r = pd.Series(returns, dtype=float)
    if r.empty or r.isna().any() or not np.isfinite(r).all() or (r < -1).any():
        raise ValueError("Returns must be nonempty, finite and >= -100%")
    wealth = np.r_[1.0, (1 + r).cumprod().values]
    vol = r.std(ddof=1) * np.sqrt(periods)
    excess = r - ((1 + annual_risk_free) ** (1 / periods) - 1)
    return {
        "total_return": wealth[-1] - 1,
        "annualized_return": wealth[-1] ** (periods / len(r)) - 1,
        "volatility": vol,
        "sharpe": excess.mean() * periods / vol if vol > 1e-12 else np.nan,
        "max_drawdown": float((wealth / np.maximum.accumulate(wealth) - 1).min()),
    }


def information_coefficient(signal, returns):
    pair = pd.concat([signal.rename("signal"), returns.rename("return")], axis=1).dropna()
    if len(pair) < 3 or pair.signal.nunique() < 2 or pair["return"].nunique() < 2:
        return np.nan
    return float(spearmanr(pair.signal, pair["return"]).statistic)


def forward_returns(prices, dates, months=(1, 3, 6)):
    """Calendar-month labels from an execution close; no endpoint extrapolation.

    Prices indexed by session; columns permanent security IDs. NaN remains missing.
    """
    rows = []
    for date in dates:
        date = pd.Timestamp(date)
        if date not in prices.index:
            continue
        for horizon in months:
            target = date + pd.DateOffset(months=horizon)
            candidates = prices.index[prices.index >= target]
            if not len(candidates) or (candidates[0] - target).days > 7:
                continue
            end = candidates[0]
            ret = prices.loc[end].div(prices.loc[date]) - 1
            rows.extend(
                {"date": date, "security_id": s, "months": horizon, "end_date": end, "forward_return": v}
                for s, v in ret.items()
            )
    return pd.DataFrame(rows, columns=["date", "security_id", "months", "end_date", "forward_return"])
