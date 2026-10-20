# utils/sentiment.py  —  MAM v5.4 · Tonalité des titres d'actualité et pertinence par classe d'actifs
"""
Analyse de sentiment par LEXIQUE FINANCIER (français + anglais), inspirée du
dictionnaire de Loughran et McDonald (2011), conçu pour les textes financiers :
des mots neutres dans la langue courante (« passif », « volatilité », « défaut »)
y ont un sens négatif précis.

Chaque titre reçoit une tonalité entre −1 (mauvaise nouvelle pour les marchés) et
+1 (bonne nouvelle), selon trois règles :
1. mots positifs / négatifs du lexique ;
2. NÉGATION : « pas », « sans », « no », « not »… inversent le mot qui suit (fenêtre
   de 3 mots) — « no recession » devient positif ;
3. mots de DIRECTION (« hausse », « rise », « baisse », « fall »…) dont le sens dépend
   de ce qui monte (mot voisin, à 3 mots près) : la hausse des actions est positive,
   celle de l'inflation, des taux, du chômage ou du pétrole est négative.

La PERTINENCE rattache chaque titre aux classes d'actifs qu'il concerne (mots-clés
par classe) : on obtient une tonalité par classe d'actifs, en plus de l'intensité
par thème déjà mesurée par la veille.

Limites assumées : un lexique ne comprend ni l'ironie, ni le contexte long, ni les
nuances de dosage ; c'est un indicateur de tonalité moyenne, pas une compréhension
du texte. Il est léger, gratuit, transparent et fonctionne sur Streamlit Cloud.
"""
from __future__ import annotations

import math
import re
import unicodedata

SENTIMENT_VERSION = "1.0"


def _n(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)?", _n(text))


# ── Lexique (formes normalisées sans accents ; racines suivies de « * ») ─────────
POS = """
gain* rebond* rally rallies rallied surge* surg* soar* jump* optimis* confian* reprise recover* rebound*
croissance growth expan* accord* deal* ceasefire cessez paix peace detente desescalad* de-escalat* stabilis* stabiliz*
solid* robust* beat* beats depasse* surpass* amelior* improv* hausse_actions benefic* profit* upgrad*
resilien* soutien support* stimul* relance boost* accelerat* creation embauche* hiring hire* emplois_crees
apaise* calme calm* baisse_taux assoupliss* desinflation disinflation opportunit* succes success*
favorable positive positif upbeat bullish haussier* record_high sommet* plus_haut
""".split()
NEG = """
chute* chut* plong* krach crash* effondr* collapse* plunge* tumbl* slump* sell-off selloff panique panic* peur fear*
recession* contraction* ralentiss* slowdown* stagflation crise* crisis default* defaut* faillite* bankrupt* insolvab*
licenci* layoff* chomage unemployment destruction* deficit* dette_excessive downgrad* degrad* abaiss* sanction* embargo*
guerre war* conflit* conflict* attaque* attack* frappe* strike* missile* invasion* bombard* escalad* escalat* tension*
menace* threat* risque* risk* incertitude* uncertain* volatil* instabil* instab* turmoil turbulen* tarif* tariff*
droits_de_douane protectionnis* represaill* retaliat* inflation_hausse pression* pressure* perte* loss* losses deficit
warn* alert* avertiss* inquiet* worr* concern* fragil* weak* faibl* miss missed decevant* disappoint* shutdown censure
blocage* deadlock* gel* freeze* penurie* shortage* choc* shock* bearish baissier* plus_bas
""".split()
NEGATORS = {"pas", "sans", "aucun", "aucune", "ni", "jamais", "no", "not", "without", "never", "nor", "non", "neither",
            "avoid", "avoids", "avoided", "evite", "evitent", "ecarte", "ecartee", "eloigne"}
UP = {"hausse", "monte", "montee", "grimpe", "grimpent", "bondit", "augmente", "augmentation", "accelere", "rise",
      "rises", "rising", "rose", "climb", "climbs", "climbing", "jumps", "higher", "increase", "increases", "up",
      "flambe", "flambee", "envolee", "spike", "spikes", "soars", "surges", "surge", "surged", "soar", "soared", "soaring", "jump", "jumped", "record", "records"}
