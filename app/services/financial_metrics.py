"""Financial health analysis. Uses only data returned by the provider; never invents values."""
import logging
import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger(__name__)

DISCLAIMER = ("Educational screening aid based on annual statements from a free data provider. "
              "Data can be incomplete or restated. This is not a credit rating or investment advice.")


class FundamentalsError(Exception):
    pass


class FundamentalsProvider(ABC):
    name = "abstract"

    @abstractmethod
    def get_fundamentals(self, symbol: str) -> dict:
        """Return {'income','balance','cashflow': DataFrame (rows=items, columns=dates), 'info': dict}.
        Raise FundamentalsError if nothing usable is available."""


class YFinanceFundamentals(FundamentalsProvider):
    name = "Yahoo Finance (yfinance)"

    def __init__(self, retries=3, backoff=1.5):
        self.retries, self.backoff = retries, backoff

    def get_fundamentals(self, symbol):
        import yfinance as yf
        last = None
        for attempt in range(1, self.retries + 1):
            try:
                t = yf.Ticker(symbol)
                income, balance, cash = t.financials, t.balance_sheet, t.cashflow
                try:
                    info = t.info or {}
                except Exception:
                    info = {}
                if income is None or income.empty:
                    raise FundamentalsError("No income statement data returned")
                return {"income": income, "balance": balance, "cashflow": cash, "info": info}
            except Exception as exc:
                last = exc
                log.warning("fundamentals %s attempt %d/%d failed: %s", symbol, attempt, self.retries, exc)
                time.sleep(self.backoff ** attempt)
        raise FundamentalsError(f"Could not load fundamentals: {last}")


# key: (label, unit, description)
METRIC_INFO = {
    "revenue_growth": ("Revenue growth (YoY)", "pct", "Latest fiscal year revenue vs the previous year"),
    "net_margin": ("Net profit margin", "pct", "Net income / total revenue"),
    "operating_margin": ("Operating margin", "pct", "Operating income / total revenue"),
    "debt_to_equity": ("Debt-to-equity", "ratio", "Total debt / shareholders' equity (lower is better)"),
    "roe": ("Return on equity", "pct", "Net income / year-end shareholders' equity"),
    "roa": ("Return on assets", "pct", "Net income / year-end total assets"),
    "ocf_margin": ("Operating cash flow margin", "pct", "Operating cash flow / total revenue"),
}
# key: (weight, [(value, score), ...]) scores are linearly interpolated, clamped at both ends
SCORING = {
    "revenue_growth": (15, [(-0.10, 0), (0.0, 40), (0.10, 70), (0.20, 100)]),
    "net_margin": (15, [(0.0, 0), (0.05, 40), (0.10, 65), (0.20, 100)]),
    "operating_margin": (10, [(0.0, 0), (0.08, 40), (0.15, 65), (0.25, 100)]),
    "debt_to_equity": (15, [(0.0, 100), (0.5, 85), (1.0, 65), (2.0, 35), (3.0, 0)]),
    "roe": (15, [(0.0, 0), (0.08, 40), (0.15, 70), (0.20, 100)]),
    "roa": (15, [(0.0, 0), (0.02, 40), (0.05, 70), (0.10, 100)]),
    "ocf_margin": (15, [(0.0, 0), (0.05, 40), (0.12, 70), (0.20, 100)]),
}
BANK_ROA = [(0.0, 0), (0.007, 40), (0.012, 70), (0.02, 100)]
BANK_EXCLUDED = {"operating_margin", "debt_to_equity", "ocf_margin"}
MIN_COVERAGE = 50  # percent of total weight that must be available to publish a score


def interpolate(x, points):
    if x <= points[0][0]:
        return float(points[0][1])
    if x >= points[-1][0]:
        return float(points[-1][1])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        if x0 <= x <= x1:
            return float(y0 + (y1 - y0) * (x - x0) / (x1 - x0))


def _row(df, names):
    if df is None or getattr(df, "empty", True):
        return {}
    for n in names:
        if n in df.index:
            s = df.loc[n]
            if isinstance(s, pd.DataFrame):
                s = s.iloc[0]
            s = pd.to_numeric(s, errors="coerce").dropna()
            return {pd.Timestamp(k): float(v) for k, v in s.items()}
    return {}


def _at(series, date):
    for k, v in series.items():
        if abs((k - date).days) <= 10:
            return v
    return None


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def _fmt(key, v):
    unit = METRIC_INFO[key][1]
    return f"{v * 100:.1f}%" if unit == "pct" else f"{v:.2f}"


def _label(score):
    if score is None:
        return "Insufficient data"
    return "Strong" if score >= 70 else "Moderate" if score >= 50 else "Weak"


