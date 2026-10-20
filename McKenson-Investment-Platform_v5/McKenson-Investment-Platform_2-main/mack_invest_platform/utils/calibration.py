# utils/calibration.py  —  MAM v5.4 · Calibration des hypothèses d'expert sur l'historique
"""
Feuille de route du dossier de conception, lot 1 : remplacer (ou confronter) les
hypothèses fixées « à dire d'expert » par des valeurs estimées sur l'historique.

1. Matrice de sensibilité classes × facteurs
   Régression (ridge, variables centrées-réduites) des rendements hebdomadaires de
   chaque classe sur les variations hebdomadaires des facteurs ; stabilité mesurée
   sur des fenêtres glissantes de 3 ans ; comparaison avec la matrice d'expert.
2. Volatilité typique des stratégies (revue de création du comité)
   Volatilité réalisée d'un panier d'ETF représentatif de chaque stratégie.
3. Couvertures par options
   Multiplicateur de volatilité (vol réalisée / VIX), choc de référence (quantile 5 %
   des rendements à 3 mois) et part couverte reliée à la probabilité historique
   d'une forte baisse selon le niveau de risque du panier (régression logistique).
4. Seuils d'alerte
   Seuils choisis pour atteindre une fréquence cible d'alertes par gravité.

Règles communes
* On ne calibre JAMAIS sur des données simulées : un élément sans historique réel
  suffisant garde la valeur d'expert, ce qui est affiché.
* Une calibration ne s'applique qu'après validation d'un administrateur ; elle est
  enregistrée en base (table hedge_fund_state) et vaut pour la plateforme ET pour
  le traitement planifié. Les valeurs d'expert restent le repli.
* Les facteurs historiques ne contiennent que leur composante « marché » : l'actualité
  n'a pas d'historique ; le facteur géopolitique (100 % actualité) n'est pas estimable.
"""
from __future__ import annotations

import math
import time
from datetime import datetime

import numpy as np
import pandas as pd

from utils import advisor as A

CALIB_VERSION = "1.0"
HISTORY_PERIOD = "10y"
MIN_DAYS = 3 * 252                 # au moins 3 ans de cours réels par série utilisée

# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES
# ══════════════════════════════════════════════════════════════════════════════
STRATEGY_BASKETS = {
    # stratégie (identifiant du comité) : panier d'ETF représentatif
    "growth":    {"QQQ": 1.0},
    "value":     {"VTV": 1.0},
    "momentum":  {"MTUM": 1.0},
    "income":    {"VYM": 0.5, "AGG": 0.5},
    "macro":     {"SPY": 0.25, "TLT": 0.25, "GLD": 0.25, "DBC": 0.25},
    "hedging":   {"TLT": 0.4, "GLD": 0.3, "BIL": 0.3},
    "balanced":  {"SPY": 0.6, "AGG": 0.4},
    "commodity": {"DBC": 1.0},
    "crypto":    {"BTC-USD": 1.0},
    "arbitrage": {"MNA": 1.0},
    "etf":       {"AOR": 1.0},
}
HEDGE_ETFS = ("QQQ", "SPY", "VGK", "EEM", "XLE", "USO", "TLT")


def history_tickers() -> tuple:
    t = set(A.ALL_TICKERS) | set(HEDGE_ETFS)
    for b in STRATEGY_BASKETS.values():
        t |= set(b)
    return tuple(sorted(t))


def load_history() -> tuple[pd.DataFrame, list]:
    """Cours quotidiens sur 10 ans (mis en cache) et liste des séries simulées (inutilisables)."""
    px, missing = A.load_prices(history_tickers(), HISTORY_PERIOD)
    return px, list(missing or [])


def _usable(px: pd.DataFrame, missing: list, tickers) -> list[str]:
    return [t for t in tickers if t in px.columns and t not in missing and px[t].notna().sum() >= MIN_DAYS]


# ══════════════════════════════════════════════════════════════════════════════
#  FACTEURS HISTORIQUES (composante marché, calcul vectoriel identique à compute_macro)
# ══════════════════════════════════════════════════════════════════════════════
def _c(x: pd.Series) -> pd.Series:
    return x.clip(-2, 2)


