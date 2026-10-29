# utils/auto_portfolio.py  —  MAM v5 · Construction automatique de portefeuille
"""
Construit un portefeuille en fonction des conditions de marché :

  profil de risque  ─┐
  régime de marché  ─┼─► bornes par classe d'actifs (allocation stratégique)
  signaux ML        ─┼─► vues Black-Litterman (rendements attendus)
  actualités        ─┘        │
                              ▼
            optimisation sous contraintes (utilité, Sharpe, parité de risque…)
                              │
       backtest walk-forward · stress tests · Monte Carlo · ordres d'exécution
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from utils.market_intel import (ASSET_CLASSES, asset_class, asset_subclass,
                                asset_name, macro_features, news_tilt_for)
from utils.ml_engine import (HORIZON, SAMPLE_EVERY, MarketModel, build_panel,
                             confidence_from_validation, detect_regimes, REGIME_TEXT)
from utils.portfolio import (hrp_weights, optimize_scipy, portfolio_stats,
                             risk_contributions, shrink_cov)

# ══════════════════════════════════════════════════════════════════════════════
#  PROFILS & RÉGIMES
# ══════════════════════════════════════════════════════════════════════════════

PROFILES: dict[str, dict] = {
    "Prudent": {
        "target_vol": 0.06, "lam": 8.0, "max_w": 0.25, "emoji": "🛡️",
        "desc": "Préservation du capital, volatilité cible ≈ 6 %",
        "bounds": {"Actions": (.10, .35), "Obligations": (.35, .75), "Or & métaux": (.03, .15),
                   "Matières premières": (0, .05), "Immobilier": (0, .05), "Crypto": (0, 0),
                   "Monétaire": (0, .40)}},
    "Équilibré": {
        "target_vol": 0.10, "lam": 4.0, "max_w": 0.25, "emoji": "⚖️",
        "desc": "Croissance et protection, volatilité cible ≈ 10 %",
        "bounds": {"Actions": (.30, .65), "Obligations": (.15, .50), "Or & métaux": (.03, .15),
                   "Matières premières": (0, .08), "Immobilier": (0, .08), "Crypto": (0, .03),
                   "Monétaire": (0, .30)}},
    "Dynamique": {
        "target_vol": 0.15, "lam": 2.5, "max_w": 0.30, "emoji": "🚀",
        "desc": "Recherche de performance, volatilité cible ≈ 15 %",
        "bounds": {"Actions": (.50, .85), "Obligations": (0, .30), "Or & métaux": (0, .15),
                   "Matières premières": (0, .10), "Immobilier": (0, .10), "Crypto": (0, .07),
                   "Monétaire": (0, .20)}},
    "Agressif": {
        "target_vol": 0.20, "lam": 1.5, "max_w": 0.35, "emoji": "🔥",
        "desc": "Performance maximale, volatilité cible ≈ 20 %",
        "bounds": {"Actions": (.60, .95), "Obligations": (0, .20), "Or & métaux": (0, .15),
                   "Matières premières": (0, .15), "Immobilier": (0, .10), "Crypto": (0, .15),
                   "Monétaire": (0, .10)}},
}

METHODS = {
    "ia_bl": "IA · Black-Litterman (utilité moyenne-variance)",
    "ia_sharpe": "IA · Black-Litterman (Sharpe maximal)",
    "ia_rp": "IA · Parité de risque inclinée par les signaux",
    "min_vol": "Variance minimale (sans vues)",
    "hrp": "Hierarchical Risk Parity (sans vues)",
}

# multiplicateurs (bas, haut) par classe selon le régime
_REGIME_ADJ = {
    "Crise / Risk-off": {"Actions": (.5, .7), "Obligations": (1.3, 1.25), "Or & métaux": (1.6, 1.3),
                         "Matières premières": (1, .6), "Immobilier": (1, .6), "Crypto": (0, .4),
                         "Monétaire": (1, 1.6)},
    "Ralentissement": {"Actions": (.85, .85), "Obligations": (1.15, 1.1), "Or & métaux": (1.3, 1.15),
                       "Matières premières": (1, .8), "Immobilier": (1, .8), "Crypto": (1, .7),
                       "Monétaire": (1, 1.2)},
    "Reprise": {"Actions": (1.1, 1.0), "Obligations": (.9, 1.0), "Or & métaux": (1, 1),
                "Matières premières": (1, 1.1), "Immobilier": (1, 1.1), "Crypto": (1, 1),
                "Monétaire": (1, .8)},
    "Expansion / Risk-on": {"Actions": (1.15, 1.05), "Obligations": (.8, .9), "Or & métaux": (.7, 1),
                            "Matières premières": (1, 1.1), "Immobilier": (1, 1.1), "Crypto": (1, 1.1),
                            "Monétaire": (1, .6)},
}


def class_bounds_for(profile: str, regime: str, inflation: bool, present: set[str]) -> dict:
    base = PROFILES[profile]["bounds"]
    adj = _REGIME_ADJ.get(regime, {})
    out = {}
    for c in ASSET_CLASSES:
        if c not in present:
            continue
        lo, hi = base.get(c, (0, 1))
        a_lo, a_hi = adj.get(c, (1, 1))
        lo, hi = lo * a_lo, min(1.0, hi * a_hi)
        if inflation and c == "Matières premières":
            hi = min(1.0, hi * 1.5 + .03)
        if inflation and c == "Or & métaux":
            lo = lo + .02
        out[c] = [lo, max(hi, lo)]
    # faisabilité : Σ bas ≤ 1 ≤ Σ haut
    s_lo = sum(v[0] for v in out.values())
    if s_lo > 0.98:
        for c in out:
            out[c][0] *= 0.98 / s_lo
    s_hi = sum(v[1] for v in out.values())
    if s_hi < 1.0 and out:
        for c in out:
            out[c][1] = min(1.0, out[c][1] * 1.02 / s_hi + 1e-6)
    return {c: (float(v[0]), float(v[1])) for c, v in out.items()}


# ══════════════════════════════════════════════════════════════════════════════
#  BLACK-LITTERMAN
# ══════════════════════════════════════════════════════════════════════════════

def prior_weights(tickers: list[str], bounds: dict) -> pd.Series:
    """Allocation stratégique neutre : milieu des bornes de classe, équirépartie dans la classe."""
    mids = {c: (lo + hi) / 2 for c, (lo, hi) in bounds.items()}
    tot = sum(mids.values()) or 1
    w = {}
    for c, m in mids.items():
        members = [t for t in tickers if asset_class(t) == c]
        for t in members:
            w[t] = m / tot / len(members)
    s = pd.Series(w).reindex(tickers).fillna(0)
    return s / s.sum() if s.sum() > 0 else pd.Series(1 / len(tickers), index=tickers)


def ml_views(signals: pd.DataFrame, tickers: list[str], vols: pd.Series,
             news_tilt: pd.Series | None = None, inflation: bool = False,
             regime: str | None = None) -> pd.Series:
    """Rendement annuel attendu par actif selon le ML (+ actualités / régime)."""
    q = {}
    for t in tickers:
        if t not in signals.index:
            q[t] = 0.0
            continue
        s = signals.loc[t]
        p = float(s["p_up"])
        er = float(s["exp_ret_1m"]) * 12
        v = float(vols.get(t, 0.15))
        q[t] = 0.5 * er + 0.5 * (2 * p - 1) * v * 0.6
    q = pd.Series(q)
    if news_tilt is not None:
        q = q + news_tilt.reindex(tickers).fillna(0) * 0.04
    if inflation:
        for t in tickers:
            sub = asset_subclass(t)
            q[t] += {"gov_long": -.03, "ig": -.015, "tips": .02, "commo": .02, "oil": .02, "gold": .015}.get(sub, 0)
    if regime == "Crise / Risk-off":
        for t in tickers:
            q[t] += {"Actions": -.02, "Crypto": -.04, "Obligations": .01, "Or & métaux": .02}.get(asset_class(t), 0)
    return q.clip(-0.5, 0.6)


def black_litterman(cov: pd.DataFrame, w_prior: pd.Series, views: pd.Series,
                    conf: pd.Series, delta: float = 2.5, tau: float = 0.05) -> tuple[pd.Series, pd.Series]:
    """Postérieur Black-Litterman avec vues absolues (P = I) et Ω de He-Litterman."""
    t = list(cov.index)
    S = cov.values
    pi = delta * S @ w_prior.reindex(t).fillna(0).values
    c = conf.reindex(t).fillna(0.05).clip(0.02, 0.9).values
    omega = np.diag(tau * np.diag(S) * (1 - c) / c)
    tS_inv = np.linalg.inv(tau * S)
    om_inv = np.linalg.inv(omega)
    post = np.linalg.solve(tS_inv + om_inv, tS_inv @ pi + om_inv @ views.reindex(t).fillna(0).values)
    return pd.Series(post, index=t), pd.Series(pi, index=t)


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTRUCTION
# ══════════════════════════════════════════════════════════════════════════════

def class_weights(bounds: dict, class_scores: dict | None = None, strength: float = 1.0) -> dict:
    """Poids par classe : milieu des bornes, incliné par le score moyen ML de la classe,
    puis projeté pour respecter bornes et Σ = 1."""
    w = {}
    for c, (lo, hi) in bounds.items():
        sc = (class_scores or {}).get(c, 0.0)
        w[c] = (lo + hi) / 2 + np.clip(sc * 2 * strength, -1, 1) * (hi - lo) / 2
    for _ in range(50):
        w = {c: float(np.clip(v, *bounds[c])) for c, v in w.items()}
        tot = sum(w.values())
        if abs(tot - 1) < 1e-9:
            break
        free = [c for c in w if (tot < 1 and w[c] < bounds[c][1] - 1e-12) or
                (tot > 1 and w[c] > bounds[c][0] + 1e-12)]
        if not free:
            break
        for c in free:
            w[c] += (1 - tot) / len(free)
    tot = sum(w.values())
    return {c: v / tot for c, v in w.items()} if tot > 0 else w


def _two_level(tickers, cov, daily, bounds, signals, inner: str, max_w: float) -> pd.Series:
    """Allocation hiérarchique : classes (bornes du profil/régime) puis actifs dans chaque classe."""
    scores = {}
    if signals is not None:
        for c in bounds:
            mem = [t for t in tickers if asset_class(t) == c and t in signals.index]
            scores[c] = float(np.mean([signals.loc[t, "p_up"] - .5 for t in mem])) if mem else 0.0
    cw = class_weights(bounds, scores if inner == "rp" else None)
    out = {}
    for c, wc in cw.items():
        mem = [t for t in tickers if asset_class(t) == c]
        if not mem or wc <= 0:
            continue
        if len(mem) == 1:
            inner_w = pd.Series(1.0, index=mem)
        elif inner == "hrp":
            inner_w = hrp_weights(daily[mem])
        else:
            budgets = None
            if signals is not None:
                sc = pd.Series({t: float(signals.loc[t, "p_up"]) - .5 if t in signals.index else 0 for t in mem})
                budgets = np.exp(4 * sc)
            inner_w = optimize_scipy(pd.Series(0.0, index=mem), cov.loc[mem, mem], "risk_parity",
                                     max_w=1.0, budgets=budgets)
        for t, v in inner_w.items():
            out[t] = out.get(t, 0) + wc * float(v)
    w = pd.Series(out).reindex(tickers).fillna(0)
    # plafond par ligne : redistribution de l'excédent au sein de la classe puis global
    for _ in range(20):
        over = w > max_w + 1e-9
        if not over.any():
            break
        excess = (w[over] - max_w).sum()
        w[over] = max_w
        room = w[(~over) & (w > 0)]
        if room.empty:
            break
        w[room.index] += excess * room / room.sum()
    return w / w.sum()


def _weights_for(method: str, mu: pd.Series, cov: pd.DataFrame, daily: pd.DataFrame,
                 prof: dict, bounds: dict, signals: pd.DataFrame | None,
                 max_w: float) -> pd.Series:
    tickers = list(mu.index)
    class_of = {t: asset_class(t) for t in tickers}
    if method == "hrp":
        return _two_level(tickers, cov, daily, bounds, None, "hrp", max_w)
    if method == "ia_rp":
        return _two_level(tickers, cov, daily, bounds, signals, "rp", max_w)
    if method == "min_vol":
        return optimize_scipy(mu, cov, "min_vol", max_w=max_w, class_of=class_of, class_bounds=bounds)
    if method == "ia_sharpe":
        return optimize_scipy(mu, cov, "sharpe", max_w=max_w, class_of=class_of,
                              class_bounds=bounds, target_vol=prof["target_vol"] * 1.15)
    return optimize_scipy(mu, cov, "utility", max_w=max_w, lam=prof["lam"],
                          target_vol=prof["target_vol"] * 1.15, class_of=class_of, class_bounds=bounds)


def _clean(w: pd.Series, min_line: float = 0.01) -> pd.Series:
    w = w.where(w >= min_line, 0)
    return (w / w.sum()).sort_values(ascending=False) if w.sum() > 0 else w


def build_allocation(prices: pd.DataFrame, signals: pd.DataFrame, regime: str,
                     inflation: bool, profile: str, method: str,
                     model_conf: float = 0.2, news_view: dict | None = None,
                     max_w: float | None = None, lookback: int = 504) -> dict:
    prof = PROFILES[profile]
    max_w = max_w or prof["max_w"]
    daily = prices.pct_change(fill_method=None).iloc[-lookback:]
    ok = [t for t in daily.columns if daily[t].notna().sum() > 0.8 * len(daily)]
    if profile == "Prudent":
        ok = [t for t in ok if asset_class(t) != "Crypto"]
    daily = daily[ok].dropna()
    cov = shrink_cov(daily)
    present = {asset_class(t) for t in ok}
    bounds = class_bounds_for(profile, regime, inflation, present)
    vols = pd.Series(np.sqrt(np.diag(cov)), index=cov.index)
    w_prior = prior_weights(ok, bounds)
    tilt = news_tilt_for(ok, news_view) if news_view else None
    views = ml_views(signals, ok, vols, tilt, inflation, regime)
    conf = pd.Series({t: model_conf * (0.5 + abs(2 * float(signals.loc[t, "p_up"]) - 1))
                      if t in signals.index else 0.02 for t in ok})
    mu_bl, pi = black_litterman(cov, w_prior, views, conf)
    w = _weights_for(method, mu_bl, cov, daily, prof, bounds, signals, max_w)
    w = _clean(w)
    stats = portfolio_stats(w, mu_bl, cov)
    rc = risk_contributions(w.reindex(cov.index).fillna(0), cov)
    by_class = w.groupby(lambda t: asset_class(t)).sum().sort_values(ascending=False)
    return {"weights": w, "mu_bl": mu_bl, "pi": pi, "views": views, "cov": cov,
            "bounds": bounds, "by_class": by_class, "stats": stats, "risk_contrib": rc,
            "prior": w_prior, "profile": profile, "method": method, "regime": regime,
            "inflation": inflation, "daily": daily, "news_tilt": tilt}


def explain_allocation(alloc: dict, signals: pd.DataFrame, regime_proba: float | None,
                       macro_score: float | None, gpr: float | None) -> list[str]:
    """Justification en langage clair des choix de l'algorithme."""
    out = []
    reg = alloc["regime"]
    pr = f" (probabilité {regime_proba:.0%})" if regime_proba is not None else ""
    out.append(f"Régime de marché détecté : **{reg}**{pr}. {REGIME_TEXT.get(reg, '')}")
    if alloc["inflation"]:
        out.append("Pression inflationniste détectée (taux longs et pétrole en hausse) : "
                   "matières premières, or et obligations indexées favorisés, duration longue pénalisée.")
    if macro_score is not None:
        out.append(f"Score macro composite : **{macro_score:+.0f}/100** "
                   f"({'favorable' if macro_score > 20 else 'défavorable' if macro_score < -20 else 'neutre'} au risque).")
    if gpr is not None:
        out.append(f"Indice de risque géopolitique (actualités) : **{gpr:.0f}/100** — "
                   + ("tensions fortes : couverture or / obligations d'État renforcée." if gpr > 55 else
                      "tensions modérées." if gpr > 25 else "climat géopolitique calme."))
    bc = alloc["by_class"]
    out.append("Allocation par classe : " + ", ".join(f"{c} {v:.0%}" for c, v in bc.items() if v > 0.005) + ".")
    w = alloc["weights"]
    diff = (w - alloc["prior"].reindex(w.index).fillna(0)).sort_values(ascending=False)
    for t in diff.index[:3]:
        if diff[t] <= 0.005 or t not in signals.index:
            continue
        s = signals.loc[t]
        if s["p_up"] >= 0.5:
            drv = ", ".join(s["drivers_up"][:2]) if s["drivers_up"] else "profil rendement/risque"
            out.append(f"Surpondération **{t}** ({asset_name(t)}) : probabilité de hausse "
                       f"{s['p_up']:.0%}, moteurs : {drv}.")
        else:
            out.append(f"**{t}** ({asset_name(t)}) conservé malgré un signal prudent "
                       f"({s['p_up']:.0%}) : faible volatilité / diversification nécessaires "
                       f"pour respecter les bornes du profil.")
    under = [t for t in signals.index if t not in w.index or w.get(t, 0) < 0.005]
    neg = [t for t in under if signals.loc[t, "signal"] in ("SOUS-PONDÉRER", "ALLÉGER")][:4]
    if neg:
        out.append("Écartés ou réduits (signal défavorable) : " + ", ".join(neg) + ".")
    st_ = alloc["stats"]
    out.append(f"Rendement attendu (Black-Litterman) {st_['return']:.1%} / an pour une volatilité "
               f"estimée de {st_['volatility']:.1%} (cible du profil {alloc['profile']} : "
               f"{PROFILES[alloc['profile']]['target_vol']:.0%}).")
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  BACKTEST WALK-FORWARD (aucune donnée future utilisée)
# ══════════════════════════════════════════════════════════════════════════════

