# utils/portfolio.py  —  MAM Portfolio Optimization
"""
Markowitz Mean-Variance, CVaR minimization, Efficient Frontier.
MWR (Money-Weighted Return) and TWR (Time-Weighted Return).
"""
from __future__ import annotations
import numpy as np
import pandas as pd

try:
    import cvxpy as cp
    _CVXPY = True
except ImportError:
    _CVXPY = False


# ══════════════════════════════════════════════════════════════════════════════
#  COVARIANCE & RETURNS
# ══════════════════════════════════════════════════════════════════════════════

def compute_stats(prices: pd.DataFrame) -> tuple[pd.Series, pd.DataFrame]:
    """Annual returns & covariance from daily price DataFrame."""
    daily = prices.pct_change().dropna()
    mu    = daily.mean() * 252
    cov   = daily.cov() * 252
    return mu, cov


# ══════════════════════════════════════════════════════════════════════════════
#  MARKOWITZ  (Max Sharpe / Min Variance)
# ══════════════════════════════════════════════════════════════════════════════

def markowitz_optimize(mu: pd.Series, cov: pd.DataFrame,
                       rf: float = 0.04,
                       objective: str = "sharpe") -> dict | None:
    """
    Solve Markowitz optimization.
    objective: 'sharpe' | 'min_vol'
    Returns dict with weights, expected return, volatility, sharpe.
    """
    n = len(mu)
    if n < 2:
        return None

    if not _CVXPY:
        # Fallback: equal weight
        w = np.ones(n) / n
        ret = float(mu.values @ w)
        vol = float(np.sqrt(w @ cov.values @ w))
        return {"weights": dict(zip(mu.index, w)),
                "return": ret, "volatility": vol,
                "sharpe": (ret - rf) / vol if vol else 0}

    w   = cp.Variable(n)
    ret = mu.values @ w
    vol = cp.quad_form(w, cov.values)
    constraints = [cp.sum(w) == 1, w >= 0]

    if objective == "sharpe":
        # Maximize Sharpe via parametric approach (maximise return - λ*vol²)
        # We scan multiple risk-aversion levels and pick max Sharpe
        best = None
        for lam in np.logspace(-2, 3, 60):
            prob = cp.Problem(cp.Maximize(ret - lam * vol), constraints)
            try:
                prob.solve(warm_start=True)
            except Exception:
                continue
            if w.value is None:
                continue
            wv  = np.clip(w.value, 0, 1)
            wv /= wv.sum() + 1e-12
            r_  = float(mu.values @ wv)
            v_  = float(np.sqrt(wv @ cov.values @ wv))
            sr_ = (r_ - rf) / v_ if v_ > 0 else -999
            if best is None or sr_ > best["sharpe"]:
                best = {"weights": dict(zip(mu.index, wv.tolist())),
                        "return": r_, "volatility": v_, "sharpe": sr_}
        return best

    else:  # min_vol
        prob = cp.Problem(cp.Minimize(vol), constraints)
        try:
            prob.solve()
        except Exception:
            return None
        if w.value is None:
            return None
        wv = np.clip(w.value, 0, 1)
        wv /= wv.sum() + 1e-12
        r_ = float(mu.values @ wv)
        v_ = float(np.sqrt(wv @ cov.values @ wv))
        return {"weights": dict(zip(mu.index, wv.tolist())),
                "return": r_, "volatility": v_,
                "sharpe": (r_ - rf) / v_ if v_ > 0 else 0}


# ══════════════════════════════════════════════════════════════════════════════
#  CVaR OPTIMIZATION
# ══════════════════════════════════════════════════════════════════════════════

