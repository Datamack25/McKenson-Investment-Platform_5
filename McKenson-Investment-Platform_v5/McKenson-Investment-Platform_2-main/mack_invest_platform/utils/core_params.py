# utils/core_params.py  —  MAM v5.12 · Cœur de la plateforme paramétrable par l'administrateur
"""
Le cœur de la plateforme fonctionne avec des valeurs par défaut (lecture du marché, risque, scénarios,
formules). L'administrateur — en tant que financier — peut les surcharger depuis
Admin → « 🧮 PARAMÈTRES FINANCIERS » selon ses préférences ou son analyse personnelle :

  * VALEURS : seuils (z-score, RSI, moyennes mobiles), fenêtres (bêta, volatilité), seuils de
    grosse perte, ratio de couverture cible, plafonds d'exposition personnels (ex. États-Unis, tech/IA)…
    Chaque valeur a des bornes de validation.
  * FORMULES : méthode de volatilité (historique / EWMA), et l'expression du score de scénario,
    évaluée de façon SÉCURISÉE (arithmétique et fonctions mathématiques autorisées uniquement,
    aucun code exécuté).
  * SCÉNARIOS : probabilités a priori, catalyseurs (probabilité, sens, force), impact attendu par
    secteur / actif et plans de remédiation ; probabilités forcées à la main si souhaité.
  * HISTORIQUE : chaque modification est tracée (qui, quand, ancienne → nouvelle valeur) ;
    retour aux valeurs par défaut en un clic.

Stockage : table hedge_fund_state (Supabase/PostgreSQL, clé « core_params ») — la même surcharge vaut
pour la plateforme ET pour le job hebdomadaire ; repli en mémoire si la base est indisponible.
Quand des paramètres personnalisés sont actifs, les rapports le mentionnent.
"""
from __future__ import annotations

import ast
import copy
import json
import math
import time
from datetime import datetime

STATE_KEY = "core_params"
CP_VERSION = "1.0"