def backtest(prices: pd.DataFrame, macro: pd.DataFrame, profile: str, method: str,
             retrain_months: int = 3, cost_bps: float = 10.0, use_ml: bool = True,
             smoothing: float = 0.5, progress=None) -> dict:
    """smoothing : part de l'ancienne allocation conservée à chaque rééquilibrage
    (limite la rotation et les frais ; 0 = rééquilibrage complet)."""
    prices = prices.sort_index()
    rets = prices.pct_change(fill_method=None)
    mf = macro_features(macro, prices)
    panel = build_panel(prices, macro) if use_ml else pd.DataFrame()
    month_ends = prices.groupby(prices.index.to_period("M")).tail(1).index
    pos = {d: i for i, d in enumerate(prices.index)}
    start_i = 504 + HORIZON
    rebal = [d for d in month_ends if pos[d] >= start_i and d < prices.index[-1]]
    if len(rebal) < 6:
        return {"ok": False, "error": "historique trop court pour un backtest (≥ 3 ans requis)"}
    model, last_train, conf = None, None, 0.15
    weights_hist, port_ret, turnover = {}, [], []
    w_prev = pd.Series(dtype=float)
    regimes_used = {}
    for k, d in enumerate(rebal):
        if progress:
            progress((k + 1) / len(rebal), f"Rééquilibrage {d:%Y-%m} ({k + 1}/{len(rebal)})")
        i = pos[d]
        # (ré)entraînement : uniquement les étiquettes connues à la date d
        signals = None
        if use_ml and not panel.empty:
            if model is None or (last_train is not None and
                                 (d.year - last_train.year) * 12 + d.month - last_train.month >= retrain_months):
                cutoff = prices.index[i - HORIZON]
                tr = panel[(panel["date"] <= cutoff)].dropna(subset=["y_ret"])
                dts = np.sort(tr["date"].unique())
                tr = tr[tr["date"].isin(dts[::SAMPLE_EVERY])]
                m = MarketModel().fit(tr)
                if m.fitted:
                    model, last_train = m, d
            if model is not None:
                cur = panel[panel["date"] == d].set_index("ticker")
                if not cur.empty:
                    p = model.predict(cur)
                    signals = pd.DataFrame({"p_up": p["p_up"], "exp_ret_1m": p["exp_ret"]})
        reg = detect_regimes(mf.loc[:d])
        regime = reg["current"] if reg.get("ok") else "Ralentissement"
        infl = reg.get("inflation_flag", False) if reg.get("ok") else False
        regimes_used[d] = regime
        hist = prices.iloc[:i + 1]
        avail = [t for t in prices.columns if hist[t].iloc[-300:].notna().all()]
        if len(avail) < 3:
            continue
        sig = signals if signals is not None else pd.DataFrame(
            {"p_up": 0.5, "exp_ret_1m": 0.0}, index=avail)
        try:
            alloc = build_allocation(hist[avail], sig, regime, infl, profile, method,
                                     model_conf=conf if use_ml else 0.02)
            w = alloc["weights"]
        except Exception:
            w = w_prev if len(w_prev) else pd.Series(1 / len(avail), index=avail)
        if len(w_prev) and smoothing > 0:
            u = w.index.union(w_prev.index)
            w = ((1 - smoothing) * w.reindex(u).fillna(0) + smoothing * w_prev.reindex(u).fillna(0))
            w = w[w > 1e-4]
            w = w / w.sum()
        weights_hist[d] = w
        to = (w.reindex(w.index.union(w_prev.index)).fillna(0) -
              w_prev.reindex(w.index.union(w_prev.index)).fillna(0)).abs().sum()
        turnover.append(to)
        nxt = rebal[k + 1] if k + 1 < len(rebal) else prices.index[-1]
        seg = rets.loc[(rets.index > d) & (rets.index <= nxt), w.index].fillna(0)
        # dérive des poids entre deux rééquilibrages
        growth = (1 + seg).cumprod()
        val = (growth * w.values).sum(axis=1)
        prev = val.shift(1).fillna(1.0)
        r = val / prev - 1
        if len(r):
            r.iloc[0] -= to * cost_bps / 1e4
        port_ret.append(r)
        last = growth.iloc[-1] * w.values if len(growth) else w
        w_prev = pd.Series(np.asarray(last) / np.sum(last), index=w.index)
    if not port_ret:
        return {"ok": False, "error": "backtest vide"}
    pr = pd.concat(port_ret)
    pr = pr[~pr.index.duplicated()]
    W = pd.DataFrame(weights_hist).T.fillna(0)
    # rotation « aller simple » annualisée (convention usuelle) ; les frais portent sur Σ|Δw|
    return {"ok": True, "returns": pr, "weights": W, "turnover": float(np.mean(turnover[1:] or turnover) * 12 / 2),
            "regimes": pd.Series(regimes_used), "start": pr.index[0], "end": pr.index[-1],
            "cost_bps": cost_bps}