def cvar_optimize(daily_returns: pd.DataFrame,
                  alpha: float = 0.05,
                  target_return: float | None = None) -> dict | None:
    """Minimize CVaR (Expected Shortfall) at confidence level (1-alpha)."""
    n_assets  = daily_returns.shape[1]
    scenarios = daily_returns.values          # T × N
    T         = scenarios.shape[0]

    if not _CVXPY or T < 30 or n_assets < 2:
        return None

    w  = cp.Variable(n_assets, nonneg=True)
    z  = cp.Variable(T)
    VaR = cp.Variable()

    portfolio_rets = scenarios @ w
    constraints = [
        cp.sum(w) == 1,
        z >= -portfolio_rets - VaR,
        z >= 0,
    ]
    if target_return is not None:
        ann_mu = daily_returns.mean().values * 252
        constraints.append(ann_mu @ w >= target_return)

    cvar = VaR + (1 / (alpha * T)) * cp.sum(z)
    prob = cp.Problem(cp.Minimize(cvar), constraints)
    try:
        prob.solve()
    except Exception:
        return None
    if w.value is None:
        return None

    wv = np.clip(w.value, 0, 1)
    wv /= wv.sum() + 1e-12
    ann_ret = float(daily_returns.mean().values * 252 @ wv)
    ann_vol = float(np.sqrt(wv @ (daily_returns.cov().values * 252) @ wv))
    return {"weights": dict(zip(daily_returns.columns, wv.tolist())),
            "return": ann_ret, "volatility": ann_vol,
            "cvar": float(cvar.value) if cvar.value else 0,
            "sharpe": ann_ret / ann_vol if ann_vol > 0 else 0}


# ══════════════════════════════════════════════════════════════════════════════
#  EFFICIENT FRONTIER
# ══════════════════════════════════════════════════════════════════════════════

def efficient_frontier(mu: pd.Series, cov: pd.DataFrame,
                       n_points: int = 60) -> pd.DataFrame:
    """
    Generate efficient frontier points.
    Returns DataFrame with columns: return, volatility, sharpe.
    """
    n = len(mu)
    rows = []

    if not _CVXPY or n < 2:
        # Monte Carlo random portfolios as fallback
        for _ in range(400):
            w = np.random.dirichlet(np.ones(n))
            r = float(mu.values @ w)
            v = float(np.sqrt(w @ cov.values @ w))
            rows.append({"return": r, "volatility": v,
                         "sharpe": r / v if v > 0 else 0})
        return pd.DataFrame(rows)

    w   = cp.Variable(n)
    vol = cp.quad_form(w, cov.values)
    constraints_base = [cp.sum(w) == 1, w >= 0]

    target_rets = np.linspace(float(mu.min()), float(mu.max()), n_points)
    for tr in target_rets:
        constraints = constraints_base + [mu.values @ w >= tr]
        prob = cp.Problem(cp.Minimize(vol), constraints)
        try:
            prob.solve(warm_start=True)
        except Exception:
            continue
        if w.value is None:
            continue
        wv  = np.clip(w.value, 0, 1)
        wv /= wv.sum() + 1e-12
        r_  = float(mu.values @ wv)
        v_  = float(np.sqrt(wv @ cov.values @ wv))
        rows.append({"return": r_, "volatility": v_,
                     "sharpe": r_ / v_ if v_ > 0 else 0})

    # Also add random portfolios for interior scatter
    for _ in range(200):
        w2 = np.random.dirichlet(np.ones(n))
        r2 = float(mu.values @ w2)
        v2 = float(np.sqrt(w2 @ cov.values @ w2))
        rows.append({"return": r2, "volatility": v2,
                     "sharpe": r2 / v2 if v2 > 0 else 0})

    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  MWR / TWR
# ══════════════════════════════════════════════════════════════════════════════

def compute_twr(sub_period_returns: list[float]) -> float:
    """Time-Weighted Return = product of (1 + ri) - 1."""
    p = 1.0
    for r in sub_period_returns:
        p *= (1 + r)
    return p - 1.0


def compute_mwr(cash_flows: list[tuple[int, float]],
                final_value: float,
                max_iter: int = 500) -> float | None:
    """
    Money-Weighted Return (IRR of cash flows).
    cash_flows: [(day_offset, amount)]  negative = outflow
    final_value: portfolio value at end (positive)
    Returns annualised MWR.
    """
    if not cash_flows:
        return None
    all_cf = list(cash_flows) + [(max(d for d, _ in cash_flows), final_value)]

    r = 0.08 / 365  # initial guess
    for _ in range(max_iter):
        npv  = sum(cf / (1 + r) ** d for d, cf in all_cf)
        dnpv = sum(-d * cf / (1 + r) ** (d + 1) for d, cf in all_cf)
        if abs(dnpv) < 1e-15:
            return None
        r_new = r - npv / dnpv
        if abs(r_new - r) < 1e-12:
            return (1 + r_new) ** 365 - 1
        r = r_new
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMISEURS SCIPY (sans dépendance à cvxpy / ECOS)
#  cvxpy >= 1.6 n'embarque plus ECOS : les anciens appels `solver=cp.ECOS`
#  échouaient silencieusement (solveur par défaut désormais). Ces versions SciPy servent de moteur
#  principal pour l'auto-portefeuille et de repli pour l'optimiseur.
# ══════════════════════════════════════════════════════════════════════════════
from scipy.optimize import minimize, linprog
from scipy.cluster.hierarchy import linkage, leaves_list
from scipy.spatial.distance import squareform


