"""FinBERT headline sentiment. The model is loaded lazily and results are cached per headline."""
import logging
import os
import threading
from collections import defaultdict
from datetime import datetime, timezone

from app.services.news_service import news_service

os.environ.setdefault("USE_TF", "0")             # avoid the TensorFlow/Keras 3 clash in transformers
os.environ.setdefault("TRANSFORMERS_NO_TF", "1")

log = logging.getLogger(__name__)
MODEL_NAME = "ProsusAI/finbert"
MAX_HEADLINES = 30
DISCLAIMER = ("Headline sentiment describes the tone of recent news. It is not a price forecast "
              "and not investment advice.")


class SentimentModelError(Exception):
    pass


class FinBERTClassifier:
    def __init__(self):
        self._pipe, self._lock, self._cache = None, threading.Lock(), {}

    def _load(self):
        if self._pipe is None:
            try:
                from transformers import pipeline
                self._pipe = pipeline("text-classification", model=MODEL_NAME, top_k=None, truncation=True)
            except Exception as exc:
                log.exception("Could not load FinBERT")
                raise SentimentModelError(
                    "FinBERT could not be loaded. Run 'flask warm-finbert' once with internet access "
                    f"(needs transformers and torch). Details: {exc}")

    def classify(self, texts: list) -> list:
        with self._lock:
            todo = [t for t in dict.fromkeys(texts) if t not in self._cache]
            if todo:
                self._load()
                outs = self._pipe(todo, batch_size=8)
                for t, scores in zip(todo, outs):
                    p = {s["label"].lower(): float(s["score"]) for s in scores}
                    self._cache[t] = {"positive": p.get("positive", 0.0), "negative": p.get("negative", 0.0),
                                      "neutral": p.get("neutral", 0.0)}
            result = []
            for t in texts:
                p = self._cache[t]
                result.append({**p, "label": max(p, key=p.get), "score": p["positive"] - p["negative"]})
            return result


def aggregate(items: list) -> dict:
    """items already carry label and score. Returns proportions, overall label and an optional trend."""
    n = len(items)
    if n == 0:
        return {"count": 0}
    counts = {k: sum(1 for i in items if i["label"] == k) for k in ("positive", "negative", "neutral")}
    mean = sum(i["score"] for i in items) / n
    overall = "Positive" if mean > 0.15 else "Negative" if mean < -0.15 else "Neutral / mixed"
    by_day = defaultdict(list)
    for i in items:
        if i.get("published"):
            by_day[i["published"][:10]].append(i["score"])
    trend, trend_note = None, None
    if n >= 8 and len(by_day) >= 3:
        trend = [{"date": d, "mean_score": sum(v) / len(v), "count": len(v)} for d, v in sorted(by_day.items())]
    else:
        trend_note = "Not enough dated headlines (need at least 8 headlines across 3 days) for a trend."
    return {
        "count": n, "counts": counts,
        "proportions": {k: v / n for k, v in counts.items()},
        "mean_score": mean, "overall": overall,
        "low_sample": n < 10, "trend": trend, "trend_note": trend_note,
    }


class SentimentService:
    def __init__(self, news, classifier):
        self.news, self.classifier = news, classifier

    def analyze(self, symbol: str) -> dict:
        res = self.news.get(symbol)
        if res.get("items") is None:
            return {"symbol": symbol, "error": res["error"], "kind": "news"}
        items = sorted(res["items"], key=lambda i: i["published"] or "", reverse=True)[:MAX_HEADLINES]
        base = {"symbol": symbol, "fetched_at": res["fetched_at"], "source": res["source"],
                "model": MODEL_NAME, "disclaimer": DISCLAIMER}
        if not items:
            return {**base, "headlines": [], "summary": {"count": 0},
                    "message": "No recent headlines mentioning this company were found."}
        scored = self.classifier.classify([i["title"] for i in items])
        headlines = [{**i, **{k: s[k] for k in ("label", "score", "positive", "negative", "neutral")}}
                     for i, s in zip(items, scored)]
        return {**base, "headlines": headlines, "summary": aggregate(headlines)}


sentiment_service = SentimentService(news_service, FinBERTClassifier())