# ══════════════════════════════════════════════════════════════════════════════
#  VALEURS PAR DÉFAUT (avec bornes)
# ══════════════════════════════════════════════════════════════════════════════
# kind : "float" | "int" | "pct" (stocké en fraction, affiché en %)
PARAMS: dict[str, dict] = {
    # ── Lecture du marché ──
    "z_stable": dict(group="Lecture du marché", label="z-score sous lequel le marché est « stable »", default=0.3,
                     min=0.0, max=1.0, step=0.05, kind="float"),
    "z_norme": dict(group="Lecture du marché", label="z-score « dans la norme » (en dessous)", default=1.2,
                    min=0.5, max=3.0, step=0.1, kind="float"),
    "z_fort": dict(group="Lecture du marché", label="z-score « mouvement fort »", default=2.0, min=1.0, max=4.0,
                   step=0.1, kind="float"),
    "z_exceptionnel": dict(group="Lecture du marché", label="z-score « mouvement exceptionnel »", default=3.0,
                           min=2.0, max=6.0, step=0.1, kind="float"),
    "vol_fenetre": dict(group="Lecture du marché", label="Fenêtre de la volatilité habituelle (séances)", default=252,
                        min=60, max=750, step=10, kind="int"),
    "rsi_survente": dict(group="Lecture du marché", label="RSI — seuil de survente", default=30, min=10, max=45,
                         step=1, kind="int"),
    "rsi_surachat": dict(group="Lecture du marché", label="RSI — seuil de surachat", default=70, min=55, max=90,
                         step=1, kind="int"),
    "mm_courte": dict(group="Lecture du marché", label="Moyenne mobile courte (séances)", default=50, min=10,
                      max=100, step=5, kind="int"),
    "mm_longue": dict(group="Lecture du marché", label="Moyenne mobile longue (séances)", default=200, min=100,
                      max=300, step=10, kind="int"),
    "ridge": dict(group="Lecture du marché", label="Régression des facteurs — pénalité ridge", default=2.0,
                  min=0.0, max=20.0, step=0.5, kind="float"),
    "fenetre_facteurs": dict(group="Lecture du marché", label="Régression des facteurs — séances d'estimation",
                             default=500, min=120, max=1000, step=20, kind="int"),
    # ── Portefeuille, pertes et couvertures ──
    "beta_fenetre": dict(group="Portefeuille & risque", label="Fenêtre du bêta du portefeuille (séances)", default=500,
                         min=60, max=1000, step=20, kind="int"),
    "beta_eleve": dict(group="Portefeuille & risque", label="Bêta jugé élevé", default=1.1, min=0.5, max=2.5,
                       step=0.05, kind="float"),
    "perte_jour": dict(group="Portefeuille & risque", label="Grosse perte — sur une séance", default=-0.03,
                       min=-0.20, max=-0.005, step=0.005, kind="pct"),
    "perte_semaine": dict(group="Portefeuille & risque", label="Grosse perte — sur une semaine", default=-0.05,
                          min=-0.30, max=-0.01, step=0.005, kind="pct"),
    "perte_drawdown": dict(group="Portefeuille & risque", label="Grosse perte — recul depuis le plus haut",
                           default=-0.10, min=-0.50, max=-0.02, step=0.01, kind="pct"),
    "couverture_cible": dict(group="Portefeuille & risque", label="Ratio de couverture cible (part protégée)",
                             default=0.50, min=0.10, max=1.0, step=0.05, kind="pct"),
    "couverture_ecart": dict(group="Portefeuille & risque",
                             label="Écart toléré entre perte couverte attendue et réelle", default=0.25, min=0.05,
                             max=0.80, step=0.05, kind="pct"),
    "put_otm_max": dict(group="Portefeuille & risque", label="Put jugé trop hors de la monnaie (strike sous le spot)",
                        default=0.07, min=0.02, max=0.25, step=0.01, kind="pct"),
    # ── Préférences personnelles du gérant ──
    "plafond_us": dict(group="Préférences du gérant", label="Plafond d'exposition aux actions américaines",
                       default=1.0, min=0.0, max=1.0, step=0.05, kind="pct"),
    "plafond_tech_ia": dict(group="Préférences du gérant", label="Plafond d'exposition tech / IA / semi-conducteurs",
                            default=1.0, min=0.0, max=1.0, step=0.05, kind="pct"),
    "plafond_ligne": dict(group="Préférences du gérant", label="Plafond par ligne (concentration)", default=0.20,
                          min=0.02, max=1.0, step=0.01, kind="pct"),
    # ── Scénarios ──
    "sc_sensibilite": dict(group="Scénarios", label="Sensibilité des probabilités au score (k)", default=0.55,
                           min=0.0, max=2.0, step=0.05, kind="float"),
    "w_momentum": dict(group="Scénarios", label="Poids — ampleur du mouvement (z)", default=0.35, min=-2, max=2,
                       step=0.05, kind="float"),
    "w_tendance": dict(group="Scénarios", label="Poids — tendance (vs moyenne longue)", default=0.45, min=-2, max=2,
                       step=0.05, kind="float"),
    "w_rsi": dict(group="Scénarios", label="Poids — RSI (contrarien : survente = rebond)", default=0.20, min=-2,
                  max=2, step=0.05, kind="float"),
    "w_peur": dict(group="Scénarios", label="Poids — peur (VIX)", default=0.45, min=-2, max=2, step=0.05,
                   kind="float"),
    "w_credit": dict(group="Scénarios", label="Poids — crédit", default=0.35, min=-2, max=2, step=0.05, kind="float"),
    "w_sentiment": dict(group="Scénarios", label="Poids — actualités et réseaux sociaux", default=0.25, min=-2,
                        max=2, step=0.05, kind="float"),
    "w_intraday": dict(group="Scénarios", label="Poids — dynamique intraday (6 h)", default=0.20, min=-2, max=2,
                       step=0.05, kind="float"),
    "w_catalyseurs": dict(group="Scénarios", label="Poids — catalyseurs / hypothèses", default=1.0, min=0, max=3,
                          step=0.05, kind="float"),
    # ── Intraday ──
    "intra_alerte": dict(group="Intraday", label="Alerte mouvement intraday (6 h)", default=0.015, min=0.002,
                         max=0.10, step=0.001, kind="pct"),
    "senti_bascule": dict(group="Intraday", label="Bascule de sentiment (écart 6 h vs 24 h)", default=0.25,
                          min=0.05, max=1.0, step=0.05, kind="float"),
}

