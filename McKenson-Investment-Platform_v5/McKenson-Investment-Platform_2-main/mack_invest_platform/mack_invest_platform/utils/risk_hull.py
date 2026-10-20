# utils/risk_hull.py  —  MAM v5.3 · Mesures de risque (méthodes du manuel de John Hull)
"""
Outils de la directrice des risques du comité (Aline DE MARGE), d'après les
méthodes présentées dans *Risk Management and Financial Institutions* (J. Hull) :

* VaR historique et paramétrique (99 %, 1 jour et 10 jours — règle de la racine du temps)
* Expected Shortfall 97,5 % (mesure retenue par Bâle / FRTB à la place de la VaR 99 %)
* Volatilité EWMA (λ = 0,94, méthode RiskMetrics) — plus réactive que l'écart-type simple
* Décomposition de la VaR par ligne (contributions d'Euler, VaR paramétrique)
* Backtesting de la VaR : test de couverture inconditionnelle de Kupiec (1995)
* Stress tests historiques / hypothétiques et stress test inversé
* Grecques agrégées des positions d'options

Module sans dépendance à l'interface : utilisable par la plateforme et par le job
hebdomadaire (GitHub Actions).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

LAMBDA = 0.94          # RiskMetrics
Z95, Z99 = norm.ppf(0.95), norm.ppf(0.99)


# ══════════════════════════════════════════════════════════════════════════════
#  BRIQUES
# ══════════════════════════════════════════════════════════════════════════════
def ewma_vol(r: pd.Series, lam: float = LAMBDA) -> float:
    """Volatilité journalière EWMA : σ²_n = λ σ²_{n-1} + (1-λ) u²_{n-1}."""
    r = r.dropna()
    if len(r) < 20:
        return float(r.std()) if len(r) > 1 else float("nan")
    var = float(r.iloc[:20].var())
    for u in r.iloc[20:].values:
        var = lam * var + (1 - lam) * u * u
    return math.sqrt(var)


def ewma_cov(R: pd.DataFrame, lam: float = LAMBDA) -> pd.DataFrame:
    """Matrice de covariance EWMA (journalière)."""
    R = R.dropna()
    X = R.values - R.values.mean(axis=0)
    w = lam ** np.arange(len(X))[::-1]
    w = w / w.sum()
    C = (X * w[:, None]).T @ X
    return pd.DataFrame(C, index=R.columns, columns=R.columns)


def var_hist(r: pd.Series, alpha: float = 0.99, horizon: int = 1) -> float:
    r = r.dropna()
    return float(-np.quantile(r, 1 - alpha) * math.sqrt(horizon)) if len(r) >= 30 else float("nan")


def es_hist(r: pd.Series, alpha: float = 0.975, horizon: int = 1) -> float:
    r = r.dropna()
    if len(r) < 40:
        return float("nan")
    q = np.quantile(r, 1 - alpha)
    tail = r[r <= q]
    return float(-tail.mean() * math.sqrt(horizon)) if len(tail) else float("nan")


def var_param(sigma_d: float, alpha: float = 0.99, horizon: int = 1) -> float:
    return float(norm.ppf(alpha) * sigma_d * math.sqrt(horizon))


def es_param(sigma_d: float, alpha: float = 0.975, horizon: int = 1) -> float:
    """ES d'une loi normale : σ · φ(z_α) / (1 − α)."""
    return float(sigma_d * norm.pdf(norm.ppf(alpha)) / (1 - alpha) * math.sqrt(horizon))


def euler_contributions(w: pd.Series, cov: pd.DataFrame) -> pd.Series:
    """Part de la VaR paramétrique due à chaque ligne (somme = 100 %)."""
    w = w.reindex(cov.index).fillna(0.0)
    s2 = float(w @ cov @ w)
    if s2 <= 0:
        return pd.Series(0.0, index=w.index)
    return (w * (cov @ w)) / s2


def kupiec(r: pd.Series, alpha: float = 0.99, window: int = 250, test_days: int = 250) -> dict:
    """Backtesting de la VaR historique 99 % 1 jour sur les `test_days` derniers jours :
    VaR de chaque jour calculée sur les `window` jours précédents (sans anticipation)."""
    r = r.dropna()
    n_need = window + 60
    if len(r) < n_need:
        return dict(ok=False, detail=f"historique insuffisant ({len(r)} jours, {n_need} nécessaires)")
    test = r.iloc[-min(test_days, len(r) - window):]
    exc = 0
    for i, (d, x) in enumerate(test.items()):
        pos = r.index.get_loc(d)
        past = r.iloc[pos - window:pos]
        if x < np.quantile(past, 1 - alpha):
            exc += 1
    n = len(test)
    p = 1 - alpha
    expected = n * p
    if exc == 0:
        lr = -2 * n * math.log(1 - p)
    elif exc == n:
        lr = -2 * n * math.log(p)
    else:
        ph = exc / n
        lr = -2 * ((n - exc) * math.log(1 - p) + exc * math.log(p)
                   - (n - exc) * math.log(1 - ph) - exc * math.log(ph))
    pval = float(1 - chi2.cdf(lr, 1))
    verdict = "modèle validé" if pval >= 0.05 else ("modèle trop optimiste" if exc > expected else "modèle trop prudent")
    return dict(ok=True, n=n, exceptions=exc, attendues=expected, lr=lr, p_value=pval, verdict=verdict)


