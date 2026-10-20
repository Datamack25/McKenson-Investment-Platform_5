import pytest

from utils.sentiment import score_title, relevant_classes, class_sentiment, theme_sentiment


@pytest.mark.parametrize("title,sign", [
    ("Wall Street termine en forte hausse, le Nasdaq bat un record", 1),
    ("L'inflation accélère en zone euro, la BCE sous pression", -1),
    ("Le chômage recule fortement en France", 1),
    ("Oil prices surge after missile strikes in the Middle East", -1),
    ("US CPI falls more than expected, Treasury yields drop", 1),
    ("No recession in sight as US economy beats expectations", 1),
    ("Bitcoin plunges 10% amid crypto sell-off", -1),
    ("Cessez-le-feu : accord de paix signé entre les deux pays", 1),
    ("Les taux d'intérêt grimpent, les obligations chutent", -1),
])
def test_tone(title, sign):
    assert score_title(title)["score"] * sign > 0


def test_relevance():
    assert "Crypto" in relevant_classes("Bitcoin hits new high")
    assert "Or" in relevant_classes("Le prix de l'or au plus haut")
    assert "Or" not in relevant_classes("Or, les marchés hésitent")   # « or » conjonction


def test_class_sentiment_aggregation():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    items = [dict(title="Bitcoin plunges amid crypto sell-off", date=now),
             dict(title="Wall Street rallies to record", date=now)]
    th = {"x": dict(sentiment=theme_sentiment(items))}
    cs = class_sentiment(th)
    assert cs["Crypto"]["score"] < 0 and cs["Actions US"]["score"] > 0