FORMULAS: dict[str, dict] = {
    "vol_methode": dict(label="Méthode de volatilité (z-score)", default="historique",
                        choices=["historique", "ewma"], help="EWMA λ = 0,94 (RiskMetrics) réagit plus vite aux chocs."),
    "score_scenario": dict(
        label="Formule du score de scénario (positif = haussier)",
        default="w_momentum*momentum + w_tendance*tendance + w_rsi*rsi + w_peur*peur + w_credit*credit"
                " + w_sentiment*sentiment + w_intraday*intraday + w_catalyseurs*catalyseurs",
        help="Variables : momentum, tendance, rsi, peur, credit, sentiment, intraday, catalyseurs (chacune entre "
             "−1 et +1 environ) et tous les poids w_… ; fonctions : abs, min, max, clip, tanh, sqrt, log, exp, sign."),
}

# Impact attendu de chaque scénario par secteur / actif (en %, sur l'horizon du scénario)
SECTORS = ["Technologie", "Semi-conducteurs", "Communication & médias", "Consommation discrétionnaire",
           "Consommation de base", "Finance", "Santé", "Énergie", "Industrie", "Matériaux", "Services publics",
           "Immobilier", "Actions Europe", "Actions émergentes", "Or", "Obligations longues", "Bitcoin"]

DEFAULT_SCENARIOS: list[dict] = [
    dict(id="haussier", nom="Haussier — rebond et reprise", prior=0.30, prob_forcee=None, couleur="#00ff88",
         description="Les inquiétudes se dissipent (financement de l'IA rassurant, inflation qui reflue, "
                     "politique monétaire accommodante) : rebond mené par les valeurs les plus vendues.",
         impacts={"Technologie": 8, "Semi-conducteurs": 12, "Communication & médias": 6,
                  "Consommation discrétionnaire": 7, "Consommation de base": 1, "Finance": 5, "Santé": 2,
                  "Énergie": 3, "Industrie": 5, "Matériaux": 4, "Services publics": 0, "Immobilier": 4,
                  "Actions Europe": 5, "Actions émergentes": 6, "Or": -2, "Obligations longues": -1, "Bitcoin": 10},
         remediation=["Rester investi selon l'allocation cible ; renforcer par paliers les lignes de qualité sous-pondérées.",
                      "Alléger progressivement les couvertures devenues chères plutôt que de les garder jusqu'à l'échéance.",
                      "Ne pas courir après les titres les plus volatils : rééquilibrer si un poids dépasse sa bande."]),
    dict(id="central", nom="Central — volatilité et marché sans direction", prior=0.45, prob_forcee=None,
         couleur="#ffd700",
         description="Le marché digère le choc : rotation sectorielle, forte dispersion entre titres, volatilité "
                     "élevée mais sans nouvelle baisse généralisée.",
         impacts={"Technologie": -1, "Semi-conducteurs": -2, "Communication & médias": 0,
                  "Consommation discrétionnaire": -1, "Consommation de base": 2, "Finance": 1, "Santé": 2,
                  "Énergie": 1, "Industrie": 1, "Matériaux": 0, "Services publics": 2, "Immobilier": 0,
                  "Actions Europe": 1, "Actions émergentes": 0, "Or": 2, "Obligations longues": 1, "Bitcoin": -2},
         remediation=["Rééquilibrer vers l'allocation cible ; diversifier hors des secteurs les plus concentrés.",
                      "Privilégier des couvertures peu coûteuses (put spread, collar) sur l'exposition la plus risquée.",
                      "Investir les liquidités par paliers (investissement programmé) plutôt qu'en une fois."]),
    dict(id="baissier", nom="Baissier — correction prolongée", prior=0.25, prob_forcee=None, couleur="#ff3b6b",
         description="Le doute sur le financement de l'IA s'étend (crédit qui se tend, révisions de bénéfices, "
                     "choc politique ou géopolitique) : correction plus large et contagion aux autres places.",
         impacts={"Technologie": -15, "Semi-conducteurs": -22, "Communication & médias": -10,
                  "Consommation discrétionnaire": -12, "Consommation de base": -2, "Finance": -9, "Santé": -3,
                  "Énergie": -6, "Industrie": -8, "Matériaux": -8, "Services publics": -1, "Immobilier": -7,
                  "Actions Europe": -9, "Actions émergentes": -12, "Or": 5, "Obligations longues": 4, "Bitcoin": -20},
         remediation=["Vérifier que la perte potentielle reste sous la limite du profil ; réduire en priorité les "
                      "lignes à bêta élevé et les plus concentrées (tech / semi-conducteurs).",
                      "Compléter la couverture : puts plus proches de la monnaie, sur le bon sous-jacent (QQQ / SOXX "
                      "pour une exposition tech), avec une échéance d'au moins 2 à 3 mois.",
                      "Monter en qualité : obligations d'État, valeurs défensives, un peu d'or ; garder des liquidités "
                      "pour racheter par paliers.",
                      "Diversifier géographiquement (Europe, émergents de qualité) si l'exposition américaine dépasse "
                      "votre plafond."]),
]