def market_factor_series(px: pd.DataFrame) -> pd.DataFrame:
    """Facteurs quotidiens reconstitués sans la composante actualité (inconnue dans le passé)."""
    g = lambda t: px[t] if t in px.columns else pd.Series(np.nan, index=px.index)
    spy, vix, tnx, irx = g("SPY"), g("^VIX"), g("^TNX"), g("^IRX")
    oil, cop, gold, dxy, hyg, ief = g("CL=F"), g("HG=F"), g("GC=F"), g("DX-Y.NYB"), g("HYG"), g("IEF")
    mean = lambda *parts: pd.concat(parts, axis=1).mean(axis=1, skipna=True)
    f = pd.DataFrame(index=px.index)
    f["croissance"] = mean(_c((spy / spy.rolling(200).mean() - 1) / 0.05),
                           _c((cop.pct_change(63) - gold.pct_change(63)) / 0.08),
                           _c((tnx - irx) / 1.0))
    f["inflation"] = mean(_c(oil.pct_change(63) / 0.15), _c(tnx.diff(63) / 0.5), _c(gold.pct_change(63) / 0.08))
    f["monetaire"] = mean(_c(irx.diff(126) / 0.75), _c((irx - 3.0) / 1.5))
    f["credit"] = _c((hyg / ief).pct_change(63) / 0.03)
    f["stress"] = _c((vix - 18) / 6)
    f["dollar"] = _c(dxy.pct_change(63) / 0.04)
    f["geopolitique"] = np.nan                      # 100 % actualité : pas d'historique
    f["energie"] = _c(oil.pct_change(21) / 0.10)
    return f[A.F_KEYS].iloc[200:]


# ══════════════════════════════════════════════════════════════════════════════
#  1. MATRICE DE SENSIBILITÉ
# ══════════════════════════════════════════════════════════════════════════════
def _ridge(X: np.ndarray, Y: np.ndarray, lam: float) -> tuple[np.ndarray, np.ndarray]:
    """Coefficients ridge et statistiques t approchées (variables centrées-réduites)."""
    n, k = X.shape
    XtX = X.T @ X
    inv = np.linalg.inv(XtX + lam * np.eye(k))
    B = inv @ X.T @ Y
    resid = Y - X @ B
    s2 = (resid ** 2).sum(axis=0) / max(n - k, 1)
    se = np.sqrt(np.outer(np.diag(inv @ XtX @ inv), s2))
    return B, B / np.where(se > 0, se, np.nan)