DOWN = {"baisse", "recul", "recule", "reculent", "repli", "diminue", "diminution", "ralentit", "fall", "falls",
        "falling", "fell", "drop", "drops", "dropped", "decline", "declines", "lower", "down", "eases", "easing",
        "cools", "cooling", "retombe", "chute", "chutent", "plonge", "plongent", "plunge", "plunges", "plunged",
        "slump", "slumps", "slumped", "tumble", "tumbles", "tumbled", "sink", "sinks"}
# Ce qui, en montant, est une MAUVAISE nouvelle pour les marchés (le sens des mots de direction s'inverse)
BAD_WHEN_UP = {"inflation", "prix", "prices", "taux", "rates", "rate", "yields", "rendements", "chomage",
               "unemployment", "jobless", "petrole", "oil", "brent", "gaz", "gas", "dette", "debt", "deficit",
               "volatilite", "volatility", "vix", "spreads", "spread", "defaillances", "defaults", "tensions",
               "tarifs", "tariffs", "douane", "cpi", "pce", "salaires"}


def _match(word: str, lex: list[str]) -> bool:
    for e in lex:
        if "_" in e:
            continue
        if e.endswith("*"):
            if word.startswith(e[:-1]):
                return True
        elif word == e:
            return True
    return False


POS_STEMS = [e for e in POS if "_" not in e]
NEG_STEMS = [e for e in NEG if "_" not in e]
# faux amis à exclure des racines (ex. « fort » dans « effort », « gain » ok)
_STOP = {"risque_zero", "or", "et", "de", "la", "le", "les", "des", "du", "en", "a", "the", "of", "to", "in", "on",
         "for", "and", "is", "are", "by", "with", "as", "at", "from", "fortune", "forte", "fortement"}


def score_title(title: str) -> dict:
    """Tonalité d'un titre : dict(score ∈ [−1, 1], pos, neg, mots)."""
    w = _words(title)
    pos = neg = 0.0
    hits = []
    bad_ctx = any(x in BAD_WHEN_UP for x in w)
    has_dir = any(x in UP or x in DOWN for x in w)
    for i, x in enumerate(w):
        if x in _STOP or (has_dir and x in BAD_WHEN_UP):
            continue          # « le chômage recule » : c'est la direction qui porte le sens
        negated = any(y in NEGATORS for y in w[max(0, i - 3):i])
        val = 0.0
        if x in UP or x in DOWN:
            direction = 1.0 if x in UP else -1.0
            # direction appliquée à un terme « mauvais quand il monte » → sens inversé
            near = w[max(0, i - 3):i + 4]
            val = -direction if any(y in BAD_WHEN_UP for y in near) else 0.5 * direction
        elif _match(x, NEG_STEMS):
            val = -1.0
        elif _match(x, POS_STEMS):
            val = 1.0
        if val == 0.0:
            continue
        if negated:
            val = -val
        hits.append((x, val))
        if val > 0:
            pos += val
        else:
            neg += -val
    tot = pos + neg
    score = 0.0 if tot == 0 else (pos - neg) / (tot + 1.0)
    return dict(score=float(max(-1.0, min(1.0, score))), pos=pos, neg=neg, mots=hits)


