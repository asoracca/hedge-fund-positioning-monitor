import json
from io import BytesIO
from zipfile import ZipFile
import httpx
import numpy as np
import pandas as pd
import pytest
from crowding.normalization.holdings import validate, snapshot, map_securities, position_changes
from crowding.analytics.crowding import crowding_score, manager_network, weighted_overlap
from crowding.backtesting.metrics import performance, information_coefficient, forward_returns
from crowding.backtesting.engine import walk_forward, Config, validate_prices
from crowding.ingestion.archives import parse_archive
from crowding.ingestion.sec import SECClient, facts_as_of
from crowding.ingestion.prices import import_prices
from crowding.storage import connect, load_dataset
from crowding.demo import generate


@pytest.fixture
def small():
    f = pd.DataFrame(
        [
            ["a", "1", "Manager", "2023-03-31", "2023-05-15", "original"],
            ["b", "1", "Manager", "2023-03-31", "2023-05-20", "addition"],
            ["c", "1", "Manager", "2023-03-31", "2023-06-01", "restatement"],
        ],
        columns=["accession", "cik", "manager", "report_date", "filing_date", "amendment"],
    )
    p = pd.DataFrame(
        [["a", "AAA", 10, 100], ["b", "AAA", 2, 20], ["b", "BBB", 5, 50], ["c", "BBB", 9, 90]],
        columns=["accession", "security_id", "shares", "value_usd"],
    )
    return validate(f, p)


def test_actual_disclosure_dates(small):
    f, p = small
    assert snapshot(f, p, "2023-05-14").empty
    assert snapshot(f, p, "2023-05-15").value_usd.sum() == 100
    assert snapshot(f, p, "2023-05-19").value_usd.sum() == 100


def test_additions_and_restatements(small):
    f, p = small
    amended = snapshot(f, p, "2023-05-21").set_index("security_id")
    assert amended.loc["AAA", "shares"] == 12
    assert amended.value_usd.sum() == 170
    restated = snapshot(f, p, "2023-06-01")
    assert restated.security_id.tolist() == ["BBB"]
    assert restated.value_usd.sum() == 90
    assert snapshot(f, p, "2023-05-16").security_id.tolist() == ["AAA"]


def test_missing_base_rejected(small):
    f, p = small
    with pytest.raises(ValueError, match="without base"):
        snapshot(f[f.accession == "b"], p, "2023-05-21")


def test_staleness_and_validation(small):
    f, p = small
    assert snapshot(f, p, "2024-01-01").empty
    with pytest.raises(ValueError, match="Duplicate accession"):
        validate(pd.concat([f, f]), p)
    bad = p.copy()
    bad.loc[0, "shares"] = -1
    with pytest.raises(ValueError, match="nonnegative"):
        validate(f, bad)
    bad = f.copy()
    bad.loc[0, "filing_date"] = pd.Timestamp("2020-01-01")
    with pytest.raises(ValueError, match="precedes"):
        validate(bad, p)


def test_mapping_knowledge_date(small):
    f, p = small
    h = snapshot(f, p, "2023-05-15")
    m = pd.DataFrame(
        [
            dict(
                security_id="AAA",
                ticker="LATER",
                sector="Tech",
                valid_from="2020-01-01",
                valid_to=None,
                known_at="2023-06-01",
            )
        ]
    )
    assert map_securities(h, m, "2023-05-15").iloc[0].mapping_status == "unmapped"
    assert map_securities(h, m, "2023-06-01").iloc[0].ticker == "LATER"


def test_missing_manager_not_exit(small):
    f, p = small
    old = snapshot(f, p, "2023-05-15")
    new = old.copy()
    new["cik"] = "2"
    assert position_changes(new, old).empty


def test_drawdown_includes_initial_capital():
    assert performance([-0.2, 0.1])["max_drawdown"] == pytest.approx(-0.2)
    assert performance([0.1, -0.1])["total_return"] == pytest.approx(-0.01)
    assert np.isnan(performance([0, 0])["sharpe"])