# Catalyseurs (hypothèses qualitatives) : probabilité de survenue, sens (+1 haussier / −1 baissier), force (0–1)
DEFAULT_CATALYSTS: list[dict] = [
    dict(nom="Doutes sur le financement de l'IA (dette, capex, valorisations)", proba=0.35, sens=-1, force=0.8,
         actif=True),
    dict(nom="Résultats et prévisions solides des géants de la tech", proba=0.50, sens=1, force=0.6, actif=True),
    dict(nom="Banque centrale (Fed) plus accommodante que prévu", proba=0.40, sens=1, force=0.5, actif=True),
    dict(nom="Inflation plus forte que prévu / taux longs en hausse", proba=0.30, sens=-1, force=0.5, actif=True),
    dict(nom="Choc politique (élections, budget, régulation de la tech)", proba=0.30, sens=-1, force=0.5, actif=True),
    dict(nom="Tensions géopolitiques / commerciales", proba=0.30, sens=-1, force=0.4, actif=True),
]


# ══════════════════════════════════════════════════════════════════════════════
#  STOCKAGE (base → repli mémoire), CACHE
# ══════════════════════════════════════════════════════════════════════════════
_LOCAL: dict = {}
_CACHE = {"t": 0.0, "v": None}
PERSIST = {"ok": None}      # dernière écriture : True = en base, False = en mémoire seulement (base indisponible)
TTL = 120


def _empty() -> dict:
    return dict(values={}, formulas={}, scenarios=None, catalysts=None, history=[], revisions=[])


def _load() -> dict:
    if time.time() - _CACHE["t"] < TTL and _CACHE["v"] is not None:
        return _CACHE["v"]
    v = None
    try:
        from utils.alerts import get_state
        v = get_state(STATE_KEY)
    except Exception:
        v = None
    if not isinstance(v, dict):
        v = _LOCAL.get("state")
    st_ = {**_empty(), **(v or {})}
    _CACHE.update(t=time.time(), v=st_)
    return st_