def shrink_cov(daily: pd.DataFrame) -> pd.DataFrame:
    """Covariance annualisée Ledoit-Wolf (plus stable que l'estimateur empirique)."""
    d = daily.dropna()
    try:
        from sklearn.covariance import LedoitWolf
        c = LedoitWolf().fit(d.values).covariance_ * 252
        return pd.DataFrame(c, index=d.columns, columns=d.columns)
    except Exception:
        return d.cov() * 252


def _class_constraints(tickers, class_of: dict | None, class_bounds: dict | None):
    cons = []
    if not class_of or not class_bounds:
        return cons
    for cls, (lo, hi) in class_bounds.items():
        idx = [i for i, t in enumerate(tickers) if class_of.get(t) == cls]
        if not idx:
            continue
        if lo > 0:
            cons.append({"type": "ineq", "fun": lambda w, idx=idx, lo=lo: w[idx].sum() - lo})
        if hi < 1:
            cons.append({"type": "ineq", "fun": lambda w, idx=idx, hi=hi: hi - w[idx].sum()})
    return cons


def _feasible_start(n, bounds, class_of, class_bounds, tickers):
    w = np.array([min(max(1.0 / n, b[0]), b[1]) for b in bounds])
    return w / w.sum()


def optimize_scipy(mu: pd.Series, cov: pd.DataFrame, method: str = "utility",
                   max_w: float = 0.25, min_w: float = 0.0, lam: float = 4.0,
                   target_vol: float | None = None, rf: float = 0.0,
                   class_of: dict | None = None, class_bounds: dict | None = None,
                   budgets: pd.Series | None = None) -> pd.Series:
    """
    method : 'utility'  max w·μ − λ/2·wΣw (+ plafond de volatilité)
             'sharpe'   max (w·μ − rf)/σ
             'min_vol'  min wΣw
             'risk_parity' contributions au risque égales (ou `budgets`)
    Contraintes : Σw = 1, min_w ≤ w ≤ max_w, bornes par classe d'actifs.
    """
    tickers = list(mu.index)
    n = len(tickers)
    S = cov.loc[tickers, tickers].values
    m = mu.values
    bounds = [(min_w, max_w)] * n
    if max_w * n < 1:
        bounds = [(min_w, 1.0 / n + 1e-9)] * n
    cons = [{"type": "eq", "fun": lambda w: w.sum() - 1}]
    cons += _class_constraints(tickers, class_of, class_bounds)
    if target_vol and method in ("utility", "sharpe"):
        cons.append({"type": "ineq", "fun": lambda w: target_vol ** 2 - w @ S @ w})
    w0 = _feasible_start(n, bounds, class_of, class_bounds, tickers)

    if method == "min_vol":
        obj = lambda w: w @ S @ w * 100
    elif method == "sharpe":
        obj = lambda w: -(w @ m - rf) / np.sqrt(max(w @ S @ w, 1e-12))
    elif method == "risk_parity":
        b = (budgets.reindex(tickers).fillna(1.0).values if budgets is not None else np.ones(n))
        b = b / b.sum()

        def obj(w):
            pv = max(w @ S @ w, 1e-12)
            rc = w * (S @ w) / pv
            return float(((rc - b) ** 2).sum() * 1e3)
    else:
        obj = lambda w: -(w @ m - 0.5 * lam * (w @ S @ w))

    res = minimize(obj, w0, method="SLSQP", bounds=bounds, constraints=cons,
                   options={"maxiter": 500, "ftol": 1e-10})
    w = res.x if res.success or res.x is not None else w0
    if not res.success:
        # relâche les contraintes de classe / volatilité si infaisable
        res2 = minimize(obj, w0, method="SLSQP", bounds=bounds,
                        constraints=[cons[0]], options={"maxiter": 500})
        if res2.x is not None and (not np.isfinite(w).all() or obj(res2.x) < obj(w)):
            w = res2.x if res2.success else w
    w = np.clip(w, 0, 1)
    w[w < 1e-4] = 0
    w = w / w.sum() if w.sum() > 0 else np.ones(n) / n
    return pd.Series(w, index=tickers)


