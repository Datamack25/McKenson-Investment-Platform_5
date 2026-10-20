# utils/performance.py  —  MAM v5.2 · Performance des portefeuilles vs marché
"""
Reconstitue la valeur quotidienne (NAV) de chaque portefeuille à partir de ses
transactions et des cours de clôture historiques, puis calcule les indicateurs
qu'utilise un gérant : performance, volatilité, perte maximale, Sharpe, bêta,
écart de suivi, ratio d'information, surperformance vs un indice de référence.

Hypothèses (affichées à l'utilisateur) :
* les transactions au comptant (achats / ventes) sont rejouées ; depuis la v5.4,
  les options sont incluses : prime payée ou encaissée à la date d'ouverture, puis
  valeur Black-Scholes quotidienne (volatilité d'entrée, échéance qui se rapproche),
  valeur intrinsèque figée à l'échéance ;
* un cours manquant un jour donné est remplacé par le dernier connu, ou par le
  prix de la transaction avant la première cotation ;
* repli : si les cours historiques sont indisponibles, les snapshots quotidiens
  enregistrés en base (mam_snapshots) sont utilisés.
"""
from __future__ import annotations

from datetime import datetime

import math

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


OPT_RATE = 0.0425           # taux sans risque utilisé pour valoriser les options (comme le Dashboard)


def _option_positions(port: dict) -> list[dict]:
    out = []
    for o in port.get("options", []) or []:
        try:
            d = pd.to_datetime(o.get("date"))
            if pd.isna(d):
                continue
            n, mult = float(o.get("n_contracts", 0)), float(o.get("contract_mult", 100))
            out.append(dict(date=d, ticker=o["ticker"], type=str(o.get("type", "call")).lower(),
                            sign=1.0 if str(o.get("action", "BUY")).upper() == "BUY" else -1.0,
                            K=float(o["strike"]), mat=float(o.get("maturity_days", 30)),
                            sigma=float(o.get("sigma", 20)) / 100, units=n * mult,
                            premium=float(o.get("premium", 0.0)), spot0=float(o.get("spot_at_entry", 0) or 0)))
        except Exception:
            continue
    return out


def _option_value(o: dict, d: pd.Timestamp, spot: float) -> float:
    """Valeur (signée) d'une position d'option à la date d : Black-Scholes avec la volatilité
    d'entrée ; à l'échéance et après, valeur intrinsèque figée (règlement en espèces)."""
    from utils.options import bs_price
    elapsed = (d.normalize() - o["date"].normalize()).days
    T = (o["mat"] - elapsed) / 365.0
    if T <= 0:
        intrinsic = max(spot - o["K"], 0.0) if o["type"] == "call" else max(o["K"] - spot, 0.0)
        return o["sign"] * intrinsic * o["units"]
    return o["sign"] * float(bs_price(spot, o["K"], T, OPT_RATE, o["sigma"], o["type"])) * o["units"]


def nav_detail(port: dict, prices: pd.DataFrame | None = None, include_options: bool = True) -> pd.DataFrame:
    """Valeur quotidienne de chaque ligne au comptant, des options (« OPTIONS ») et du cash (« CASH »).
    La NAV est la somme des colonnes. DataFrame vide si aucune transaction ni option."""
    tr = _spot_trades(port)
    opts = _option_positions(port) if include_options else []
    if tr.empty and not opts:
        return pd.DataFrame()
    dates = ([tr["date"].min()] if not tr.empty else []) + [o["date"] for o in opts]
    start = min(dates).normalize()
    tickers = tuple(sorted(set(tr["ticker"].unique() if not tr.empty else []) | {o["ticker"] for o in opts}))
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
    spot_tk = sorted(tr["ticker"].unique()) if not tr.empty else []
    qty = {t: 0.0 for t in spot_tk}
    last_px: dict[str, float] = {}
    for o in opts:
        if o["spot0"] > 0:
            last_px.setdefault(o["ticker"], o["spot0"])
    rows = []
    trades = tr.to_dict("records") if not tr.empty else []
    opts = sorted(opts, key=lambda o: o["date"])
    i = j = 0

    def px_at(tk, d):
        if prices is not None and tk in getattr(prices, "columns", []):
            s_ = prices[tk].loc[:d].dropna()
            if len(s_):
                last_px[tk] = float(s_.iloc[-1])
        return last_px.get(tk, 0.0)

    for d in days:
        while i < len(trades) and trades[i]["date"].normalize() <= d:
            t = trades[i]
            sgn = 1 if t["action"] == "BUY" else -1
            qty[t["ticker"]] += sgn * t["qty"]
            cash -= sgn * t["qty"] * t["price"]
            last_px.setdefault(t["ticker"], t["price"])
            i += 1
        while j < len(opts) and opts[j]["date"].normalize() <= d:
            o = opts[j]
            cash -= o["sign"] * o["premium"] * o["units"]      # prime payée (achat) ou encaissée (vente)
            j += 1
        row = {"CASH": cash}
        for tk in spot_tk:
            q = qty[tk]
            row[tk] = q * px_at(tk, d) if abs(q) > 1e-12 else 0.0
        ov = 0.0
        for o in opts[:j]:
            expiry = o["date"].normalize() + pd.Timedelta(days=int(o["mat"]))
            ov += _option_value(o, d, px_at(o["ticker"], min(d, expiry)) or o["spot0"])
        row["OPTIONS"] = ov
        rows.append(row)
    return pd.DataFrame(rows, index=days)