def benchmarks(prices: pd.DataFrame, start, end) -> pd.DataFrame:
    rets = prices.pct_change(fill_method=None).loc[start:end]
    out = {}
    if "SPY" in rets:
        out["S&P 500 (SPY)"] = rets["SPY"].fillna(0)
    if "SPY" in rets and "IEF" in rets:
        out["60/40 actions/obligations"] = (0.6 * rets["SPY"] + 0.4 * rets["IEF"]).fillna(0)
    eq_cols = [c for c in rets.columns if rets[c].notna().mean() > 0.95]
    if eq_cols:
        out["Équipondéré univers"] = rets[eq_cols].mean(axis=1).fillna(0)
    return pd.DataFrame(out)


# ══════════════════════════════════════════════════════════════════════════════
#  MESURES DE PERFORMANCE & DE RISQUE
# ══════════════════════════════════════════════════════════════════════════════

def perf_metrics(r: pd.Series, bench: pd.Series | None = None, rf: float = 0.02) -> dict:
    r = r.dropna()
    if len(r) < 20:
        return {}
    n = len(r)
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (252 / n) - 1
    vol = r.std() * np.sqrt(252)
    dd = eq / eq.cummax() - 1
    down = r[r < 0].std() * np.sqrt(252)
    var95 = -np.percentile(r, 5)
    cvar95 = -r[r <= -var95].mean() if (r <= -var95).any() else var95
    m = (1 + r).resample("ME").prod() - 1
    out = {
        "Performance totale": eq.iloc[-1] - 1, "Rendement annualisé": cagr, "Volatilité": vol,
        "Sharpe": (cagr - rf) / vol if vol > 0 else 0, "Sortino": (cagr - rf) / down if down > 0 else 0,
        "Drawdown max": dd.min(), "Calmar": cagr / abs(dd.min()) if dd.min() < 0 else 0,
        "VaR 95 % (1 j)": var95, "CVaR 95 % (1 j)": cvar95,
        "Meilleur mois": m.max(), "Pire mois": m.min(), "Mois positifs": (m > 0).mean(),
    }
    if bench is not None:
        b = bench.reindex(r.index).fillna(0)
        cov = np.cov(r, b)
        beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 0
        b_cagr = (1 + b).prod() ** (252 / n) - 1
        te = (r - b).std() * np.sqrt(252)
        out.update({"Bêta": beta, "Alpha (Jensen)": cagr - (rf + beta * (b_cagr - rf)),
                    "Tracking error": te, "Ratio d'information": (cagr - b_cagr) / te if te > 0 else 0})
    return {k: float(v) for k, v in out.items()}


