# utils/performance.py  —  MAM v5.2 · Performance des portefeuilles vs marché
"""
Reconstitue la valeur quotidienne (NAV) de chaque portefeuille à partir de ses
transactions et des cours de clôture historiques, puis calcule les indicateurs
qu'utilise un gérant : performance, volatilité, perte maximale, Sharpe, bêta,
écart de suivi, ratio d'information, surperformance vs un indice de référence.

Hypothèses (affichées à l'utilisateur) :
* seules les transactions au comptant (achats / ventes) sont rejouées ; les
  options sont neutralisées (ni leur prime ni leur valeur ne bougent la NAV
  reconstituée) ;
* un cours manquant un jour donné est remplacé par le dernier connu, ou par le
  prix de la transaction avant la première cotation ;
* repli : si les cours historiques sont indisponibles, les snapshots quotidiens
  enregistrés en base (mam_snapshots) sont utilisés.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

BENCHMARKS = {
    "S&P 500": "SPY",
    "MSCI World": "URTH",
    "Nasdaq 100": "QQQ",
    "CAC 40": "^FCHI",
    "60 % actions / 40 % obligations": "60/40",
}
RF = 0.03  # taux sans risque annuel retenu pour le ratio de Sharpe


@st.cache_data(ttl=3600, show_spinner=False)
def price_history(tickers: tuple, start: str) -> pd.DataFrame:
    """Clôtures quotidiennes depuis `start` (ffill). DataFrame vide si indisponible."""
    if not tickers:
        return pd.DataFrame()
    try:
        import yfinance as yf
        raw = yf.download(list(tickers), start=start, interval="1d", auto_adjust=True,
                          progress=False, threads=True)
        px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
        if isinstance(px, pd.Series):
            px = px.to_frame(tickers[0])
        if list(px.columns) == ["Close"]:
            px.columns = [tickers[0]]
        if px.index.tz is not None:
            px.index = px.index.tz_localize(None)
        return px.dropna(how="all").ffill()
    except Exception:
        return pd.DataFrame()


def _spot_trades(port: dict) -> pd.DataFrame:
    rows = []
    for t in port.get("trades", []) or []:
        a = str(t.get("action", "")).upper()
        if a not in ("BUY", "SELL"):
            continue
        try:
            rows.append(dict(date=pd.to_datetime(t.get("date")), ticker=t["ticker"], action=a,
                             qty=float(t.get("qty", 0)), price=float(t.get("price", 0))))
        except Exception:
            continue
    df = pd.DataFrame(rows)
    return df.dropna(subset=["date"]).sort_values("date") if not df.empty else df


def reconstruct_nav(port: dict, prices: pd.DataFrame | None = None) -> pd.Series:
    """NAV quotidienne reconstituée (index = dates). Série vide si aucune transaction."""
    tr = _spot_trades(port)
    if tr.empty:
        return pd.Series(dtype=float)
    start = tr["date"].min().normalize()
    tickers = tuple(sorted(tr["ticker"].unique()))
    if prices is None:
        prices = price_history(tickers, start.strftime("%Y-%m-%d"))
    end = pd.Timestamp(datetime.now().date())
    days = pd.bdate_range(start, end)
    if prices is not None and not prices.empty:
        days = days.union(prices.index[prices.index >= start])
    days = days[days <= end]
    if len(days) == 0:
        days = pd.DatetimeIndex([start])

    cash = float(port.get("initial_cash", 1_000_000.0))
    qty = {t: 0.0 for t in tickers}
    last_px = {}
    nav = []
    trades = tr.to_dict("records")
    i = 0
    for d in days:
        while i < len(trades) and trades[i]["date"].normalize() <= d:
            t = trades[i]
            sgn = 1 if t["action"] == "BUY" else -1
            qty[t["ticker"]] += sgn * t["qty"]
            cash -= sgn * t["qty"] * t["price"]
            last_px.setdefault(t["ticker"], t["price"])
            i += 1
        val = cash
        for tk, q in qty.items():
            if abs(q) < 1e-12:
                continue
            p = None
            if prices is not None and tk in getattr(prices, "columns", []):
                s = prices[tk].loc[:d].dropna()
                if len(s):
                    p = float(s.iloc[-1])
            if p is None:
                p = last_px.get(tk, 0.0)
            last_px[tk] = p
            val += q * p
        nav.append(val)
    return pd.Series(nav, index=days, name=port.get("name", "Portefeuille"))


def snapshots_nav(port: dict) -> pd.Series:
    """Repli : NAV quotidienne enregistrée en base (snapshots automatiques)."""
    try:
        from utils.db import get_snapshots, is_db_available
        if not is_db_available() or not port.get("id"):
            return pd.Series(dtype=float)
        rows = get_snapshots(port["id"], 3650)
        if not rows:
            return pd.Series(dtype=float)
        df = pd.DataFrame(rows)
        return pd.Series(df["nav"].astype(float).values, index=pd.to_datetime(df["snapshot_date"]),
                         name=port.get("name", "Portefeuille"))
    except Exception:
        return pd.Series(dtype=float)


def portfolio_series(port: dict) -> tuple[pd.Series, str]:
    """(NAV quotidienne, source) — reconstitution par les transactions, sinon snapshots."""
    s = reconstruct_nav(port)
    if len(s) >= 2:
        return s, "transactions + cours historiques"
    s2 = snapshots_nav(port)
    if len(s2) >= 2:
        return s2, "snapshots quotidiens enregistrés"
    return s, "historique insuffisant"


def benchmark_series(name: str, start: pd.Timestamp) -> pd.Series:
    code = BENCHMARKS.get(name, "SPY")
    st_ = start.strftime("%Y-%m-%d")
    if code == "60/40":
        px = price_history(("SPY", "AGG"), st_)
        if px.empty or not {"SPY", "AGG"} <= set(px.columns):
            return pd.Series(dtype=float)
        r = 0.6 * px["SPY"].pct_change() + 0.4 * px["AGG"].pct_change()
        return (1 + r.fillna(0)).cumprod().rename(name)
    px = price_history((code,), st_)
    if px.empty or code not in px.columns:
        return pd.Series(dtype=float)
    return px[code].dropna().rename(name)


def metrics(nav: pd.Series, bench: pd.Series | None = None) -> dict:
    """Indicateurs de gestion. Les ratios annualisés exigent au moins 5 points."""
    out = {"Performance": np.nan, "Volatilité (ann.)": np.nan, "Perte max": np.nan, "Sharpe": np.nan,
           "Bêta": np.nan, "Perf. indice": np.nan, "Surperformance": np.nan,
           "Écart de suivi": np.nan, "Ratio d'information": np.nan, "Jours": 0}
    nav = nav.dropna()
    if len(nav) < 2 or nav.iloc[0] <= 0:
        return out
    r = nav.pct_change().dropna()
    out["Jours"] = len(nav)
    out["Performance"] = float(nav.iloc[-1] / nav.iloc[0] - 1)
    out["Perte max"] = float((nav / nav.cummax() - 1).min())
    if len(r) >= 5 and r.std() > 0:
        vol = float(r.std() * np.sqrt(252))
        out["Volatilité (ann.)"] = vol
        ann = float((1 + r.mean()) ** 252 - 1)
        out["Sharpe"] = (ann - RF) / vol if vol else np.nan
    if bench is not None and len(bench.dropna()) >= 2:
        b = bench.reindex(nav.index).ffill().bfill()
        out["Perf. indice"] = float(b.iloc[-1] / b.iloc[0] - 1)
        out["Surperformance"] = out["Performance"] - out["Perf. indice"]
        rb = b.pct_change().dropna()
        j = pd.concat([r, rb], axis=1, join="inner").dropna()
        if len(j) >= 5 and j.iloc[:, 1].var() > 0:
            out["Bêta"] = float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var())
            te = float((j.iloc[:, 0] - j.iloc[:, 1]).std() * np.sqrt(252))
            out["Écart de suivi"] = te
            if te > 0:
                act = float((j.iloc[:, 0] - j.iloc[:, 1]).mean() * 252)
                out["Ratio d'information"] = act / te
    return out


def base100(s: pd.Series) -> pd.Series:
    s = s.dropna()
    return s / s.iloc[0] * 100 if len(s) and s.iloc[0] else s
