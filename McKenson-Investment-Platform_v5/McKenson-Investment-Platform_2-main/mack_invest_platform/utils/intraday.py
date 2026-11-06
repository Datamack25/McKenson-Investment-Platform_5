# utils/intraday.py  —  MAM v5.12 · Analyse Marché : évolution et sentiment sur 1 h et 6 h
"""
Prix : barres de 5 minutes (contrat à terme pour un suivi continu hors séance, ex. NQ=F pour le Nasdaq 100,
et l'indice au comptant quand il cote). Pour chaque fenêtre : variation, volatilité réalisée, plus haut /
plus bas, position dans la fourchette, tendance.
Sentiment : actualités (date de publication), Reddit (date de création) et StockTwits (date du message),
notés sur 1 h, 6 h et 24 h ; une bascule (6 h vs 24 h) au-delà du seuil admin est signalée.
Données Yahoo Finance gratuites ≈ 15 min de différé : suffisant pour une plateforme éducative, pas pour
du trading en temps réel.
"""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import numpy as np
import pandas as pd

# Marché analysé → (contrat à terme / série continue, indice au comptant)
INTRADAY_TICKERS = {
    "Nasdaq 100": ("NQ=F", "^NDX"), "S&P 500": ("ES=F", "^GSPC"), "Dow Jones": ("YM=F", "^DJI"),
    "Russell 2000": ("RTY=F", "^RUT"), "CAC 40": ("^FCHI", "^FCHI"), "Euro Stoxx 50": ("^STOXX50E", "^STOXX50E"),
    "DAX": ("^GDAXI", "^GDAXI"), "Nikkei 225": ("NIY=F", "^N225"), "Marchés émergents": ("EEM", "EEM"),
    "Or": ("GC=F", "GC=F"), "Pétrole WTI": ("CL=F", "CL=F"), "Bitcoin": ("BTC-USD", "BTC-USD"),
}
WINDOWS = {"w1": 1, "w6": 6}


def _ts(v) -> pd.Timestamp | None:
    """Horodatage UTC naïf depuis une date RFC 2822, ISO 8601 ou un epoch."""
    if v in (None, "", 0):
        return None
    try:
        if isinstance(v, (int, float)):
            return pd.Timestamp(datetime.fromtimestamp(float(v), tz=timezone.utc)).tz_localize(None)
        s = str(v)
        try:
            d = parsedate_to_datetime(s)
        except (TypeError, ValueError):
            d = pd.Timestamp(s).to_pydatetime()
        d = pd.Timestamp(d)
        return d.tz_convert("UTC").tz_localize(None) if d.tzinfo is not None else d
    except Exception:
        return None


def sentiment_items(news_rows: list[dict] | None, reddit: list[dict] | None, twits: list[dict] | None,
                    market_kw: str | None = None) -> pd.DataFrame:
    """Une ligne par message horodaté : date (UTC), source, score (−1 … +1)."""
    import re
    from utils.market_intel import score_headline
    from utils.sentiment import score_title
    kw = re.compile(market_kw, re.I) if market_kw else None
    rows = []
    for r in news_rows or []:
        t, d = r.get("title", ""), _ts(r.get("pubdate"))
        if t and d is not None and (kw is None or kw.search(t) or r.get("category") == "Marché"):
            rows.append(dict(date=d, source="Actualités", score=float(score_headline(t)["sentiment"]), texte=t))
    for p in reddit or []:
        t, d = p.get("title", ""), _ts(p.get("created"))
        if t and d is not None and (kw is None or kw.search(t)):
            s = (score_title(t)["score"] + score_headline(t)["sentiment"]) / 2
            rows.append(dict(date=d, source="Reddit", score=float(s), texte=t))
    for m in twits or []:
        d = _ts(m.get("created"))
        lab = m.get("sentiment")
        if d is None:
            continue
        s = 1.0 if lab == "Bullish" else -1.0 if lab == "Bearish" else float(score_headline(m.get("body", ""))["sentiment"])
        rows.append(dict(date=d, source="StockTwits", score=s, texte=m.get("body", "")[:140]))
    return pd.DataFrame(rows)


def sentiment_windows(items: pd.DataFrame, now: pd.Timestamp | None = None) -> dict:
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.utcnow().tz_localize(None)
    out = {}
    for lab, h in (("1 h", 1), ("6 h", 6), ("24 h", 24)):
        if items is None or items.empty:
            out[lab] = dict(n=0, score=np.nan)
            continue
        w = items[(items["date"] > now - pd.Timedelta(hours=h)) & (items["date"] <= now + pd.Timedelta(minutes=5))]
        out[lab] = dict(n=int(len(w)), score=float(w["score"].mean()) if len(w) else np.nan,
                        par_source={s: float(g["score"].mean()) for s, g in w.groupby("source")} if len(w) else {})
    return out


def analyse_intraday(market: str, bars: pd.DataFrame | None, news_rows=None, reddit=None, twits=None,
                     market_kw: str | None = None, now: pd.Timestamp | None = None) -> dict:
    """Synthèse 1 h / 6 h : prix (série continue puis indice) + sentiment, alertes."""
    from utils import core_params as CP
    from utils import prices as P
    fut, spot = INTRADAY_TICKERS.get(market, (None, None))
    res = dict(market=market, ticker=None, ok=False, alerts=[])
    s = None
    for t in (fut, spot):
        if bars is not None and t in bars and bars[t].dropna().shape[0] > 10:
            s, res["ticker"] = bars[t].dropna(), t
            break
    if s is not None:
        for k, h in WINDOWS.items():
            res[k] = P.window_stats(s, h)
        res["ok"] = bool(res["w1"].get("ok") or res["w6"].get("ok"))
        res["last_bar"] = s.index[-1]
        res["series"] = s.iloc[-int(12 * 8):]   # ≈ 8 h de barres 5 min pour le graphique
        age_min = ((now or pd.Timestamp.utcnow().tz_localize(None)) - s.index[-1]).total_seconds() / 60
        res["age_min"] = age_min
    items = sentiment_items(news_rows, reddit, twits, market_kw)
    res["sentiment"] = sentiment_windows(items, now)
    res["n_items"] = int(len(items))
    th, sb = CP.get("intra_alerte"), CP.get("senti_bascule")
    w6 = res.get("w6") or {}
    if w6.get("ok") and abs(w6["ret"]) >= th:
        res["alerts"].append(f"{market} : {w6['ret']:+.2%} sur 6 h (seuil {th:.1%}) — mouvement intraday marqué.")
    w1 = res.get("w1") or {}
    if w1.get("ok") and abs(w1["ret"]) >= th / 2:
        res["alerts"].append(f"{market} : {w1['ret']:+.2%} sur la dernière heure.")
    s6, s24 = res["sentiment"]["6 h"]["score"], res["sentiment"]["24 h"]["score"]
    if s6 == s6 and s24 == s24 and abs(s6 - s24) >= sb:
        res["alerts"].append(f"Bascule de sentiment : {s6:+.2f} sur 6 h contre {s24:+.2f} sur 24 h "
                             f"({'amélioration' if s6 > s24 else 'dégradation'}).")
    res["shift"] = (s6 - s24) if (s6 == s6 and s24 == s24) else np.nan
    return res