PCT_KEYS = {"Performance totale", "Rendement annualisé", "Volatilité", "Drawdown max", "VaR 95 % (1 j)",
            "CVaR 95 % (1 j)", "Meilleur mois", "Pire mois", "Mois positifs", "Alpha (Jensen)",
            "Tracking error"}


def fmt_metric(k: str, v: float) -> str:
    if v != v:
        return "—"
    return f"{v:+.2%}" if k in PCT_KEYS and k not in ("Volatilité", "Mois positifs", "Tracking error") \
        else (f"{v:.2%}" if k in PCT_KEYS else f"{v:.2f}")


# ══════════════════════════════════════════════════════════════════════════════
#  STRESS TESTS & MONTE CARLO
# ══════════════════════════════════════════════════════════════════════════════

# chocs hypothétiques par sous-classe, ordres de grandeur inspirés d'épisodes historiques
SCENARIOS: dict[str, dict[str, float]] = {
    "Crise financière (type 2008)": {"us_eq": -.35, "tech": -.38, "us_small": -.40, "intl_eq": -.40,
        "em_eq": -.45, "financials": -.55, "energy_eq": -.40, "defensive_eq": -.22, "defense": -.30,
        "gov_long": .15, "gov_int": .08, "gov_short": .02, "tips": -.05, "ig": -.08, "hy": -.28,
        "gold": .02, "silver": -.30, "commo": -.40, "oil": -.55, "reit": -.45, "crypto": -.60, "cash": .005},
    "Krach Covid (mars 2020)": {"us_eq": -.33, "tech": -.27, "us_small": -.40, "intl_eq": -.33,
        "em_eq": -.31, "financials": -.40, "energy_eq": -.50, "defensive_eq": -.25, "defense": -.40,
        "gov_long": .12, "gov_int": .06, "gov_short": .01, "tips": -.03, "ig": -.12, "hy": -.20,
        "gold": -.03, "silver": -.25, "commo": -.30, "oil": -.60, "reit": -.42, "crypto": -.50, "cash": .002},
    "Choc de taux (type 2022)": {"us_eq": -.20, "tech": -.30, "us_small": -.22, "intl_eq": -.18,
        "em_eq": -.22, "financials": -.15, "energy_eq": .35, "defensive_eq": -.05, "defense": .05,
        "gov_long": -.31, "gov_int": -.15, "gov_short": -.04, "tips": -.12, "ig": -.18, "hy": -.13,
        "gold": -.02, "silver": -.05, "commo": .18, "oil": .25, "reit": -.27, "crypto": -.65, "cash": .015},
    "Escalade géopolitique / choc pétrolier": {"us_eq": -.10, "tech": -.12, "us_small": -.12,
        "intl_eq": -.15, "em_eq": -.16, "financials": -.12, "energy_eq": .15, "defensive_eq": -.03,
        "defense": .12, "gov_long": .05, "gov_int": .03, "gov_short": .01, "tips": .03, "ig": -.02,
        "hy": -.07, "gold": .12, "silver": .05, "commo": .18, "oil": .35, "reit": -.08, "crypto": -.18, "cash": .003},
    "Stagflation": {"us_eq": -.18, "tech": -.25, "us_small": -.22, "intl_eq": -.18, "em_eq": -.20,
        "financials": -.15, "energy_eq": .10, "defensive_eq": -.06, "defense": -.05, "gov_long": -.12,
        "gov_int": -.05, "gov_short": .00, "tips": .04, "ig": -.08, "hy": -.12, "gold": .15,
        "silver": .10, "commo": .15, "oil": .20, "reit": -.18, "crypto": -.30, "cash": .01},
    "Rally risk-on (euphorie IA)": {"us_eq": .15, "tech": .25, "us_small": .14, "intl_eq": .10,
        "em_eq": .12, "financials": .12, "energy_eq": .05, "defensive_eq": .04, "defense": .06,
        "gov_long": -.04, "gov_int": -.02, "gov_short": 0, "tips": 0, "ig": .02, "hy": .05,
        "gold": -.05, "silver": .05, "commo": .05, "oil": .03, "reit": .08, "crypto": .40, "cash": .002},
}


