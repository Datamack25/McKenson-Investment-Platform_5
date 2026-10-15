# utils/options.py  —  MAM Options Engine
"""
Black-Scholes pricing, full Greeks, implied volatility, payoff diagrams.
"""
from __future__ import annotations
import math
import numpy as np
from scipy.stats import norm
from scipy.optimize import brentq


# ══════════════════════════════════════════════════════════════════════════════
#  BLACK-SCHOLES CORE
# ══════════════════════════════════════════════════════════════════════════════

def _d1d2(S: float, K: float, T: float, r: float, sigma: float):
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return d1, d2


def bs_price(S: float, K: float, T: float, r: float,
             sigma: float, opt: str = "call") -> float:
    """European option price — Black-Scholes."""
    if T <= 0:
        return max(S - K, 0.0) if opt == "call" else max(K - S, 0.0)
    d1, d2 = _d1d2(S, K, T, r, sigma)
    if opt == "call":
        return S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
    return K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_greeks(S: float, K: float, T: float, r: float,
              sigma: float, opt: str = "call") -> dict[str, float]:
    """Full Greeks: delta, gamma, theta, vega, rho."""
    if T <= 0 or sigma <= 0:
        return {g: 0.0 for g in ["delta", "gamma", "theta", "vega", "rho"]}
    d1, d2 = _d1d2(S, K, T, r, sigma)
    nd1    = norm.pdf(d1)
    sqT    = math.sqrt(T)
    eKrT   = K * math.exp(-r * T)

    gamma = nd1 / (S * sigma * sqT)
    vega  = S * nd1 * sqT / 100          # per 1% vol move

    if opt == "call":
        delta = norm.cdf(d1)
        theta = (-(S * nd1 * sigma) / (2 * sqT)
                 - r * eKrT * norm.cdf(d2)) / 365
        rho   = eKrT * T * norm.cdf(d2) / 100
    else:
        delta = norm.cdf(d1) - 1
        theta = (-(S * nd1 * sigma) / (2 * sqT)
                 + r * eKrT * norm.cdf(-d2)) / 365
        rho   = -eKrT * T * norm.cdf(-d2) / 100

    return {"delta": delta, "gamma": gamma,
            "theta": theta, "vega": vega, "rho": rho}


