# utils/option_strategies.py  —  MAM v5.1 · Stratégies d'options selon le régime de marché
"""
* Catalogue de stratégies multi-jambes (couverture, risque limité, vente couverte)
  avec, pour chacune : vue de marché, niveau de risque, moment opportun.
* Construction des jambes (strikes arrondis, primes Black-Scholes).
* Analyse complète d'un ensemble de jambes : prime nette, gain / perte max,
  points morts, grecques agrégées, capital immobilisé.
* Recommandations selon le régime de marché (nomenclature de utils.advisor)
  et le niveau de volatilité.

Aucune stratégie à perte illimitée (vente de call non couverte, short straddle…)
n'est proposée : elles sont bloquées par utils.compliance.
"""
from __future__ import annotations

import math

import numpy as np

from utils.options import bs_price, bs_greeks

# ══════════════════════════════════════════════════════════════════════════════
#  CATALOGUE
# ══════════════════════════════════════════════════════════════════════════════
# legs : (type, sens, strike en multiple du spot)   sens +1 = achat, -1 = vente
# stock : nombre de titres par contrat (1 = un lot de `mult` titres) détenus / achetés
CATALOG: dict[str, dict] = {
    "Put de protection": {
        "en": "Protective Put", "vue": "Garder ses titres en se protégeant d'une baisse",
        "niveau": "couverture", "stock": 1,
        "legs": [("put", +1, 0.95)],
        "quand": "Marché nerveux ou fin de cycle, quand on veut garder ses actions mais limiter la perte.",
        "risque": "Perte limitée à (cours − strike du put) + prime. Coût : la prime, comme une assurance.",
    },
    "Call couvert": {
        "en": "Covered Call", "vue": "Neutre à légèrement haussière — générer un revenu",
        "niveau": "couverture", "stock": 1,
        "legs": [("call", -1, 1.05)],
        "quand": "Marché calme ou en hausse lente, volatilité élevée (primes généreuses).",
        "risque": "Gain plafonné au strike du call ; le risque de baisse reste celui des titres, amorti par la prime.",
    },
    "Tunnel (collar)": {
        "en": "Collar", "vue": "Protéger ses titres pour un coût quasi nul",
        "niveau": "couverture", "stock": 1,
        "legs": [("put", +1, 0.95), ("call", -1, 1.05)],
        "quand": "Ralentissement ou incertitude : on finance la protection en renonçant à une partie de la hausse.",
        "risque": "Perte et gain bornés entre les deux strikes.",
    },
    "Achat de call": {
        "en": "Long Call", "vue": "Haussière",
        "niveau": "risque_limite", "stock": 0,
        "legs": [("call", +1, 1.00)],
        "quand": "Forte conviction haussière, volatilité implicite basse (options bon marché).",
        "risque": "Perte maximale = prime payée.",
    },
    "Achat de put": {
        "en": "Long Put", "vue": "Baissière",
        "niveau": "risque_limite", "stock": 0,
        "legs": [("put", +1, 1.00)],
        "quand": "Anticipation d'une baisse marquée.",
        "risque": "Perte maximale = prime payée.",
    },
    "Spread haussier (call)": {
        "en": "Bull Call Spread", "vue": "Modérément haussière",
        "niveau": "risque_limite", "stock": 0,
        "legs": [("call", +1, 1.00), ("call", -1, 1.08)],
        "quand": "Expansion économique, hausse attendue mais limitée ; réduit le coût d'un achat de call.",
        "risque": "Perte maximale = prime nette ; gain maximal = écart des strikes − prime.",
    },
    "Spread baissier (put)": {
        "en": "Bear Put Spread", "vue": "Modérément baissière",
        "niveau": "risque_limite", "stock": 0,
        "legs": [("put", +1, 1.00), ("put", -1, 0.92)],
        "quand": "Ralentissement / stagflation : profiter d'une baisse modérée à coût réduit.",
        "risque": "Perte maximale = prime nette ; gain maximal = écart des strikes − prime.",
    },
    "Straddle acheteur": {
        "en": "Long Straddle", "vue": "Gros mouvement attendu, direction inconnue",
        "niveau": "risque_limite", "stock": 0,
        "legs": [("call", +1, 1.00), ("put", +1, 1.00)],
        "quand": "Avant un événement majeur (banque centrale, élection) si la volatilité implicite est basse.",
        "risque": "Perte maximale = les deux primes, si le cours finit au strike.",
    },
    "Strangle acheteur": {
        "en": "Long Strangle", "vue": "Gros mouvement attendu, à moindre coût",
        "niveau": "risque_limite", "stock": 0,
        "legs": [("call", +1, 1.05), ("put", +1, 0.95)],
        "quand": "Comme le straddle, moins cher mais il faut un mouvement plus ample.",
        "risque": "Perte maximale = les deux primes.",
    },
    "Iron condor": {
        "en": "Iron Condor", "vue": "Marché sans tendance",
        "niveau": "risque_limite", "stock": 0,
        "legs": [("put", +1, 0.90), ("put", -1, 0.95), ("call", -1, 1.05), ("call", +1, 1.10)],
        "quand": "Marché stable avec volatilité implicite élevée : on encaisse des primes.",
        "risque": "Gain maximal = prime nette encaissée ; perte maximale = écart d'un côté − prime.",
    },
    "Papillon (butterfly)": {
        "en": "Butterfly", "vue": "Le cours restera proche d'un niveau",
        "niveau": "risque_limite", "stock": 0,
        "legs": [("call", +1, 0.95), ("call", -2, 1.00), ("call", +1, 1.05)],
        "quand": "Conviction forte sur un niveau de prix à l'échéance, faible coût.",
        "risque": "Perte maximale = prime nette payée.",
    },
    "Vente de put couverte (cash-secured)": {
        "en": "Cash-Secured Put", "vue": "Neutre à haussière — acheter moins cher",
        "niveau": "vente_couverte", "stock": 0,
        "legs": [("put", -1, 0.95)],
        "quand": "Envie d'acheter le titre plus bas ; on est payé pour attendre. Liquidités bloquées en garantie.",
        "risque": "Perte maximale = strike − prime (si le titre tombe à zéro), entièrement couverte par le cash.",
    },
}