# ══════════════════════════════════════════════════════════════════════════════
#  PROFIL DE RISQUE COMPLET D'UN PORTEFEUILLE
# ══════════════════════════════════════════════════════════════════════════════
def portfolio_risk(values: dict[str, float], cash: float, R: pd.DataFrame | None,
                   class_cov: pd.DataFrame | None = None, perte_max: float | None = None) -> dict:
    """
    values : {ticker: valeur $} des lignes ; cash : liquidités ; R : rendements journaliers
    des lignes (colonnes = tickers). Repli sur la covariance par classe (utils.advisor)
    si l'historique des lignes est indisponible.
    """
    from utils import advisor as A
    nav = float(cash) + sum(v for v in values.values() if v > 0)
    out = dict(nav=nav, source="", lignes=pd.DataFrame())
    if nav <= 0:
        return out
    w = pd.Series({t: v / nav for t, v in values.items() if v > 0}, dtype=float)

    cols = [t for t in w.index if R is not None and t in R.columns and R[t].notna().sum() >= 60]
    use_lines = len(cols) >= max(1, int(0.6 * len(w))) and w[cols].sum() >= 0.5 * w.sum()
    if use_lines:
        Rl = R[cols].dropna(how="all").fillna(0.0).iloc[-504:]
        wl = w[cols]
        rp = Rl @ wl.values                               # rendement du portefeuille (cash = 0 %)
        if wl.sum() < w.sum() - 1e-9:                     # lignes sans historique : approximées par leur classe moyenne
            rp = rp * (w.sum() / wl.sum())
        cov_s = Rl.cov()
        cov_e = ewma_cov(Rl)
        sig_hist = float(rp.std())
        sig_ewma = ewma_vol(rp)
        contrib = euler_contributions(wl, cov_e if np.isfinite(sig_ewma) else cov_s)
        out["source"] = f"historique des lignes ({len(Rl)} séances)"
        out["var99_1j_hist"] = var_hist(rp, .99, 1)
        out["var99_10j_hist"] = var_hist(rp, .99, 10)
        out["es975_1j_hist"] = es_hist(rp, .975, 1)
        out["es975_10j_hist"] = es_hist(rp, .975, 10)
        out["kupiec"] = kupiec(rp)
        eq = (1 + rp).cumprod()
        out["perte_max_histo"] = float((eq / eq.cummax() - 1).min())
    else:
        cls_w, _ = A.portfolio_to_classes({**{t: v for t, v in values.items() if v > 0}, "CASH": cash})
        if class_cov is None or class_cov.empty:
            return out
        sig_hist = A.port_vol(cls_w, class_cov) / math.sqrt(252)   # covariance de classe annualisée
        sig_ewma = sig_hist
        contrib = pd.Series(dtype=float)
        out["source"] = "covariance par classe d'actifs (historique des lignes indisponible)"
        out["kupiec"] = dict(ok=False, detail="historique des lignes indisponible")

    sig_d = max(x for x in (sig_hist, sig_ewma) if np.isfinite(x)) if any(np.isfinite([sig_hist, sig_ewma])) else float("nan")
    out.update(
        vol_hist_ann=sig_hist * math.sqrt(252), vol_ewma_ann=sig_ewma * math.sqrt(252),
        vol_retenue_ann=sig_d * math.sqrt(252),
        var99_1j=var_param(sig_d, .99, 1), var99_10j=var_param(sig_d, .99, 10),
        es975_1j=es_param(sig_d, .975, 1), es975_10j=es_param(sig_d, .975, 10),
        # perte potentielle sur 1 an à 95 % (comparée à la perte maximale acceptable de l'IPS)
        var95_1an=float(Z95 * sig_d * math.sqrt(252)),
    )
    out["var95_1an_usd"] = out["var95_1an"] * nav

    # Stress tests (scénarios du desk par classe d'actifs)
    cls_w, _ = A.portfolio_to_classes({**{t: v for t, v in values.items() if v > 0}, "CASH": cash})
    st_ = A.stress_test(cls_w)
    out["stress"] = st_
    worst_name, worst = st_.index[0], float(st_.iloc[0])
    out["pire_scenario"] = (worst_name, worst)
    if perte_max and worst < 0:
        out["stress_inverse"] = dict(
            facteur=perte_max / abs(worst), scenario=worst_name,
            texte=(f"Un choc égal à {perte_max / abs(worst):.1f} × « {worst_name} » vous ferait perdre "
                   f"votre perte maximale acceptable ({perte_max:.0%})."))

    lines = pd.DataFrame({"Poids": w})
    lines["Classe"] = [A.classify_ticker(t) or "Autre" for t in lines.index]
    if len(contrib):
        lines["Part du risque"] = contrib.reindex(lines.index)
    out["lignes"] = lines.sort_values("Poids", ascending=False)
    out["poids_cash"] = cash / nav
    return out


def option_greeks(options: list[dict], spots: dict[str, float], r: float = 0.04) -> dict:
    """Grecques agrégées ($) des positions d'options (Black-Scholes)."""
    from utils.options import bs_greeks
    tot = {g: 0.0 for g in ("delta", "gamma", "vega", "theta")}
    by_und: dict[str, float] = {}
    for o in options or []:
        S = float(spots.get(o.get("ticker"), o.get("spot_at_entry", 0)) or 0)
        if S <= 0:
            continue
        T = max(float(o.get("maturity_days", 30)), 1) / 365
        g = bs_greeks(S, float(o["strike"]), T, r, float(o.get("sigma", 20)) / 100, o["type"])
        q = float(o.get("n_contracts", 0)) * float(o.get("contract_mult", 100)) * (1 if o.get("action", "BUY") == "BUY" else -1)
        tot["delta"] += q * g["delta"] * S          # delta en $ d'exposition
        tot["gamma"] += q * g["gamma"] * S * S / 100
        tot["vega"] += q * g["vega"]
        tot["theta"] += q * g["theta"]
        by_und[o["ticker"]] = by_und.get(o["ticker"], 0.0) + q * g["delta"] * S
    tot["delta_par_sous_jacent"] = by_und
    return tot
