# utils/fx.py  —  MAM v5.8 · Conversion des devises vers la devise du portefeuille (USD)
"""
Les portefeuilles MIP sont tenus en dollars (USD). Un titre coté dans une autre devise
(EUR, GBP, CHF, JPY, HKD, KRW, INR…) doit être converti au taux de change du marché :

* à l'achat et à la vente (cours d'exécution en USD) ;
* pour la valorisation quotidienne (taux du jour) ;
* pour l'historique (taux historiques, jour par jour).

Particularité : la Bourse de Londres cote la plupart des actions en PENCE (GBp) —
1 GBp = 0,01 GBP. Les ETF cotés à Londres en USD ou en EUR sont traités dans leur devise.

Taux : paires Yahoo Finance « XXXUSD=X » (réelles, différées). En cas d'indisponibilité,
taux de secours signalés comme tels (source « repli »).
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

BASE = "USD"
# Taux de secours (USD pour 1 unité) — utilisés seulement si Yahoo Finance ne répond pas
FALLBACK = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CHF": 1.13, "JPY": 0.0067, "HKD": 0.128, "KRW": 0.00072,
            "INR": 0.0119, "SEK": 0.095, "DKK": 0.145, "NOK": 0.093, "CAD": 0.73, "AUD": 0.66, "SGD": 0.74,
            "CNY": 0.138, "BRL": 0.18, "MXN": 0.055, "ZAR": 0.055, "TWD": 0.031}
_SUFFIX = {".PA": "EUR", ".DE": "EUR", ".AS": "EUR", ".MI": "EUR", ".MC": "EUR", ".BR": "EUR", ".LS": "EUR",
           ".IR": "EUR", ".VI": "EUR", ".HE": "EUR", ".SW": "CHF", ".T": "JPY", ".HK": "HKD", ".KS": "KRW",
           ".NS": "INR", ".ST": "SEK", ".CO": "DKK", ".OL": "NOK", ".TO": "CAD", ".AX": "AUD", ".SI": "SGD",
           ".TW": "TWD", ".SS": "CNY", ".SZ": "CNY", ".SA": "BRL", ".MX": "MXN", ".JO": "ZAR"}
_OVERRIDE: dict[str, float] | None = None      # tests : taux imposés


def set_rates(rates: dict[str, float] | None):
    """Impose des taux (tests hors réseau). None rétablit les taux de marché."""
    global _OVERRIDE
    _OVERRIDE = dict(rates) if rates else None


@lru_cache(maxsize=1)
def _csv_currency() -> dict[str, str]:
    try:
        from utils.data import load_assets
        df = load_assets()
        if "currency" in df.columns:
            return {str(t).upper(): str(c).strip() for t, c in zip(df["ticker"], df["currency"]) if str(c).strip()}
    except Exception:
        pass
    return {}


def quote_currency(ticker: str) -> str:
    """Devise de cotation Yahoo Finance d'un titre (« GBp » pour les actions de Londres en pence).
    Les indices (^…), devises (=X), contrats à terme (=F) et crypto en USD sont en USD / points."""
    t = str(ticker or "").upper().strip()
    if t.startswith("^") or t.endswith(("=X", "=F", "-USD")) or t == "CASH":
        return BASE
    if t.endswith("-EUR"):
        return "EUR"
    c = _csv_currency().get(t)
    if not c:
        c = next((v for s, v in _SUFFIX.items() if t.endswith(s)), None)
        if not c:
            c = "GBp" if t.endswith(".L") else BASE
    if c == "GBP" and t.endswith(".L"):
        return "GBp"                     # actions de Londres cotées en pence
    return c


def _unit(ccy: str) -> tuple[str, float]:
    return ("GBP", 0.01) if ccy == "GBp" else (ccy, 1.0)


def _cache(ttl: int):
    try:
        import streamlit as st
        return st.cache_data(ttl=ttl, show_spinner=False)
    except Exception:  # pragma: no cover
        return lru_cache(maxsize=32)


@_cache(600)
def _spot_rates(ccys: tuple) -> dict[str, tuple[float, str]]:
    out = {}
    need = [c for c in ccys if c != BASE]
    if need:
        try:
            import yfinance as yf
            pairs = [f"{c}USD=X" for c in need]
            raw = yf.download(pairs, period="5d", auto_adjust=False, progress=False, threads=True)
            closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
            if list(closes.columns) == ["Close"]:
                closes.columns = pairs[:1]
            for c, p in zip(need, pairs):
                if p in closes.columns and closes[p].dropna().size:
                    v = float(closes[p].dropna().iloc[-1])
                    if v > 0:
                        out[c] = (v, "live")
        except Exception:
            pass
    for c in ccys:
        if c not in out:
            out[c] = (1.0, "live") if c == BASE else (FALLBACK.get(c, 1.0), "repli")
    return out


def rates(ccys) -> dict[str, float]:
    """USD pour 1 unité de chaque devise de cotation (GBp inclus)."""
    ccys = list(dict.fromkeys(ccys))
    if _OVERRIDE is not None:
        return {c: _OVERRIDE.get(_unit(c)[0], FALLBACK.get(_unit(c)[0], 1.0)) * _unit(c)[1] for c in ccys}
    base = tuple(sorted({_unit(c)[0] for c in ccys}))
    sp = _spot_rates(base)
    return {c: sp[_unit(c)[0]][0] * _unit(c)[1] for c in ccys}


def rate_source(ccys) -> str:
    if _OVERRIDE is not None:
        return "live"
    base = tuple(sorted({_unit(c)[0] for c in ccys} - {BASE}))
    if not base:
        return "live"
    return "live" if all(s == "live" for _, s in _spot_rates(base).values()) else "repli"


def to_usd(ticker: str, price: float) -> float:
    c = quote_currency(ticker)
    return float(price) if c == BASE else float(price) * rates([c])[c]


def usd_factors(tickers) -> dict[str, float]:
    """{ticker: facteur de conversion vers l'USD} (1 pour les titres en USD)."""
    cc = {t: quote_currency(t) for t in tickers}
    r = rates(set(cc.values()))
    return {t: r[c] for t, c in cc.items()}


@_cache(3600)
def _history(ccys: tuple, start: str) -> pd.DataFrame:
    if _OVERRIDE is not None or not ccys:
        return pd.DataFrame()
    try:
        import yfinance as yf
        pairs = [f"{c}USD=X" for c in ccys]
        raw = yf.download(pairs, start=start, auto_adjust=False, progress=False, threads=True)
        closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if list(closes.columns) == ["Close"]:
            closes.columns = pairs[:1]
        if closes.index.tz is not None:
            closes.index = closes.index.tz_localize(None)
        closes = closes.rename(columns={p: c for c, p in zip(ccys, pairs)})
        return closes.dropna(how="all").ffill()
    except Exception:
        return pd.DataFrame()


def convert_history(px: pd.DataFrame, start: str | None = None) -> pd.DataFrame:
    """Convertit en USD un tableau de cours (colonnes = tickers) avec les taux HISTORIQUES du jour.
    Taux manquant un jour : dernier taux connu, sinon taux du jour (ou de secours)."""
    if px is None or px.empty:
        return px
    cc = {t: quote_currency(t) for t in px.columns}
    foreign = sorted({_unit(c)[0] for c in cc.values()} - {BASE})
    if not foreign:
        return px
    start = start or px.index.min().strftime("%Y-%m-%d")
    hist = _history(tuple(foreign), start)
    spot = rates(set(cc.values()))
    out = px.copy()
    for t, c in cc.items():
        if c == BASE:
            continue
        b, mult = _unit(c)
        if not hist.empty and b in hist.columns:
            fx = hist[b].reindex(out.index.union(hist.index)).ffill().reindex(out.index)
            fx = fx.fillna(spot[c] / mult)
            out[t] = out[t] * fx * mult
        else:
            out[t] = out[t] * spot[c]
    return out