def hrp_weights(daily: pd.DataFrame) -> pd.Series:
    """Hierarchical Risk Parity (López de Prado, 2016)."""
    d = daily.dropna()
    cov, corr = d.cov().values, d.corr().values
    dist = np.sqrt(np.clip((1 - corr) / 2, 0, 1))
    np.fill_diagonal(dist, 0)
    order = leaves_list(linkage(squareform(dist, checks=False), "single"))
    w = pd.Series(1.0, index=order)
    clusters = [list(order)]
    while clusters:
        clusters = [c[j:k] for c in clusters for j, k in ((0, len(c) // 2), (len(c) // 2, len(c)))
                    if len(c) > 1]
        for i in range(0, len(clusters), 2):
            c0, c1 = clusters[i], clusters[i + 1]

            def cvar(c):
                sub = cov[np.ix_(c, c)]
                iv = 1 / np.diag(sub)
                iv /= iv.sum()
                return iv @ sub @ iv
            v0, v1 = cvar(c0), cvar(c1)
            a = 1 - v0 / (v0 + v1)
            w[c0] *= a
            w[c1] *= 1 - a
    out = pd.Series(w.sort_index().values, index=d.columns)
    return out / out.sum()


def min_cvar_lp(daily: pd.DataFrame, alpha: float = 0.05, max_w: float = 1.0) -> pd.Series:
    """Minimisation de la CVaR (Rockafellar-Uryasev) en programmation linéaire (HiGHS)."""
    R = daily.dropna().values
    T, n = R.shape
    # variables : w (n), VaR (1), z (T)
    c = np.concatenate([np.zeros(n), [1.0], np.full(T, 1 / (alpha * T))])
    A_ub = np.hstack([-R, -np.ones((T, 1)), -np.eye(T)])
    b_ub = np.zeros(T)
    A_eq = np.concatenate([np.ones(n), [0], np.zeros(T)])[None, :]
    bounds = [(0, max_w)] * n + [(None, None)] + [(0, None)] * T
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=[1], bounds=bounds, method="highs")
    if not res.success:
        return pd.Series(np.ones(n) / n, index=daily.columns)
    w = np.clip(res.x[:n], 0, 1)
    return pd.Series(w / w.sum(), index=daily.columns)


def portfolio_stats(w: pd.Series, mu: pd.Series, cov: pd.DataFrame, rf: float = 0.0) -> dict:
    w = w.reindex(mu.index).fillna(0)
    r = float(w @ mu)
    v = float(np.sqrt(w @ cov.loc[mu.index, mu.index] @ w))
    return {"return": r, "volatility": v, "sharpe": (r - rf) / v if v > 0 else 0.0}


def risk_contributions(w: pd.Series, cov: pd.DataFrame) -> pd.Series:
    t = w.index
    S = cov.loc[t, t].values
    pv = w.values @ S @ w.values
    return pd.Series(w.values * (S @ w.values) / pv if pv > 0 else 0, index=t)


def frontier_scipy(mu: pd.Series, cov: pd.DataFrame, n_points: int = 30,
                   max_w: float = 1.0) -> pd.DataFrame:
    rows = []
    tickers = list(mu.index)
    S = cov.loc[tickers, tickers].values
    n = len(tickers)
    lo = float(portfolio_stats(optimize_scipy(mu, cov, "min_vol", max_w=max_w), mu, cov)["return"])
    hi = float(mu.max()) if max_w >= 1 else float(np.sort(mu.values)[::-1][:max(1, int(np.ceil(1 / max_w)))].mean())
    for tr in np.linspace(lo, hi, n_points):
        cons = [{"type": "eq", "fun": lambda w: w.sum() - 1},
                {"type": "ineq", "fun": lambda w, tr=tr: w @ mu.values - tr}]
        res = minimize(lambda w: w @ S @ w, np.ones(n) / n, method="SLSQP",
                       bounds=[(0, max_w)] * n, constraints=cons, options={"maxiter": 300})
        if res.success:
            w = np.clip(res.x, 0, 1)
            w /= w.sum()
            r, v = float(w @ mu.values), float(np.sqrt(w @ S @ w))
            rows.append({"return": r, "volatility": v, "sharpe": r / v if v > 0 else 0})
    return pd.DataFrame(rows)
