import pandas as pd
import pytest
from datetime import datetime, timezone
from app import create_app
from app.services.stock_data_service import (
    StockDataService, MarketDataProvider, HistoryResult)


class FakeProvider(MarketDataProvider):
    def get_history(self, symbol, period):
        if symbol == "BAD.NS":
            return HistoryResult(symbol=symbol, error="no data")
        idx = pd.date_range("2025-01-01", periods=5, freq="B")
        df = pd.DataFrame({"Open": [1, 2, 3, 4, 5.0], "High": [2, 3, 4, 5, 6.0],
                           "Low": [0.5] * 5, "Close": [1, 2, 3, 4, 5.0],
                           "Volume": [10] * 5}, index=idx)
        return HistoryResult(symbol=symbol, data=df, resolved_symbol=symbol,
                             fetched_at=datetime.now(timezone.utc), source="fake")


def test_summary_math():
    svc = StockDataService(FakeProvider())
    s = svc.summary("X.NS")
    assert s["close"] == 5.0 and s["change"] == 1.0
    assert round(s["change_pct"], 2) == 25.0


def test_error_is_reported_not_raised():
    assert "error" in StockDataService(FakeProvider()).summary("BAD.NS")


def test_invalid_period():
    assert StockDataService(FakeProvider()).get_history("X.NS", "99y").error


def test_unknown_symbol_404():
    c = create_app("testing").test_client()
    assert c.get("/api/stocks/FAKE.NS/summary").status_code == 404
    assert c.get("/api/stocks/TCS.NS/history?period=bogus").status_code == 400