def _save(state: dict) -> bool:
    state = {**state, "version": CP_VERSION, "date": datetime.now().strftime("%Y-%m-%d %H:%M")}
    state["history"] = (state.get("history") or [])[-300:]
    state["revisions"] = (state.get("revisions") or [])[-500:]
    _LOCAL["state"] = copy.deepcopy(state)
    ok = False
    try:
        from utils.alerts import set_state
        ok = bool(set_state(STATE_KEY, json.loads(json.dumps(state, default=str))))
    except Exception:
        ok = False
    _CACHE.update(t=time.time(), v=state)
    PERSIST["ok"] = ok
    return True   # toujours appliqué (en base si possible, sinon pour la session du serveur)


def clear_cache():
    _CACHE.update(t=0.0, v=None)


# ══════════════════════════════════════════════════════════════════════════════
#  LECTURE
# ══════════════════════════════════════════════════════════════════════════════
def _coerce(key: str, v):
    p = PARAMS[key]
    try:
        v = float(v)
    except (TypeError, ValueError):
        return p["default"]
    if not math.isfinite(v):
        return p["default"]
    v = min(max(v, p["min"]), p["max"])
    return int(round(v)) if p["kind"] == "int" else v


def get(key: str):
    """Valeur active (surcharge admin si présente, sinon défaut)."""
    if key not in PARAMS:
        raise KeyError(key)
    o = _load()["values"]
    return _coerce(key, o[key]) if key in o else PARAMS[key]["default"]


def values() -> dict:
    return {k: get(k) for k in PARAMS}


def formula(name: str) -> str:
    o = _load()["formulas"]
    f = FORMULAS[name]
    v = o.get(name, f["default"])
    if "choices" in f and v not in f["choices"]:
        return f["default"]
    return v


def scenarios() -> list[dict]:
    sc = _load().get("scenarios")
    base = copy.deepcopy(DEFAULT_SCENARIOS)
    if not sc:
        return base
    by_id = {s["id"]: s for s in sc if isinstance(s, dict) and s.get("id")}
    out = []
    for s in base:
        o = by_id.get(s["id"], {})
        m = {**s, **{k: v for k, v in o.items() if k in s}}
        m["impacts"] = {**s["impacts"], **{k: float(v) for k, v in (o.get("impacts") or {}).items()
                                           if _num(v) is not None}}
        out.append(m)
    return out


def catalysts() -> list[dict]:
    c = _load().get("catalysts")
    return copy.deepcopy(c) if isinstance(c, list) and c else copy.deepcopy(DEFAULT_CATALYSTS)


