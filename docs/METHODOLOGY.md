# Methodology

## Research question

Do publicly observable changes in institutional long-equity positioning relate
to subsequent total returns, after disclosure delay and trading costs? This
repository supplies a falsifiable research workflow, not evidence that such an
edge exists. The bundled data is synthetic and cannot answer that question.

## Availability and reporting

A holding belongs to reporting quarter q and filing accession a. Its information
becomes eligible only when `filing_date(a) < execution_date`. The explorer includes
filings through its selected date; the backtester uses the prior calendar day at
each first observed session of a month and executes at that session's close.
This is conservative for date-only filings, including after-hours submissions.
A report filed June 2 about March 31 cannot affect the June 1 rebalance.
The 45-day normal reporting deadline is not a substitute for actual filing dates:
late filings and confidential disclosures enter when actually public.

The simulator sees the latest known report per manager, capped at 200 calendar
days old. This can mix reporting quarters and omit tardy managers. Inspect report
ages, matched-cohort sizes and filing coverage; never equate lack of a report
with selling. Research labels are outcomes, not model inputs.

Original filings and restatements replace the whole report for that manager and
quarter. New-holdings amendments add entries. Rows for the same security are
summed; additions without a known base fail. Ambiguous amendment types fail.
Reconstruction orders same-day filings by accession because bulk files lack
acceptance timestamps. Intraday sequencing is not supported. Across-day
amendments never rewrite an earlier information set.

## Crowding heuristic

Let V_ms be disclosed value held by manager m in security s. Manager portfolio
weight is w_ms = V_ms / sum_j V_mj. The five raw components are:

| Component | Definition | Default weight |
|---|---|---:|
| Breadth | Number of distinct positive-value holders | 30% |
| Value | Sum of reported USD position values | 20% |
| Holder concentration | Sum_m (V_ms / sum_k V_ks)^2 | 15% |
| Ownership change | (current holder count − prior holder count) / matched manager count | 20% |
| Holder overlap | Mean pairwise cosine similarity among holders' complete portfolio-weight vectors | 15% |

Previous information set is three calendar months before the current cutoff.
Ownership changes restrict both sets to managers observed in both. This is a
change between public information sets, not synchronized quarter-end ownership.
With no matched managers the change component is neutral (zero before ranking).

For each component, p_s = (average_rank_s − 1)/(N − 1). If N < 2 or the whole
component is constant, p_s = 0.5. The composite is

`C_s = 100 × sum_k(alpha_k × p_sk) / sum_k(alpha_k)`.

Weights must be finite, nonnegative and have a positive sum. Rank transforms
bound outlier influence; monotone log transforms would not change these ranks.
Ties receive average ranks. High holder HHI represents dependence on a few
large holders, not widespread ownership. A one-holder security has HHI 1;
breadth and HHI deliberately measure different dimensions. Mean overlap is zero
for a singleton. Report the decomposition, not merely a total score.

Scores are relative to the observed universe. Correlated components double-count
some information; defaults are heuristic, not estimated optimal weights. Large
managers, mixed reporting periods and overlapping discretion distort values.
There is no float denominator, and no claim about percentage ownership of the
issuer. There is no established industry status for this score.

## Manager relationships

Cosine = dot(w_a,w_b)/(norm(w_a) norm(w_b)). Weighted overlap =
sum_s min(w_as,w_bs). Both range from zero to one for nonnegative weights.
Average-linkage agglomerative clustering uses distance 1 − cosine and up to three
clusters. Cluster membership is descriptive, unstable to universe changes, and
not evidence of coordination. Graph positions use a deterministic circular layout.

## Walk-forward protocol

The baseline is an **untrained, pre-specified rule**. It does not fit a predictive
model: six calendar months of observation precede evaluation; subsequent monthly
folds expand the available information set. Rank by ownership change or crowding,
buy the highest (or lowest) N eligible securities, equal weight, and hold until
the next rebalance. Ties break by permanent security identifier. Positions drift
between rebalances. All research parameter choices made after looking at output
are exploratory; reserve a fresh holdout before claiming generalization.

If adding learned models, purge all training observations whose forward endpoint
reaches the test start, fit scalers only on training data, choose hyperparameters
inside the training window, and use an embargo for overlapping labels. That
model-fitting/purged-CV extension is not implemented or implied here.

Daily gross return is R_t = sum_s(w_(s,t−1) r_st). Before rebalancing,
weights drift to w_s(1+r_s)/(1+R). Gross traded notional is
T_t = sum_s |w_target − w_drift|. Entry from cash is one notional; full rotation
is two. The proportional cost convention is

`R_net,t = (1 + R_gross,t) × (1 − T_t × bps/10000) − 1`.

This is a post-return NAV haircut approximation; targets are then expressed as
fractions of post-cost NAV. Defaults are 15 bps per traded dollar. Inspect 0/15/50
bps sensitivity. Slippage is not market-impact calibrated, and no capacity,
borrow, taxes, management fees or forced end-date liquidation are modeled.
Cash earns zero. A selected security with no execution price is excluded before
selection; once held, missing prices fail loudly. Delisting outcomes must be
supplied as positive total-return-index endpoints; a total wipeout needs an
explicit portfolio exit policy and is not supported by the positive-price contract.
No forward-fill, backfill or artificial flat return is applied to held securities.
The observed date index is the session calendar; use a complete validated
exchange calendar in real research (demo dates are weekdays, including holidays).

## Statistics

- h-month forward return: P_e/P_t − 1, where e is the first observed session on or
  after t plus h calendar months, at most seven days later. No endpoint means no
  label. Horizons are 1, 3 and 6 months. Missing asset endpoints remain NaN.
- Annualized volatility: sample daily standard deviation × sqrt(252).
- Sharpe: mean daily excess return × 252 / annualized volatility. Default annual
  risk-free rate is zero; constant-return samples return NaN.
- Wealth W_t = product(1+R_t), W_0 = 1. Maximum drawdown is
  min_t(W_t / max_(u≤t) W_u − 1), including initial capital.
- Rank IC: cross-sectional Spearman correlation of the signal and forward return.
  Fewer than three paired observations or constant inputs return NaN.
- Portfolio concentration: sum_s w_s²; cash excluded. Fully cash portfolio HHI is 0.
- Sector attribution: sums of daily gross asset contributions using classifications
  known before the return date. Arithmetic attribution does not equal compounded
  performance. Transaction costs are unallocated and visible in the ledger.
- Regimes: prior-close benchmark above/below its trailing 126-session mean.
  Conditional metrics concatenate assigned sessions; they are not tradable paths.

Overlapping forward labels, repeated manager exposures and multiple experiments
invalidate naive independent-observation p-values. No significance test or claim
is provided. Block bootstrap/HAC inference and a registered holdout are future
research steps, not silently assumed validation.
