import pytest
from app.services.news_service import parse_rss, matches_company, NewsService, NewsError
from app.services.sentiment_service import aggregate, SentimentService

RSS = """<rss><channel>
<item><title>TCS wins big deal - Economic Times</title><link>https://x.test/1</link>
<pubDate>Mon, 05 Oct 2026 08:00:00 GMT</pubDate><source>Economic Times</source></item>
<item><title>TCS wins big deal - Economic Times</title><link>https://x.test/dup</link>
<source>Economic Times</source></item>
<item><title>Market rally continues - Mint</title><link>https://x.test/2</link>
<pubDate>Tue, 06 Oct 2026 08:00:00 GMT</pubDate><source>Mint</source></item>
</channel></rss>"""


def test_parse_rss_strips_source_and_dedups():
    items = parse_rss(RSS)
    assert [i["title"] for i in items] == ["TCS wins big deal", "Market rally continues"]
    assert items[0]["published"].startswith("2026-10-05")


def test_bad_xml_raises():
    with pytest.raises(NewsError):
        parse_rss("<rss><item>")


def test_company_matching_uses_whole_words():
    assert matches_company("TCS wins deal", ["TCS"])
    assert not matches_company("ITCHY market sentiment", ["ITC"])
    assert matches_company("ITC hotels demerger", ["ITC"])


class FakeNews:
    def __init__(self, items): self.items = items
    def get(self, s):
        return {"items": self.items, "fetched_at": "2026-10-09T00:00:00+00:00", "source": "fake"}


class FakeClf:
    def classify(self, texts):
        out = []
        for t in texts:
            s = 0.9 if "win" in t else -0.8 if "fall" in t else 0.0
            lab = "positive" if s > 0 else "negative" if s < 0 else "neutral"
            out.append({"label": lab, "score": s, "positive": max(s, 0), "negative": max(-s, 0), "neutral": 0.1})
        return out


def test_aggregate_and_service():
    items = [{"title": "TCS wins A", "link": "", "source": "s", "published": "2026-10-01T00:00:00+00:00"},
             {"title": "TCS shares fall", "link": "", "source": "s", "published": "2026-10-02T00:00:00+00:00"},
             {"title": "TCS update", "link": "", "source": "s", "published": "2026-10-03T00:00:00+00:00"}]
    out = SentimentService(FakeNews(items), FakeClf()).analyze("TCS.NS")
    s = out["summary"]
    assert s["count"] == 3 and s["counts"] == {"positive": 1, "negative": 1, "neutral": 1}
    assert s["low_sample"] and s["trend"] is None          # fewer than 8 headlines
    assert abs(sum(s["proportions"].values()) - 1) < 1e-9


def test_no_headlines_is_reported_not_invented():
    out = SentimentService(FakeNews([]), FakeClf()).analyze("TCS.NS")
    assert out["headlines"] == [] and "No recent headlines" in out["message"]


def test_news_failure_is_an_error_dict():
    class Boom:
        name = "x"
        def fetch(self, s): raise NewsError("offline")
    out = SentimentService(NewsService(Boom()), FakeClf()).analyze("TCS.NS")
    assert "error" in out