# ── Pertinence par classe d'actifs ──────────────────────────────────────────────
CLASS_KEYWORDS = {
    "Actions US": ["wall street", "s&p", "sp 500", "nasdaq", "dow jones", "us stocks", "american stocks",
                   "actions americaines", "nvidia", "apple", "microsoft", "tesla", "earnings", "resultats trimestriels"],
    "Actions Europe": ["europe", "europeen", "european", "cac 40", "cac", "dax", "stoxx", "bourse de paris",
                       "zone euro", "eurozone", "bce", "ecb", "france", "allemagne", "germany"],
    "Actions Asie & émergents": ["chine", "china", "chinese", "emergent", "emerging", "inde", "india", "japon", "japan",
                                 "bresil", "brazil", "hong kong", "asie", "asia", "taiwan", "coree", "korea"],
    "Oblig. long terme": ["treasury", "treasuries", "bond", "bonds", "obligation", "obligataire", "10 ans", "10-year",
                          "30 ans", "30-year", "rendement", "yields", "oat", "bund"],
    "Oblig. moyen terme": ["fed", "federal reserve", "taux directeur", "interest rate", "rate cut", "rate hike",
                           "baisse des taux", "hausse des taux", "banque centrale", "central bank"],
    "Crédit IG": ["credit", "corporate bond", "obligations d'entreprises", "notation", "rating", "moody", "fitch",
                  "standard & poor"],
    "High yield": ["high yield", "junk", "haut rendement", "default", "defaut", "faillite", "bankruptcy", "leveraged"],
    "Or": ["gold", "l'or", "prix de l'or", "metal jaune", "lingot", "bullion"],
    "Matières premières": ["oil", "petrole", "brent", "wti", "opep", "opec", "gaz", "gas", "cuivre", "copper",
                           "ble", "wheat", "matieres premieres", "commodities", "energie", "energy"],
    "Crypto": ["bitcoin", "crypto", "ether", "ethereum", "stablecoin", "blockchain"],
    "Liquidités": ["dollar", "devise", "currency", "euro dollar", "change", "forex"],
}


def relevant_classes(title: str) -> list[str]:
    t = " " + _n(title) + " "
    out = []
    for cls, kws in CLASS_KEYWORDS.items():
        for k in kws:
            kk = _n(k)
            if re.search(r"(?<![a-z])" + re.escape(kk) + r"(?![a-z])", t):
                out.append(cls)
                break
    return out


def label(score: float, n: int) -> str:
    if n == 0:
        return "sans titre"
    if score >= 0.15:
        return "plutôt positive"
    if score <= -0.15:
        return "plutôt négative"
    return "neutre / partagée"


def theme_sentiment(items: list[dict], now=None) -> dict:
    """Tonalité moyenne d'un thème, pondérée par la fraîcheur (mêmes poids que l'intensité)."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    num = den = 0.0
    pos = neg = 0
    scored = []
    for it in items:
        s = score_title(it.get("title", ""))
        try:
            age = max((now - it["date"]).total_seconds() / 86400, 0)
        except Exception:
            age = 3
        w = 1.0 if age <= 2 else (0.6 if age <= 4 else 0.3)
        num += w * s["score"]
        den += w
        pos += s["score"] > 0.05
        neg += s["score"] < -0.05
        scored.append((it, s["score"], w))
    sc = num / den if den else 0.0
    return dict(score=sc, n=len(items), positifs=int(pos), negatifs=int(neg), libelle=label(sc, len(items)),
                scored=scored)


def class_sentiment(themes: dict) -> dict:
    """Tonalité par classe d'actifs à partir de tous les titres de la veille (dédoublonnés)."""
    acc: dict[str, list] = {}
    seen = set()
    for th in themes.values():
        for it, s, w in (th.get("sentiment") or {}).get("scored", []):
            key = _n(it.get("title", ""))[:60]
            if key in seen:
                continue
            seen.add(key)
            for c in relevant_classes(it.get("title", "")):
                acc.setdefault(c, []).append((s, w, it.get("title", "")))
    out = {}
    for c, lst in acc.items():
        den = sum(w for _, w, _ in lst)
        sc = sum(s * w for s, w, _ in lst) / den if den else 0.0
        worst = sorted(lst, key=lambda x: x[0])[:2]
        best = sorted(lst, key=lambda x: -x[0])[:2]
        out[c] = dict(score=sc, n=len(lst), libelle=label(sc, len(lst)),
                      exemples_neg=[t for s, _, t in worst if s < -0.05],
                      exemples_pos=[t for s, _, t in best if s > 0.05])
    return out


def enrich(themes: dict) -> dict:
    """Ajoute à chaque thème sa tonalité (clé « sentiment ») et la tonalité de ses titres affichés."""
    for th in themes.values():
        items = th.get("_all") or th.get("headlines") or []
        th["sentiment"] = theme_sentiment(items)
        for h in th.get("headlines", []):
            h["tonalite"] = score_title(h.get("title", ""))["score"]
        th.pop("_all", None)
    return themes
