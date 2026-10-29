# utils/compliance.py  —  MAM v5.1 · Contrôles de conformité pré-négociation
"""
Chaque ordre (spot, option, stratégie, Auto-Portefeuille) passe par ces contrôles
AVANT exécution. Un contrôle « bloquant » empêche l'ordre et explique pourquoi,
avec la règle et la référence réglementaire dont elle s'inspire. Chaque décision
(ordre exécuté ou bloqué) est enregistrée dans un journal d'audit horodaté.

Inspiration réglementaire (plateforme éducative — les références situent la
logique de chaque règle, elles ne valent pas conformité juridique) :
  · MiFID II art. 25 — adéquation et caractère approprié (profil, produits complexes)
  · MiFID II art. 27 — meilleure exécution (prix de marché fiable)
  · RTS 6 (règlement délégué 2017/589) — contrôles pré-négociation (« fat finger »)
  · Directive UCITS 2009/65/CE art. 52 — diversification (règle 5/10/40)
  · Règlement MiCA (UE) 2023/1114 et mises en garde AMF — crypto-actifs
  · Règlement (UE) 833/2014 — mesures restrictives (sanctions)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
#  PARAMÈTRES
# ══════════════════════════════════════════════════════════════════════════════
COMPLIANCE_VERSION = "1.0"

PROFILES = ["Prudent", "Équilibré", "Dynamique", "Agressif"]

# Limites DURES (au-delà, l'ordre est bloqué). Les allocations cibles du
# Hedge Fund Agent (utils.advisor.LIMITS) sont plus strictes : ce sont des objectifs.
HARD_LIMITS = {
    #             ligne max  crypto max  cash min  budget primes  usage dérivés max
    "Prudent":   dict(line=0.10, crypto=0.00, cash_min=0.05, premium=0.03, options="couverture"),
    "Équilibré": dict(line=0.20, crypto=0.10, cash_min=0.02, premium=0.08, options="risque_limite"),
    "Dynamique": dict(line=0.30, crypto=0.25, cash_min=0.00, premium=0.15, options="vente_couverte"),
    "Agressif":  dict(line=0.40, crypto=0.50, cash_min=0.00, premium=0.25, options="vente_couverte"),
}
OPTION_RANK = {"couverture": 1, "risque_limite": 2, "vente_couverte": 3, "illimite": 99}

BROAD_ETF_LINE_CAP = 0.70     # ETF indiciel large (centaines de titres) : déjà diversifié
FAT_FINGER_SHARE = 0.50       # ordre > 50 % de l'actif net : alerte
THEMATIC_CRYPTO = {"Crypto Alpha": ("Dynamique", "Agressif")}

# Instruments restreints (sanctions / politique interne)
RESTRICTED_SUFFIXES = {
    ".ME": "Bourse de Moscou — mesures restrictives de l'UE contre la Russie (règlement 833/2014)",
}
RESTRICTED_TICKERS = {
    "SBER.ME": "Sberbank — banque russe sanctionnée par l'UE",
    "GAZP.ME": "Gazprom — mesures restrictives UE",
    "ROSN.ME": "Rosneft — mesures restrictives UE",
    "LKOH.ME": "Lukoil — mesures restrictives UE",
    "VTBR.ME": "VTB Bank — banque russe sanctionnée par l'UE",
}

DEFAULT_PROFILE = {"risque": "Équilibré", "options_ok": False, "defini": False}

# ══════════════════════════════════════════════════════════════════════════════
#  MANDATS DE GESTION (stratégie du portefeuille)
# ══════════════════════════════════════════════════════════════════════════════
PORTFOLIO_TYPES = {
    "Libre":         {"emoji":"🔓","color":"#94a3b8","allowed":None,          "forbidden":[],                                  "max_w":1.0,  "rules":"Aucune contrainte de mandat (les limites du profil investisseur s'appliquent)."},
    "Growth":        {"emoji":"🚀","color":"#00ff88","allowed":["Equities","ETF","Equity"], "forbidden":["Bonds","Commodities","Crypto"], "max_w":0.30, "rules":"Actions croissance. Interdit : bonds, commodities, crypto. Max 30 % par ligne."},
    "Value":         {"emoji":"💎","color":"#ffd700","allowed":["Equities","ETF","Equity"], "forbidden":["Crypto","Commodities"],         "max_w":0.25, "rules":"Actions décotées. Interdit : crypto, spéculatif. Max 25 % par ligne."},
    "Momentum":      {"emoji":"⚡","color":"#ff8c00","allowed":["Equities","ETF","Equity","Crypto"], "forbidden":["Bonds"],               "max_w":0.20, "rules":"Tendance positive. Interdit : obligations. Max 20 % par ligne."},
    "Income":        {"emoji":"💰","color":"#00d4ff","allowed":["Equities","ETF","Bonds","Equity"],  "forbidden":["Crypto"],              "max_w":0.20, "rules":"Dividendes + obligations. Interdit : crypto. Max 20 % par ligne."},
    "Global Macro":  {"emoji":"🌍","color":"#7c3aed","allowed":None,          "forbidden":[],                                  "max_w":0.25, "rules":"Multi-actifs. Max 25 % par ligne."},
    "Hedging":       {"emoji":"🛡️","color":"#475569","allowed":["Bonds","ETF","Commodities","Equities","Equity"], "forbidden":["Crypto"], "max_w":0.20, "rules":"Défensif. Interdit : crypto. Max 20 % par ligne."},
    "Balanced 60/40":{"emoji":"⚖️","color":"#00ff88","allowed":["Equities","Bonds","ETF","Equity"],  "forbidden":["Crypto","Commodities"],"max_w":0.20, "rules":"60 % actions / 40 % obligations. Max 20 % par ligne."},
    "Commodity":     {"emoji":"🏭","color":"#ff8c00","allowed":["Commodities","ETF"],       "forbidden":["Crypto","Equities","Bonds","Equity"], "max_w":0.30, "rules":"Commodities uniquement. Max 30 % par ligne."},
    "Crypto Alpha":  {"emoji":"₿", "color":"#ff3b6b","allowed":["Crypto"],    "forbidden":["Equities","Bonds","Commodities","Equity","ETF"], "max_w":0.40, "rules":"Crypto uniquement — réservé aux profils Dynamique et Agressif. Max 40 % par ligne."},
    "Arbitrage":     {"emoji":"↔️","color":"#94a3b8","allowed":None,          "forbidden":[],                                  "max_w":0.15, "rules":"Delta-neutre. Max 15 % par ligne."},
    "ETF Core":      {"emoji":"🧺","color":"#00d4ff","allowed":["ETF"],       "forbidden":["Crypto","Equities","Equity"], "max_w":0.70, "rules":"Uniquement des ETF (gestion passive pour petits investisseurs)."},
}

CATEGORY_MAP = {
    "Technology":"Equities","Financial Services":"Equities","Healthcare":"Equities",
    "Consumer Cyclical":"Equities","Consumer Defensive":"Equities","Industrials":"Equities",
    "Energy":"Equities","Utilities":"Equities","Real Estate":"Equities",
    "Communication Services":"Equities","Basic Materials":"Equities",
    "ETF":"ETF","Bond":"Bonds","Bonds":"Bonds","Crypto":"Crypto",
    "Cryptocurrency":"Crypto","Commodities":"Commodities","Commodity":"Commodities",
    "Equity":"Equities","Equities":"Equities",
}

_STRAT_ALIAS = {"growth":"Growth","value":"Value","momentum":"Momentum","income":"Income",
                "macro":"Global Macro","hedging":"Hedging","balanced":"Balanced 60/40",
                "commodity":"Commodity","crypto":"Crypto Alpha","arbitrage":"Arbitrage",
                "etf":"ETF Core"}


def normalize_port_type(port: dict) -> str:
    t = port.get("portfolio_type") or port.get("strategy") or "Libre"
    t = _STRAT_ALIAS.get(t, t)
    return t if t in PORTFOLIO_TYPES else "Libre"


def validate_mandate(category: str, port_type: str) -> tuple[bool, str]:
    rules = PORTFOLIO_TYPES.get(port_type, PORTFOLIO_TYPES["Libre"])
    if rules["allowed"] is None and not rules["forbidden"]:
        return True, f"✅ Autorisé ({port_type})"
    cat = CATEGORY_MAP.get(str(category or "Equities"), "Equities")
    if cat in rules["forbidden"]:
        return False, f"❌ '{cat}' interdit pour {port_type}"
    if rules["allowed"] and cat not in rules["allowed"]:
        return False, f"❌ '{cat}' non autorisé pour {port_type}"
    return True, f"✅ '{cat}' conforme à {port_type}"


# ══════════════════════════════════════════════════════════════════════════════
#  CATALOGUE DES RÈGLES (explications)
# ══════════════════════════════════════════════════════════════════════════════
RULES = {
    "C01": ("Qualité des données de marché",
            "Le cours de cet instrument est un prix de secours : Yahoo Finance n'a pas répondu. Exécuter un ordre "
            "à ce prix fausserait la valorisation du portefeuille et le classement.",
            "Meilleure exécution — MiFID II art. 27"),
    "C02": ("Instrument restreint (sanctions)",
            "L'instrument figure sur la liste des instruments restreints : aucun nouvel investissement n'est possible.",
            "Mesures restrictives de l'UE — règlement (UE) 833/2014 · politique interne"),
    "C03": ("Respect du mandat de gestion",
            "La stratégie de ce portefeuille interdit cette classe d'actifs. Un gérant ne peut pas sortir du cadre "
            "de gestion promis à l'investisseur.",
            "Mandat de gestion · MiFID II art. 25(2) (adéquation)"),
    "C04": ("Limite de concentration par ligne",
            "Une ligne trop lourde expose le portefeuille au risque d'un seul émetteur (faillite, scandale, "
            "résultats décevants), qui n'est pas diversifié.",
            "Diversification — directive UCITS 2009/65/CE art. 52 (règle 5/10/40), transposée en limite interne"),
    "C05": ("Plafond crypto-actifs",
            "Les crypto-actifs sont extrêmement volatils (pertes de 70 à 80 % déjà observées), ne sont pas couverts "
            "par le Fonds de garantie des dépôts et de résolution et peuvent perdre toute leur valeur.",
            "Règlement MiCA (UE) 2023/1114 · mises en garde AMF"),
    "C06": ("Réserve de liquidités minimale",
            "Le profil impose de garder une réserve de liquidités pour faire face aux imprévus sans vendre "
            "dans l'urgence.",
            "Gestion du risque de liquidité — profil investisseur"),
    "C07": ("Provision et position suffisantes",
            "Un ordre ne peut pas dépasser les liquidités disponibles (pas de crédit ni d'effet de levier), "
            "ni vendre plus de titres que détenus (pas de vente à découvert).",
            "Interdiction du découvert et de la vente à découvert pour les clients de détail"),
    "C08": ("Ordre de taille inhabituelle",
            "L'ordre représente une part très importante de l'actif net : vérifiez qu'il ne s'agit pas d'une erreur "
            "de saisie (« fat finger »).",
            "Contrôles pré-négociation — RTS 6 (règlement délégué 2017/589)"),
    "D01": ("Dérogation à la limite de concentration",
            "Un dépassement temporaire du plafond par ligne est possible s'il est justifié par écrit, plafonné, "
            "limité dans le temps (7 jours au plus) et notifié avant l'ordre. À l'échéance, la ligne doit revenir "
            "sous le plafond : une dérogation expirée est signalée à chaque ordre et dans les rapports.",
            "Diversification — directive UCITS 2009/65/CE art. 52 · procédure interne de dérogation"),
    "C09": ("Profil investisseur",
            "Sans questionnaire rempli, le profil par défaut « Équilibré » s'applique et les produits dérivés "
            "restent fermés.",
            "Connaissance client — MiFID II art. 25(2)"),
    "P01": ("Politique d'investissement du portefeuille (avis du comité)",
            "L'ordre s'écarte de la politique d'investissement que vous avez définie pour ce portefeuille "
            "(exclusions, enveloppe, plafond crypto). Sur le Trading Desk, l'avis du comité est consultatif : "
            "l'ordre reste possible, mais il sera signalé lors de la prochaine revue.",
            "Déclaration de politique d'investissement (IPS, CFA Institute) · adéquation MiFID II art. 25(2)"),
    "O01": ("Caractère approprié — produits complexes",
            "Les options sont des produits complexes : il faut d'abord réussir le test de connaissances du "
            "profil investisseur (bouton « Mon profil investisseur » en haut du Trading Desk).",
            "MiFID II art. 25(3) · orientations ESMA sur le caractère approprié"),
    "O02": ("Usage des dérivés autorisé par le profil",
            "Chaque profil n'autorise qu'un certain usage des options : Prudent = couverture de titres détenus ; "
            "Équilibré = + stratégies à risque limité ; Dynamique / Agressif = + ventes de puts couvertes par du cash.",
            "Adéquation au profil de risque — MiFID II art. 25(2)"),
    "O03": ("Vente d'option non couverte (perte illimitée)",
            "Vendre un call sans détenir les titres expose à une perte théoriquement illimitée si le cours monte. "
            "Ce type d'ordre est interdit pour tous les profils.",
            "Protection des investisseurs de détail — politique interne d'interdiction des ventes non couvertes"),
    "O04": ("Budget de primes d'options",
            "Les primes payées sont perdues si les options expirent sans valeur : leur total est plafonné "
            "en pourcentage de l'actif net.",
            "Limite de risque interne par profil"),
    "O05": ("Perte maximale couverte par les liquidités",
            "La perte maximale de la stratégie doit pouvoir être payée avec les liquidités disponibles "
            "(garantie / « cash-secured »).",
            "Exigence de couverture — appels de marge"),
    "O06": ("Échéance de l'option",
            "Une échéance très courte accélère la perte de valeur temps (thêta) ; une échéance très longue "
            "immobilise du capital et rend le prix plus incertain.",
            "Information sur les risques — produits dérivés"),
}


@dataclass
class Check:
    code: str
    status: str          # "ok" | "warn" | "block"
    detail: str

    @property
    def title(self) -> str:
        return RULES.get(self.code, (self.code, "", ""))[0]

    @property
    def why(self) -> str:
        return RULES.get(self.code, ("", "", ""))[1]

    @property
    def ref(self) -> str:
        return RULES.get(self.code, ("", "", ""))[2]


@dataclass
class Decision:
    kind: str                      # "spot" | "option"
    checks: list[Check] = field(default_factory=list)

    def add(self, code: str, status: str, detail: str):
        self.checks.append(Check(code, status, detail))

    @property
    def blocks(self) -> list[Check]:
        return [c for c in self.checks if c.status == "block"]

    @property
    def warnings(self) -> list[Check]:
        return [c for c in self.checks if c.status == "warn"]

    @property
    def allowed(self) -> bool:
        return not self.blocks

    def short_reason(self) -> str:
        return " · ".join(f"[{c.code}] {c.title} — {c.detail}" for c in self.blocks)

    def to_records(self) -> list[dict]:
        return [dict(code=c.code, statut=c.status, regle=c.title, detail=c.detail) for c in self.checks]

    def merge(self, other: "Decision", skip: tuple = ()):
        for c in other.checks:
            if c.code not in skip:
                self.checks.append(c)


# ══════════════════════════════════════════════════════════════════════════════
#  PROFIL INVESTISSEUR
# ══════════════════════════════════════════════════════════════════════════════
def get_profile() -> dict:
    """Profil de l'utilisateur connecté (base de données), ou profil par défaut."""
    prof = st.session_state.get("mam_investor_profile")
    if prof is None:
        prof = {}
        user = st.session_state.get("mam_user")
        if user:
            try:
                from utils.db import get_investor_profile
                prof = get_investor_profile(user["id"]) or {}
            except Exception:
                prof = {}
        st.session_state["mam_investor_profile"] = prof
    out = {**DEFAULT_PROFILE, **(prof or {})}
    if out.get("risque") not in PROFILES:
        out["risque"] = "Équilibré"
    return out