def _num(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def custom_keys() -> list[str]:
    st_ = _load()
    keys = [k for k, v in st_["values"].items() if k in PARAMS and _coerce(k, v) != PARAMS[k]["default"]]
    keys += [f"formule:{k}" for k, v in st_["formulas"].items() if k in FORMULAS and v != FORMULAS[k]["default"]]
    if st_.get("scenarios"):
        keys.append("scénarios")
    if st_.get("catalysts"):
        keys.append("catalyseurs")
    return keys


def is_custom() -> bool:
    return bool(custom_keys())


def custom_note() -> str | None:
    """Phrase pour les rapports quand le cœur a été personnalisé."""
    keys = custom_keys()
    if not keys:
        return None
    labels = []
    for k in keys[:8]:
        if k in PARAMS:
            p = PARAMS[k]
            v = get(k)
            labels.append(f"{p['label'].lower()} = {v:.1%}" if p["kind"] == "pct" else f"{p['label'].lower()} = {v:g}")
        else:
            labels.append(k)
    st_ = _load()
    return ("Paramètres personnalisés par l'administrateur (jugement d'expert, "
            f"{st_.get('date', '')}) : " + " ; ".join(labels) + (" …" if len(keys) > 8 else "") + ".")


def history() -> list[dict]:
    return list(reversed(_load().get("history") or []))


# ══════════════════════════════════════════════════════════════════════════════
#  ÉCRITURE (avec bornes et historique)
# ══════════════════════════════════════════════════════════════════════════════
def validate_value(key: str, v) -> str | None:
    p = PARAMS.get(key)
    if p is None:
        return f"paramètre inconnu : {key}"
    x = _num(v)
    if x is None:
        return f"{p['label']} : valeur non numérique"
    if not (p["min"] <= x <= p["max"]):
        return f"{p['label']} : {x:g} hors bornes [{p['min']:g} ; {p['max']:g}]"
    return None


def _cross_checks(vals: dict) -> list[str]:
    g = lambda k: vals.get(k, PARAMS[k]["default"])  # noqa: E731
    errs = []
    if not g("z_stable") < g("z_norme") < g("z_fort") < g("z_exceptionnel"):
        errs.append("Les seuils de z-score doivent être croissants : stable < norme < fort < exceptionnel.")
    if not g("rsi_survente") < g("rsi_surachat"):
        errs.append("Le seuil de survente du RSI doit être inférieur au seuil de surachat.")
    if not g("mm_courte") < g("mm_longue"):
        errs.append("La moyenne mobile courte doit être plus courte que la longue.")
    return errs


def set_values(changes: dict, who: str = "admin") -> tuple[bool, list[str]]:
    errs = [e for k, v in changes.items() if (e := validate_value(k, v))]
    st_ = copy.deepcopy(_load())
    new_vals = {**st_["values"], **{k: _coerce(k, v) for k, v in changes.items() if k in PARAMS}}
    errs += _cross_checks(new_vals)
    if errs:
        return False, errs
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for k, v in changes.items():
        old = get(k)
        nv = _coerce(k, v)
        if nv != old:
            st_["history"].append(dict(date=now, qui=who, cle=k, libelle=PARAMS[k]["label"], avant=old, apres=nv))
    st_["values"] = {k: v for k, v in new_vals.items() if v != PARAMS[k]["default"]}
    return _save(st_), []


def set_formula(name: str, value: str, who: str = "admin") -> tuple[bool, list[str]]:
    f = FORMULAS.get(name)
    if f is None:
        return False, [f"formule inconnue : {name}"]
    value = str(value).strip()
    if "choices" in f:
        if value not in f["choices"]:
            return False, [f"{f['label']} : choix invalide"]
    else:
        err = check_expression(value)
        if err:
            return False, [err]
    st_ = copy.deepcopy(_load())
    old = formula(name)
    if value != old:
        st_["history"].append(dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), qui=who, cle=f"formule:{name}",
                                   libelle=f["label"], avant=old, apres=value))
    if value == f["default"]:
        st_["formulas"].pop(name, None)
    else:
        st_["formulas"][name] = value
    return _save(st_), []


def set_scenarios(scs: list[dict], who: str = "admin") -> tuple[bool, list[str]]:
    errs = []
    clean = []
    for s in scs:
        pr = _num(s.get("prior"))
        if pr is None or not 0 < pr < 1:
            errs.append(f"{s.get('nom', s.get('id'))} : probabilité a priori entre 0 et 1 exclus")
        pf = s.get("prob_forcee")
        if pf not in (None, "") and (_num(pf) is None or not 0 <= _num(pf) <= 1):
            errs.append(f"{s.get('nom', s.get('id'))} : probabilité forcée entre 0 et 1")
        clean.append(dict(id=s["id"], nom=str(s.get("nom", s["id"]))[:80], prior=pr,
                          prob_forcee=None if pf in (None, "") or _num(pf) is None else _num(pf),
                          description=str(s.get("description", ""))[:600],
                          impacts={k: _num(v) for k, v in (s.get("impacts") or {}).items() if _num(v) is not None},
                          remediation=[str(x)[:400] for x in (s.get("remediation") or []) if str(x).strip()]))
    forced = [c["prob_forcee"] for c in clean if c["prob_forcee"] is not None]
    if forced and len(forced) == len(clean) and abs(sum(forced) - 1) > 0.02:
        errs.append(f"Les probabilités forcées doivent totaliser 100 % (actuellement {sum(forced):.0%}).")
    if errs:
        return False, errs
    st_ = copy.deepcopy(_load())
    st_["history"].append(dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), qui=who, cle="scénarios",
                               libelle="Scénarios (probabilités, impacts, remédiation)", avant="—", apres="modifiés"))
    st_["scenarios"] = clean
    return _save(st_), []