def stress_test(weights: pd.Series) -> pd.DataFrame:
    rows = []
    for name, shocks in SCENARIOS.items():
        contrib = {t: w * shocks.get(asset_subclass(t), -.2) for t, w in weights.items()}
        tot = sum(contrib.values())
        worst = min(contrib, key=contrib.get) if contrib else ""
        rows.append({"Scénario": name, "Impact": tot, "Pire contributeur": worst,
                     "Contribution": contrib.get(worst, 0)})
    return pd.DataFrame(rows).sort_values("Impact")


def historical_worst(weights: pd.Series, prices: pd.DataFrame, window: int = 21) -> dict:
    r = prices[weights.index].pct_change(fill_method=None).fillna(0) @ weights.values
    roll = (1 + r).rolling(window).apply(np.prod, raw=True) - 1
    if roll.dropna().empty:
        return {}
    d = roll.idxmin()
    return {"perte": float(roll.min()), "fin": d, "debut": r.index[max(0, r.index.get_loc(d) - window)]}


def monte_carlo(daily: pd.Series, capital: float, horizon: int = 252, n_paths: int = 2000,
                block: int = 10, seed: int = 42) -> dict:
    """Bootstrap par blocs des rendements journaliers (conserve l'autocorrélation courte)."""
    r = daily.dropna().values
    if len(r) < block * 5:
        return {}
    rng = np.random.default_rng(seed)
    n_blocks = int(np.ceil(horizon / block))
    starts = rng.integers(0, len(r) - block, size=(n_paths, n_blocks))
    paths = np.stack([r[s:s + block] for s in starts.ravel()]).reshape(n_paths, -1)[:, :horizon]
    val = capital * np.cumprod(1 + paths, axis=1)
    pct = np.percentile(val, [5, 25, 50, 75, 95], axis=0)
    final = val[:, -1]
    return {"percentiles": pd.DataFrame(pct.T, columns=["p5", "p25", "p50", "p75", "p95"]),
            "final": final, "prob_loss": float((final < capital).mean()),
            "exp": float(final.mean()), "var95": float(capital - np.percentile(final, 5)),
            "p5": float(np.percentile(final, 5)), "p95": float(np.percentile(final, 95)),
            "capital": capital, "horizon": horizon}