def implied_vol(market_price: float, S: float, K: float, T: float,
                r: float, opt: str = "call") -> float | None:
    """Compute implied volatility via Brent solver."""
    if T <= 0 or market_price <= 0:
        return None
    try:
        def objective(sigma):
            return bs_price(S, K, T, r, sigma, opt) - market_price
        iv = brentq(objective, 1e-6, 10.0, xtol=1e-8, maxiter=200)
        return iv
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  STRATEGY PAYOFF ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def payoff_at_expiry(legs: list[dict], spots: np.ndarray) -> np.ndarray:
    """
    Compute strategy P&L at expiry across a range of spot prices.
    Each leg dict: {type:'call'|'put'|'stock', K, qty, premium, entry?}
    qty > 0 = long; qty < 0 = short
    """
    total = np.zeros_like(spots, dtype=float)
    for leg in legs:
        qty  = leg["qty"]
        ltype = leg["type"]
        prem = leg.get("premium", 0.0)
        if ltype == "call":
            total += qty * (np.maximum(spots - leg["K"], 0) - prem)
        elif ltype == "put":
            total += qty * (np.maximum(leg["K"] - spots, 0) - prem)
        elif ltype == "stock":
            entry = leg.get("entry", spots[len(spots) // 2])
            total += qty * (spots - entry)
    return total


def build_strategy_legs(name: str, S: float, K: float,
                         T: float, r: float, sig: float) -> list[dict]:
    """Return leg list for a named strategy."""
    def c(k): return bs_price(S, k, T, r, sig, "call")
    def p(k): return bs_price(S, k, T, r, sig, "put")

    strats = {
        "Protective Put": [
            {"type": "stock", "qty": 1,  "entry": S},
            {"type": "put",   "qty": 1,  "K": K,         "premium": p(K)},
        ],
        "Covered Call": [
            {"type": "stock", "qty": 1,  "entry": S},
            {"type": "call",  "qty": -1, "K": K*1.05,    "premium": c(K*1.05)},
        ],
        "Collar": [
            {"type": "stock", "qty": 1,  "entry": S},
            {"type": "put",   "qty": 1,  "K": K*0.95,    "premium": p(K*0.95)},
            {"type": "call",  "qty": -1, "K": K*1.05,    "premium": c(K*1.05)},
        ],
        "Long Call": [
            {"type": "call",  "qty": 1,  "K": K,         "premium": c(K)},
        ],
        "Long Put": [
            {"type": "put",   "qty": 1,  "K": K,         "premium": p(K)},
        ],
        "Bull Call Spread": [
            {"type": "call",  "qty": 1,  "K": K,         "premium": c(K)},
            {"type": "call",  "qty": -1, "K": K*1.10,    "premium": c(K*1.10)},
        ],
        "Bear Put Spread": [
            {"type": "put",   "qty": 1,  "K": K,         "premium": p(K)},
            {"type": "put",   "qty": -1, "K": K*0.90,    "premium": p(K*0.90)},
        ],
        "Long Straddle": [
            {"type": "call",  "qty": 1,  "K": K,         "premium": c(K)},
            {"type": "put",   "qty": 1,  "K": K,         "premium": p(K)},
        ],
        "Long Strangle": [
            {"type": "call",  "qty": 1,  "K": K*1.05,    "premium": c(K*1.05)},
            {"type": "put",   "qty": 1,  "K": K*0.95,    "premium": p(K*0.95)},
        ],
        "Iron Condor": [
            {"type": "put",   "qty": -1, "K": K*0.95,    "premium": p(K*0.95)},
            {"type": "put",   "qty": 1,  "K": K*0.90,    "premium": p(K*0.90)},
            {"type": "call",  "qty": -1, "K": K*1.05,    "premium": c(K*1.05)},
            {"type": "call",  "qty": 1,  "K": K*1.10,    "premium": c(K*1.10)},
        ],
        "Butterfly Spread": [
            {"type": "call",  "qty": 1,  "K": K*0.95,    "premium": c(K*0.95)},
            {"type": "call",  "qty": -2, "K": K,         "premium": c(K)},
            {"type": "call",  "qty": 1,  "K": K*1.05,    "premium": c(K*1.05)},
        ],
        "Calendar Spread": [
            # Short near, long far — simplified same strike
            {"type": "call",  "qty": -1, "K": K,         "premium": c(K) * 0.6},
            {"type": "call",  "qty": 1,  "K": K,         "premium": c(K)},
        ],
        "Short Straddle": [
            {"type": "call",  "qty": -1, "K": K,         "premium": c(K)},
            {"type": "put",   "qty": -1, "K": K,         "premium": p(K)},
        ],
        "Risk Reversal": [
            {"type": "put",   "qty": -1, "K": K*0.95,    "premium": p(K*0.95)},
            {"type": "call",  "qty": 1,  "K": K*1.05,    "premium": c(K*1.05)},
        ],
    }
    return strats.get(name, [{"type": "call", "qty": 1, "K": K, "premium": c(K)}])


STRATEGY_META: dict[str, dict] = {
    "Protective Put":   {"cat": "Hedging",    "color": "#00d4ff", "use": "Protéger une position longue contre la baisse"},
    "Covered Call":     {"cat": "Income",     "color": "#00ff88", "use": "Générer des revenus sur une position longue"},
    "Collar":           {"cat": "Hedging",    "color": "#7c3aed", "use": "Limiter gains ET pertes — coût quasi-nul"},
    "Long Call":        {"cat": "Bullish",    "color": "#00ff88", "use": "Levier haussier — risque limité à la prime"},
    "Long Put":         {"cat": "Bearish",    "color": "#ff3b6b", "use": "Levier baissier — spéculation ou couverture"},
    "Bull Call Spread": {"cat": "Bullish",    "color": "#00d4ff", "use": "Vue haussière modérée — coût réduit"},
    "Bear Put Spread":  {"cat": "Bearish",    "color": "#ff8c00", "use": "Vue baissière modérée — budget limité"},
    "Long Straddle":    {"cat": "Volatility", "color": "#ffd700", "use": "Anticiper un gros mouvement (direction inconnue)"},
    "Long Strangle":    {"cat": "Volatility", "color": "#ffd700", "use": "Straddle moins cher — seuil plus éloigné"},
    "Iron Condor":      {"cat": "Neutral",    "color": "#7c3aed", "use": "Marché stable — collecte de prime"},
    "Butterfly Spread": {"cat": "Neutral",    "color": "#ff8c00", "use": "Conviction forte sur un niveau de prix précis"},
    "Calendar Spread":  {"cat": "Neutral",    "color": "#94a3b8", "use": "Jouer la décroissance temporelle"},
    "Short Straddle":   {"cat": "Neutral",    "color": "#ff3b6b", "use": "Vendre la volatilité — risque illimité"},
    "Risk Reversal":    {"cat": "Bullish",    "color": "#ff8c00", "use": "Exposition haussière — financement par put vendu"},
}
