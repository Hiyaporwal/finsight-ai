import pandas as pd
import pytest
from app.services.financial_metrics import (
    analyze_fundamentals, interpolate, FundamentalsError, SCORING)

D0, D1 = pd.Timestamp("2025-03-31"), pd.Timestamp("2024-03-31")


def frame(rows):
    return pd.DataFrame(rows, index=[D0, D1]).T


def healthy():
    return {
        "income": frame({"Total Revenue": [120.0, 100.0], "Net Income": [24.0, 18.0],
                         "Operating Income": [30.0, 22.0], "Diluted EPS": [5.0, 4.0]}),
        "balance": frame({"Total Debt": [20.0, 25.0], "Stockholders Equity": [100.0, 90.0],
                          "Total Assets": [250.0, 230.0]}),
        "cashflow": frame({"Operating Cash Flow": [28.0, 20.0]}),
        "info": {"trailingPE": 22.5},
    }


def test_interpolation_and_clamping():
    pts = SCORING["net_margin"][1]
    assert interpolate(-1, pts) == 0 and interpolate(1, pts) == 100
    assert interpolate(0.075, pts) == pytest.approx(52.5)


def test_weights_sum_to_100():
    assert sum(w for w, _ in SCORING.values()) == 100


def test_healthy_company_scores_high():
    out = analyze_fundamentals(healthy(), "IT Services")
    assert out["overall_score"] > 70 and out["rating"] == "Strong"
    assert out["coverage_pct"] == 60
    m = {x["key"]: x for x in out["metrics"]}
    assert m["revenue_growth"]["value"] == pytest.approx(0.2)
    assert m["debt_to_equity"]["value"] == pytest.approx(0.2)


def test_missing_metric_is_missing_not_invented():
    d = healthy()
    d["cashflow"] = pd.DataFrame()
    out = analyze_fundamentals(d, "IT Services")
    m = {x["key"]: x for x in out["metrics"]}
    assert m["ocf_margin"]["status"] == "missing" and m["ocf_margin"]["value"] is None
    assert out["coverage_pct"] == 85


def test_bank_excludes_leverage_metrics():
    out = analyze_fundamentals(healthy(), "Banking")
    m = {x["key"]: x for x in out["metrics"]}
    for k in ("debt_to_equity", "operating_margin", "ocf_margin"):
        assert m[k]["status"] == "not_meaningful"
    assert out["coverage_pct"] == 55


def test_insufficient_data_gives_no_score():
    d = {"income": frame({"Total Revenue": [120.0, 100.0]}), "balance": pd.DataFrame(),
         "cashflow": pd.DataFrame(), "info": {}}
    out = analyze_fundamentals(d, "IT Services")
    assert out["overall_score"] is None and out["rating"] == "Insufficient data"


def test_nothing_usable_raises():
    with pytest.raises(FundamentalsError):
        analyze_fundamentals({"income": pd.DataFrame({"x": [1]}, index=["Foo"]),
                              "balance": pd.DataFrame(), "cashflow": pd.DataFrame()}, "")