# ══════════════════════════════════════════════════════════════════════════════
#  EXÉCUTION DANS UN PORTEFEUILLE DE LA PLATEFORME
# ══════════════════════════════════════════════════════════════════════════════

def plan_orders(port: dict, weights: pd.Series, live: dict, invest_pct: float = 1.0,
                mode: str = "full", cash_proxy: str = "BIL", min_trade: float = 100.0) -> pd.DataFrame:
    """Calcule les ordres pour atteindre l'allocation cible.
    mode 'full' : rééquilibrage complet de la poche spot ; 'cash' : investit seulement le cash."""
    holdings = port.get("holdings", {}) or {}
    cash = float(port.get("cash", 0))
    px = {t: float(live.get(t, (0, 0))[0]) for t in set(weights.index) | set(holdings)}
    cur_val = {t: holdings[t].get("qty", 0) * px.get(t, holdings[t].get("avg_price", 0)) for t in holdings}
    nav = cash + sum(cur_val.values())
    w = weights.drop(labels=[cash_proxy], errors="ignore")   # le monétaire reste en cash
    orders = []
    if mode == "cash":
        budget = cash * invest_pct
        for t, wt in w.items():
            amt = budget * wt
            if px.get(t, 0) > 0 and amt >= min_trade:
                orders.append({"ticker": t, "action": "BUY", "qty": amt / px[t], "price": px[t], "montant": amt})
    else:
        target = {t: nav * invest_pct * wt for t, wt in w.items()}
        for t in set(target) | set(holdings):
            p = px.get(t, 0)
            if p <= 0:
                continue
            diff = target.get(t, 0) - cur_val.get(t, 0)
            if abs(diff) < min_trade:
                continue
            q = abs(diff) / p
            if diff < 0:
                q = min(q, holdings.get(t, {}).get("qty", 0))
            orders.append({"ticker": t, "action": "BUY" if diff > 0 else "SELL",
                           "qty": q, "price": p, "montant": q * p})
    df = pd.DataFrame(orders)
    if df.empty:
        return df
    df["qty"] = df.apply(lambda r: round(r["qty"], 6 if r["ticker"].endswith("-USD") else 4), axis=1)
    df["montant"] = df["qty"] * df["price"]
    df = df[df["qty"] > 0]
    # les ventes d'abord, puis achats ajustés au cash disponible
    sells = df[df["action"] == "SELL"]
    buys = df[df["action"] == "BUY"]
    avail = cash + sells["montant"].sum()
    if buys["montant"].sum() > avail > 0:
        k = avail / buys["montant"].sum() * 0.999
        buys = buys.assign(qty=(buys["qty"] * k).round(4))
        buys = buys.assign(montant=buys["qty"] * buys["price"])
    return pd.concat([sells, buys], ignore_index=True)