# Libellés lisibles des niveaux d'usage des dérivés
LEVEL_LABEL = {
    "couverture": "Couverture de titres détenus",
    "risque_limite": "Stratégies à risque limité",
    "vente_couverte": "Ventes d'options couvertes",
    "illimite": "Risque illimité (interdit)",
}

# ══════════════════════════════════════════════════════════════════════════════
#  RÉGIMES DE MARCHÉ → STRATÉGIES
# ══════════════════════════════════════════════════════════════════════════════
REGIMES = [
    "Expansion désinflationniste", "Surchauffe / reflation", "Ralentissement désinflationniste",
    "Stagflation", "Aversion au risque", "Marché sans tendance",
]

REGIME_STRATEGIES: dict[str, list[tuple[str, str]]] = {
    "Expansion désinflationniste": [
        ("Spread haussier (call)", "Croissance solide : on joue la hausse avec un coût et un risque maîtrisés."),
        ("Call couvert", "Sur des titres déjà détenus : on encaisse une prime en acceptant de plafonner la hausse."),
        ("Achat de call", "Conviction forte sur un titre, si la volatilité implicite est basse."),
    ],
    "Surchauffe / reflation": [
        ("Spread haussier (call)", "Cycliques et matières premières favorisées : hausse modérée attendue."),
        ("Tunnel (collar)", "Les taux montent : on protège les actions détenues pour un coût quasi nul."),
        ("Call couvert", "Volatilité plus élevée : primes attractives sur les titres détenus."),
    ],
    "Ralentissement désinflationniste": [
        ("Tunnel (collar)", "On protège le portefeuille sans payer de prime nette."),
        ("Spread baissier (put)", "Baisse modérée attendue sur les indices actions."),
        ("Put de protection", "Assurance sur les positions les plus exposées."),
    ],
    "Stagflation": [
        ("Put de protection", "Environnement le plus difficile pour les actions : priorité à la protection."),
        ("Spread baissier (put)", "Profiter d'une baisse des actions à coût réduit."),
        ("Tunnel (collar)", "Bornage des pertes sur les titres conservés."),
    ],
    "Aversion au risque": [
        ("Put de protection", "Stress de marché élevé : on assure le capital."),
        ("Spread baissier (put)", "Baisse attendue ; la volatilité élevée rend l'achat sec de put cher, le spread le finance."),
        ("Tunnel (collar)", "Protection financée par la vente d'un call."),
    ],
    "Marché sans tendance": [
        ("Iron condor", "Cours stable : on encaisse des primes avec une perte maximale connue."),
        ("Papillon (butterfly)", "Pari peu coûteux sur un cours stable autour du niveau actuel."),
        ("Call couvert", "Revenu régulier sur des titres détenus."),
    ],
}