def _weekly_panel(px: pd.DataFrame, classes: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    F = market_factor_series(px)
    proxies = [A.CLASS_PROXY[c] for c in classes]
    P = px[proxies].reindex(F.index)
    Fw, Pw = F.iloc[::5], P.iloc[::5]
    dF = Fw.diff()
    R = np.log(Pw).diff()
    R.columns = classes
    j = pd.concat([dF, R], axis=1, keys=["f", "r"]).dropna(subset=[("f", k) for k in dF.columns
                                                                  if dF[k].notna().any()])
    return j["f"], j["r"]


def estimate_sensitivity(px: pd.DataFrame, missing: list, lam: float = 5.0,
                         window_weeks: int = 156, step_weeks: int = 26) -> dict:
    """Matrice estimée (échelle −1 … +1), statistiques t, stabilité et comparaison avec l'expert."""
    need = ["SPY", "^VIX", "^TNX", "^IRX", "CL=F", "GC=F", "HYG", "IEF"]
    ok_macro = _usable(px, missing, need)
    if len(ok_macro) < len(need):
        return dict(ok=False, detail="Données de marché réelles insuffisantes (repli simulé) : la matrice d'expert "
                                     "est conservée. Indicateurs manquants : "
                                     + ", ".join(sorted(set(need) - set(ok_macro))))
    classes = [c for c in A.CLASSES if A.CLASS_PROXY[c] in _usable(px, missing, [A.CLASS_PROXY[c]])]
    dF, R = _weekly_panel(px, classes)
    keys = [k for k in A.F_KEYS if dF[k].notna().sum() > 0]
    J = pd.concat([dF[keys], R], axis=1).dropna()
    if len(J) < 104:
        return dict(ok=False, detail=f"Historique trop court ({len(J)} semaines, 104 nécessaires).")
    X, Y = J[keys], J[classes]
    Xs = ((X - X.mean()) / X.std()).values
    Ys = ((Y - Y.mean()) / Y.std()).values
    B, T = _ridge(Xs, Ys, lam)
    scale = np.nanmax(np.abs(B)) or 1.0
    est = pd.DataFrame(np.nan, index=A.CLASSES, columns=A.F_KEYS)
    tst = est.copy()
    est.loc[classes, keys] = (B.T / scale).round(2)
    tst.loc[classes, keys] = T.T.round(1)

    # Stabilité : signe identique sur les fenêtres glissantes de 3 ans
    same = pd.DataFrame(0.0, index=classes, columns=keys)
    nwin = 0
    for start in range(0, len(J) - window_weeks + 1, step_weeks):
        sub = J.iloc[start:start + window_weeks]
        xs = ((sub[keys] - sub[keys].mean()) / sub[keys].std()).fillna(0).values
        ys = ((sub[classes] - sub[classes].mean()) / sub[classes].std()).fillna(0).values
        b, _ = _ridge(xs, ys, lam)
        same += (np.sign(b.T) == np.sign(B.T)).astype(float)
        nwin += 1
    stab = est.copy() * np.nan
    if nwin:
        stab.loc[classes, keys] = (same / nwin).round(2)

    exp = A.SENSITIVITY
    m = est.notna()
    mk = m.values
    e, x = exp.values[mk], est.values[mk]
    corr = float(np.corrcoef(e, x)[0, 1]) if len(e) > 3 and np.std(x) > 0 else float("nan")
    strong = (exp.abs() >= 0.3) & (tst.abs() >= 2) & m
    sk = strong.values
    agree = float((np.sign(exp.values[sk]) == np.sign(est.values[sk])).mean()) if sk.any() else float("nan")
    disagreements = []
    for c in classes:
        for k in keys:
            if strong.loc[c, k] and np.sign(exp.loc[c, k]) != np.sign(est.loc[c, k]):
                disagreements.append(dict(classe=c, facteur=A.FACTORS[k][0], expert=float(exp.loc[c, k]),
                                          estime=float(est.loc[c, k]), t=float(tst.loc[c, k]),
                                          stabilite=float(stab.loc[c, k])))
    return dict(ok=True, estimee=est, t=tst, stabilite=stab, n_semaines=len(J), fenetres=nwin,
                periode=(str(J.index[0].date()), str(J.index[-1].date())), facteurs=keys, classes=classes,
                correlation=corr, accord_signes=agree, n_cellules_fortes=int(strong.values.sum()),
                desaccords=disagreements, lam=lam,
                note=("Coefficients centrés-réduits (ridge λ = {:.0f}) ramenés sur l'échelle −1 … +1 de la matrice "
                      "d'expert. Les facteurs étant construits à partir de prix de marché, certains coefficients "
                      "sont en partie mécaniques (par exemple Actions US / croissance, qui utilise le S&P 500). "
                      "Le facteur géopolitique, fondé uniquement sur l'actualité, n'a pas d'historique.").format(lam))


def blend(estimated: pd.DataFrame, weight: float) -> pd.DataFrame:
    """Matrice mixte : (1 − w) × expert + w × estimée ; une cellule non estimée garde l'expert."""
    w = float(np.clip(weight, 0, 1))
    est = estimated.reindex(index=A.CLASSES, columns=A.F_KEYS)
    out = A.SENSITIVITY.copy()
    m = est.notna()
    out[m] = ((1 - w) * A.SENSITIVITY[m] + w * est[m]).round(2)
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  2. VOLATILITÉ TYPIQUE DES STRATÉGIES
# ══════════════════════════════════════════════════════════════════════════════
def calibrate_strategy_vols(px: pd.DataFrame, missing: list) -> pd.DataFrame:
    from utils.committee import STRATEGY_VOL, STRATEGY_TYPE
    rows = []
    for sid, basket in STRATEGY_BASKETS.items():
        ok = _usable(px, missing, basket)
        row = dict(id=sid, strategie=STRATEGY_TYPE.get(sid, sid), panier=" + ".join(
            f"{int(w * 100)} % {t}" if w < 1 else t for t, w in basket.items()), expert=STRATEGY_VOL.get(sid))
        if len(ok) < len(basket):
            rows.append({**row, "calibree": np.nan, "vol_stress": np.nan, "perte_max": np.nan, "annees": 0.0,
                         "source": "expert (historique réel indisponible)"})
            continue
        r = np.log(px[list(basket)]).diff().dropna()
        rp = r @ pd.Series(basket)[r.columns]
        vol = float(rp.std() * math.sqrt(252))
        roll = rp.rolling(63).std() * math.sqrt(252)
        eq = np.exp(rp.cumsum())
        rows.append({**row, "calibree": round(vol * 200) / 200, "vol_stress": float(roll.quantile(0.9)),
                     "perte_max": float((eq / eq.cummax() - 1).min()), "annees": len(rp) / 252,
                     "source": "historique"})
    return pd.DataFrame(rows).set_index("id")


# ══════════════════════════════════════════════════════════════════════════════
#  3. COUVERTURES
# ══════════════════════════════════════════════════════════════════════════════
HORIZON_D = 63                      # ≈ 90 jours calendaires (échéance des couvertures)


def calibrate_hedges(px: pd.DataFrame, missing: list) -> pd.DataFrame:
    from utils.hedging import BUCKETS, bucket_risk
    F = market_factor_series(px).fillna(0.0)
    vix_ok = bool(_usable(px, missing, ["^VIX"]))
    rows = []
    for b, meta in BUCKETS.items():
        und = meta["hedge"]
        base = dict(cle=b, panier=meta["label"], etf=und, vol_expert=meta["vol"], choc_expert=meta["choc"])
        if not (_usable(px, missing, [und]) and vix_ok):
            rows.append({**base, "source": "expert (historique réel indisponible)"})
            continue
        s = px[und].dropna()
        r = np.log(s).diff().dropna()
        rv = (r.rolling(63).std() * math.sqrt(252)).dropna()
        vix = px["^VIX"].reindex(rv.index).ffill() / 100
        vol_mult = float((rv / vix).replace([np.inf, -np.inf], np.nan).dropna().median())
        fwd = (s.shift(-HORIZON_D) / s - 1).dropna()
        choc = float(np.floor(fwd.quantile(0.05) * 100) / 100)
        risk = pd.Series([bucket_risk(b, F.loc[d].to_dict())[0] for d in F.index], index=F.index)
        J = pd.concat([risk.rename("risk"), fwd.rename("fwd")], axis=1).dropna().iloc[::5]
        tail = (J["fwd"] <= choc / 2).astype(int)
        row = {**base, "vol_calibre": round(vol_mult, 2), "choc_calibre": choc,
               "seuil_perte": choc / 2, "frequence": float(tail.mean()), "n_obs": len(J),
               "n_evenements": int(tail.sum()), "source": "historique"}
        if tail.sum() >= 8 and (1 - tail).sum() >= 8 and J["risk"].std() > 0:
            from sklearn.linear_model import LogisticRegression
            lr = LogisticRegression(C=1.0).fit(J[["risk"]].values, tail.values)
            a, k = float(lr.intercept_[0]), float(lr.coef_[0][0])
            row.update(logit_a=a, logit_b=k)
            p = lambda x: 1 / (1 + math.exp(-(a + k * x)))
            row.update(p_risque_0=p(0.0), p_risque_05=p(0.5), p_risque_1=p(1.0))
            # prédictif si la probabilité de forte baisse augmente nettement avec le risque
            row["predictif"] = bool(k > 0 and p(1.0) / max(p(0.0), 1e-9) >= 1.2)
            if k > 0:
                # seuil de recommandation : risque au-delà duquel la probabilité dépasse la moyenne
                pbar = float(tail.mean())
                row["seuil_reco"] = float(np.clip((math.log(pbar / (1 - pbar)) - a) / k, -1.0, 2.0))
        else:
            row["predictif"] = False
        rows.append(row)
    return pd.DataFrame(rows).set_index("cle")


def hedge_ratio_from_calibration(c: dict, risk: float) -> tuple[float, bool]:
    """Part couverte et recommandation à partir des paramètres calibrés.
    ratio = 25 % + 50 % × (surcroît de probabilité de forte baisse) : une probabilité
    doublée par rapport à la moyenne → 50 % couverts ; triplée → 75 %."""
    if not c.get("predictif") or "logit_a" not in c:
        return 0.25, False
    p = 1 / (1 + math.exp(-(c["logit_a"] + c["logit_b"] * risk)))
    lift = p / max(c.get("frequence", 1e-9), 1e-9)
    ratio = float(np.clip(0.25 + 0.25 * (lift - 1), 0.25, 0.75)) if lift > 1 else 0.25
    return ratio, risk >= c.get("seuil_reco", 0.25)


# ══════════════════════════════════════════════════════════════════════════════
#  4. SEUILS D'ALERTE
# ══════════════════════════════════════════════════════════════════════════════
EXPERT_ALERTS = dict(z_info=2.0, z_important=2.5, z_critique=3.5, taux_info=0.20, taux_important=0.30)
TARGETS = dict(info=8.0, important=3.0, critique=1.0, taux_info=2.0, taux_important=0.5)   # alertes / mois


def _thr_for(values: np.ndarray, per_month: float, months: float) -> float:
    n = int(round(per_month * months))
    v = np.sort(values)[::-1]
    if n <= 0 or len(v) == 0:
        return float("inf")
    return float(v[min(n, len(v)) - 1])


def _freq(values: np.ndarray, thr: float, months: float) -> float:
    return float((values >= thr).sum() / months) if months else float("nan")


def calibrate_alerts(px: pd.DataFrame, missing: list, targets: dict | None = None) -> dict:
    from utils.alerts import WATCH
    tg = {**TARGETS, **(targets or {})}
    zs = []
    days = 0
    for t in WATCH:
        if not _usable(px, missing, [t]):
            continue
        r = np.log(px[t].dropna()).diff().dropna()
        sd = r.rolling(252).std().shift(1)
        z1 = (r / sd).abs()
        z5 = (r.rolling(5).sum() / (sd * math.sqrt(5))).abs()
        zz = pd.concat([z1, z5]).dropna()
        zs.append(zz.values)
        days = max(days, int(z1.notna().sum()))
    out = dict(ok=False, lignes=[])
    if not zs or days < 2 * 252:
        out["detail"] = "Historique réel insuffisant : seuils d'expert conservés."
        return out
    z = np.concatenate(zs)
    months = days / 21.0
    zi = _thr_for(z, tg["info"] + tg["important"] + tg["critique"], months)
    zm = _thr_for(z, tg["important"] + tg["critique"], months)
    zc = _thr_for(z, tg["critique"], months)
    zi = float(np.clip(zi, 1.5, 3.0)); zm = float(np.clip(zm, zi + 0.25, 4.0)); zc = float(np.clip(zc, zm + 0.5, 6.0))
    cal = dict(z_info=round(zi, 2), z_important=round(zm, 2), z_critique=round(zc, 2))
    E = EXPERT_ALERTS
    lines = [
        dict(regle="Mouvement de marché (écarts-types)", gravite="info", expert=E["z_info"], calibre=cal["z_info"],
             freq_expert=_freq(z, E["z_info"], months) - _freq(z, E["z_important"], months),
             freq_calibree=_freq(z, zi, months) - _freq(z, zm, months), cible=tg["info"]),
        dict(regle="Mouvement de marché (écarts-types)", gravite="important", expert=E["z_important"],
             calibre=cal["z_important"], freq_expert=_freq(z, E["z_important"], months) - _freq(z, E["z_critique"], months),
             freq_calibree=_freq(z, zm, months) - _freq(z, zc, months), cible=tg["important"]),
        dict(regle="Mouvement de marché (écarts-types)", gravite="critique", expert=E["z_critique"],
             calibre=cal["z_critique"], freq_expert=_freq(z, E["z_critique"], months),
             freq_calibree=_freq(z, zc, months), cible=tg["critique"]),
    ]
    if _usable(px, missing, ["^TNX"]):
        d = px["^TNX"].dropna().diff(5).abs().dropna().values
        mo = len(d) / 21.0
        ti = float(np.clip(_thr_for(d, tg["taux_info"] + tg["taux_important"], mo), 0.10, 0.40))
        tm = float(np.clip(_thr_for(d, tg["taux_important"], mo), ti + 0.05, 0.60))
        cal.update(taux_info=round(ti, 2), taux_important=round(tm, 2))
        lines += [
            dict(regle="Taux 10 ans US sur 5 jours (points)", gravite="info", expert=E["taux_info"], calibre=cal["taux_info"],
                 freq_expert=_freq(d, E["taux_info"], mo) - _freq(d, E["taux_important"], mo),
                 freq_calibree=_freq(d, ti, mo) - _freq(d, tm, mo), cible=tg["taux_info"]),
            dict(regle="Taux 10 ans US sur 5 jours (points)", gravite="important", expert=E["taux_important"],
                 calibre=cal["taux_important"], freq_expert=_freq(d, E["taux_important"], mo),
                 freq_calibree=_freq(d, tm, mo), cible=tg["taux_important"]),
        ]
    if _usable(px, missing, ["^VIX"]):
        v = px["^VIX"].dropna().values
        mo = len(v) / 21.0
        lines.append(dict(regle="VIX (niveau, seuils conventionnels conservés)", gravite="important / critique",
                          expert="25 / 30", calibre="25 / 30",
                          freq_expert=_freq(v, 25, mo), freq_calibree=_freq(v, 25, mo), cible=np.nan))
    out.update(ok=True, seuils=cal, lignes=lines, mois=months, cibles=tg)
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  ÉTAT ACTIF (lu par advisor, committee, hedging, alerts — cache 5 minutes)
# ══════════════════════════════════════════════════════════════════════════════
STATE_KEY = "calibration_active"
_CACHE = {"t": 0.0, "v": None}


def active() -> dict:
    """Calibration appliquée par un administrateur ({} si aucune)."""
    if time.time() - _CACHE["t"] < 300:
        return _CACHE["v"] or {}
    v = None
    try:
        from utils.alerts import get_state
        v = get_state(STATE_KEY)
    except Exception:
        v = None
    _CACHE.update(t=time.time(), v=v or {})
    return _CACHE["v"]


def _clean(v):
    """JSON strict : NaN / infini → None, types NumPy → types Python."""
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        return float(v) if np.isfinite(v) else None
    return v


def save_active(payload: dict) -> bool:
    from utils.alerts import set_state
    payload = _clean(payload)
    if payload:
        payload = {**payload, "date": datetime.now().strftime("%Y-%m-%d %H:%M"), "version": CALIB_VERSION}
    ok = set_state(STATE_KEY, payload)
    if ok:
        _CACHE.update(t=time.time(), v=payload)
    return bool(ok)


def clear_cache():
    _CACHE.update(t=0.0, v=None)


def active_sensitivity() -> pd.DataFrame:
    s = active().get("sensibilite")
    if not s or not s.get("matrice"):
        return A.SENSITIVITY
    try:
        m = pd.DataFrame(s["matrice"]).reindex(index=A.CLASSES, columns=A.F_KEYS)
        return m.fillna(A.SENSITIVITY)
    except Exception:
        return A.SENSITIVITY


def active_strategy_vol(sid: str, default: float) -> float:
    v = (active().get("strategies") or {}).get(sid)
    return float(v) if v else default


def active_hedge(bucket: str) -> dict | None:
    return (active().get("couvertures") or {}).get(bucket)


def active_alert_thresholds() -> dict:
    return {**EXPERT_ALERTS, **(active().get("alertes") or {})}


def sensitivity_source() -> str:
    s = active().get("sensibilite")
    if not s:
        return "expert"
    return f"mixte ({s.get('poids', 0):.0%} estimée, {active().get('date', '')})"
