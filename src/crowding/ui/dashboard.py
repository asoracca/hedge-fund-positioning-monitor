from pathlib import Path
import json
import os
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from crowding.storage import load_dataset, connect
from crowding.normalization.holdings import snapshot, position_changes, map_securities
from crowding.analytics.crowding import crowding_score, manager_network, weighted_overlap, DEFAULT_WEIGHTS
from crowding.backtesting.engine import walk_forward, Config, regime_analysis
from crowding.backtesting.attribution import sector_attribution

TEAL = "#63C7BB"


def chart(fig, height=420):
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="#0B1220",
        plot_bgcolor="#0B1220",
        font=dict(family="Inter, Arial", color="#BDCBD8"),
        height=height,
        margin=dict(l=12, r=15, t=35, b=20),
        colorway=[TEAL, "#7C93D0", "#D3AC72", "#AE83BB"],
        legend=dict(orientation="h", y=1.12),
        hoverlabel=dict(bgcolor="#172738"),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#203044", zerolinecolor="#203044")
    st.plotly_chart(fig, use_container_width=True)


def table(frame):
    st.dataframe(frame, use_container_width=True, hide_index=True)


@st.cache_data
def data(path, stamp):
    return load_dataset(path)


@st.cache_data(show_spinner="Reconstructing disclosure-time portfolios…")
def research(f, p, prices, config, weights):
    return walk_forward(f, p, prices, config, weights)