def reconstruct_nav(port: dict, prices: pd.DataFrame | None = None, include_options: bool = True) -> pd.Series:
    """NAV quotidienne reconstituée (index = dates), options comprises. Série vide si aucune transaction."""
    det = nav_detail(port, prices, include_options)
    if det.empty:
        return pd.Series(dtype=float)
    return det.sum(axis=1).rename(port.get("name", "Portefeuille"))


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


# ══════════════════════════════════════════════════════════════════════════════
#  ALLOCATION STRATÉGIQUE DE RÉFÉRENCE ET ATTRIBUTION DE PERFORMANCE (v5.4)
# ══════════════════════════════════════════════════════════════════════════════
def portfolio_profile_name(port: dict) -> tuple[str, str]:
    """(profil, origine) : politique d'investissement du portefeuille, sinon profil investisseur."""
    try:
        if port.get("ips"):
            from utils.committee import ips_profile
            return ips_profile(port["ips"])[0], "politique d'investissement du portefeuille"
    except Exception:
        pass
    try:
        from utils.compliance import portfolio_profile
        return portfolio_profile(port).get("risque", "Équilibré"), "profil investisseur"
    except Exception:
        return "Équilibré", "profil par défaut"


def strategic_weights(profile: str) -> pd.Series:
    from utils import advisor as A
    return pd.Series(A.PROFILES.get(profile, A.PROFILES["Équilibré"]), index=A.CLASSES)


def _carino(rp: pd.Series, rb: pd.Series) -> pd.Series:
    """Coefficients de lissage de Carino : la somme des effets quotidiens pondérés est égale
    à l'écart de performance géométrique sur la période."""
    Rp, Rb = float((1 + rp).prod() - 1), float((1 + rb).prod() - 1)
    K = (math.log1p(Rp) - math.log1p(Rb)) / (Rp - Rb) if abs(Rp - Rb) > 1e-12 else 1 / (1 + Rp)
    d = rp - rb
    k = pd.Series(np.where(d.abs() > 1e-12, (np.log1p(rp) - np.log1p(rb)) / d.where(d.abs() > 1e-12, 1), 1 / (1 + rp)),
                  index=rp.index)
    return k / K