def set_catalysts(cats: list[dict], who: str = "admin") -> tuple[bool, list[str]]:
    clean, errs = [], []
    for c in cats:
        nom = str(c.get("nom", "")).strip()
        if not nom:
            continue
        p, f, s = _num(c.get("proba")), _num(c.get("force")), _num(c.get("sens"))
        if p is None or not 0 <= p <= 1:
            errs.append(f"{nom} : probabilité entre 0 et 1")
        if f is None or not 0 <= f <= 1:
            errs.append(f"{nom} : force entre 0 et 1")
        if s not in (-1, 1, -1.0, 1.0):
            errs.append(f"{nom} : sens = +1 (haussier) ou −1 (baissier)")
        clean.append(dict(nom=nom[:120], proba=p, sens=int(s or 0), force=f, actif=bool(c.get("actif", True))))
    if errs:
        return False, errs
    st_ = copy.deepcopy(_load())
    st_["history"].append(dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), qui=who, cle="catalyseurs",
                               libelle="Catalyseurs / hypothèses", avant="—", apres=f"{len(clean)} catalyseur(s)"))
    st_["catalysts"] = clean
    return _save(st_), []


def reset(what: str = "all", who: str = "admin") -> bool:
    st_ = copy.deepcopy(_load())
    if what in ("all", "values"):
        st_["values"] = {}
    if what in ("all", "formulas"):
        st_["formulas"] = {}
    if what in ("all", "scenarios"):
        st_["scenarios"] = None
    if what in ("all", "catalysts"):
        st_["catalysts"] = None
    st_["history"].append(dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), qui=who, cle=f"reset:{what}",
                               libelle="Retour aux valeurs par défaut", avant="personnalisé", apres="défaut"))
    return _save(st_)


def export_json() -> str:
    st_ = _load()
    return json.dumps({k: st_.get(k) for k in ("values", "formulas", "scenarios", "catalysts")}, ensure_ascii=False,
                      indent=1, default=str)


def import_json(text: str, who: str = "admin") -> tuple[bool, list[str]]:
    try:
        d = json.loads(text)
    except Exception as e:
        return False, [f"JSON invalide : {e}"]
    errs = []
    if d.get("values"):
        ok, e = set_values(d["values"], who)
        errs += e
    for k, v in (d.get("formulas") or {}).items():
        ok, e = set_formula(k, v, who)
        errs += e
    if d.get("scenarios"):
        ok, e = set_scenarios(d["scenarios"], who)
        errs += e
    if d.get("catalysts"):
        ok, e = set_catalysts(d["catalysts"], who)
        errs += e
    return not errs, errs


# ══════════════════════════════════════════════════════════════════════════════
#  RÉVISIONS DE PROBABILITÉS (historique « 20 % → 30 % »)
# ══════════════════════════════════════════════════════════════════════════════
def add_revision(market: str, probs: dict, note: str = "", who: str = "admin") -> bool:
    st_ = copy.deepcopy(_load())
    st_["revisions"].append(dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), marche=market, qui=who,
                                 note=str(note)[:300], **{f"p_{k}": round(float(v), 4) for k, v in probs.items()}))
    return _save(st_)


def revisions(market: str | None = None) -> list[dict]:
    r = _load().get("revisions") or []
    return [x for x in r if market is None or x.get("marche") == market]