def recommend(regime: str, vix: float | None = None) -> list[dict]:
    """Stratégies adaptées au régime, ajustées au niveau de volatilité (VIX)."""
    recs = [dict(nom=n, raison=r) for n, r in REGIME_STRATEGIES.get(regime, [])]
    if vix is not None and np.isfinite(vix):
        if vix >= 25:
            note = ("Volatilité élevée (VIX {:.0f}) : les options sont chères — privilégier les stratégies "
                    "qui VENDENT de la prime en risque limité (spreads, collar, call couvert).").format(vix)
            extra = ("Iron condor", "Volatilité implicite élevée : primes encaissées importantes, risque borné.")
        elif vix <= 15:
            note = ("Volatilité basse (VIX {:.0f}) : les options sont bon marché — privilégier les stratégies "
                    "qui ACHÈTENT de la prime (achat de call / put, straddle).").format(vix)
            extra = ("Straddle acheteur", "Options peu chères : un gros mouvement surprise serait bien rémunéré.")
        else:
            note, extra = None, None
        if extra and extra[0] not in [r["nom"] for r in recs]:
            recs.append(dict(nom=extra[0], raison=extra[1]))
        if note:
            for r in recs:
                r["vol"] = note
    return recs


def quick_regime() -> dict:
    """Régime simplifié à partir du VIX et de la tendance du S&P 500 (moyenne 200 j).
    Pour l'analyse complète (8 facteurs macro + actualités), voir le Hedge Fund Agent."""
    from utils.data import get_history
    out = dict(regime="Marché sans tendance", vix=float("nan"), trend=float("nan"),
               ok=False, explication="Données indisponibles : choisissez le régime manuellement.")
    try:
        spy = get_history("SPY", "1y")
        vix = get_history("^VIX", "3mo")
        if spy.empty or vix.empty or len(spy) < 200:
            return out
        close = spy["Close"].dropna()
        trend = float(close.iloc[-1] / close.rolling(200).mean().iloc[-1] - 1)
        v = float(vix["Close"].dropna().iloc[-1])
        mom3 = float(close.iloc[-1] / close.iloc[-63] - 1) if len(close) > 63 else 0.0
        if v >= 28:
            reg = "Aversion au risque"
        elif trend > 0.03 and v < 20:
            reg = "Expansion désinflationniste"
        elif trend > 0.03:
            reg = "Surchauffe / reflation"
        elif trend < -0.03 and v >= 20:
            reg = "Stagflation" if mom3 < -0.05 else "Ralentissement désinflationniste"
        elif trend < -0.03:
            reg = "Ralentissement désinflationniste"
        else:
            reg = "Marché sans tendance"
        out.update(regime=reg, vix=v, trend=trend, ok=True,
                   explication=(f"S&P 500 {'au-dessus' if trend > 0 else 'sous'} sa moyenne 200 jours "
                                f"({trend:+.1%}), VIX à {v:.1f}, performance 3 mois {mom3:+.1%}."))
    except Exception:
        pass
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTRUCTION ET ANALYSE
# ══════════════════════════════════════════════════════════════════════════════
def round_strike(k: float) -> float:
    """Arrondi au pas de cotation usuel des strikes."""
    if k <= 0:
        return 0.01
    step = 0.5 if k < 25 else 1 if k < 100 else 2.5 if k < 250 else 5 if k < 1000 else 10 if k < 5000 else 50
    return max(round(round(k / step) * step, 2), step)


def build_legs(name: str, S: float, T: float, r: float, sigma: float,
               n_contracts: int = 1, with_stock: bool = True) -> list[dict]:
    """Jambes d'une stratégie du catalogue.
    qty : nombre de contrats signé (+ achat, − vente) ; pour 'stock', qty = nombre de lots."""
    spec = CATALOG[name]
    legs = []
    if spec["stock"] and with_stock:
        legs.append({"type": "stock", "qty": spec["stock"] * n_contracts, "entry": S})
    for typ, side, m in spec["legs"]:
        K = round_strike(S * m)
        legs.append({"type": typ, "qty": side * n_contracts, "K": K,
                     "premium": float(bs_price(S, K, T, r, sigma, typ))})
    return legs


def _payoff(legs: list[dict], spots: np.ndarray, mult: int) -> np.ndarray:
    total = np.zeros_like(spots, dtype=float)
    for leg in legs:
        q = leg["qty"] * mult
        if leg["type"] == "call":
            total += q * (np.maximum(spots - leg["K"], 0) - leg["premium"])
        elif leg["type"] == "put":
            total += q * (np.maximum(leg["K"] - spots, 0) - leg["premium"])
        elif leg["type"] == "stock":
            total += q * (spots - leg["entry"])
    return total


