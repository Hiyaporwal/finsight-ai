"""Market-data layer. Providers are swappable via MarketDataProvider."""
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

VALID_PERIODS = {"1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"}
# Tickers change after corporate actions. Candidates are tried in order.
SYMBOL_FALLBACKS = {"TMPV.NS": ["TATAMOTORS.NS"]}
DATA_STATUS = "Delayed / end-of-day data (not live)"


@dataclass
class HistoryResult:
    symbol: str
    data: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    fetched_at: Optional[datetime] = None
    resolved_symbol: Optional[str] = None
    source: str = ""

    @property
    def ok(self) -> bool:
        return self.data is not None and not self.data.empty


class MarketDataProvider(ABC):
    name = "abstract"

    @abstractmethod
    def get_history(self, symbol: str, period: str) -> HistoryResult:
        """Return daily OHLCV with a DatetimeIndex. Never raise for data problems."""


class YFinanceProvider(MarketDataProvider):
    name = "Yahoo Finance (yfinance)"

    def __init__(self, retries: int = 3, timeout: int = 10, backoff: float = 1.5):
        self.retries = retries
        self.timeout = timeout
        self.backoff = backoff

    def _fetch(self, symbol: str, period: str) -> pd.DataFrame:
        last_exc = None
        for attempt in range(1, self.retries + 1):
            try:
                df = yf.Ticker(symbol).history(
                    period=period, interval="1d", auto_adjust=False, timeout=self.timeout)
                return df
            except Exception as exc:  # network errors, rate limits, parsing errors
                last_exc = exc
                log.warning("yfinance %s attempt %d/%d failed: %s",
                            symbol, attempt, self.retries, exc)
                time.sleep(self.backoff ** attempt)
        raise RuntimeError(f"Provider failed after {self.retries} attempts: {last_exc}")

    @staticmethod
    def _clean(df: pd.DataFrame) -> pd.DataFrame:
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        df.index.name = "Date"
        return df.dropna(subset=["Close"]).sort_index()

    def get_history(self, symbol: str, period: str) -> HistoryResult:
        candidates = [symbol] + SYMBOL_FALLBACKS.get(symbol, [])
        errors = []
        for cand in candidates:
            try:
                df = self._fetch(cand, period)
            except RuntimeError as exc:
                errors.append(str(exc))
                continue
            if df is None or df.empty:
                errors.append(f"No data returned for {cand}")
                continue
            return HistoryResult(symbol=symbol, data=self._clean(df),
                                 fetched_at=datetime.now(timezone.utc),
                                 resolved_symbol=cand, source=self.name)
        return HistoryResult(symbol=symbol, error="; ".join(errors),
                             fetched_at=datetime.now(timezone.utc), source=self.name)


class StockDataService:
    """Adds caching (including short-lived error caching) on top of a provider."""

    def __init__(self, provider: MarketDataProvider, ttl: int = 900, error_ttl: int = 60):
        self.provider = provider
        self.ttl = ttl
        self.error_ttl = error_ttl
        self._cache = {}
        self._lock = threading.Lock()

    def get_history(self, symbol: str, period: str = "1y") -> HistoryResult:
        if period not in VALID_PERIODS:
            return HistoryResult(symbol=symbol, error=f"Invalid period '{period}'")
        key = (symbol, period)
        now = time.time()
        with self._lock:
            hit = self._cache.get(key)
            if hit and now - hit[0] < (self.ttl if hit[1].ok else self.error_ttl):
                return hit[1]
        result = self.provider.get_history(symbol, period)
        with self._lock:
            self._cache[key] = (time.time(), result)
        return result

    def summary(self, symbol: str) -> dict:
        res = self.get_history(symbol, "3mo")
        if not res.ok:
            return {"symbol": symbol, "error": res.error or "No data available"}
        df = res.data
        last = df.iloc[-1]
        prev = df.iloc[-2]["Close"] if len(df) > 1 else None
        change = float(last["Close"] - prev) if prev is not None else None
        pct = float(change / prev * 100) if prev else None
        return {
            "symbol": symbol,
            "resolved_symbol": res.resolved_symbol,
            "as_of": df.index[-1].strftime("%Y-%m-%d"),
            "close": float(last["Close"]),
            "open": float(last["Open"]),
            "high": float(last["High"]),
            "low": float(last["Low"]),
            "volume": int(last["Volume"]),
            "change": change,
            "change_pct": pct,
            "fetched_at": res.fetched_at.isoformat(),
            "source": res.source,
            "data_status": DATA_STATUS,
        }

    @staticmethod
    def _clean_list(series):
        return [None if pd.isna(v) else float(v) for v in series]

    def history_json(self, symbol: str, period: str) -> dict:
        res = self.get_history(symbol, period)
        if not res.ok:
            return {"symbol": symbol, "error": res.error or "No data available"}
        df = res.data
        return {
            "symbol": symbol,
            "resolved_symbol": res.resolved_symbol,
            "period": period,
            "dates": [d.strftime("%Y-%m-%d") for d in df.index],
            "open": self._clean_list(df["Open"]),
            "high": self._clean_list(df["High"]),
            "low": self._clean_list(df["Low"]),
            "close": self._clean_list(df["Close"]),
            "volume": [int(v) for v in df["Volume"]],
            "fetched_at": res.fetched_at.isoformat(),
            "source": res.source,
            "data_status": DATA_STATUS,
        }


# Single shared instance. To change provider, only this line changes.
market_data = StockDataService(YFinanceProvider())


if __name__ == "__main__":  # quick manual check: python -m app.services.stock_data_service
    from app import SUPPORTED_STOCKS
    for sym, name, _ in SUPPORTED_STOCKS:
        s = market_data.summary(sym)
        if "error" in s:
            print(f"{sym:15} FAILED: {s['error']}")
        else:
            print(f"{sym:15} {s['as_of']}  close={s['close']:.2f}  via {s['resolved_symbol']}")