def attribution(port: dict, prices: pd.DataFrame | None = None, profile: str | None = None) -> dict:
    """Attribution de performance (Brinson-Fachler, lissage de Carino) du portefeuille par classe
    d'actifs, par rapport à son allocation stratégique (proxies du desk, rééquilibrage quotidien)."""
    from utils import advisor as A
    prof, origin = (profile, "choisi") if profile else portfolio_profile_name(port)
    wb = strategic_weights(prof)
    tr = _spot_trades(port)
    opts = _option_positions(port)
    if tr.empty and not opts:
        return dict(ok=False, detail="Aucune transaction : rien à attribuer.")
    start = min(([tr["date"].min()] if not tr.empty else []) + [o["date"] for o in opts]).normalize()
    tickers = set(tr["ticker"].unique()) if not tr.empty else set()
    tickers |= {o["ticker"] for o in opts} | set(A.CLASS_PROXY.values())
    if prices is None:
        prices = price_history(tuple(sorted(tickers)), start.strftime("%Y-%m-%d"))
    if prices is None or prices.empty:
        return dict(ok=False, detail="Cours historiques indisponibles.")
    det = nav_detail(port, prices)
    det = det[det.index.isin(prices.index) | (det.index == det.index[-1])]
    if len(det) < 6:
        return dict(ok=False, detail="Historique trop court (au moins 6 séances).")
    nav = det.sum(axis=1)
    rp = nav.pct_change().dropna()
    px = prices.reindex(det.index).ffill()
    spot_cols = [c for c in det.columns if c not in ("CASH", "OPTIONS")]
    cls_of = {t: (A.classify_ticker(t) or "Actions US") for t in spot_cols}
    prev = det.shift(1).iloc[1:]
    nav_prev = nav.shift(1).iloc[1:]
    r_tk = px[spot_cols].pct_change().iloc[1:].fillna(0.0) if spot_cols else pd.DataFrame(index=prev.index)
    proxies = {c: A.CLASS_PROXY[c] for c in A.CLASSES}
    r_b = pd.DataFrame({c: px[t].pct_change() if t in px.columns else 0.0 for c, t in proxies.items()},
                       index=px.index).iloc[1:].fillna(0.0)
    Rb = (r_b * wb).sum(axis=1)

    w_p = pd.DataFrame(0.0, index=prev.index, columns=A.CLASSES)
    contrib_p = pd.DataFrame(0.0, index=prev.index, columns=A.CLASSES)
    for t in spot_cols:
        c = cls_of[t]
        w_p[c] += prev[t] / nav_prev
        contrib_p[c] += prev[t] / nav_prev * r_tk[t]
    w_p["Liquidités"] += prev["CASH"] / nav_prev             # le cash non investi ne rapporte rien
    w_opt = prev["OPTIONS"] / nav_prev
    spot_total = contrib_p.sum(axis=1)
    resid = rp.reindex(prev.index) - spot_total               # options + effets de négociation
    r_pc = (contrib_p / w_p.where(w_p.abs() > 1e-9)).fillna(r_b)   # classe non détenue : rendement neutre
    alloc = (w_p - wb).mul(1, axis=0) * r_b.sub(Rb, axis=0)
    select = r_pc.sub(r_b).mul(wb, axis=1)
    inter = (w_p - wb) * (r_pc - r_b)
    opt_eff = resid - w_opt * Rb
    k = _carino(rp.reindex(prev.index).fillna(0.0), Rb)
    L = lambda df: (df.mul(k, axis=0)).sum()
    tab = pd.DataFrame({"Allocation": L(alloc), "Sélection": L(select), "Interaction": L(inter)})
    tab["Total"] = tab.sum(axis=1)
    tab["Poids moyen portefeuille"] = w_p.mean()
    tab["Poids stratégique"] = wb
    tab.loc["Options et négociation"] = [float((opt_eff * k).sum()), 0.0, 0.0, float((opt_eff * k).sum()),
                                         float(w_opt.mean()), 0.0]
    Rp_tot, Rb_tot = float((1 + rp).prod() - 1), float((1 + Rb).prod() - 1)
    act = rp.reindex(prev.index) - Rb
    te = float(act.std() * math.sqrt(252)) if len(act) >= 5 else float("nan")
    ir = float(act.mean() * 252 / te) if te and np.isfinite(te) and te > 0 else float("nan")
    bench_nav = (1 + Rb).cumprod() * float(nav.iloc[0])
    bench_nav = pd.concat([pd.Series([float(nav.iloc[0])], index=[nav.index[0]]), bench_nav])
    return dict(ok=True, profil=prof, origine=origin, poids_strategiques=wb, effets=tab,
                perf_portefeuille=Rp_tot, perf_strategique=Rb_tot, ecart=Rp_tot - Rb_tot,
                ecart_explique=float(tab["Total"].sum()), tracking_error=te, ratio_information=ir,
                nav=nav, nav_strategique=bench_nav, jours=len(rp),
                periode=(str(nav.index[0].date()), str(nav.index[-1].date())))
