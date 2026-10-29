# utils/income.py  —  MAM v5.8 · Revenus du portefeuille : dividendes et intérêts monétaires
"""
Comme chez un teneur de compte, les revenus sont versés en liquidités :

* DIVIDENDES — pour chaque titre détenu à la veille de la date de détachement (ex-date),
  dividende par action Yahoo Finance × quantité détenue, converti en USD au taux du jour,
  net de la retenue à la source NON récupérable (hypothèse : résident fiscal français,
  compte-titres ; l'impôt personnel n'est pas déduit, conformément à GIPS).

* INTÉRÊTS — les liquidités sont rémunérées chaque jour au taux monétaire du marché :
  rendement des bons du Trésor américain à 13 semaines (^IRX), la devise des portefeuilles
  étant l'USD. Base exact/360 (convention monétaire), solde de fin de journée, un vendredi
  rapporte les trois jours du week-end. Si le taux n'est pas disponible, aucun intérêt n'est
  inventé : le calcul reprendra quand la donnée sera disponible.

Les revenus sont inscrits dans le journal des mouvements (utils/ledger.py) à leur date,
y compris pour le passé lors de la première mise à jour (rattrapage).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from utils import ledger as LG

RATE_TICKER = "^IRX"
DAY_COUNT = 360
MIN_AMOUNT = 0.005
# Retenue à la source non récupérable pour un résident fiscal français (conventions fiscales)
WITHHOLDING_DEFAULT = 0.15
WITHHOLDING = {"FR": 0.0, "GB": 0.0, "HK": 0.0, "IE": 0.0, "US": 0.15, "CH": 0.15, "DE": 0.15, "NL": 0.15,
               "IT": 0.15, "ES": 0.15, "BE": 0.15, "JP": 0.10, "KR": 0.15, "IN": 0.15}
_SUFFIX_COUNTRY = {".PA": "FR", ".L": "GB", ".HK": "HK", ".SW": "CH", ".DE": "DE", ".AS": "NL", ".MI": "IT",
                   ".MC": "ES", ".BR": "BE", ".T": "JP", ".KS": "KR", ".NS": "IN", ".IR": "IE"}


def issuer_country(ticker: str) -> str:
    t = str(ticker).upper()
    try:  # ETF UCITS cotés en Europe : fonds irlandais / luxembourgeois, pas de retenue à la distribution
        from utils.sectors import sector_of
        if sector_of(t).startswith(("ETF", "ETC")) and not t.isalpha():
            return "IE"
    except Exception:
        pass
    return next((c for s, c in _SUFFIX_COUNTRY.items() if t.endswith(s)), "US")


def withholding(ticker: str) -> float:
    return WITHHOLDING.get(issuer_country(ticker), WITHHOLDING_DEFAULT)


# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES DE MARCHÉ
# ══════════════════════════════════════════════════════════════════════════════
def _cache(ttl):
    try:
        import streamlit as st
        return st.cache_data(ttl=ttl, show_spinner=False)
    except Exception:  # pragma: no cover
        from functools import lru_cache
        return lru_cache(maxsize=64)


@_cache(6 * 3600)
def money_market_rates(start: str) -> pd.Series:
    """Taux monétaire quotidien (fraction annuelle, ex. 0.042), depuis `start`. Vide si indisponible."""
    try:
        from utils.performance import _download
        px = _download((RATE_TICKER,), start, False)
        if px is None or px.empty or RATE_TICKER not in px:
            return pd.Series(dtype=float)
        s = px[RATE_TICKER].dropna() / 100.0
        return s[(s >= 0) & (s < 0.25)]
    except Exception:
        return pd.Series(dtype=float)


@_cache(12 * 3600)
def dividends_of(ticker: str) -> pd.Series:
    """Dividendes par action (devise de cotation), index = date de détachement."""
    try:
        import yfinance as yf
        d = yf.Ticker(ticker).dividends
        if d is None or len(d) == 0:
            return pd.Series(dtype=float)
        d.index = pd.to_datetime(d.index)
        if d.index.tz is not None:
            d.index = d.index.tz_localize(None)
        return d.astype(float)
    except Exception:
        return pd.Series(dtype=float)


# ══════════════════════════════════════════════════════════════════════════════
#  CALCULS
# ══════════════════════════════════════════════════════════════════════════════
def _state(port: dict) -> dict:
    return port.setdefault("revenus_maj", {})


def _inception(port: dict) -> pd.Timestamp | None:
    dates = [pd.to_datetime(t.get("date"), errors="coerce") for t in port.get("trades", []) or []]
    dates += [pd.to_datetime(m.get("date"), errors="coerce") for m in port.get("mouvements", []) or []]
    dates += [pd.to_datetime(o.get("date"), errors="coerce") for o in port.get("options", []) or []]
    dates = [d for d in dates if d is not None and not pd.isna(d)]
    if dates:
        return min(dates).normalize()
    c = pd.to_datetime(port.get("created"), errors="coerce")
    return None if c is None or pd.isna(c) else c.normalize()


def qty_on(port: dict, ticker: str, when: pd.Timestamp) -> float:
    """Quantité détenue en fin de journée la veille de `when` (droit au dividende)."""
    q = 0.0
    for t in port.get("trades", []) or []:
        if t.get("ticker") != ticker or str(t.get("action", "")).upper() not in ("BUY", "SELL"):
            continue
        d = pd.to_datetime(t.get("date"), errors="coerce")
        if d is None or pd.isna(d) or d.normalize() >= when.normalize():
            continue
        q += (1 if str(t["action"]).upper() == "BUY" else -1) * float(t.get("qty", 0) or 0)
    return max(q, 0.0)


def accrue_dividends(port: dict, today: date | None = None, fetch=dividends_of) -> list[dict]:
    """Verse les dividendes détachés depuis la dernière mise à jour. Renvoie les mouvements créés."""
    today = pd.Timestamp(today or date.today())
    st_ = _state(port)
    start = pd.to_datetime(st_.get("dividendes")) if st_.get("dividendes") else _inception(port)
    if start is None:
        return []
    tickers = sorted({t.get("ticker") for t in port.get("trades", []) or []
                      if str(t.get("action", "")).upper() in ("BUY", "SELL") and t.get("ticker")})
    done = {(m.get("ticker"), str(m.get("date"))[:10]) for m in port.get("mouvements", []) or []
            if m.get("type") == "dividende"}
    created = []
    from utils.fx import convert_history
    for tk in tickers:
        if tk.endswith(("=F", "=X", "-USD", "-EUR")) or tk.startswith("^"):
            continue
        d = fetch(tk)
        if d is None or d.empty:
            continue
        d = d[(d.index.normalize() > start.normalize()) & (d.index.normalize() <= today.normalize())]
        if d.empty:
            continue
        usd = convert_history(pd.DataFrame({tk: d}), d.index.min().strftime("%Y-%m-%d"))[tk]
        wh = withholding(tk)
        for ex, per_share in usd.items():
            key = (tk, ex.strftime("%Y-%m-%d"))
            if key in done:
                continue
            q = qty_on(port, tk, ex)
            gross = q * float(per_share)
            net = gross * (1 - wh)
            if net < MIN_AMOUNT:
                continue
            created.append(LG.add(port, "dividende", net, date=ex.strftime("%Y-%m-%d") + " 09:00", ticker=tk,
                                  detail=(f"{q:,.4g} titre(s) × {float(per_share):.4f} $ brut"
                                          + (f", retenue à la source {wh:.0%}" if wh else ""))))
    st_["dividendes"] = today.strftime("%Y-%m-%d")
    return created


def cash_path(port: dict, index: pd.DatetimeIndex) -> pd.Series:
    """Solde de liquidités en fin de journée, reconstitué à partir des ordres, primes et mouvements."""
    from utils import performance as PF
    det = PF.nav_detail(port, prices=pd.DataFrame(index=index))
    if det.empty or "CASH" not in det:
        return pd.Series(float(port.get("cash", 0.0)), index=index)
    return det["CASH"].reindex(index.union(det.index)).ffill().reindex(index).fillna(
        float(port.get("initial_cash", port.get("cash", 0.0))))


def accrue_interest(port: dict, today: date | None = None, rates: pd.Series | None = None) -> list[dict]:
    """Intérêts quotidiens sur les liquidités, du dernier jour traité jusqu'à la veille."""
    today = pd.Timestamp(today or date.today()).normalize()
    st_ = _state(port)
    last = pd.to_datetime(st_.get("interets")) if st_.get("interets") else None
    inc = _inception(port)
    if inc is None:
        return []
    first = (last + timedelta(days=1)) if last is not None else inc
    days = pd.bdate_range(first, today - timedelta(days=1))
    if len(days) == 0:
        return []
    if rates is None:
        rates = money_market_rates((first - timedelta(days=10)).strftime("%Y-%m-%d"))
    if rates is None or rates.empty:
        return []                                         # pas de taux réel : on n'invente rien
    r = rates.reindex(rates.index.union(days)).ffill().reindex(days)
    covered = r.dropna()
    if covered.empty:
        return []
    days = covered.index
    base = cash_path(port, pd.bdate_range(inc, days[-1]))
    created, cum = [], 0.0
    nxt = list(days[1:]) + [days[-1] + pd.offsets.BDay(1)]
    for d, n in zip(days, nxt):
        bal = max(0.0, float(base.get(d, 0.0)) + cum)
        span = max(1, (pd.Timestamp(n) - d).days)          # vendredi : 3 jours
        amt = bal * float(covered[d]) * span / DAY_COUNT
        if amt >= MIN_AMOUNT:
            created.append(LG.add(port, "interet", amt, date=d.strftime("%Y-%m-%d") + " 23:59",
                                  detail=f"{bal:,.0f} $ × {float(covered[d]):.2%} × {span}/360".replace(",", " ")))
            cum += amt
    st_["interets"] = days[-1].strftime("%Y-%m-%d")
    st_["taux_monetaire"] = round(float(covered.iloc[-1]), 6)
    return created