def analyze_fundamentals(data: dict, sector: str = "") -> dict:
    inc, bal, cf, info = data["income"], data["balance"], data["cashflow"], data.get("info") or {}
    is_bank = "bank" in (sector or "").lower()

    rev = _row(inc, ["Total Revenue", "Operating Revenue"])
    ni = _row(inc, ["Net Income", "Net Income Common Stockholders"])
    opi = _row(inc, ["Operating Income", "Total Operating Income As Reported"])
    eps_s = _row(inc, ["Diluted EPS", "Basic EPS"])
    debt = _row(bal, ["Total Debt"])
    equity = _row(bal, ["Stockholders Equity", "Common Stock Equity", "Total Equity Gross Minority Interest"])
    assets = _row(bal, ["Total Assets"])
    ocf = _row(cf, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"])

    dates = sorted(set(rev) | set(ni), reverse=True)
    if not dates:
        raise FundamentalsError("Revenue and net income are both missing")
    d0 = dates[0]
    rev0, ni0 = _at(rev, d0), _at(ni, d0)
    rev_dates = sorted(rev, reverse=True)
    prior = rev[rev_dates[1]] if len(rev_dates) > 1 and _at(rev, d0) is not None else None
    eq0 = _at(equity, d0)

    notes = {}
    values = {
        "revenue_growth": (rev0 - prior) / prior if rev0 is not None and prior and prior > 0 else None,
        "net_margin": _div(ni0, rev0),
        "operating_margin": _div(_at(opi, d0), rev0),
        "debt_to_equity": None,
        "roe": None,
        "roa": _div(ni0, _at(assets, d0)),
        "ocf_margin": _div(_at(ocf, d0), rev0),
    }
    if eq0 is not None and eq0 <= 0:
        notes["debt_to_equity"] = notes["roe"] = "Shareholders' equity is not positive, so this ratio is not meaningful"
    else:
        values["debt_to_equity"] = _div(_at(debt, d0), eq0)
        values["roe"] = _div(ni0, eq0)

    metrics, scored = [], []
    for key, (label, unit, desc) in METRIC_INFO.items():
        weight, points = SCORING[key]
        if key == "roa" and is_bank:
            points = BANK_ROA
        v = values[key]
        row = {"key": key, "label": label, "unit": unit, "description": desc,
               "weight": weight, "value": v, "score": None}
        if is_bank and key in BANK_EXCLUDED:
            row["status"], row["note"] = "not_meaningful", "Not meaningful for banks, so it is excluded from the score"
        elif v is None:
            row["status"] = "missing"
            row["note"] = notes.get(key, "Not reported by the data provider")
        else:
            row["status"] = "scored"
            row["score"] = round(interpolate(v, points), 1)
            scored.append(row)
        metrics.append(row)

    covered = sum(m["weight"] for m in scored)
    overall = round(sum(m["score"] * m["weight"] for m in scored) / covered, 1) if covered >= MIN_COVERAGE else None

    strengths = [f"{m['label']}: {_fmt(m['key'], m['value'])} (score {m['score']:.0f}/100)"
                 for m in sorted(scored, key=lambda m: -m["score"]) if m["score"] >= 70][:4]
    risks = [f"{m['label']}: {_fmt(m['key'], m['value'])} (score {m['score']:.0f}/100)"
             for m in sorted(scored, key=lambda m: m["score"]) if m["score"] <= 40][:4]
    if eq0 is not None and eq0 <= 0:
        risks.insert(0, "Shareholders' equity is not positive")

    eps = _at(eps_s, d0)
    if eps is None and info.get("trailingEps") is not None:
        eps = float(info["trailingEps"])
    pe = info.get("trailingPE")
    context = [
        {"key": "eps", "label": "Earnings per share (INR)", "value": eps, "unit": "plain"},
        {"key": "pe", "label": "Price-to-earnings (trailing)", "unit": "ratio",
         "value": float(pe) if isinstance(pe, (int, float)) and pe == pe else None},
        {"key": "operating_cash_flow", "label": "Operating cash flow (INR)", "unit": "inr",
         "value": _at(ocf, d0)},
    ]
    for c in context:
        if c["value"] is None:
            c["note"] = "Not reported by the data provider"

    trend = []
    for d in dates[:4][::-1]:
        r, n = _at(rev, d), _at(ni, d)
        trend.append({"fiscal_year_end": d.strftime("%Y-%m-%d"), "revenue": r, "net_income": n,
                      "net_margin": _div(n, r)})

    return {
        "fiscal_year_end": d0.strftime("%Y-%m-%d"),
        "is_bank": is_bank,
        "overall_score": overall, "rating": _label(overall),
        "coverage_pct": covered, "metrics": metrics, "context": context,
        "strengths": strengths, "risks": risks, "trend": trend,
        "methodology": {
            "summary": ("Each scored metric maps to 0-100 by linear interpolation between fixed thresholds. "
                        "The overall score is the weighted average of available metrics; weights are "
                        f"renormalised, and no score is shown below {MIN_COVERAGE}% coverage. "
                        "Strong 70+, Moderate 50-69, Weak below 50."),
            "metrics": [{"label": METRIC_INFO[k][0], "weight": SCORING[k][0],
                         "points": [[x, y] for x, y in (BANK_ROA if k == "roa" and is_bank else SCORING[k][1])]}
                        for k in METRIC_INFO],
            "limitations": ["Annual statements only; the latest fiscal year may be several months old.",
                            "Thresholds are general rules of thumb, not sector-calibrated (banks excepted for ROA).",
                            "Provider data may be missing, restated or classified differently across companies."],
        },
    }


class FinancialAnalysisService:
    def __init__(self, provider: FundamentalsProvider, ttl=12 * 3600, error_ttl=60):
        self.provider, self.ttl, self.error_ttl = provider, ttl, error_ttl
        self._cache, self._lock = {}, threading.Lock()

    def analyze(self, symbol: str, sector: str = "") -> dict:
        key = (symbol, sector)
        with self._lock:
            hit = self._cache.get(key)
            if hit and time.time() - hit[0] < (self.ttl if "error" not in hit[1] else self.error_ttl):
                return hit[1]
        fetched = datetime.now(timezone.utc).isoformat()
        try:
            out = analyze_fundamentals(self.provider.get_fundamentals(symbol), sector)
            out.update(symbol=symbol, fetched_at=fetched, source=self.provider.name, disclaimer=DISCLAIMER)
        except FundamentalsError as exc:
            out = {"symbol": symbol, "error": str(exc), "fetched_at": fetched}
        with self._lock:
            self._cache[key] = (time.time(), out)
        return out


financial_service = FinancialAnalysisService(YFinanceFundamentals())