def test_ic_and_forward_horizons():
    assert information_coefficient(pd.Series([1, 2, 3]), pd.Series([0.3, 0.2, 0.1])) == pytest.approx(-1)
    assert np.isnan(information_coefficient(pd.Series([1, 1, 1]), pd.Series([1, 2, 3])))
    dates = pd.bdate_range("2023-01-02", "2023-04-05")
    prices = pd.DataFrame({"A": np.arange(len(dates)) + 100.0}, index=dates)
    result = forward_returns(prices, [dates[0]])
    assert set(result.months) == {1, 3}
    first = result[result.months == 1].iloc[0]
    assert first.end_date == pd.Timestamp("2023-02-02")
    assert first.forward_return == pytest.approx(prices.loc["2023-02-02", "A"] / 100 - 1)


def test_crowding_and_network(small):
    f, p = small
    h = snapshot(f, p, "2023-05-21")
    other = h.copy()
    other["cik"] = "2"
    both = pd.concat([h, other])
    sim, clusters = manager_network(both)
    assert sim.iloc[0, 1] == pytest.approx(1)
    assert weighted_overlap(both, h.cik.iloc[0], "2") == pytest.approx(1)
    score = crowding_score(both, h)
    assert score.score.between(0, 100).all()
    assert (score.ownership_change == 0).all()  # newly sampled manager cannot create ownership growth
    with pytest.raises(ValueError):
        crowding_score(h, weights={"bad": 1})


def test_walk_forward_no_future_and_costs(small):
    f, p = small
    prices = pd.DataFrame(100.0, index=pd.bdate_range("2023-01-01", "2023-09-01"), columns=["AAA", "BBB"])
    cfg = Config(top_n=1, cost_bps=100, warmup_months=1)
    result = walk_forward(f, p, prices, cfg)
    active = result["allocations"]
    assert active.date.min() > f.filing_date.min()
    assert (
        result["folds"].latest_filing.dropna() < result["folds"].dropna(subset=["latest_filing"]).test_start
    ).all()
    assert result["daily"].gross_return.eq(0).all()
    trades = result["daily"].query("traded_notional > 0")
    assert trades.net_return.iloc[0] == pytest.approx(-0.01)
    assert np.allclose(trades.net_return, -trades.traded_notional * 0.01)
    future = f.copy()
    future.loc[future.accession == "c", "filing_date"] = pd.Timestamp("2023-08-15")
    a = walk_forward(f, p, prices.loc[:"2023-05-31"], cfg)["daily"]
    b = walk_forward(future, p, prices.loc[:"2023-05-31"], cfg)["daily"]
    pd.testing.assert_frame_equal(a, b)


def test_missing_held_price_fails(small):
    f, p = small
    prices = pd.DataFrame(100.0, index=pd.bdate_range("2023-01-01", "2023-09-01"), columns=["AAA", "BBB"])
    prices.loc["2023-06-15", :] = np.nan
    with pytest.raises(ValueError, match="Missing held-asset"):
        walk_forward(f, p, prices, Config(warmup_months=1))


def test_price_validation():
    with pytest.raises(ValueError):
        validate_prices(pd.DataFrame({"A": [0.0]}, index=pd.to_datetime(["2023-01-01"])))


def test_sec_adapter_units_and_options():
    archive = BytesIO()
    with ZipFile(archive, "w") as z:
        z.writestr(
            "SUBMISSION.tsv",
            "ACCESSION_NUMBER\tFILING_DATE\tSUBMISSIONTYPE\tCIK\tPERIODOFREPORT\na\t15-MAY-2022\t13F-HR\t1\t31-MAR-2022\n",
        )
        z.writestr("COVERPAGE.tsv", "ACCESSION_NUMBER\tFILINGMANAGER_NAME\tAMENDMENTTYPE\na\tTest\t\n")
        z.writestr(
            "INFOTABLE.tsv",
            "ACCESSION_NUMBER\tCUSIP\tVALUE\tSSHPRNAMT\tSSHPRNAMTTYPE\tPUTCALL\na\t123456789\t10\t20\tSH\t\na\t123456789\t100\t200\tSH\tPUT\n",
        )
    f, p = parse_archive(archive.getvalue())
    assert len(p) == 1 and p.value_usd.iloc[0] == 10000
    _, p = parse_archive(archive.getvalue(), "usd")
    assert p.value_usd.iloc[0] == 10


