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


# ══════════════════════════════════════════════════════════════════════════════
#  CARNET DE POSITIONS D'OPTIONS (v5.5) — une ligne par instrument
# ══════════════════════════════════════════════════════════════════════════════
# Un même instrument (sous-jacent, call/put, prix d'exercice, échéance) n'occupe qu'UNE ligne :
# un achat supplémentaire augmente la quantité (prime moyenne pondérée), une vente réduit la
# quantité ou clôture la ligne, au lieu d'ajouter une nouvelle ligne en double.
from datetime import datetime as _dt, timedelta as _td

EXPIRY_TOLERANCE_DAYS = 7      # échéances continues : deux échéances à ±7 jours = même contrat


def _entry_date(o: dict) -> _dt:
    try:
        return _dt.strptime(str(o.get("date", ""))[:16], "%Y-%m-%d %H:%M")
    except ValueError:
        try:
            return _dt.fromisoformat(str(o.get("date", ""))[:19])
        except ValueError:
            return _dt.now()


def option_expiry(o: dict) -> _dt:
    return _entry_date(o) + _td(days=float(o.get("maturity_days", 30)))


def remaining_days(o: dict, now: _dt | None = None) -> float:
    return (option_expiry(o) - (now or _dt.now())).total_seconds() / 86400


def same_instrument(a: dict, b: dict) -> bool:
    return (str(a.get("ticker")).upper() == str(b.get("ticker")).upper()
            and str(a.get("type")).lower() == str(b.get("type")).lower()
            and abs(float(a.get("strike", 0)) - float(b.get("strike", 0))) < 1e-6
            and abs((option_expiry(a) - option_expiry(b)).days) <= EXPIRY_TOLERANCE_DAYS)


def book_option(port: dict, leg: dict) -> str:
    """Enregistre une jambe d'option dans le carnet du portefeuille SANS dupliquer l'instrument.
    `leg` a le format d'une ligne d'options (date, ticker, type, action, strike, maturity_days, sigma,
    n_contracts, contract_mult, premium…). Le cash est géré par l'appelant.
    Renvoie : « nouvelle ligne » | « renforcement » | « réduction » | « clôture » | « retournement »."""
    opts = port.setdefault("options", [])
    n_new = int(abs(leg.get("n_contracts", 0)))
    if n_new <= 0:
        return "aucun changement"
    leg = {**leg, "n_contracts": n_new}
    match = next((o for o in opts if same_instrument(o, leg) and int(o.get("n_contracts", 0)) > 0), None)
    if match is None:
        opts.append(leg)
        return "nouvelle ligne"
    mult = float(match.get("contract_mult", 100))
    n_old = int(match.get("n_contracts", 0))
    if str(match.get("action", "BUY")).upper() == str(leg.get("action", "BUY")).upper():
        n = n_old + n_new
        match["premium"] = round((float(match["premium"]) * n_old + float(leg["premium"]) * n_new) / n, 6)
        match["n_contracts"] = n
        match["total_premium"] = round(match["premium"] * n * mult, 2)
        match["sigma"] = leg.get("sigma", match.get("sigma"))
        match["derniere_modification"] = leg.get("date")
        return "renforcement"
    if n_new < n_old:                                   # vente partielle d'une position détenue (ou rachat partiel)
        match["n_contracts"] = n_old - n_new
        match["total_premium"] = round(float(match["premium"]) * match["n_contracts"] * mult, 2)
        match["derniere_modification"] = leg.get("date")
        return "réduction"
    opts.remove(match)
    if n_new == n_old:
        return "clôture"
    opts.append({**leg, "n_contracts": n_new - n_old,
                 "total_premium": round(float(leg["premium"]) * (n_new - n_old) * mult, 2)})
    return "retournement"


def consolidate_options(port: dict) -> int:
    """Regroupe les lignes déjà en double (même instrument, même sens). Renvoie le nombre de lignes fusionnées."""
    opts = port.get("options", []) or []
    merged, before = [], len(opts)
    for o in opts:
        tgt = next((m for m in merged if same_instrument(m, o)
                    and str(m.get("action")).upper() == str(o.get("action")).upper()), None)
        if tgt is None:
            merged.append(dict(o))
            continue
        n1, n2 = int(tgt["n_contracts"]), int(o["n_contracts"])
        tgt["premium"] = round((float(tgt["premium"]) * n1 + float(o["premium"]) * n2) / (n1 + n2), 6)
        tgt["n_contracts"] = n1 + n2
        tgt["total_premium"] = round(tgt["premium"] * tgt["n_contracts"] * float(tgt.get("contract_mult", 100)), 2)
    port["options"] = merged
    return before - len(merged)