def upside_slope(legs: list[dict], mult: int, extra_shares: float = 0.0) -> float:
    """Exposition (en titres) quand le cours tend vers l'infini.
    < 0 ⇒ perte illimitée à la hausse (call vendu non couvert)."""
    s = extra_shares
    for leg in legs:
        if leg["type"] in ("call", "stock"):
            s += leg["qty"] * mult
    return s


def analyze(legs: list[dict], S: float, mult: int, T: float, r: float, sigma: float) -> dict:
    """Profil complet de la stratégie (à l'échéance + grecques actuelles)."""
    strikes = [l["K"] for l in legs if l["type"] in ("call", "put")] or [S]
    hi = max(3.0 * S, 1.5 * max(strikes))
    grid = np.unique(np.concatenate([np.linspace(0.0, hi, 4001), np.array(strikes, float)]))
    pnl = _payoff(legs, grid, mult)

    slope_up = upside_slope(legs, mult)
    unlimited_loss = slope_up < -1e-9
    unlimited_gain = slope_up > 1e-9

    max_gain = float(pnl.max())
    max_loss = float(-pnl.min())

    # points morts : changements de signe du P&L
    be = []
    sgn = np.sign(np.round(pnl, 6))
    for i in range(1, len(grid)):
        if sgn[i - 1] != 0 and sgn[i] != 0 and sgn[i] != sgn[i - 1]:
            x0, x1, y0, y1 = grid[i - 1], grid[i], pnl[i - 1], pnl[i]
            be.append(float(x0 - y0 * (x1 - x0) / (y1 - y0)))

    net_premium = float(sum(-l["qty"] * mult * l["premium"] for l in legs if l["type"] in ("call", "put")))
    stock_cost = float(sum(l["qty"] * mult * l["entry"] for l in legs if l["type"] == "stock" and l["qty"] > 0))

    greeks = {g: 0.0 for g in ("delta", "gamma", "theta", "vega", "rho")}
    for l in legs:
        if l["type"] == "stock":
            greeks["delta"] += l["qty"] * mult
            continue
        g = bs_greeks(S, l["K"], T, r, sigma, l["type"])
        for k in greeks:
            greeks[k] += l["qty"] * mult * g[k]

    # Garantie à immobiliser (perte maximale des jambes optionnelles bornées)
    puts = [l for l in legs if l["type"] == "put"]
    calls = [l for l in legs if l["type"] == "call"]
    coll = 0.0
    if puts:
        coll += max(0.0, float(-_payoff(puts, np.linspace(0.0, hi, 2001), mult).min()))
    if calls:
        kmax = max(l["K"] for l in calls)
        coll += max(0.0, float(-_payoff(calls, np.linspace(0.0, kmax, 2001), mult).min()))
    # sans titres dans la stratégie, les deux ailes ne peuvent pas perdre en même temps
    if not any(l["type"] == "stock" for l in legs) and not unlimited_loss:
        coll = min(coll, max_loss)

    return dict(
        grid=grid, pnl=pnl,
        net_premium=net_premium,                   # > 0 crédit encaissé, < 0 débit payé
        debit=max(0.0, -net_premium), credit=max(0.0, net_premium),
        max_gain=max_gain, max_loss=max_loss,
        unlimited_gain=unlimited_gain, unlimited_loss=unlimited_loss,
        breakevens=be, greeks=greeks, stock_cost=stock_cost,
        collateral=coll,
    )


def usage_level(legs: list[dict], mult: int, shares_held: float = 0.0) -> str:
    """Niveau d'usage des dérivés exigé par l'ensemble de jambes.
    couverture < risque_limite < vente_couverte ; 'illimite' = interdit."""
    pkg_shares = sum(l["qty"] * mult for l in legs if l["type"] == "stock" and l["qty"] > 0)
    available = max(shares_held, 0.0) + pkg_shares
    if upside_slope(legs, mult, extra_shares=max(shares_held, 0.0)) < -1e-9:
        return "illimite"
    long_calls = sum(l["qty"] * mult for l in legs if l["type"] == "call" and l["qty"] > 0)
    short_calls = sum(-l["qty"] * mult for l in legs if l["type"] == "call" and l["qty"] < 0)
    long_puts = sum(l["qty"] * mult for l in legs if l["type"] == "put" and l["qty"] > 0)
    short_puts = sum(-l["qty"] * mult for l in legs if l["type"] == "put" and l["qty"] < 0)
    if short_puts > long_puts + 1e-9:
        return "vente_couverte"
    if long_calls == 0 and short_puts == 0 and (long_puts or short_calls) \
            and long_puts <= available + 1e-9 and short_calls <= available + 1e-9:
        return "couverture"
    return "risque_limite"