def test_sec_cache_and_identity(tmp_path):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=b'{"test":true}')

    client = SECClient("Research researcher@university.edu", tmp_path, transport=httpx.MockTransport(handler))
    url = "https://data.sec.gov/submissions/CIK0000000001.json"
    assert client.get(url) == client.get(url)
    assert len(calls) == 1
    with pytest.raises(ValueError):
        client.get("https://example.com")
    client.close()
    with pytest.raises(ValueError):
        SECClient("Anonymous")


def test_fundamentals_vintages():
    payload = {
        "facts": {
            "us-gaap": {
                "Assets": {
                    "units": {"USD": [{"filed": "2023-03-01", "val": 1}, {"filed": "2024-03-01", "val": 2}]}
                }
            }
        }
    }
    assert facts_as_of(payload, "2023-04-01").val.tolist() == [1]


def test_price_license_contract(tmp_path):
    csv = tmp_path / "prices.csv"
    meta = tmp_path / "meta.json"
    csv.write_text("date,security_id,adjusted_close\n2023-01-03,ABC,100\n")
    meta.write_text(
        json.dumps(
            {
                "provider": "Test",
                "source_url": "https://test.invalid",
                "license": "CC0",
                "retrieved_at": "2023-01-04",
                "adjustment": "total_return",
                "redistribution_allowed": False,
            }
        )
    )
    prices, provenance = import_prices(csv, meta)
    assert prices.iloc[0, 0] == 100
    meta.write_text("{}")
    with pytest.raises(ValueError):
        import_prices(csv, meta)


def test_demo_parquet_duckdb_reproducible(tmp_path):
    generate(tmp_path / "a")
    generate(tmp_path / "b")
    a = load_dataset(tmp_path / "a")
    b = load_dataset(tmp_path / "b")
    pd.testing.assert_frame_equal(a["prices"], b["prices"])
    with connect(tmp_path / "a") as db:
        assert db.execute("select count(*) from filings").fetchone()[0] == len(a["filings"])


def test_drift_turnover_and_contribution_identity(small):
    f, p = small
    prices = pd.DataFrame(100.0, index=pd.bdate_range("2023-01-01", "2023-07-31"), columns=["AAA", "BBB"])
    prices.loc["2023-06-15":, "AAA"] = 110.0
    result = walk_forward(f[f.accession != "c"], p, prices, Config(top_n=2, cost_bps=0, warmup_months=1))
    daily = result["daily"]
    assert daily.loc["2023-06-15", "gross_return"] == pytest.approx(0.05)
    contributions = result["contributions"].groupby("date").gross_contribution.sum()
    assert np.allclose(contributions, daily.loc[contributions.index, "gross_return"])
    assert daily.loc["2023-07-03", "traded_notional"] == pytest.approx(2 * (0.55 / 1.05 - 0.5))


def test_sector_classification_is_point_in_time():
    from crowding.backtesting.attribution import sector_attribution

    c = pd.DataFrame(
        {
            "date": pd.to_datetime(["2023-01-02", "2023-01-04"]),
            "security_id": ["A", "A"],
            "gross_contribution": [0.1, 0.2],
        }
    )
    m = pd.DataFrame(
        {
            "security_id": ["A"],
            "sector": ["Tech"],
            "valid_from": ["2020-01-01"],
            "valid_to": [None],
            "known_at": ["2023-01-03"],
        }
    )
    result = sector_attribution(c, m).set_index("sector")
    assert result.loc["Unmapped", "gross_contribution_sum"] == 0.1
    assert result.loc["Tech", "gross_contribution_sum"] == 0.2