def main():
    st.set_page_config(page_title="Positioning / Research Terminal", page_icon="◈", layout="wide")
    st.markdown(
        """<style>
    .block-container {padding-top:2rem; max-width:1600px;}
    [data-testid="stSidebar"] {border-right:1px solid #233247;}
    h1 {font-size:2rem!important; letter-spacing:-.045em; font-weight:650!important;}
    h2,h3 {letter-spacing:-.025em;}
    [data-testid="stMetric"] {background:#111D2C;border:1px solid #233247;border-radius:8px;padding:18px;}
    [data-testid="stMetricLabel"] {color:#92A7BA;font-size:12px;text-transform:uppercase;letter-spacing:.09em;}
    .eyebrow {color:#63C7BB;font-size:11px;letter-spacing:.23em;font-weight:600;margin-bottom:12px;}
    .subtitle {color:#8EA3B7;font-size:14px;margin-top:-8px;margin-bottom:24px;}
    .status {background:#132B2C;border:1px solid #28514E;padding:9px 14px;border-radius:5px;color:#9BD5CA;font-size:12px;}
    </style>""",
        unsafe_allow_html=True,
    )
    default = Path(__file__).resolve().parents[3] / "data" / "demo"
    path = Path(os.getenv("CROWDING_DATA_DIR", str(default)))
    if not (path / "manifest.json").exists():
        st.error("Dataset missing. Run: python -m crowding.cli demo")
        st.stop()
    stamps = tuple(p.stat().st_mtime_ns for p in sorted(path.glob("*.parquet")))
    d = data(str(path), stamps)
    f, p, prices, mappings = (d[k] for k in ["filings", "positions", "prices", "mappings"])
    demo = d["manifest"].get("kind") == "synthetic"
    st.sidebar.markdown("### ◈ POSITIONING")
    st.sidebar.caption("INSTITUTIONAL RESEARCH TERMINAL")
    page = st.sidebar.radio(
        "Workspace",
        [
            "Overview",
            "Crowding monitor",
            "Holdings explorer",
            "Manager network",
            "Signal research",
            "Company research",
            "Data & methodology",
        ],
        label_visibility="collapsed",
    )
    st.sidebar.divider()
    as_of = pd.Timestamp(
        st.sidebar.date_input(
            "Information available through",
            value=f.filing_date.max().date(),
            min_value=f.filing_date.min().date(),
            max_value=prices.index.max().date(),
        )
    )
    st.sidebar.caption(
        "Only filings public on or before this date enter the explorer. Research trades strictly after filing dates."
    )
    with st.sidebar.expander("Crowding weights"):
        weights = {
            key: st.slider(key.replace("_", " ").title(), 0.0, 1.0, float(value), 0.05)
            for key, value in DEFAULT_WEIGHTS.items()
        }
    if sum(weights.values()) == 0:
        st.error("At least one crowding component must have positive weight.")
        st.stop()
    current = snapshot(f, p, as_of)
    prior = snapshot(f, p, as_of - pd.DateOffset(months=3))
    if current.empty:
        st.info("No eligible filings for this date.")
        st.stop()
    enriched = map_securities(current, mappings, as_of)
    labels = enriched.drop_duplicates("security_id").set_index("security_id")
    scores = crowding_score(current, prior, weights).merge(
        labels[["ticker", "sector"]], left_on="security_id", right_index=True, how="left"
    )
    st.markdown('<div class="eyebrow">13F / PUBLIC DISCLOSURES / RESEARCH</div>', unsafe_allow_html=True)
    st.title("Hedge Fund Positioning & Crowding Monitor")
    st.markdown(
        '<div class="subtitle">Trace institutional conviction. Measure shared exposure. Test the evidence.</div>',
        unsafe_allow_html=True,
    )
    badge = (
        "SYNTHETIC DEMO · All managers, holdings, prices and performance are generated."
        if demo
        else "PUBLIC FILINGS · Review source coverage and price licensing before interpreting results."
    )
    st.markdown(f'<div class="status">{badge}</div>', unsafe_allow_html=True)
    st.caption(f"{page.upper()}  /  AS OF {as_of:%d %b %Y}  /  USD  /  LONG SHARE POSITIONS ONLY")
    st.sidebar.divider()
    st.sidebar.caption(
        "RESEARCH, NOT INVESTMENT ADVICE\n\n13F ≠ full portfolio. Shorts, many derivatives and undisclosed positions are absent. Managers include institutions other than hedge funds."
    )
    if page == "Overview":
        a, b, c, e = st.columns(4)
        a.metric("Reporting managers", current.cik.nunique())
        b.metric("Disclosed value", f"${current.value_usd.sum() / 1e9:.2f}B")
        c.metric("Securities observed", current.security_id.nunique())
        e.metric("Median report age", f"{(as_of - current.report_date).dt.days.median():.0f} days")
        left, right = st.columns([1.35, 1])
        with left:
            st.subheader("Most crowded disclosures")
            top = scores.head(12).sort_values("score")
            chart(
                px.bar(
                    top,
                    x="score",
                    y="ticker",
                    orientation="h",
                    color="score",
                    color_continuous_scale=["#224447", TEAL],
                    hover_data=["breadth", "value", "holder_hhi"],
                ).update_layout(coloraxis_showscale=False)
            )
        with right:
            st.subheader("Reported sector exposure")
            sector = enriched.groupby("sector", as_index=False).value_usd.sum()
            chart(
                px.pie(sector, names="sector", values="value_usd", hole=0.7).update_traces(
                    textposition="inside", textinfo="percent"
                )
            )
        st.subheader("Manager concentration")
        summary = current.groupby(["manager", "cik"], as_index=False).agg(
            reported_value=("value_usd", "sum"),
            holdings=("security_id", "nunique"),
            hhi=("weight", lambda x: (x * x).sum()),
            filing_date=("filing_date", "max"),
        )
        table(summary.sort_values("reported_value", ascending=False))
        st.caption(
            "Values may double-count shared investment discretion. Mixed reporting quarters are shown as latest known; totals are neither AUM nor current institutional ownership."
        )
    elif page == "Crowding monitor":
        st.subheader("A decomposable crowding heuristic")
        st.caption(
            "Within-snapshot percentile ranks. Higher holder HHI means dependence on fewer large holders; it does not mean broader ownership."
        )
        sector = st.multiselect("Sector filter", sorted(scores.sector.unique()))
        view = scores[scores.sector.isin(sector)] if sector else scores
        heat = view.set_index("ticker")[[k + "_rank" for k in weights]].head(30)
        heat.columns = [k.replace("_", " ").title() for k in weights]
        chart(
            px.imshow(
                heat, color_continuous_scale=["#101F31", "#275C60", TEAL], zmin=0, zmax=1, aspect="auto"
            ),
            600,
        )
        table(
            view[
                ["ticker", "sector", "score", "breadth", "value", "holder_hhi", "ownership_change", "overlap"]
            ].round(4)
        )
        st.download_button(
            "Export score decomposition", view.to_csv(index=False), "crowding_scores.csv", "text/csv"
        )
    elif page == "Holdings explorer":
        query = st.text_input("Search managers by name or CIK", placeholder="e.g. Alder or 9000000000")
        managers = f[["cik", "manager"]].drop_duplicates()
        managers = managers[
            managers.manager.str.contains(query, case=False, regex=False)
            | managers.cik.str.contains(query, regex=False)
        ]
        if managers.empty:
            st.info("No managers match this search in the loaded dataset.")
            return
        names = managers.set_index("cik").manager.to_dict()
        cik = st.selectbox("Manager", list(names), format_func=lambda c: f"{names[c]} · {c}")
        periods = sorted(f[(f.cik == cik) & (f.filing_date <= as_of)].report_date.unique(), reverse=True)
        if not periods:
            st.info("No public filings for this manager at selected date.")
            return
        period = st.selectbox("Reporting quarter", periods, format_func=lambda x: str(pd.Timestamp(x).date()))
        all_current = snapshot(f, p, as_of, period, max_age_days=36500)
        manager = all_current[all_current.cik == cik]
        mapped = map_securities(manager, mappings, as_of)
        a, b, c = st.columns(3)
        a.metric("Reported long value", f"${manager.value_usd.sum() / 1e6:,.1f}M")
        b.metric("Top 5 weight", f"{manager.weight.nlargest(5).sum():.1%}")
        c.metric("Portfolio HHI", f"{(manager.weight**2).sum():.3f}")
        chart(px.bar(mapped.sort_values("weight", ascending=False), x="ticker", y="weight", color="sector"))
        table(mapped[["ticker", "security_id", "sector", "shares", "value_usd", "weight", "filing_date"]])
        previous_period = pd.Timestamp(period) - pd.offsets.QuarterEnd()
        old = snapshot(f, p, as_of, previous_period, max_age_days=36500)
        change = position_changes(manager, old[old.cik == cik])
        st.subheader("Changes versus prior quarter")
        if change.empty:
            st.info("No comparable prior report. Missing filings are not treated as exits.")
        else:
            table(change.merge(labels[["ticker"]], left_on="security_id", right_index=True, how="left"))
        st.caption(
            "Share changes are as reported, not inferred transactions. Splits, mergers and amendments can explain changes; market-value changes also reflect price moves."
        )
    elif page == "Manager network":
        st.subheader("Shared exposures, visible structure")
        sim, clusters = manager_network(current)
        names = current.drop_duplicates("cik").set_index("cik").manager.to_dict()
        threshold = st.slider("Minimum cosine similarity", 0.0, 1.0, 0.45, 0.05)
        angles = np.linspace(0, 2 * np.pi, len(sim), endpoint=False)
        xy = {c: (np.cos(t), np.sin(t)) for c, t in zip(sim.index, angles)}
        fig = go.Figure()
        edges = []
        for i, a in enumerate(sim.index):
            for b in sim.index[i + 1 :]:
                if sim.loc[a, b] >= threshold:
                    fig.add_trace(
                        go.Scatter(
                            x=[xy[a][0], xy[b][0]],
                            y=[xy[a][1], xy[b][1]],
                            mode="lines",
                            line=dict(color="rgba(99,199,187,.25)", width=1 + 3 * sim.loc[a, b]),
                            hoverinfo="skip",
                            showlegend=False,
                        )
                    )
                    edges.append(
                        {
                            "manager_a": names[a],
                            "manager_b": names[b],
                            "cosine": sim.loc[a, b],
                            "weighted_overlap": weighted_overlap(current, a, b),
                        }
                    )
        fig.add_trace(
            go.Scatter(
                x=[xy[c][0] for c in sim.index],
                y=[xy[c][1] for c in sim.index],
                mode="markers+text",
                text=[names[c].replace(" [DEMO]", "") for c in sim.index],
                textposition="top center",
                marker=dict(size=22, color=clusters.values, colorscale=["#63C7BB", "#7C93D0", "#D3AC72"]),
                customdata=sim.index,
                hovertemplate="%{text}<br>CIK %{customdata}<extra></extra>",
                showlegend=False,
            )
        )
        fig.update_xaxes(visible=False, range=[-1.5, 1.5])
        fig.update_yaxes(visible=False, range=[-1.35, 1.35])
        chart(fig, 540)
        st.caption(
            "Nodes: managers. Edges: portfolio-weight cosine similarity. Colors: average-linkage clusters, not inferred coordination. Circular layout is deterministic."
        )
        table(pd.DataFrame(edges))
        table(
            current.groupby("manager", as_index=False).agg(
                hhi=("weight", lambda x: (x * x).sum()), largest_position=("weight", "max")
            )
        )
    elif page == "Signal research":
        st.subheader("Disclosure-aware walk-forward evaluation")
        a, b, c, dcol = st.columns(4)
        signal = a.selectbox("Signal", ["ownership_change", "score"])
        n = b.slider("Holdings per rebalance", 1, min(20, len(prices.columns)), 5)
        cost = c.number_input("Cost per traded dollar · bps", 0.0, 200.0, 15.0, 5.0)
        direction = dcol.selectbox("Direction", ["Highest signal", "Lowest signal"])
        st.caption(
            "Fixed, untrained signal · six-month observation warmup · monthly equal-weight selection · prior-day disclosure cutoff · execution at first observed session close. Selecting parameters here is exploratory, not an untouched holdout."
        )
        try:
            result = research(
                f[f.filing_date <= as_of],
                p,
                prices.loc[:as_of],
                Config(
                    top_n=n,
                    cost_bps=cost,
                    signal=signal,
                    direction=1 if direction == "Highest signal" else -1,
                ),
                weights,
            )
        except ValueError as exc:
            st.warning(str(exc))
            return
        daily = result["daily"]
        a, b, c, dcol = st.columns(4)
        m = result["metrics"]
        a.metric("Net total return", f"{m['total_return']:.1%}")
        b.metric("Annualized volatility", f"{m['volatility']:.1%}")
        c.metric("Sharpe · risk-free 0%", f"{m['sharpe']:.2f}")
        dcol.metric("Maximum drawdown", f"{m['max_drawdown']:.1%}")
        bench_returns = prices.pct_change(fill_method=None).mean(axis=1)
        curves = pd.DataFrame(
            {
                "Signal · net": (1 + daily.net_return).cumprod(),
                "Signal · gross": (1 + daily.gross_return).cumprod(),
                "Synthetic universe · daily equal weight"
                if demo
                else "Loaded universe · daily equal weight": (
                    1 + bench_returns.reindex(daily.index)
                ).cumprod(),
            }
        )
        chart(px.line(curves, labels={"value": "Growth of $1", "index": "Date"}), 440)
        st.caption(
            "Benchmark is a descriptive frictionless universe comparator, not a tradable cost-matched strategy. No leverage, shorting or terminal liquidation is modeled."
        )
        left, right = st.columns(2)
        with left:
            st.subheader("Forward rank IC")
            if not result["ic"].empty:
                chart(
                    px.bar(result["ic"].groupby("months", as_index=False).ic.mean(), x="months", y="ic"), 270
                )
                st.caption(
                    "1, 3 and 6 calendar-month forward returns; overlapping labels are not independent. No significance claim."
                )
        with right:
            st.subheader("Trading and concentration")
            chart(px.line(daily[["traded_notional", "hhi"]], labels={"value": "Fraction"}), 270)
        st.subheader("Sector contribution to strategy returns")
        table(sector_attribution(result["contributions"], mappings))
        st.caption(
            "Sum of daily gross portfolio-return contributions, classified using information known before each session. Contributions sum to arithmetic gross returns, not compounded return. Costs are reported separately in the ledger."
        )
        st.subheader("Sector / forward-return diagnostics")
        if not result["signals"].empty:
            sector_labels = (
                result["labels"].merge(
                    mappings[["security_id", "sector"]].drop_duplicates("security_id"), on="security_id"
                )
                if demo
                else pd.DataFrame()
            )
            if not sector_labels.empty:
                table(
                    sector_labels.groupby(["sector", "months"], as_index=False)
                    .forward_return.agg(["mean", "count"])
                    .reset_index()
                )
                st.caption(
                    "Universe-level forward-return diagnostics, not sector strategy attribution. Real data requires historical sector classification."
                )
        benchmark = (1 + bench_returns.fillna(0)).cumprod()
        table(regime_analysis(daily, benchmark).reset_index())
        st.caption(
            "Regime statistics concatenate the sessions assigned to each regime; they are conditional diagnostics, not standalone trading strategies."
        )
        with st.expander("Audit walk-forward boundaries"):
            table(result["folds"])
        st.download_button(
            "Download daily research ledger", daily.to_csv(), "research_ledger.csv", "text/csv"
        )
    elif page == "Company research":
        security = st.selectbox(
            "Security", scores.security_id, format_func=lambda s: f"{labels.loc[s, 'ticker']} · {s}"
        )
        row = scores[scores.security_id == security].iloc[0]
        a, b, c = st.columns(3)
        a.metric("Crowding heuristic", f"{row.score:.1f} / 100")
        b.metric("Reporting holders", int(row.breadth))
        c.metric("Reported value", f"${row.value / 1e6:,.1f}M")
        if security in prices:
            chart(
                px.line(
                    prices.loc[:as_of, security],
                    labels={"value": "Total-return price index", "index": "Date"},
                )
            )
        table(
            enriched[enriched.security_id == security][
                ["manager", "cik", "shares", "value_usd", "weight", "report_date", "filing_date"]
            ].sort_values("value_usd", ascending=False)
        )
        st.subheader("Supporting SEC fundamentals")
        issuer = labels.loc[security].get("issuer_cik")
        issuer = str(int(issuer)).zfill(10) if pd.notna(issuer) else None
        facts_path = path / "facts" / f"CIK{issuer}.json"
        if issuer and facts_path.exists():
            from crowding.ingestion.sec import facts_as_of

            payload = json.loads(facts_path.read_text())
            if str(payload.get("cik", "")).zfill(10) != issuer:
                st.error("Company facts CIK does not match the historical security mapping.")
                return
            st.caption(f"Source issuer: {payload.get('entityName', 'Unknown')} · CIK {issuer}")
            table(facts_as_of(payload, as_of))
        else:
            st.info(
                "No company fundamentals loaded. Fetch SEC company-facts by issuer CIK using the CLI; no fundamentals are fabricated for demo securities."
            )
    else:
        st.subheader("Provenance and research controls")
        st.json(d["manifest"])
        with connect(path) as db:
            table(db.execute("SELECT amendment, COUNT(*) AS filings FROM filings GROUP BY amendment").df())
        st.markdown("""**Availability:** filing dates, never report dates, gate information. Date-only filings become tradeable at the next observed session close. Amendments enter only when public.

**Coverage:** latest known reports can mix periods; 200-day staleness cap. Missing reports are not exits. Options and non-share positions are excluded. Institutional managers are not synonymous with hedge funds.

**Biases:** selection and survivorship bias, confidential holdings, overlapping investment discretion, reporting errors, missing delisting returns, identifier changes and unobserved shorts can dominate results.

**Score:** a weighted mean of within-snapshot percentile ranks of manager breadth, reported value, holder HHI, matched-cohort ownership change and average holder cosine similarity. Scores are relative and not comparable across changing universes without caution.

**Licensing:** SEC public filings only. No PitchBook data. Real prices require a separate documented source/license and total-return treatment. Synthetic data is released under CC0.""")
        st.link_button(
            "SEC 13F datasets", "https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets"
        )