# ══════════════════════════════════════════════════════════════════════════════
#  ÉVALUATION SÉCURISÉE DES FORMULES
# ══════════════════════════════════════════════════════════════════════════════
_FUNCS = {"abs": abs, "min": min, "max": max, "sqrt": math.sqrt, "log": math.log, "exp": math.exp,
          "tanh": math.tanh, "sign": lambda x: (x > 0) - (x < 0),
          "clip": lambda x, lo, hi: max(lo, min(hi, x))}
_OK_NODES = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Name, ast.Load, ast.Call, ast.Add, ast.Sub,
             ast.Mult, ast.Div, ast.Pow, ast.USub, ast.UAdd, ast.Mod, ast.IfExp, ast.Compare, ast.Gt, ast.Lt,
             ast.GtE, ast.LtE, ast.BoolOp, ast.And, ast.Or)
SCORE_VARS = ["momentum", "tendance", "rsi", "peur", "credit", "sentiment", "intraday", "catalyseurs"]


def check_expression(expr: str, extra_vars=()) -> str | None:
    if not expr or len(expr) > 600:
        return "Formule vide ou trop longue (600 caractères maximum)."
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as e:
        return f"Syntaxe invalide : {e.msg}"
    allowed = set(_FUNCS) | set(SCORE_VARS) | {k for k in PARAMS if k.startswith("w_")} | set(extra_vars)
    for n in ast.walk(tree):
        if not isinstance(n, _OK_NODES):
            return f"Élément non autorisé dans la formule : {type(n).__name__}"
        if isinstance(n, ast.Name) and n.id not in allowed:
            return f"Variable inconnue : {n.id}"
        if isinstance(n, ast.Call) and not (isinstance(n.func, ast.Name) and n.func.id in _FUNCS):
            return "Seules les fonctions abs, min, max, clip, tanh, sqrt, log, exp, sign sont autorisées."
        if isinstance(n, ast.Constant) and not isinstance(n.value, (int, float)):
            return "Seuls des nombres sont autorisés comme constantes."
    try:
        safe_eval(expr, {v: 0.1 for v in allowed if v not in _FUNCS})
    except Exception as e:
        return f"La formule ne peut pas être calculée : {type(e).__name__}"
    return None


def safe_eval(expr: str, env: dict) -> float:
    tree = ast.parse(expr, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant):
            return float(n.value)
        if isinstance(n, ast.Name):
            if n.id in env:
                return float(env[n.id])
            raise NameError(n.id)
        if isinstance(n, ast.UnaryOp):
            v = ev(n.operand)
            return -v if isinstance(n.op, ast.USub) else v
        if isinstance(n, ast.BinOp):
            a, b = ev(n.left), ev(n.right)
            op = n.op
            if isinstance(op, ast.Add):
                return a + b
            if isinstance(op, ast.Sub):
                return a - b
            if isinstance(op, ast.Mult):
                return a * b
            if isinstance(op, ast.Div):
                return a / b if b else 0.0
            if isinstance(op, ast.Mod):
                return a % b if b else 0.0
            if isinstance(op, ast.Pow):
                if abs(b) > 10:
                    raise ValueError("exposant trop grand")
                return a ** b
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS:
            return float(_FUNCS[n.func.id](*[ev(a) for a in n.args]))
        if isinstance(n, ast.IfExp):
            return ev(n.body) if ev(n.test) else ev(n.orelse)
        if isinstance(n, ast.Compare) and len(n.ops) == 1:
            a, b, op = ev(n.left), ev(n.comparators[0]), n.ops[0]
            return float(a > b if isinstance(op, ast.Gt) else a < b if isinstance(op, ast.Lt)
                         else a >= b if isinstance(op, ast.GtE) else a <= b)
        if isinstance(n, ast.BoolOp):
            vals = [ev(v) for v in n.values]
            return float(all(vals) if isinstance(n.op, ast.And) else any(vals))
        raise ValueError(f"élément non autorisé : {type(n).__name__}")

    out = ev(tree)
    if not math.isfinite(out):
        raise ValueError("résultat non fini")
    return out