def save_profile(prof: dict) -> bool:
    """Enregistre le profil (session + base si connecté). Retourne True si sauvegardé en base."""
    prof = {**prof, "defini": True, "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
    st.session_state["mam_investor_profile"] = prof
    user = st.session_state.get("mam_user")
    if user:
        try:
            from utils.db import save_investor_profile
            save_investor_profile(user["id"], prof)
            return True
        except Exception:
            return False
    return False


# ══════════════════════════════════════════════════════════════════════════════
#  OUTILS
# ══════════════════════════════════════════════════════════════════════════════
def portfolio_profile(port: dict, profile: dict | None = None) -> dict:
    """Profil appliqué aux ordres : celui de la politique d'investissement (IPS) du portefeuille
    s'il en a une, sinon celui de l'utilisateur. Le test de connaissances options reste celui
    de l'utilisateur (caractère approprié = connaissance de la personne)."""
    base = profile or get_profile()
    if port.get("ips"):
        try:
            from utils.committee import constraints
            return {**base, "risque": constraints(port["ips"])["profil"], "defini": True}
        except Exception:
            pass
    return base


def restricted_reason(ticker: str) -> str | None:
    t = (ticker or "").upper().strip()
    if t in RESTRICTED_TICKERS:
        return RESTRICTED_TICKERS[t]
    for suf, why in RESTRICTED_SUFFIXES.items():
        if t.endswith(suf):
            return why
    return None


def _category_of(ticker: str) -> str:
    try:
        from utils.data import load_assets
        df = load_assets()
        row = df[df["ticker"] == ticker]
        if not row.empty:
            return str(row["category"].iloc[0])
    except Exception:
        pass
    if ticker.endswith("-USD"):
        return "Crypto"
    if ticker.endswith("=F"):
        return "Commodity"
    return "Equity"


def _is_crypto(ticker: str, category: str | None = None) -> bool:
    return ticker.upper().endswith(("-USD", "-EUR")) or CATEGORY_MAP.get(str(category), "") == "Crypto"


def _is_cash_like(ticker: str) -> bool:
    try:
        from utils.etf_universe import etf_class
        if etf_class(ticker) == "Liquidités":
            return True
    except Exception:
        pass
    return ticker.upper() in ("BIL", "SGOV", "SHV", "XEON.DE")


def _is_broad_etf(ticker: str) -> bool:
    try:
        from utils.etf_universe import is_broad_etf
        return is_broad_etf(ticker)
    except Exception:
        return False


def _snapshot(port: dict, extra: tuple = (), prices: dict | None = None) -> dict:
    """Valorisation du portefeuille : liquidités, valeur par ligne, actif net."""
    holdings = port.get("holdings", {}) or {}
    tick = tuple(sorted(set(holdings) | set(extra)))
    if prices is None:
        try:
            from utils.data import get_multi_prices
            prices = get_multi_prices(tick) if tick else {}
        except Exception:
            prices = {}

    def px(t):
        v = prices.get(t)
        p = v[0] if isinstance(v, (list, tuple)) else v
        if not p or p != p or p <= 0:
            p = holdings.get(t, {}).get("avg_price", 0.0)
        return float(p)

    vals = {t: float(h.get("qty", 0)) * px(t) for t, h in holdings.items()}
    cash = float(port.get("cash", 0.0))
    return dict(cash=cash, vals=vals, nav=cash + sum(vals.values()), px=px)


def _price_source(ticker: str) -> str:
    try:
        from utils.data import get_price_source
        return get_price_source(ticker)
    except Exception:
        return "repli"


# ══════════════════════════════════════════════════════════════════════════════
#  DÉROGATIONS À LA LIMITE DE CONCENTRATION (v5.6)
# ══════════════════════════════════════════════════════════════════════════════
DEROGATION_MAX_DAYS = 7
DEROGATION_MIN_CHARS = 30


def derogation_ceiling(cap: float) -> float:
    """Poids maximal autorisable par dérogation : plafond + 10 points, et au plus 1,5 fois le plafond."""
    return round(min(cap + 0.10, cap * 1.5), 4)


def line_cap(port: dict, ticker: str, category: str | None = None, profile: dict | None = None) -> tuple[float, str]:
    """Plafond par ligne applicable (même calcul que le contrôle C04)."""
    profile = portfolio_profile(port, profile)
    risk = profile.get("risque", "Équilibré")
    port_type = normalize_port_type(port)
    cap = min(HARD_LIMITS.get(risk, HARD_LIMITS["Équilibré"])["line"], PORTFOLIO_TYPES[port_type]["max_w"])
    label = f"profil {risk}"
    if _is_broad_etf(ticker):
        cap, label = max(cap, BROAD_ETF_LINE_CAP), "ETF indiciel diversifié"
    elif port_type in THEMATIC_CRYPTO and _is_crypto(ticker, category):
        cap, label = PORTFOLIO_TYPES[port_type]["max_w"], f"mandat {port_type}"
    return cap, label


def _parse_dt(x) -> datetime | None:
    try:
        return datetime.fromisoformat(str(x))
    except Exception:
        return None


def active_derogation(port: dict, ticker: str, now: datetime | None = None) -> dict | None:
    """Dérogation en cours (non close et non échue) pour cette ligne."""
    d = (port.get("derogations") or {}).get(ticker)
    if not d or d.get("statut") != "active":
        return None
    end = _parse_dt(d.get("echeance"))
    if end is None or (now or datetime.now()) > end:
        return None
    return d


def request_derogation(port: dict, ticker: str, poids_max: float, jours: int, justification: str, *,
                       category: str | None = None, author: str | None = None,
                       now: datetime | None = None) -> tuple[bool, str]:
    """Enregistre une dérogation justifiée, plafonnée et datée. Renvoie (accordée, message)."""
    now = now or datetime.now()
    cap, label = line_cap(port, ticker, category)
    ceiling = derogation_ceiling(cap)
    just = str(justification or "").strip()
    if len(just) < DEROGATION_MIN_CHARS:
        return False, (f"Justification trop courte : expliquez en au moins {DEROGATION_MIN_CHARS} caractères "
                       "pourquoi la position mérite de dépasser le plafond et comment elle sera réduite.")
    if not 1 <= int(jours) <= DEROGATION_MAX_DAYS:
        return False, f"Durée invalide : une dérogation dure de 1 à {DEROGATION_MAX_DAYS} jours."
    if poids_max <= cap + 1e-9:
        return False, f"Inutile : {poids_max:.0%} reste sous le plafond de {cap:.0%}."
    if poids_max > ceiling + 1e-9:
        return False, (f"Refusée : {poids_max:.0%} dépasse le maximum autorisable par dérogation "
                       f"({ceiling:.0%} pour un plafond de {cap:.0%}).")
    from datetime import timedelta
    rec = dict(ticker=ticker, plafond_normal=cap, regle=label, poids_max=float(poids_max), jours=int(jours),
               justification=just, debut=now.isoformat(timespec="seconds"),
               echeance=(now + timedelta(days=int(jours))).isoformat(timespec="seconds"),
               statut="active", notifie=now.isoformat(timespec="seconds"), auteur=author)
    port.setdefault("derogations", {})[ticker] = rec
    try:  # notification à l'investisseur AVANT l'ordre (e-mail du compte, si configuré)
        from utils.notifier import _dispatch
        _dispatch(port, f"Dérogation de concentration sur {ticker}",
                  f"MAM — dérogation temporaire sur {ticker} ({port.get('name', '')})",
                  [f"Ligne {ticker} autorisée jusqu'à {poids_max:.0%} (plafond habituel {cap:.0%}, {label}).",
                   f"Durée : {jours} jour(s), échéance le {rec['echeance'][:16].replace('T', ' ')}.",
                   f"Justification : {just}",
                   "À l'échéance, la ligne devra revenir sous le plafond habituel."])
    except Exception:
        pass
    return True, (f"Dérogation accordée : {ticker} jusqu'à {poids_max:.0%} pendant {jours} jour(s) "
                  f"(échéance {rec['echeance'][:16].replace('T', ' ')}).")


def close_derogation(port: dict, ticker: str, reason: str = "clôturée par l'utilisateur") -> bool:
    d = (port.get("derogations") or {}).get(ticker)
    if not d or d.get("statut") != "active":
        return False
    d["statut"], d["cloture"] = "close", f"{datetime.now():%Y-%m-%d %H:%M} — {reason}"
    return True


def derogation_status(port: dict, weights: dict[str, float] | None = None, now: datetime | None = None) -> list[dict]:
    """État de toutes les dérogations : active / échue à régulariser / régularisée / close.
    weights : poids actuels par ligne (pour savoir si une ligne échue est revenue sous son plafond)."""
    now = now or datetime.now()
    out = []
    for t, d in (port.get("derogations") or {}).items():
        end = _parse_dt(d.get("echeance"))
        w = (weights or {}).get(t)
        if d.get("statut") == "close":
            etat = "close"
        elif end and now <= end:
            etat = "active"
        elif w is not None and w <= d.get("plafond_normal", 1) + 1e-9:
            etat = "régularisée"
        else:
            etat = "échue — à régulariser"
        out.append({**d, "etat": etat, "poids_actuel": w})
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  CONTRÔLES — ORDRE SPOT
# ══════════════════════════════════════════════════════════════════════════════
def pre_trade_spot(port: dict, ticker: str, action: str, qty: float, price: float, *,
                   profile: dict | None = None, prices: dict | None = None,
                   price_source: str | None = None, category: str | None = None) -> Decision:
    d = Decision("spot")
    profile = portfolio_profile(port, profile)
    risk = profile.get("risque", "Équilibré")
    lim = HARD_LIMITS.get(risk, HARD_LIMITS["Équilibré"])
    port_type = normalize_port_type(port)
    category = category or _category_of(ticker)
    buy = str(action).upper().startswith("BUY")
    amount = float(qty) * float(price)
    snap = _snapshot(port, (ticker,), prices)
    nav, cash = snap["nav"], snap["cash"]
    held = float((port.get("holdings", {}) or {}).get(ticker, {}).get("qty", 0.0))

    # C09 — profil
    if not profile.get("defini"):
        d.add("C09", "warn", "Profil par défaut « Équilibré » appliqué — remplissez « Mon profil investisseur ».")
    else:
        d.add("C09", "ok", f"Profil {risk}" + (" (politique d'investissement du portefeuille)" if port.get("ips") else ""))

    # C01 — données
    src = price_source or _price_source(ticker)
    if src != "live":
        d.add("C01", "block", f"Cours de {ticker} indisponible : prix de secours {price:,.4f} non exécutable.")
    else:
        d.add("C01", "ok", "Cours Yahoo Finance (différé)")

    # C02 — instruments restreints
    why = restricted_reason(ticker)
    if why and buy:
        d.add("C02", "block", why)
    elif why:
        d.add("C02", "warn", f"{why} — cession autorisée pour sortir de la position.")

    # C07 — provision / position
    if qty <= 0 or price <= 0:
        d.add("C07", "block", "Quantité ou prix invalide.")
    elif buy and amount > cash + 0.01:
        d.add("C07", "block", f"Ordre de {amount:,.2f} $ pour {cash:,.2f} $ de liquidités.")
    elif not buy and qty > held + 1e-6:
        d.add("C07", "block", f"Vente de {qty:,.4f} titres pour {held:,.4f} détenus (vente à découvert interdite).")
    else:
        d.add("C07", "ok", "Provision suffisante" if buy else "Position suffisante")

    if buy and nav > 0:
        # C03 — mandat
        ok, msg = validate_mandate(category, port_type)
        if not ok:
            d.add("C03", "block", msg.replace("❌ ", ""))
        else:
            d.add("C03", "ok", msg.replace("✅ ", ""))

        # C04 — concentration (le monétaire n'est pas concerné)
        if not _is_cash_like(ticker):
            line_after = snap["vals"].get(ticker, 0.0) + amount
            w = line_after / nav
            cap = min(lim["line"], PORTFOLIO_TYPES[port_type]["max_w"])
            label = f"profil {risk}"
            if _is_broad_etf(ticker):
                cap, label = max(cap, BROAD_ETF_LINE_CAP), "ETF indiciel diversifié"
            elif port_type in THEMATIC_CRYPTO and _is_crypto(ticker, category):
                cap, label = PORTFOLIO_TYPES[port_type]["max_w"], f"mandat {port_type}"
            der = active_derogation(port, ticker) if w > cap + 1e-9 else None
            if der and w <= der["poids_max"] + 1e-9:
                d.add("C04", "warn", f"{ticker} pèserait {w:.1%} de l'actif net, au-delà du plafond {cap:.0%} "
                                      f"({label}) — autorisé par une dérogation temporaire (règle D01) jusqu'à {der['poids_max']:.0%}, "
                                      f"échéance le {str(der['echeance'])[:16].replace('T', ' ')}.")
            elif w > cap + 1e-9:
                extra = (f" La dérogation en cours s'arrête à {der['poids_max']:.0%}." if der else
                         f" Une dérogation justifiée et temporaire (≤ {DEROGATION_MAX_DAYS} jours, jusqu'à "
                         f"{derogation_ceiling(cap):.0%}) peut être demandée.")
                d.add("C04", "block", f"{ticker} pèserait {w:.1%} de l'actif net, plafond {cap:.0%} ({label}). "
                                       f"Montant maximal : {max(0.0, cap * nav - snap['vals'].get(ticker, 0.0)):,.0f} $."
                                       + extra)
            else:
                d.add("C04", "ok", f"{ticker} : {w:.1%} après l'ordre (plafond {cap:.0%}, {label})")

        # C05 — crypto
        if _is_crypto(ticker, category):
            crypto_now = sum(v for t, v in snap["vals"].items() if _is_crypto(t))
            w = (crypto_now + amount) / nav
            cap, label = lim["crypto"], f"profil {risk}"
            if port_type in THEMATIC_CRYPTO:
                if risk in THEMATIC_CRYPTO[port_type]:
                    cap, label = 1.0, f"mandat thématique {port_type}"
                else:
                    cap, label = 0.0, (f"mandat {port_type} réservé aux profils "
                                       f"{' / '.join(THEMATIC_CRYPTO[port_type])}")
            if w > cap + 1e-9:
                d.add("C05", "block", f"Crypto-actifs : {w:.1%} de l'actif net après l'ordre, plafond {cap:.0%} ({label}).")
            else:
                d.add("C05", "ok", f"Crypto-actifs : {w:.1%} (plafond {cap:.0%})")

        # C06 — liquidités minimales (le monétaire compte comme liquidités)
        if not _is_cash_like(ticker) and lim["cash_min"] > 0:
            cash_like = cash - amount + sum(v for t, v in snap["vals"].items() if _is_cash_like(t))
            w = cash_like / nav
            if w < lim["cash_min"] - 1e-9:
                d.add("C06", "block", f"Liquidités après l'ordre : {w:.1%}, minimum {lim['cash_min']:.0%} "
                                       f"(profil {risk}). Montant maximal : "
                                       f"{max(0.0, cash_like + amount - lim['cash_min'] * nav):,.0f} $.")
            else:
                d.add("C06", "ok", f"Liquidités après l'ordre : {w:.1%} (minimum {lim['cash_min']:.0%})")

    # D01 — dérogations échues non régularisées (rappel à chaque ordre)
    if nav > 0 and port.get("derogations"):
        weights = {t: v / nav for t, v in snap["vals"].items()}
        late = [x for x in derogation_status(port, weights) if x["etat"].startswith("échue")]
        if late:
            d.add("D01", "warn", "Dérogation échue à régulariser : " + ", ".join(
                f"{x['ticker']} à {x['poids_actuel']:.0%} pour un plafond de {x['plafond_normal']:.0%}"
                for x in late if x.get("poids_actuel") is not None) + ".")

    # C08 — taille inhabituelle
    if nav > 0 and amount / nav > FAT_FINGER_SHARE:
        d.add("C08", "warn", f"Ordre = {amount / nav:.0%} de l'actif net.")

    # P01 — politique d'investissement du portefeuille (avis CONSULTATIF du comité, ne bloque pas)
    if buy and port.get("ips"):
        try:
            from utils import committee as CM
            cons = CM.constraints(port["ips"])
            why = CM.excluded_reason(ticker, cons["exclusions"])
            if why:
                d.add("P01", "warn", f"{ticker} relève d'une exclusion de votre politique ({why}).")
            if "PEA" in cons["enveloppe"] and not CM.pea_eligible(ticker):
                d.add("P01", "warn", f"{ticker} n'est pas éligible au PEA (enveloppe de ce portefeuille).")
            if _is_crypto(ticker, category) and nav > 0:
                crypto_after = (sum(v for t, v in snap["vals"].items() if _is_crypto(t)) + amount) / nav
                if crypto_after > cons["crypto_max"] + 1e-9 and port_type not in THEMATIC_CRYPTO:
                    d.add("P01", "warn", f"Crypto-actifs à {crypto_after:.0%} : au-delà des {cons['crypto_max']:.0%} "
                                         "de votre politique d'investissement.")
        except Exception:
            pass
    return d


# ══════════════════════════════════════════════════════════════════════════════
#  CONTRÔLES — OPTIONS ET STRATÉGIES
# ══════════════════════════════════════════════════════════════════════════════
def _is_put_protection(legs: list[dict]) -> bool:
    """Uniquement des puts, avec au moins autant de puts achetés que vendus (put / put spread)."""
    if not legs or any(l["type"] != "put" for l in legs):
        return False
    long_ = sum(l["qty"] for l in legs if l["qty"] > 0)
    short = sum(-l["qty"] for l in legs if l["qty"] < 0)
    return long_ > 0 and short <= long_


def _open_option_exposure(port: dict, ticker: str, mult: int) -> tuple[float, float]:
    """(titres engagés par des calls vendus ouverts − calls achetés, primes payées ouvertes)."""
    short_units, paid = 0.0, 0.0
    for o in port.get("options", []) or []:
        n = float(o.get("n_contracts", 0)) * float(o.get("contract_mult", mult))
        if o.get("action", "BUY") == "BUY":
            paid += float(o.get("total_premium", 0.0))
        if o.get("ticker") == ticker and o.get("type") == "call":
            short_units += -n if o.get("action", "BUY") == "BUY" else n
    return max(short_units, 0.0), paid


def pre_trade_options(port: dict, ticker: str, legs: list[dict], *, spot: float, mult: int,
                      T_days: int, r: float, sigma: float, profile: dict | None = None,
                      prices: dict | None = None, price_source: str | None = None,
                      hedge_exposure: float | None = None) -> tuple[Decision, dict]:
    """Contrôle d'un ensemble de jambes (option seule ou stratégie). Renvoie (décision, analyse).
    hedge_exposure : montant ($) de l'exposition du portefeuille que la stratégie protège
    (couverture d'indice proposée par le desk). Des puts achetés dont le nominal ne dépasse
    pas cette exposition sont traités comme une couverture."""
    from utils.option_strategies import analyze, usage_level, LEVEL_LABEL

    d = Decision("option")
    profile = portfolio_profile(port, profile)
    risk = profile.get("risque", "Équilibré")
    lim = HARD_LIMITS.get(risk, HARD_LIMITS["Équilibré"])
    T = max(T_days, 1) / 365.0
    a = analyze(legs, spot, mult, T, r, sigma)
    snap = _snapshot(port, (ticker,), prices)
    nav, cash = snap["nav"], snap["cash"]

    # O01 — caractère approprié
    if not profile.get("options_ok"):
        d.add("O01", "block", "Test de connaissances sur les options non validé.")
    else:
        d.add("O01", "ok", "Test de connaissances validé")

    # C01 — données / C02 — restrictions
    src = price_source or _price_source(ticker)
    if src != "live":
        d.add("C01", "block", f"Cours du sous-jacent {ticker} indisponible (prix de secours).")
    else:
        d.add("C01", "ok", "Cours du sous-jacent Yahoo Finance (différé)")
    why = restricted_reason(ticker)
    if why:
        d.add("C02", "block", why)

    # O03 / O02 — couverture et usage
    held = float((port.get("holdings", {}) or {}).get(ticker, {}).get("qty", 0.0))
    committed, paid_open = _open_option_exposure(port, ticker, mult)
    free_shares = max(held - committed, 0.0)
    level = usage_level(legs, mult, shares_held=free_shares)
    hedge_note = ""
    if level == "risque_limite" and hedge_exposure and _is_put_protection(legs):
        notional = sum(l["qty"] * mult * l["K"] for l in legs if l["type"] == "put" and l["qty"] > 0)
        if notional <= hedge_exposure * 1.10:
            level = "couverture"
            hedge_note = (f" — couverture de portefeuille : nominal {notional:,.0f} $ ≤ exposition "
                          f"protégée {hedge_exposure:,.0f} $")
    if level == "illimite":
        d.add("O03", "block", f"Calls vendus non couverts : {free_shares:,.0f} titres {ticker} disponibles "
                              f"(détenus {held:,.0f}, déjà engagés {committed:,.0f}).")
    else:
        d.add("O03", "ok", "Aucune vente non couverte")
        allowed = lim["options"]
        if OPTION_RANK[level] > OPTION_RANK[allowed]:
            d.add("O02", "block", f"Stratégie de type « {LEVEL_LABEL[level]} », profil {risk} limité à "
                                  f"« {LEVEL_LABEL[allowed]} ».")
        else:
            d.add("O02", "ok", f"{LEVEL_LABEL[level]} — autorisé pour le profil {risk}{hedge_note}")

    # C07 — provision (achat de titres + prime nette)
    need = a["stock_cost"] + a["debit"]
    if need > cash + 0.01:
        d.add("C07", "block", f"Besoin de {need:,.2f} $ (titres {a['stock_cost']:,.0f} $ + primes "
                              f"{a['debit']:,.0f} $) pour {cash:,.2f} $ de liquidités.")
    else:
        d.add("C07", "ok", f"Coût immédiat {need:,.2f} $ ≤ liquidités {cash:,.2f} $")

    # O05 — perte maximale / garantie
    if level != "illimite":
        reserve = cash - a["stock_cost"] - a["debit"]
        if a["collateral"] > reserve + 0.01 and a["collateral"] > a["debit"] + 0.01:
            d.add("O05", "block", f"Garantie nécessaire {a['collateral']:,.0f} $ (perte maximale des options), "
                                  f"liquidités restantes {reserve:,.0f} $.")
        else:
            d.add("O05", "ok", f"Perte maximale des options {a['collateral']:,.0f} $ couverte")

    # O04 — budget de primes
    if a["debit"] > 0 and nav > 0:
        w = (paid_open + a["debit"]) / nav
        if w > lim["premium"] + 1e-9:
            d.add("O04", "block", f"Primes payées (ouvertes + nouvelles) : {w:.1%} de l'actif net, plafond "
                                  f"{lim['premium']:.0%} (profil {risk}).")
        else:
            d.add("O04", "ok", f"Primes payées : {w:.1%} de l'actif net (plafond {lim['premium']:.0%})")

    # O06 — échéance
    if T_days < 7:
        d.add("O06", "warn", f"Échéance de {T_days} jour(s) : valeur temps qui fond très vite.")
    elif T_days > 365:
        d.add("O06", "warn", f"Échéance de {T_days} jours : prix très sensible à la volatilité retenue.")

    # Achat de titres inclus dans la stratégie : mêmes contrôles qu'un ordre spot
    stock_qty = sum(l["qty"] * mult for l in legs if l["type"] == "stock" and l["qty"] > 0)
    if stock_qty > 0:
        sd = pre_trade_spot(port, ticker, "BUY", stock_qty, spot, profile=profile, prices=prices,
                            price_source=src)
        d.merge(sd, skip=("C01", "C07", "C09", "C02"))
    return d, a


# ══════════════════════════════════════════════════════════════════════════════
#  JOURNAL D'AUDIT
# ══════════════════════════════════════════════════════════════════════════════
def log_decision(decision: Decision, port: dict, ticker: str, action: str, qty: float,
                 price: float, executed: bool, note: str = "") -> None:
    """Enregistre la décision (base de données si disponible, sinon session)."""
    user = st.session_state.get("mam_user") or {}
    entry = dict(
        date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_id=user.get("id"), username=user.get("username", "invité"),
        portfolio_id=port.get("id", ""), portfolio=port.get("name", ""),
        ticker=ticker, action=action, qty=float(qty), price=float(price),
        statut="exécuté" if executed else "bloqué",
        regles=", ".join(c.code for c in decision.blocks) or "—",
        detail=decision.short_reason() if decision.blocks else
               " · ".join(f"[{c.code}] {c.detail}" for c in decision.warnings),
        note=note, version=COMPLIANCE_VERSION,
    )
    st.session_state.setdefault("mam_compliance_log", []).insert(0, entry)
    st.session_state["mam_compliance_log"] = st.session_state["mam_compliance_log"][:200]
    if user.get("id"):
        try:
            from utils.db import log_compliance
            log_compliance(entry, decision.to_records())
        except Exception:
            pass


def recent_log(limit: int = 50, all_users: bool = False) -> list[dict]:
    user = st.session_state.get("mam_user") or {}
    try:
        from utils.db import get_compliance_log
        rows = get_compliance_log(None if all_users else user.get("id"), limit)
        if rows or user.get("id"):
            return rows
    except Exception:
        pass
    return st.session_state.get("mam_compliance_log", [])[:limit]


# ══════════════════════════════════════════════════════════════════════════════
#  AFFICHAGE (Streamlit)
# ══════════════════════════════════════════════════════════════════════════════
_ICON = {"ok": "✅", "warn": "⚠️", "block": "⛔"}
_COL = {"ok": "#00ff88", "warn": "#ffd700", "block": "#ff3b6b"}


def render_decision(decision: Decision, title: str = "CONTRÔLES DE CONFORMITÉ", compact: bool = False):
    """Affiche le résultat des contrôles avec l'explication de chaque blocage."""
    import html as _h
    n_b, n_w = len(decision.blocks), len(decision.warnings)
    head_col = "#ff3b6b" if n_b else ("#ffd700" if n_w else "#00ff88")
    verdict = (f"⛔ ORDRE BLOQUÉ — {n_b} règle(s) non respectée(s)" if n_b
               else f"✅ ORDRE CONFORME{f' — {n_w} alerte(s)' if n_w else ''}")
    st.markdown(
        f'<div style="border:1px solid {head_col}55;background:{head_col}0d;border-radius:8px;'
        f'padding:8px 12px;margin:6px 0;font-family:Share Tech Mono;font-size:.74rem;">'
        f'<div style="font-family:Rajdhani;font-size:.68rem;letter-spacing:.12em;color:#7a93b0;">🛡️ {title}</div>'
        f'<div style="color:{head_col};font-weight:bold;margin-top:2px;">{verdict}</div></div>',
        unsafe_allow_html=True)
    for c in decision.blocks + decision.warnings:
        st.markdown(
            f'<div style="border-left:3px solid {_COL[c.status]};background:rgba(0,0,0,.25);border-radius:4px;'
            f'padding:8px 12px;margin:4px 0;font-family:Share Tech Mono;font-size:.72rem;color:#cbd5e1;line-height:1.6;">'
            f'<b style="color:{_COL[c.status]}">{_ICON[c.status]} [{c.code}] {_h.escape(c.title)}</b><br>'
            f'{_h.escape(c.detail)}<br>'
            f'<span style="color:#94a3b8;">Pourquoi : {_h.escape(c.why)}</span><br>'
            f'<span style="color:#475569;font-size:.66rem;">Référence : {_h.escape(c.ref)}</span></div>',
            unsafe_allow_html=True)
    if not compact:
        oks = [c for c in decision.checks if c.status == "ok"]
        if oks:
            with st.expander(f"✅ {len(oks)} contrôle(s) conforme(s)"):
                for c in oks:
                    st.markdown(f"- **[{c.code}] {c.title}** — {c.detail}")


def render_rules_reference():
    """Tableau pédagogique des règles et des limites par profil."""
    import pandas as pd
    st.markdown("**Limites par profil investisseur**")
    rows = []
    for p, l in HARD_LIMITS.items():
        from utils.option_strategies import LEVEL_LABEL
        rows.append({"Profil": p, "Ligne max": f"{l['line']:.0%}", "Crypto max": f"{l['crypto']:.0%}",
                     "Liquidités min": f"{l['cash_min']:.0%}", "Budget primes": f"{l['premium']:.0%}",
                     "Options autorisées": LEVEL_LABEL[l["options"]]})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption(f"ETF indiciels diversifiés : jusqu'à {BROAD_ETF_LINE_CAP:.0%} par ligne. "
               "Les limites de mandat (stratégie du portefeuille) s'ajoutent à celles du profil.")
    st.markdown("**Règles contrôlées avant chaque ordre**")
    st.dataframe(pd.DataFrame([{"Code": k, "Règle": v[0], "Pourquoi": v[1], "Référence": v[2]}
                               for k, v in RULES.items()]),
                 use_container_width=True, hide_index=True)


# ── Questionnaire profil investisseur + test de connaissances options ─────────
_RISK_QUESTIONS = [
    ("Dans combien de temps aurez-vous besoin de cet argent ?",
     ["Moins de 2 ans", "2 à 5 ans", "5 à 8 ans", "Plus de 8 ans"]),
    ("Votre portefeuille perd 20 % en trois mois. Que faites-vous ?",
     ["Je vends tout", "Je vends une partie", "Je ne fais rien", "J'en rachète"]),
    ("Quelle part de votre épargne représente ce placement ?",
     ["Plus de 50 %", "25 à 50 %", "10 à 25 %", "Moins de 10 %"]),
    ("Votre expérience de l'investissement ?",
     ["Aucune", "Livrets, assurance-vie, quelques ETF", "Actions et obligations régulièrement",
      "Actions, ETF et produits dérivés"]),
]
_OPTION_QUIZ = [
    ("En achetant un call, quelle est votre perte maximale ?",
     ["Illimitée", "La prime payée", "Le prix d'exercice", "Rien"], 1),
    ("En vendant un call sans détenir les titres, quelle est votre perte maximale ?",
     ["La prime encaissée", "Le prix d'exercice", "Théoriquement illimitée", "Rien"], 2),
    ("À cours constant, que devient la valeur d'une option achetée avec le temps ?",
     ["Elle augmente", "Elle baisse (thêta)", "Elle ne change pas", "Elle double"], 1),
    ("Un put acheté sur des actions détenues protège contre…",
     ["La hausse du cours", "La baisse du cours", "La hausse des taux", "L'inflation"], 1),
]


def render_profile_panel():
    """Questionnaire de profil (adéquation) et test de connaissances (caractère approprié)."""
    prof = get_profile()
    status = (f"Profil **{prof['risque']}** · options "
              f"{'✅ autorisées' if prof.get('options_ok') else '🔒 fermées'}"
              + ("" if prof.get("defini") else " · ⚠️ profil par défaut (questionnaire non rempli)"))
    with st.expander(f"🧾 Mon profil investisseur — {prof['risque']}"
                     f"{'' if prof.get('defini') else ' (à compléter)'}", expanded=not prof.get("defini")):
        st.markdown(status)
        st.caption("Comme chez un prestataire réglementé, votre profil détermine les limites appliquées à vos ordres "
                   "(MiFID II art. 25). Les réponses servent uniquement à paramétrer la simulation.")
        with st.form("form_investor_profile"):
            st.markdown("**1. Profil de risque**")
            score = 0
            answers = []
            for i, (q, opts) in enumerate(_RISK_QUESTIONS):
                a = st.radio(q, opts, index=None, key=f"rq_{i}")
                answers.append(a)
                if a is not None:
                    score += opts.index(a)
            st.markdown("**2. Test de connaissances sur les options (produits complexes)**")
            quiz = []
            for i, (q, opts, good) in enumerate(_OPTION_QUIZ):
                quiz.append((st.radio(q, opts, index=None, key=f"oq_{i}"), opts, good))
            ack = st.checkbox("J'ai compris que les options peuvent faire perdre la totalité de la prime investie "
                              "et que la plateforme est une simulation éducative.", key="opt_ack")
            ok = st.form_submit_button("💾 Enregistrer mon profil", use_container_width=True)
        if ok:
            if any(a is None for a in answers):
                st.error("Répondez aux 4 questions du profil de risque.")
                return
            risk = "Prudent" if score <= 3 else "Équilibré" if score <= 6 else "Dynamique" if score <= 9 else "Agressif"
            good = sum(1 for a, opts, g in quiz if a is not None and opts.index(a) == g)
            options_ok = good >= 3 and ack
            saved = save_profile({"risque": risk, "options_ok": options_ok, "score_risque": score,
                                  "score_options": good})
            msg = (f"✅ Profil **{risk}** enregistré (score {score}/12). Test options : {good}/4 — "
                   + ("options **autorisées**." if options_ok else
                      "options **fermées** (3 bonnes réponses et la case de compréhension sont nécessaires)."))
            st.success(msg + ("" if saved else " (profil conservé pour cette session)"))
