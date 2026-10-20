# utils/backtest_desk.py  —  MAM v5.4 · Backtest walk-forward du desk complet
"""
Rejoue mois par mois, sans information future, la chaîne de décision du Hedge Fund
Agent : facteurs → régime → inclinaisons du stratège → moteur de risque, puis compare
le résultat à l'allocation stratégique du profil (même univers d'ETF, mêmes coûts).

Trois portefeuilles sont suivis, ce qui sépare les deux sources de valeur ajoutée :
* « Allocation stratégique » : poids fixes du profil ;
* « Stratégique + moteur de risque » : mêmes poids, passés par les limites et la
  volatilité cible (apport du contrôle des risques seul) ;
* « Desk complet » : inclinaisons macro + moteur de risque.

Hypothèses (affichées) : rééquilibrage le dernier jour ouvré de chaque mois, dérive des
poids entre deux rééquilibrages, coût de transaction proportionnel à la rotation,
facteurs sans leur composante actualité (pas d'historique), facteur géopolitique à 0.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from utils import advisor as A
from utils.calibration import market_factor_series, _usable

RF = 0.03
NAMES = ("Allocation stratégique", "Stratégique + moteur de risque", "Desk complet")


def _tilt(w0: pd.Series, scores: pd.Series, intensity: float) -> pd.Series:
    w = (w0 * (1 + intensity * 0.6 * np.tanh(scores / 3.0))).clip(lower=0)
    return w / w.sum()


def _stats(nav: pd.Series, bench: pd.Series | None = None) -> dict:
    r = nav.pct_change().dropna()
    yrs = len(r) / 252
    out = {"Rendement annualisé": (nav.iloc[-1] / nav.iloc[0]) ** (1 / yrs) - 1 if yrs > 0 else np.nan,
           "Volatilité": r.std() * math.sqrt(252)}
    out["Sharpe"] = (out["Rendement annualisé"] - RF) / out["Volatilité"] if out["Volatilité"] else np.nan
    out["Perte max"] = float((nav / nav.cummax() - 1).min())
    if bench is not None:
        rb = bench.pct_change().reindex(r.index)
        a = r - rb
        te = a.std() * math.sqrt(252)
        out["Écart de suivi"] = te
        out["Ratio d'information"] = a.mean() * 252 / te if te else np.nan
    return out


def run(px: pd.DataFrame, missing: list, profile: str = "Équilibré", intensity: float = 0.5,
        matrix: pd.DataFrame | None = None, cost_bp: float = 10.0, warmup: int = 252) -> dict:
    matrix = A.SENSITIVITY if matrix is None else matrix.reindex(index=A.CLASSES, columns=A.F_KEYS).fillna(A.SENSITIVITY)
    proxies = [A.CLASS_PROXY[c] for c in A.CLASSES]
    ok = _usable(px, missing, proxies)
    need = ["SPY", "^VIX", "^TNX", "^IRX", "CL=F", "GC=F", "HYG", "IEF"]
    if len(ok) < len(proxies) or len(_usable(px, missing, need)) < len(need):
        lack = sorted((set(proxies) | set(need)) - set(ok) - set(_usable(px, missing, need)))
        return dict(ok=False, detail="Historique réel insuffisant pour le backtest (aucun backtest sur données "
                                     "simulées). Séries manquantes : " + ", ".join(lack))
    P = px[proxies].copy()
    P.columns = A.CLASSES
    P = P.dropna()
    F = market_factor_series(px).reindex(P.index).fillna(0.0)
    days = P.index[warmup:]
    if len(days) < 260:
        return dict(ok=False, detail="Historique trop court après la période d'initialisation (1 an).")
    month_ends = pd.Series(days, index=days).groupby([days.year, days.month]).last().values
    w0 = pd.Series(A.PROFILES[profile], index=A.CLASSES)
    R = P.pct_change().fillna(0.0)

    navs = {n: [1.0] for n in NAMES}
    idx = [pd.Timestamp(month_ends[0])]
    weights_log, turnover = [], {n: [] for n in NAMES}
    cur = {n: None for n in NAMES}
    for m, t in enumerate(month_ends[:-1]):
        t = pd.Timestamp(t)
        f = F.loc[t].to_dict()
        cov = A.class_covariance(px.loc[:t])
        regime, _ = A.classify_regime(f)
        tgt = {
            NAMES[0]: w0,
            NAMES[1]: A.risk_engine(w0, profile, f, cov, False)[0].reindex(A.CLASSES).fillna(0),
            NAMES[2]: A.risk_engine(_tilt(w0, matrix.dot(pd.Series(f)[A.F_KEYS]), intensity), profile, f, cov,
                                    False)[0].reindex(A.CLASSES).fillna(0),
        }
        weights_log.append(dict(date=t, regime=regime, **{f"{c}": float(tgt[NAMES[2]][c]) for c in A.CLASSES}))
        nxt = pd.Timestamp(month_ends[m + 1])
        seg = R.loc[(R.index > t) & (R.index <= nxt)]
        for n in NAMES:
            w = tgt[n] / tgt[n].sum()
            to = float((w - cur[n]).abs().sum()) if cur[n] is not None else float(w.abs().sum())
            turnover[n].append(to / 2)
            v = navs[n][-1] * (1 - to * cost_bp / 1e4)
            hold = w * v
            for d, r in seg.iterrows():
                hold = hold * (1 + r)
                navs[n].append(float(hold.sum()))
            cur[n] = hold / hold.sum()
        if m == 0:
            idx = [t]
        idx += list(seg.index)
    out_nav = pd.DataFrame({n: pd.Series(v, index=idx[:len(v)]) for n, v in navs.items()})
    stats = pd.DataFrame({n: _stats(out_nav[n], None if n == NAMES[0] else out_nav[NAMES[0]]) for n in NAMES}).T
    stats["Rotation moyenne / mois"] = [float(np.mean(turnover[n][1:])) if len(turnover[n]) > 1 else 0.0 for n in NAMES]
    mret = out_nav.resample("ME").last().pct_change().dropna()
    exc = mret[NAMES[2]] - mret[NAMES[0]]
    wl = pd.DataFrame(weights_log).set_index("date")
    reg = wl["regime"].reindex(mret.index, method="ffill")
    by_regime = pd.DataFrame({"Mois": exc.groupby(reg).size(), "Surperformance moyenne / mois": exc.groupby(reg).mean(),
                              "Mois gagnants": (exc > 0).groupby(reg).mean()}).sort_values("Mois", ascending=False)
    yearly = out_nav.resample("YE").last().pct_change()
    yearly.iloc[0] = out_nav.resample("YE").last().iloc[0] / out_nav.iloc[0] - 1
    yearly.index = yearly.index.year
    return dict(ok=True, nav=out_nav, stats=stats, mois_gagnants=float((exc > 0).mean()), n_mois=len(exc),
                par_regime=by_regime, annuel=yearly, poids=wl, profil=profile, intensite=intensity,
                periode=(str(out_nav.index[0].date()), str(out_nav.index[-1].date())), cout_bp=cost_bp)