def update_portfolio(port: dict, today: date | None = None) -> dict:
    """Dividendes puis intérêts. Renvoie {'dividendes': n, 'interets': montant}."""
    out = dict(dividendes=0, interets=0.0, montant_dividendes=0.0)
    try:
        dv = accrue_dividends(port, today)
        out["dividendes"], out["montant_dividendes"] = len(dv), float(sum(m["montant"] for m in dv))
    except Exception:
        pass
    try:
        it = accrue_interest(port, today)
        out["interets"] = float(sum(m["montant"] for m in it))
    except Exception:
        pass
    return out


def update_state(state: dict, today: date | None = None) -> dict:
    """Met à jour tous les portefeuilles de l'état. Renvoie un bilan agrégé."""
    tot = dict(portefeuilles=0, dividendes=0, montant_dividendes=0.0, interets=0.0)
    for t in (state or {}).get("teams", {}).values():
        for p in (t.get("portfolios") or {}).values():
            if not p.get("name"):
                continue
            r = update_portfolio(p, today)
            if r["dividendes"] or r["interets"]:
                tot["portefeuilles"] += 1
            tot["dividendes"] += r["dividendes"]
            tot["montant_dividendes"] += r["montant_dividendes"]
            tot["interets"] += r["interets"]
    return tot


def income_summary(port: dict, start=None, end=None) -> dict:
    """Revenus et frais de la période (rapports)."""
    df = LG.movements(port)
    if start is not None:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["date"] <= pd.Timestamp(end)]
    fees_trades = 0.0
    for t in port.get("trades", []) or []:
        d = pd.to_datetime(t.get("date"), errors="coerce")
        if d is None or pd.isna(d) or (start is not None and d < pd.Timestamp(start)) or \
                (end is not None and d > pd.Timestamp(end)):
            continue
        fees_trades += float(t.get("frais", 0) or 0)
    g = df.groupby("type")["montant"].sum() if not df.empty else pd.Series(dtype=float)
    return dict(dividendes=float(g.get("dividende", 0.0)), interets=float(g.get("interet", 0.0)),
                frais=float(-g.get("frais", 0.0)) + fees_trades, apports=float(g.get("apport", 0.0)),
                retraits=float(-g.get("retrait", 0.0)),
                taux=(port.get("revenus_maj") or {}).get("taux_monetaire"))