def execute_orders(port: dict, orders: pd.DataFrame, tag: str = "auto-IA") -> list[str]:
    """Applique les ordres (mêmes règles que record_trade) ; la sauvegarde est faite par l'appelant."""
    errors = []
    h = port.setdefault("holdings", {})
    tr = port.setdefault("trades", [])
    try:
        from utils.compliance import pre_trade_spot, log_decision
    except Exception as e:  # par prudence, aucun ordre sans contrôle de conformité
        return [f"Contrôle de conformité indisponible ({e}) : aucun ordre exécuté"]
    import math
    from utils.costs import affordable_qty
    from utils.data import apply_trade
    for _, o in orders.iterrows():
        t, q, p = o["ticker"], float(o["qty"]), float(o["price"])
        # v5.8 : un achat est réduit si les frais (écart, courtage, taxes) ne laissent pas assez de liquidités
        dec_ = 6 if t.endswith("-USD") else 4
        if o["action"] == "BUY":
            q = math.floor(affordable_qty(t, port.get("cash", 0.0), p, q) * 10 ** dec_) / 10 ** dec_
            if q <= 0:
                errors.append(f"{t} : cash insuffisant (frais compris)")
                continue
        else:
            q = min(q, h.get(t, {}).get("qty", 0))
            if q <= 0:
                continue
        # Contrôles pré-négociation : chaque ordre est vérifié sur l'état courant du portefeuille
        dec = pre_trade_spot(port, t, o["action"], q, p)
        if not dec.allowed:
            log_decision(dec, port, t, o["action"], q, p, executed=False, note=tag)
            errors.append(f"{t} bloqué — " + "; ".join(f"[{c.code}] {c.title}" for c in dec.blocks))
            continue
        log_decision(dec, port, t, o["action"], q, p, executed=True, note=tag)
        entry = apply_trade(port, t, o["action"], q, p)
        if isinstance(entry, str):
            errors.append(f"{t} : {entry}")
            continue
        entry["source"] = tag
        tr.append(entry)
    return errors
