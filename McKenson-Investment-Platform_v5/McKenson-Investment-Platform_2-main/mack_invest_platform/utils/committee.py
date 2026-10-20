# utils/committee.py  —  MAM v5.3 · Comité d'investissement virtuel
"""
Six professionnels VIRTUELS (personnages fictifs) examinent chaque portefeuille :

  🌦️ Jean-Michel TAUX-BAS   — Économiste en chef      (inspiration : Ray Dalio)
  🧮 Mc Henson ALGO-RITHME      — Recherche quantitative   (inspiration : Jim Simons)
  🏛️ Thierry BALANCEMENT        — Gérant principal (CIO)   (inspiration : Buffett, Graham, Bogle)
  🛡️ Aline DE MARGE     — Directrice des risques   (inspiration : John Hull, Howard Marks)
  ⚖️ Constance Probité      — Conformité               (cadre MiFID II / AMF / UCITS / MiCA)
  🎙️ Marc ETING-FINANCIER      — Relation client (CPM)    (inspiration : Peter Lynch)

Chaque membre rend un avis motivé (✅ favorable / ⚠️ réserves / ⛔ veto). Seules la
directrice des risques et la conformité disposent d'un VETO, qui bloque la création
d'un portefeuille et l'exécution d'une optimisation. Le CPM rédige la synthèse.

Le portefeuille est jugé au regard de sa DÉCLARATION DE POLITIQUE D'INVESTISSEMENT
(IPS, standard CFA / questionnaire d'adéquation MiFID II) : objectif, horizon, perte
maximale acceptable, liquidité, part du patrimoine, expérience, ESG, exclusions,
enveloppe, préférence de couverture.

Module sans interface : utilisé par la plateforme ET par le rapport hebdomadaire.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from utils import advisor as A

COMMITTEE_VERSION = "1.1"
COMMITTEE_NAME = "COMITÉ DE GESTION MIP — L'ÉQUIPE DU DESK"

# ══════════════════════════════════════════════════════════════════════════════
#  COMITÉ DE GESTION MIP — L'ÉQUIPE DU DESK (personnages fictifs)
# ══════════════════════════════════════════════════════════════════════════════
MEMBERS = [
    dict(id="eco", nom="Jean-Michel TAUX-BAS", role="Économiste en chef — Macro & Régimes", surnom="Le Météorologue des cycles",
         emoji="🌦️", couleur="#00d4ff", veto=False,
         inspiration="Ray Dalio",
         style=("Lit l'économie comme une machine : cycles du crédit, croissance et inflation. Il ne parie pas sur "
                "une prévision, il prépare le portefeuille à plusieurs régimes."),
         citation=("Celui qui vit par la boule de cristal finira par manger du verre brisé.", "Ray Dalio")),
    dict(id="quant", nom="Mc Henson ALGO-RITHME", role="Responsable Quant — Signaux & ML", surnom="Le Signal",
         emoji="🧮", couleur="#7c3aed", veto=False,
         inspiration="Jim Simons (Renaissance Technologies)",
         style=("Aucune opinion sans preuve statistique : beaucoup de petits signaux, testés hors échantillon. "
                "On ne contredit jamais le modèle par intuition."),
         citation=("Un signal sans preuve statistique n'est qu'une opinion.", "Mc Henson ALGO-RITHME"),
         maximes=["Un signal sans preuve statistique n'est qu'une opinion.",
                  "On ne contredit pas le modèle par intuition : on le contredit par des données.",
                  "Beaucoup de petits avantages valent mieux qu'une grande certitude.",
                  "Ce qui n'a pas été testé hors échantillon n'a pas été testé."]),
    dict(id="cio", nom="Thierry BALANCEMENT", role="Gérant de portefeuille — Ordres & Stratégie", surnom="Marge de sécurité",
         emoji="🏛️", couleur="#00ff88", veto=False,
         inspiration="Warren Buffett, Benjamin Graham, John Bogle",
         style=("Qualité, marge de sécurité et long terme. Quand on n'a pas d'avantage particulier, on diversifie "
                "largement et on réduit les frais au minimum."),
         citation=("Règle n° 1 : ne jamais perdre d'argent. Règle n° 2 : ne jamais oublier la règle n° 1.",
                   "Warren Buffett"),
         citation2=("Ne cherchez pas l'aiguille dans la botte de foin : achetez la botte de foin.", "John Bogle")),
    dict(id="cro", nom="Aline DE MARGE", role="Responsable du risque — Garde-fou & Limites", surnom="La Gardienne",
         emoji="🛡️", couleur="#ff3b6b", veto=True,
         inspiration="John Hull (Risk Management and Financial Institutions), Howard Marks",
         style=("Mesure avant de croire : VaR, Expected Shortfall, stress tests et backtesting du modèle de risque. "
                "Elle se prépare aux scénarios plutôt que de les prédire. Droit de veto."),
         citation=("On ne peut pas prédire. On peut se préparer.", "Howard Marks")),
    dict(id="cmp", nom="Constance Probité", role="Conformité — Règles & Exclusions", surnom="La Vigie",
         emoji="⚖️", couleur="#ffd700", veto=True,
         inspiration="Cadre MiFID II, AMF, UCITS, MiCA",
         style=("Vérifie que chaque décision respecte la politique d'investissement, les exclusions et les règles "
                "de protection de l'investisseur. Droit de veto."),
         citation=None),
    dict(id="cpm", nom="Marc ETING-FINANCIER", role="Relation client (CPM) — Reporting & Biais", surnom="Le Traducteur",
         emoji="🎙️", couleur="#ff8c00", veto=False,
         inspiration="Peter Lynch",
         style=("Explique simplement ce que vous possédez et pourquoi, repère les biais comportementaux qui "
                "guettent l'investisseur, puis transforme les avis du comité en décisions claires."),
         citation=("Sachez ce que vous possédez, et pourquoi vous le possédez.", "Peter Lynch")),
]
MEMBER = {m["id"]: m for m in MEMBERS}

VOTE_LABEL = {"ok": "✅ Favorable", "reserve": "⚠️ Favorable avec réserves", "veto": "⛔ Défavorable — veto"}
VOTE_COLOR = {"ok": "#00ff88", "reserve": "#ffd700", "veto": "#ff3b6b"}
VERDICT_LABEL = {"ok": "✅ VALIDÉ PAR LE COMITÉ", "reserve": "⚠️ VALIDÉ AVEC RÉSERVES",
                 "veto": "⛔ REFUSÉ PAR LE COMITÉ"}

# ══════════════════════════════════════════════════════════════════════════════
#  DÉCLARATION DE POLITIQUE D'INVESTISSEMENT (IPS)
# ══════════════════════════════════════════════════════════════════════════════
IPS_OPTIONS = {
    "objectif": ["Préserver le capital", "Revenu régulier", "Croissance équilibrée", "Croissance forte",
                 "Performance maximale (spéculatif)"],
    "horizon": ["Moins de 2 ans", "2 à 5 ans", "5 à 8 ans", "8 à 15 ans", "Plus de 15 ans"],
    "perte_max": [0.05, 0.10, 0.15, 0.20, 0.30, 0.40],
    "reaction": ["Je vends tout", "Je vends une partie", "Je ne fais rien", "J'en rachète"],
    "liquidite": ["Probable (retraits prévus)", "Possible (imprévu)", "Aucun besoin"],
    "patrimoine": ["Plus de 50 %", "25 à 50 %", "10 à 25 %", "Moins de 10 %"],
    "experience": ["Débutant", "Intermédiaire", "Confirmé", "Expert (dérivés)"],
    "esg": ["Indifférent", "Préférence ESG", "ESG strict"],
    "exclusions": ["Crypto-actifs", "Énergies fossiles", "Armement", "Tabac"],
    "enveloppe": ["Compte-titres (ETF US)", "Compte-titres (ETF UCITS européens)", "PEA", "Assurance-vie (UCITS)"],
    "couvertures": ["Le comité peut proposer des couvertures", "Seulement si le risque est élevé", "Jamais d'options"],
}
IPS_LABELS = {
    "objectif": "Objectif principal", "horizon": "Horizon de placement",
    "perte_max": "Perte maximale acceptable sur 1 an",
    "reaction": "Si le portefeuille perd 20 % en 3 mois…", "liquidite": "Besoin de retirer de l'argent avant l'horizon",
    "patrimoine": "Part de votre épargne investie ici", "experience": "Expérience de l'investissement",
    "esg": "Critères ESG", "exclusions": "Exclusions", "enveloppe": "Enveloppe / univers d'ETF",
    "couvertures": "Couvertures par options",
}
PROFILES = ["Prudent", "Équilibré", "Dynamique", "Agressif"]

EXCLUSION_TICKERS = {
    "Énergies fossiles": {"XOM", "CVX", "COP", "OXY", "SLB", "EOG", "XLE", "USO", "BNO", "UNG", "CL=F", "BZ=F", "NG=F",
                          "MCL=F", "TTE.PA", "BP.L", "SHEL.L", "SHEL", "ENI.MI", "EQNR", "REP.MC", "DBC", "PDBC", "GSG"},
    "Armement": {"ITA", "LMT", "RTX", "NOC", "GD", "LHX", "BA", "AIR.PA", "HO.PA", "RHM.DE", "BA.L"},
    "Tabac": {"MO", "PM", "BTI", "IMB.L"},
}
_PEA_SUFFIX = (".PA", ".DE", ".AS", ".MI", ".MC", ".BR", ".LS", ".IR", ".VI", ".HE", ".ST", ".CO", ".OL")


def default_ips(profile: str = "Équilibré") -> dict:
    base = {
        "Prudent":   dict(objectif=1, horizon=1, perte_max=0.10, reaction=1, liquidite=1, patrimoine=1),
        "Équilibré": dict(objectif=2, horizon=2, perte_max=0.15, reaction=2, liquidite=1, patrimoine=2),
        "Dynamique": dict(objectif=3, horizon=3, perte_max=0.20, reaction=2, liquidite=2, patrimoine=2),
        "Agressif":  dict(objectif=3, horizon=4, perte_max=0.30, reaction=3, liquidite=2, patrimoine=3),
    }[profile if profile in PROFILES else "Équilibré"]
    o = IPS_OPTIONS
    return dict(objectif=o["objectif"][base["objectif"]], horizon=o["horizon"][base["horizon"]],
                perte_max=base["perte_max"], reaction=o["reaction"][base["reaction"]],
                liquidite=o["liquidite"][base["liquidite"]], patrimoine=o["patrimoine"][base["patrimoine"]],
                experience="Intermédiaire", esg="Indifférent", exclusions=[],
                enveloppe=o["enveloppe"][0], couvertures=o["couvertures"][0])


def _idx(ips: dict, key: str, default: int = 0) -> int:
    try:
        return IPS_OPTIONS[key].index(ips.get(key))
    except Exception:
        return default


def ips_profile(ips: dict) -> tuple[str, int, list[str]]:
    """Profil de risque issu de l'IPS : (profil, score /21, contraintes qui l'ont plafonné).
    Comme pour l'adéquation MiFID II, la contrainte la plus prudente l'emporte."""
    pm = float(ips.get("perte_max", 0.15))
    pm_pts = min(range(len(IPS_OPTIONS["perte_max"])), key=lambda i: abs(IPS_OPTIONS["perte_max"][i] - pm))
    score = (_idx(ips, "horizon", 2) + pm_pts + _idx(ips, "reaction", 2) + _idx(ips, "liquidite", 1)
             + _idx(ips, "patrimoine", 2) + _idx(ips, "objectif", 2))
    prof = 0 if score <= 6 else 1 if score <= 11 else 2 if score <= 16 else 3
    caps, why = [], []
    h = _idx(ips, "horizon", 2)
    if h == 0:
        caps.append(0); why.append("horizon de moins de 2 ans → profil Prudent au maximum")
    elif h == 1:
        caps.append(1); why.append("horizon de 2 à 5 ans → profil Équilibré au maximum")
    if pm <= 0.10:
        caps.append(0); why.append(f"perte maximale acceptable de {pm:.0%} → profil Prudent au maximum")
    elif pm <= 0.15:
        caps.append(1); why.append(f"perte maximale acceptable de {pm:.0%} → profil Équilibré au maximum")
    if _idx(ips, "liquidite", 1) == 0:
        caps.append(1); why.append("retraits prévus avant l'horizon → profil Équilibré au maximum")
    if _idx(ips, "reaction", 2) == 0:
        caps.append(1); why.append("vente totale en cas de baisse de 20 % → profil Équilibré au maximum")
    final = min([prof] + caps)
    return PROFILES[final], score, (why if final < prof else [])


def constraints(ips: dict) -> dict:
    """Contraintes de gestion dérivées de l'IPS (resserrent les limites du profil)."""
    prof, score, capped = ips_profile(ips)
    lim = A.LIMITS[prof]
    pm = float(ips.get("perte_max", 0.15))
    eq_by_h = [0.20, 0.50, 0.70, 0.85, 0.95][_idx(ips, "horizon", 2)]
    excl = set(ips.get("exclusions") or [])
    cash_min = lim["cash"] + {0: 0.10, 1: 0.03, 2: 0.0}[_idx(ips, "liquidite", 1)]
    return dict(
        profil=prof, score=score, plafonne_par=capped, perte_max=pm,
        # VaR 95 % à 1 an ≈ 1,645 σ : la volatilité cible garantit perte potentielle ≤ perte maximale acceptable
        vol_cible=min(lim["vol"] * 1.6, pm / 1.645),
        equity_max=min(lim["equity"] + 0.10, eq_by_h),
        crypto_max=0.0 if "Crypto-actifs" in excl else lim["crypto"],
        cash_min=cash_min,
        exclusions=excl, enveloppe=ips.get("enveloppe", IPS_OPTIONS["enveloppe"][0]),
        couvertures=ips.get("couvertures", IPS_OPTIONS["couvertures"][0]),
        esg=ips.get("esg", "Indifférent"),
    )


def excluded_reason(ticker: str, excl: set) -> str | None:
    t = ticker.upper()
    if "Crypto-actifs" in excl and (t.endswith("-USD") or t.endswith("-EUR")):
        return "Crypto-actifs"
    for k, s in EXCLUSION_TICKERS.items():
        if k in excl and t in s:
            return k
    return None


def pea_eligible(ticker: str) -> bool:
    t = ticker.upper()
    if t in ("CASH", "BIL", "XEON.DE"):
        return True
    try:
        from utils.etf_universe import etf_meta
        m = etf_meta(t)
        if m:
            return str(m.get("pea", "")).strip().lower() == "oui"
    except Exception:
        pass
    return t.endswith(_PEA_SUFFIX)


# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES DE MARCHÉ COMMUNES
# ══════════════════════════════════════════════════════════════════════════════
def market_context() -> dict:
    """Contexte macro du desk (régime OFFICIEL du comité = 8 facteurs du Hedge Fund Agent)."""
    px, missing = A.load_prices()
    news, news_sim = A.load_news()
    macro = A.compute_macro(px, news)
    cov = A.class_covariance(px)
    critical = {"SPY", "^VIX", "^TNX", "^IRX"}
    data_sim = len(missing) >= len(A.ALL_TICKERS) * 0.6 or bool(critical & set(missing))
    return dict(px=px, missing=missing, news=news, news_sim=news_sim, macro=macro, cov=cov,
                data_sim=data_sim, vix=(macro.indicators or {}).get("vix"))


def line_returns(tickers: list[str], years: float = 2.2) -> pd.DataFrame:
    """Rendements journaliers des lignes (vide si indisponible)."""
    tickers = sorted({t for t in tickers if t and t.upper() != "CASH"})
    if not tickers:
        return pd.DataFrame()
    from utils.performance import price_history
    start = (datetime.now() - timedelta(days=int(365 * years))).strftime("%Y-%m-%d")
    px = price_history(tuple(tickers), start)
    if px is None or px.empty:
        return pd.DataFrame()
    return px.pct_change(fill_method=None).iloc[1:]


# ══════════════════════════════════════════════════════════════════════════════
#  MC KENSON (QUANT) — signaux et preuve statistique
# ══════════════════════════════════════════════════════════════════════════════
def _score_at(p: np.ndarray) -> float:
    """Signal composite à partir d'un historique de prix (aucune donnée future)."""
    if len(p) < 253 or p[-252] <= 0 or p[-21] <= 0:
        return float("nan")
    r = np.diff(np.log(p[-253:]))
    vol = float(np.std(r) * math.sqrt(252)) or 0.2
    mom = p[-21] / p[-252] - 1                       # momentum 12-1 mois
    trend = p[-1] / np.mean(p[-200:]) - 1            # écart à la moyenne 200 jours
    rev = -(p[-1] / p[-21] - 1)                      # retour à la moyenne à 1 mois
    s = 0.50 * math.tanh(mom / (0.8 * vol)) + 0.35 * math.tanh(trend / 0.08) + 0.15 * math.tanh(rev / 0.06)
    return float(2 * s)                              # échelle ≈ [−2 ; +2]


def quant_signals(R: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Signal par ligne + validation hors échantillon (taux de réussite et IC de rang)."""
    if R is None or R.empty:
        return pd.DataFrame(), dict(ok=False, detail="historique indisponible")
    P = (1 + R.fillna(0)).cumprod()
    rows, pairs = [], []
    for t in P.columns:
        p = P[t].dropna().values
        if len(p) < 260:
            continue
        s = _score_at(p)
        vol = float(R[t].dropna().std() * math.sqrt(252))
        rows.append(dict(ticker=t, score=s, vol=vol,
                         mom_12_1=p[-21] / p[-252] - 1, tendance=p[-1] / np.mean(p[-200:]) - 1))
        for k in range(252, len(p) - 21, 21):        # walk-forward mensuel
            sk = _score_at(p[:k + 1])
            if np.isfinite(sk):
                pairs.append((sk, p[k + 21] / p[k] - 1))
    sig = pd.DataFrame(rows).set_index("ticker") if rows else pd.DataFrame()
    if not sig.empty:
        sig["avis"] = np.where(sig["score"] > 0.6, "Haussier", np.where(sig["score"] < -0.6, "Baissier", "Neutre"))
    ev = dict(ok=False, n=len(pairs))
    if len(pairs) >= 24:
        a = np.array(pairs)
        strong = np.abs(a[:, 0]) > 0.3
        hits = float(np.mean(np.sign(a[strong, 0]) == np.sign(a[strong, 1]))) if strong.sum() >= 10 else float("nan")
        ic = float(pd.Series(a[:, 0]).rank().corr(pd.Series(a[:, 1]).rank()))
        se = 1 / math.sqrt(len(a))
        ev = dict(ok=True, n=len(a), taux_reussite=hits, ic=ic, ic_t=ic / se if se else 0.0,
                  significatif=abs(ic / se) >= 1.96 if se else False)
    return sig, ev


# ══════════════════════════════════════════════════════════════════════════════
#  AVIS DES MEMBRES
# ══════════════════════════════════════════════════════════════════════════════
def _avis(mid: str, vote: str, titre: str, points: list[str], chiffres: dict | None = None,
          actions: list[str] | None = None) -> dict:
    m = MEMBER[mid]
    if vote == "veto" and not m["veto"]:
        vote = "reserve"
    return dict(id=mid, nom=m["nom"], role=m["role"], emoji=m["emoji"], couleur=m["couleur"], vote=vote,
                titre=titre, points=[p for p in points if p], chiffres=chiffres or {}, actions=actions or [])


def _fmt_pct(x, sign=False):
    if x is None or not np.isfinite(x):
        return "—"
    return f"{x:+.1%}" if sign else f"{x:.1%}"


def _economist(macro, cls_w: pd.Series | None, target: pd.Series | None = None) -> dict:
    f = macro.factors
    sc = A.class_scores(f)
    top = sorted(f.items(), key=lambda kv: -abs(kv[1]))[:3]
    pts = [f"Régime : **{macro.regime}** — {macro.regime_text}",
           "Facteurs dominants : " + ", ".join(f"{A.FACTORS[k][0].lower()} {v:+.1f}" for k, v in top) + "."]
    fav = sc.sort_values(ascending=False)
    pts.append(f"Classes favorisées : {', '.join(fav.index[:3])} · pénalisées : {', '.join(fav.index[-3:])}.")
    vote, actions = "ok", []
    if cls_w is not None and cls_w.sum() > 0:
        pen = sc[sc < -0.5].index
        ref = target.reindex(cls_w.index).fillna(0) if target is not None else pd.Series(0.0, index=cls_w.index)
        over = (cls_w - ref).clip(lower=0)
        bad = float(over.reindex(pen).fillna(0).sum()) if len(pen) else 0.0
        if bad > 0.15:
            vote = "reserve"
            worst = over.reindex(pen).fillna(0).sort_values(ascending=False)
            pts.append(f"Surpondération de {bad:.0%} dans des classes que le contexte pénalise "
                       f"({', '.join(worst.index[:2])}) : le portefeuille va à contre-courant du cycle.")
            actions.append("Réduire progressivement : " + ", ".join(worst.index[:2]) + ".")
        else:
            pts.append("Positionnement compatible avec le cycle : pas de surpondération notable des classes pénalisées.")
    titre = {"Aversion au risque": "Le temps est à l'orage : on réduit la voilure.",
             "Stagflation": "Croissance en panne, inflation tenace : défense d'abord.",
             "Surchauffe / reflation": "L'économie chauffe : place aux actifs réels et cycliques.",
             "Expansion désinflationniste": "Ciel dégagé : un environnement porteur pour le risque.",
             "Ralentissement désinflationniste": "L'activité ralentit : les obligations redeviennent utiles."
             }.get(macro.regime, "Lecture du cycle économique.")
    return _avis("eco", vote, titre, pts, dict(regime=macro.regime), actions)


def _quant(sig: pd.DataFrame, ev: dict, w: pd.Series | None) -> dict:
    if sig is None or sig.empty:
        return _avis("quant", "ok", "Pas assez d'historique : je ne conclus rien.",
                     ["Sans historique de cours suffisant, aucun signal ne peut être validé statistiquement.",
                      "« On ne contredit pas le modèle par intuition : on le contredit par des données. »"])
    pts, actions = [], []
    if ev.get("ok"):
        hr = ev.get("taux_reussite")
        pts.append(f"Validation hors échantillon (walk-forward mensuel, {ev['n']} observations) : taux de "
                   f"réussite {_fmt_pct(hr)} · IC de rang {ev['ic']:+.2f} (t = {ev['ic_t']:+.1f}).")
        pts.append("Le signal est **statistiquement significatif** : je lui accorde du poids." if ev["significatif"]
                   else "Le signal n'est **pas significatif** : je l'utilise comme simple départage, pas comme conviction.")
    neg = sig[sig["score"] < -0.6]
    pos = sig[sig["score"] > 0.6]
    if len(pos):
        pts.append("Signaux haussiers : " + ", ".join(f"{t} ({s:+.1f})" for t, s in pos["score"].sort_values(ascending=False).head(4).items()) + ".")
    if len(neg):
        pts.append("Signaux baissiers : " + ", ".join(f"{t} ({s:+.1f})" for t, s in neg["score"].sort_values().head(4).items()) + ".")
    vote = "ok"
    if w is not None and len(neg):
        wneg = float(w.reindex(neg.index).fillna(0).sum())
        if wneg > 0.30 and ev.get("significatif"):
            vote = "reserve"
            pts.append(f"{wneg:.0%} du portefeuille porte un signal baissier validé statistiquement.")
            actions.append("Alléger les lignes à signal baissier : " + ", ".join(neg.index[:4]) + ".")
    titre = ("Les données parlent, et elles sont plutôt d'accord." if vote == "ok"
             else "Les données contredisent une partie du portefeuille.")
    return _avis("quant", vote, titre, pts, dict(evidence=ev), actions)


def _cio(cls_w: pd.Series, target: pd.Series, lines_w: pd.Series, cons: dict, cash_w: float) -> dict:
    pts, actions = [], []
    gap = (cls_w.reindex(A.CLASSES).fillna(0) - target.reindex(A.CLASSES).fillna(0))
    drift = float(gap.abs().sum() / 2)
    pts.append(f"Écart à l'allocation cible du profil **{cons['profil']}** : {drift:.0%} du portefeuille à déplacer.")
    for c, g in gap.sort_values().items():
        if g < -0.05:
            actions.append(f"Renforcer {c} ({g:+.0%}).")
        elif g > 0.05:
            actions.append(f"Alléger {c} ({g:+.0%}).")
    n_eff = float(1 / (lines_w ** 2).sum()) if len(lines_w) else 0.0
    top = lines_w.sort_values(ascending=False)
    pts.append(f"Diversification : {len(lines_w)} ligne(s), nombre effectif {n_eff:.1f}"
               + (f", première ligne {top.index[0]} à {top.iloc[0]:.0%}." if len(top) else "."))
    try:
        from utils.etf_universe import etf_meta
        ter = sum(float((etf_meta(t) or {}).get("ter_pct", 0) or 0) / 100 * w for t, w in lines_w.items())
        if ter > 0:
            pts.append(f"Frais courants des ETF : {ter:.2%} par an sur le portefeuille.")
    except Exception:
        pass
    if cash_w > cons["cash_min"] + 0.25:
        pts.append(f"Liquidités : {cash_w:.0%} — beaucoup d'argent qui ne travaille pas.")
        actions.append("Investir progressivement une partie des liquidités.")
    vote = "ok"
    if drift > 0.25 or (len(lines_w) and n_eff < 4 and not all(_broad(t) for t in lines_w.index)):
        vote = "reserve"
    titre = ("Un portefeuille aligné sur sa politique : on garde le cap." if vote == "ok"
             else "La construction doit être resserrée autour de la cible.")
    return _avis("cio", vote, titre, pts, dict(derive=drift, n_effectif=n_eff), actions)


def _broad(t: str) -> bool:
    try:
        from utils.etf_universe import is_broad_etf
        return is_broad_etf(t)
    except Exception:
        return False


def _cro(risk: dict, cons: dict, options: list, hedges_n: int = 0) -> dict:
    pm = cons["perte_max"]
    pts, actions, vote = [], [], "ok"
    if not risk or "var95_1an" not in risk:
        return _avis("cro", "reserve", "Je ne peux pas mesurer le risque : prudence.",
                     ["Historique insuffisant pour calculer VaR et Expected Shortfall."])
    v1 = risk["var95_1an"]
    pts.append(f"Perte potentielle sur 1 an (VaR 95 %) : **{_fmt_pct(v1)}** pour une perte maximale acceptable "
               f"de {pm:.0%} — volatilité retenue {_fmt_pct(risk['vol_retenue_ann'])} (max de l'historique "
               f"{_fmt_pct(risk['vol_hist_ann'])} et de l'EWMA λ = 0,94 {_fmt_pct(risk['vol_ewma_ann'])}).")
    pts.append(f"VaR 99 % : {_fmt_pct(risk['var99_1j'])} sur 1 jour, {_fmt_pct(risk['var99_10j'])} sur 10 jours · "
               f"Expected Shortfall 97,5 % : {_fmt_pct(risk['es975_1j'])} sur 1 jour, "
               f"{_fmt_pct(risk['es975_10j'])} sur 10 jours.")
    k = risk.get("kupiec", {})
    if k.get("ok"):
        pts.append(f"Backtesting de la VaR (Kupiec) : {k['exceptions']} dépassement(s) sur {k['n']} jours "
                   f"pour {k['attendues']:.1f} attendus — {k['verdict']} (p = {k['p_value']:.2f}).")
    name, worst = risk.get("pire_scenario", ("—", 0.0))
    pts.append(f"Pire stress test : « {name} » {worst:+.1%}.")
    if risk.get("stress_inverse"):
        pts.append("Stress test inversé : " + risk["stress_inverse"]["texte"])
    lines = risk.get("lignes")
    if isinstance(lines, pd.DataFrame) and "Part du risque" in lines and lines["Part du risque"].notna().any():
        t = lines["Part du risque"].idxmax()
        pts.append(f"Contribution au risque (Euler) : {t} pèse {lines.loc[t, 'Poids']:.0%} du capital mais "
                   f"{lines.loc[t, 'Part du risque']:.0%} du risque.")
    if v1 > 1.25 * pm:
        vote = "veto"
        actions.append(f"Réduire l'exposition au risque : la perte potentielle ({v1:.0%}) dépasse nettement "
                       f"votre limite ({pm:.0%}).")
    elif v1 > pm:
        vote = "reserve"
        actions.append(f"Réduire légèrement le risque ou ajouter des couvertures (perte potentielle {v1:.0%} > {pm:.0%}).")
    if worst < -1.5 * pm and vote == "ok":
        vote = "reserve"
        actions.append(f"Le scénario « {name} » ferait perdre {abs(worst):.0%} : envisager une couverture.")
    if options:
        pts.append(f"{len(options)} position(s) d'options en portefeuille (grecques suivies dans le rapport).")
    if hedges_n:
        pts.append(f"{hedges_n} couverture(s) par options proposée(s) pour amortir une baisse.")
    titre = {"ok": "Risque mesuré, préparé, sous contrôle.",
             "reserve": "Le risque frôle votre limite : je demande des ajustements.",
             "veto": "Veto : ce niveau de risque n'est pas compatible avec votre politique."}[vote]
    return _avis("cro", vote, titre, pts, {k_: risk.get(k_) for k_ in ("var95_1an", "es975_10j", "var99_10j")}, actions)


def _compliance(values: dict, cash: float, cons: dict, options: list, options_ok: bool,
                data_sim: bool, port_type: str = "Libre") -> dict:
    from utils.compliance import HARD_LIMITS, THEMATIC_CRYPTO
    pts, actions, vote = [], [], "ok"
    nav = cash + sum(v for v in values.values() if v > 0)
    lim = HARD_LIMITS[cons["profil"]]
    held_excl = {t: excluded_reason(t, cons["exclusions"]) for t in values if values[t] > 0}
    held_excl = {t: r for t, r in held_excl.items() if r}
    if held_excl:
        vote = "veto"
        pts.append("Exclusions non respectées : " + ", ".join(f"{t} ({r})" for t, r in held_excl.items()) + ".")
        actions.append("Céder les lignes exclues par votre politique d'investissement.")
    if nav > 0:
        crypto = sum(v for t, v in values.items() if t.upper().endswith(("-USD", "-EUR"))) / nav
        cap = cons["crypto_max"] if port_type not in THEMATIC_CRYPTO else (
            1.0 if cons["profil"] in THEMATIC_CRYPTO[port_type] else 0.0)
        if crypto > cap + 1e-9:
            vote = "veto"
            pts.append(f"Crypto-actifs : {crypto:.0%} pour un plafond de {cap:.0%} (MiCA / profil {cons['profil']}).")
            actions.append(f"Ramener les crypto-actifs sous {cap:.0%}.")
        over = [(t, v / nav) for t, v in values.items() if v / nav > (0.70 if _broad(t) else lim["line"]) + 1e-9
                and t.upper() not in ("BIL", "SGOV", "XEON.DE")]
        if over:
            vote = "veto" if vote == "veto" else "reserve"
            pts.append("Concentration au-delà du plafond par ligne : "
                       + ", ".join(f"{t} {w:.0%}" for t, w in over) + f" (plafond {lim['line']:.0%}, UCITS 5/10/40).")
            actions.append("Répartir les lignes trop concentrées.")
    if "PEA" in cons["enveloppe"]:
        bad = [t for t in values if values[t] > 0 and not pea_eligible(t)]
        if bad:
            vote = "veto" if vote == "veto" else "reserve"
            pts.append("Lignes non éligibles au PEA : " + ", ".join(bad[:6]) + ".")
    if options and not options_ok:
        vote = "veto" if vote == "veto" else "reserve"
        pts.append("Positions d'options alors que le test de connaissances n'est pas validé (MiFID II art. 25(3)).")
    if options and cons["couvertures"] == "Jamais d'options":
        vote = "veto"
        pts.append("La politique d'investissement exclut les options, mais le portefeuille en contient.")
    if data_sim:
        pts.append("Données de marché simulées : toute exécution est suspendue (meilleure exécution, MiFID II art. 27).")
    if not pts:
        pts.append("Exclusions, plafonds crypto et de concentration, enveloppe et produits complexes : conformes.")
    titre = {"ok": "Conforme à la politique d'investissement.",
             "reserve": "Conforme sous réserve de corrections mineures.",
             "veto": "Veto : la politique d'investissement n'est pas respectée."}[vote]
    return _avis("cmp", vote, titre, pts, {}, actions)


def behavioral_biases(values: dict, cash: float, ips: dict | None = None) -> list[str]:
    """Biais comportementaux visibles dans la composition du portefeuille (finance comportementale :
    Kahneman & Tversky, Thaler, Shiller)."""
    nav = cash + sum(v for v in values.values() if v > 0)
    if nav <= 0:
        return []
    out = []
    w = {t: v / nav for t, v in values.items() if v > 0}
    top = max(w.items(), key=lambda kv: kv[1]) if w else None
    if top and top[1] > 0.25 and not _broad(top[0]):
        out.append(f"Biais de concentration / excès de confiance : {top[0]} pèse {top[1]:.0%} du portefeuille.")
    try:
        cls_w, _ = A.portfolio_to_classes({**values, "CASH": cash})
        eq = float(cls_w[A.EQUITY_CLASSES].sum())
        if eq > 0.3 and float(cls_w["Actions US"]) / eq > 0.85:
            out.append("Biais domestique / de familiarité : plus de 85 % des actions sont américaines.")
    except Exception:
        pass
    crypto = sum(v for t, v in w.items() if t.upper().endswith(("-USD", "-EUR")))
    if crypto > 0.10:
        out.append(f"Effet de mode (FOMO) : {crypto:.0%} en crypto-actifs, actif très médiatisé et très volatil.")
    if cash / nav > 0.35 and (ips or {}).get("horizon") not in (None, "Moins de 2 ans"):
        out.append(f"Aversion aux pertes / inertie : {cash / nav:.0%} de liquidités alors que l'horizon est long.")
    tech = {"AAPL", "MSFT", "NVDA", "GOOGL", "GOOG", "META", "AMZN", "TSLA", "NFLX", "AMD", "QQQ", "XLK", "SOXX"}
    t_w = sum(v for t, v in w.items() if t.upper() in tech)
    if t_w > 0.40:
        out.append(f"Biais de récence : {t_w:.0%} sur les valeurs technologiques qui ont le plus monté ces dernières années.")
    return out


def _cpm(avis: list[dict], cons: dict, label: str, perf: dict | None, hedges: list | None,
         biases: list[str] | None = None) -> tuple[dict, str, list, list]:
    verdict = "veto" if any(a["vote"] == "veto" for a in avis) else (
        "reserve" if any(a["vote"] == "reserve" for a in avis) else "ok")
    order = {"cmp": 0, "cro": 1, "cio": 2, "quant": 3, "eco": 4}
    recos = []
    for a in sorted(avis, key=lambda x: (x["vote"] != "veto", x["vote"] != "reserve", order.get(x["id"], 9))):
        for act in a["actions"]:
            recos.append(dict(qui=a["nom"], emoji=a["emoji"], action=act,
                              priorite="haute" if a["vote"] == "veto" else ("moyenne" if a["vote"] == "reserve" else "basse")))
    recos = recos[:6]
    decisions = []
    for h in hedges or []:
        if h.get("contrats", 0) > 0:
            decisions.append(f"Accepter ou refuser la couverture « {h['panier']} » ({h['strategie']} sur "
                             f"{h['sous_jacent']}, coût ≈ {h['cout']:,.0f} $).".replace(",", " "))
    if verdict != "ok" and recos:
        decisions.append("Valider le plan d'ajustement proposé par le comité (bouton Optimiser).")
    pts = []
    if perf and perf.get("Performance") is not None and np.isfinite(perf.get("Performance", np.nan)):
        txt = f"Performance depuis l'origine : {perf['Performance']:+.2%}"
        if np.isfinite(perf.get("Perf. indice", np.nan)):
            txt += f" contre {perf['Perf. indice']:+.2%} pour l'indice ({perf['Surperformance']:+.2%})."
        pts.append(txt)
    n_ok = sum(a["vote"] == "ok" for a in avis)
    pts.append(f"{n_ok} membre(s) sur {len(avis)} sont favorables sans réserve.")
    if verdict == "veto":
        vetos = [a for a in avis if a["vote"] == "veto"]
        pts.append("Le comité ne peut pas valider en l'état — " + " · ".join(f"{a['nom']} : {a['titre'].replace('Veto : ', '').rstrip('.')}" for a in vetos) + ".")
    elif verdict == "reserve":
        pts.append("Le comité valide, à condition de suivre les recommandations ci-dessous.")
    else:
        pts.append("Le comité valide sans réserve : le portefeuille est cohérent avec votre politique d'investissement.")
    if biases:
        pts.insert(1 if pts and pts[0].startswith("Performance") else 0,
                   "Biais comportementaux repérés : " + " ".join(biases))
        recos.append(dict(qui=MEMBER["cpm"]["nom"], emoji=MEMBER["cpm"]["emoji"],
                          action="Prendre conscience des biais repérés avant toute décision : "
                                 + " ; ".join(b.split(" : ")[0] for b in biases) + ".",
                          priorite="basse"))
    pts.append(f"Rappel de votre politique : profil {cons['profil']}, perte maximale acceptable {cons['perte_max']:.0%}, "
               f"enveloppe {cons['enveloppe']}.")
    titre = {"ok": f"« {label} » : feu vert du comité.", "reserve": f"« {label} » : oui, mais avec quelques ajustements.",
             "veto": f"« {label} » : le comité dit non pour l'instant."}[verdict]
    cpm = _avis("cpm", "ok" if verdict == "ok" else "reserve", titre, pts, {}, [])
    return cpm, verdict, recos, decisions


# ══════════════════════════════════════════════════════════════════════════════
#  REVUE D'UN PORTEFEUILLE
# ══════════════════════════════════════════════════════════════════════════════
def review_portfolio(values: dict[str, float], cash: float, ips: dict, ctx: dict, *, options: list | None = None,
                     options_ok: bool = False, port_type: str = "Libre", label: str = "Portefeuille",
                     R: pd.DataFrame | None = None, perf: dict | None = None, hedges: list | None = None) -> dict:
    """Avis des 6 membres sur un portefeuille (valeurs $ par ligne + liquidités)."""
    values = {t: float(v) for t, v in values.items() if v and float(v) > 0}
    cons = constraints(ips)
    nav = cash + sum(values.values())
    if R is None:
        R = line_returns(list(values))
    risk = None
    try:
        from utils.risk_hull import portfolio_risk
        risk = portfolio_risk(values, cash, R, ctx["cov"], cons["perte_max"])
    except Exception:
        risk = None
    cls_w, lines_w = A.portfolio_to_classes({**values, "CASH": cash})
    lines_w = pd.Series({t: v / nav for t, v in values.items()}, dtype=float) if nav else pd.Series(dtype=float)
    target, _, _ = A.risk_engine(A.propose_allocation(ctx["macro"].factors, cons["profil"], 0.5)["Proposée (avant risque)"],
                                 cons["profil"], ctx["macro"].factors, ctx["cov"], False, overrides=_overrides(cons))
    sig, ev = quant_signals(R)
    avis = [
        _economist(ctx["macro"], cls_w, target),
        _quant(sig, ev, lines_w),
        _cio(cls_w, target, lines_w, cons, cash / nav if nav else 1.0),
        _cro(risk, cons, options or [], len([h for h in (hedges or []) if h.get("contrats", 0) > 0])),
        _compliance(values, cash, cons, options or [], options_ok, ctx.get("data_sim", False), port_type),
    ]
    cpm, verdict, recos, decisions = _cpm(avis, cons, label, perf, hedges, behavioral_biases(values, cash, ips))
    avis.append(cpm)
    return dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), version=COMMITTEE_VERSION, label=label,
                verdict=verdict, verdict_label=VERDICT_LABEL[verdict], avis=avis, recommandations=recos,
                decisions=decisions, contraintes=cons, risque=risk, signaux=sig, preuve=ev,
                classes=cls_w, cible=target, regime=ctx["macro"].regime, nav=nav)


def _overrides(cons: dict) -> dict:
    return dict(crypto=cons["crypto_max"], equity=cons["equity_max"], cash=cons["cash_min"], vol=cons["vol_cible"])


# ══════════════════════════════════════════════════════════════════════════════
#  REVUE À LA CRÉATION (portefeuille encore vide)
# ══════════════════════════════════════════════════════════════════════════════
STRATEGY_VOL = {"growth": .20, "value": .16, "momentum": .22, "income": .09, "macro": .10, "hedging": .07,
                "balanced": .10, "commodity": .22, "crypto": .65, "arbitrage": .05, "etf": .11}
STRATEGY_TYPE = {"growth": "Growth", "value": "Value", "momentum": "Momentum", "income": "Income",
                 "macro": "Global Macro", "hedging": "Hedging", "balanced": "Balanced 60/40",
                 "commodity": "Commodity", "crypto": "Crypto Alpha", "arbitrage": "Arbitrage", "etf": "ETF Core"}


def review_creation(ips: dict, strategy_id: str, asset_types: list[str], ctx: dict, options_ok: bool,
                    label: str = "Nouveau portefeuille") -> dict:
    """Le comité examine la cohérence entre la politique d'investissement et la stratégie choisie."""
    cons = constraints(ips)
    pm, prof = cons["perte_max"], cons["profil"]
    vol = STRATEGY_VOL.get(strategy_id, .15)
    v1 = 1.645 * vol
    sname = STRATEGY_TYPE.get(strategy_id, strategy_id)
    obj = _idx(ips, "objectif", 2)
    hor = _idx(ips, "horizon", 2)
    avis = []

    eco = _economist(ctx["macro"], None)
    risky_strat = strategy_id in ("growth", "momentum", "crypto", "commodity")
    if ctx["macro"].regime in ("Aversion au risque", "Stagflation") and risky_strat:
        eco["vote"] = "reserve"
        eco["points"].append(f"Démarrer une stratégie {sname} dans ce régime est risqué : entrer progressivement "
                             "(par tiers sur trois mois).")
        eco["actions"].append("Investir progressivement plutôt qu'en une seule fois.")
    avis.append(eco)

    avis.append(_avis("quant", "ok", "Portefeuille vide : rien à mesurer, tout à prouver.",
                      ["Aucune ligne encore : mes signaux seront calculés à chaque revue et visibles avant chaque ordre.",
                       "« Ce qui n'a pas été testé hors échantillon n'a pas été testé. »"]))

    cio_pts, cio_act, cio_vote = [], [], "ok"
    cio_pts.append(f"Stratégie {sname} pour un objectif « {ips.get('objectif')} » sur un horizon "
                   f"« {ips.get('horizon')} ».")
    if obj <= 1 and strategy_id in ("growth", "momentum", "crypto", "commodity"):
        cio_vote = "reserve"
        cio_pts.append("Une stratégie offensive sert mal un objectif de préservation ou de revenu.")
        cio_act.append("Préférer Income, Balanced 60/40, Hedging ou ETF Core.")
    if obj >= 3 and strategy_id in ("hedging", "arbitrage", "income"):
        cio_vote = "reserve"
        cio_pts.append("Une stratégie très défensive aura du mal à atteindre un objectif de croissance forte.")
    if strategy_id == "etf":
        cio_pts.append("« Achetez la botte de foin » : une gestion indicielle à bas coût, cohérente pour la plupart des profils.")
    avis.append(_avis("cio", cio_vote, "La stratégie doit servir l'objectif, pas l'inverse." if cio_vote != "ok"
                      else "Stratégie cohérente avec l'objectif.", cio_pts, {}, cio_act))

    cro_pts = [f"Volatilité typique d'une stratégie {sname} : ≈ {vol:.0%} → perte potentielle sur 1 an "
               f"(VaR 95 %) ≈ {v1:.0%}, pour une perte maximale acceptable de {pm:.0%}."]
    cro_vote, cro_act = "ok", []
    if v1 > 1.5 * pm:
        cro_vote = "veto"
        cro_act.append("Choisir une stratégie moins volatile ou revoir la perte maximale acceptable.")
    elif v1 > pm:
        cro_vote = "reserve"
        cro_act.append("Garder une poche de liquidités ou des couvertures pour rester sous votre limite.")
    if hor == 0 and vol > 0.12:
        cro_vote = "veto"
        cro_pts.append("Horizon de moins de 2 ans : une stratégie volatile n'a pas le temps de se remettre d'une baisse.")
    if obj >= 3 and pm <= 0.10:
        cro_vote = "veto"
        cro_pts.append("Objectif de croissance forte incompatible avec une perte maximale de 10 % ou moins.")
    avis.append(_avis("cro", cro_vote, {"ok": "Risque attendu compatible avec votre limite.",
                                        "reserve": "Risque attendu un peu au-dessus de votre limite.",
                                        "veto": "Veto : la stratégie dépasse votre tolérance à la perte."}[cro_vote],
                      cro_pts, {"var95_1an": v1}, cro_act))

    from utils.compliance import THEMATIC_CRYPTO
    c_pts, c_vote, c_act = [], "ok", []
    excl = cons["exclusions"]
    if strategy_id == "crypto" and prof not in THEMATIC_CRYPTO["Crypto Alpha"]:
        c_vote = "veto"
        c_pts.append(f"Stratégie Crypto Alpha réservée aux profils Dynamique et Agressif (votre profil : {prof}).")
    if ("crypto" in asset_types or strategy_id == "crypto") and "Crypto-actifs" in excl:
        c_vote = "veto"
        c_pts.append("Vous excluez les crypto-actifs, mais la stratégie ou les classes choisies en contiennent.")
    if strategy_id == "commodity" and "Énergies fossiles" in excl:
        c_vote = "veto" if c_vote == "veto" else "reserve"
        c_pts.append("Stratégie matières premières alors que les énergies fossiles sont exclues : univers très réduit.")
    if "PEA" in cons["enveloppe"] and (set(asset_types) & {"crypto", "commodity", "forex", "bond"} or
                                       strategy_id in ("crypto", "commodity")):
        c_vote = "veto" if c_vote == "veto" else "reserve"
        c_pts.append("PEA : crypto, matières premières, devises et obligations ne sont pas éligibles.")
    if strategy_id == "hedging" and not options_ok:
        c_vote = "veto" if c_vote == "veto" else "reserve"
        c_pts.append("Stratégie Hedging (options) : le test de connaissances sur les options n'est pas validé.")
    if prof != _requested_profile(ips) and cons["plafonne_par"]:
        c_pts.append("Profil plafonné par : " + " ; ".join(cons["plafonne_par"]) + ".")
    if not c_pts:
        c_pts.append("Politique d'investissement, stratégie, exclusions et enveloppe : cohérentes.")
    avis.append(_avis("cmp", c_vote, {"ok": "Dossier conforme.", "reserve": "Conforme sous réserves.",
                                      "veto": "Veto : incompatibilité réglementaire ou avec vos exclusions."}[c_vote],
                      c_pts, {}, c_act))

    cpm, verdict, recos, decisions = _cpm(avis, cons, label, None, None)
    avis.append(cpm)
    return dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), version=COMMITTEE_VERSION, label=label,
                verdict=verdict, verdict_label=VERDICT_LABEL[verdict], avis=avis, recommandations=recos,
                decisions=decisions, contraintes=cons, regime=ctx["macro"].regime, mode="création")


def _requested_profile(ips: dict) -> str:
    s = ips_profile(ips)[1]
    return PROFILES[0 if s <= 6 else 1 if s <= 11 else 2 if s <= 16 else 3]


def summary_for_storage(rev: dict) -> dict:
    """Version compacte et sérialisable d'une revue (stockée avec le portefeuille)."""
    return dict(date=rev["date"], version=rev["version"], verdict=rev["verdict"], regime=rev.get("regime"),
                votes={a["id"]: a["vote"] for a in rev["avis"]},
                titres={a["id"]: a["titre"] for a in rev["avis"]},
                recommandations=[r["action"] for r in rev.get("recommandations", [])][:6],
                profil=rev["contraintes"]["profil"], mode=rev.get("mode", "revue"))


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMISATION PAR LE COMITÉ (bouton « Optimiser »)
# ══════════════════════════════════════════════════════════════════════════════
UCITS_PROXY = {"Actions US": "CSPX.L", "Actions Asie & émergents": "EIMI.L", "Oblig. moyen terme": "IBTS.L",
               "Crédit IG": "IEAC.L", "Or": "SGLD.L"}
PEA_PROXY = {"Actions US": "EWLD.PA", "Actions Europe": "C40.PA", "Actions Asie & émergents": "PAEEM.PA"}


def _proxy(cls: str, cons: dict) -> str | None:
    env = cons["enveloppe"]
    if cls == "Liquidités":
        return None
    if "PEA" in env:
        return PEA_PROXY.get(cls)                       # le reste n'est pas éligible : reste en liquidités
    t = (UCITS_PROXY.get(cls) if "UCITS" in env else None) or A.CLASS_PROXY.get(cls)
    if t and excluded_reason(t, cons["exclusions"]):
        return None
    return t


def committee_optimize(values: dict[str, float], cash: float, ips: dict, ctx: dict, live: dict,
                       intensity: float = 0.5, band: float = 0.02) -> dict:
    """Plan d'ajustement du comité : cible par classe (Taux-Bas + Balancement), choix des lignes
    (Mc Henson ALGO-RITHME), contrôle du risque (De Marge), contraintes (Probité), bandes de tolérance."""
    from utils.compliance import HARD_LIMITS
    cons = constraints(ips)
    prof = cons["profil"]
    f = ctx["macro"].factors
    notes = []
    values = {t: float(v) for t, v in values.items() if v and float(v) > 0}
    nav = cash + sum(values.values())

    # 1. Taux-Bas + Balancement : allocation par classe sous les contraintes de l'IPS
    prop = A.propose_allocation(f, prof, intensity)["Proposée (avant risque)"]
    if cons["crypto_max"] <= 0:
        prop["Crypto"] = 0.0
        prop = prop / prop.sum()
    target_cls, checks, allowed = A.risk_engine(prop, prof, f, ctx["cov"], ctx.get("data_sim", False),
                                                overrides=_overrides(cons))
    notes.append(("eco", f"Régime « {ctx['macro'].regime} » : inclinaisons tactiques d'intensité {intensity:.0%} "
                         f"autour de l'allocation stratégique {prof}."))
    notes.append(("cio", "Allocation par classe après limites de la politique d'investissement (actions ≤ "
                         f"{cons['equity_max']:.0%}, crypto ≤ {cons['crypto_max']:.0%}, liquidités ≥ "
                         f"{cons['cash_min']:.0%}, volatilité ≤ {cons['vol_cible']:.0%})."))

    # 2. Mc Henson ALGO-RITHME : choix des lignes dans chaque classe
    R = line_returns(list(values) + [t for c in A.CLASSES if (t := _proxy(c, cons))])
    sig, ev = quant_signals(R)
    strength = 0.35 if ev.get("significatif") else 0.15
    lim_line = HARD_LIMITS[prof]["line"]
    by_cls: dict[str, dict] = {}
    for t, v in values.items():
        if excluded_reason(t, cons["exclusions"]) or ("PEA" in cons["enveloppe"] and not pea_eligible(t)):
            continue
        by_cls.setdefault(A.classify_ticker(t) or "Actions US", {})[t] = v
    tw: dict[str, float] = {}
    for cls, w_c in target_cls.items():
        if w_c <= 1e-4 or cls == "Liquidités":
            continue
        held = by_cls.get(cls, {})
        if held:
            sc = {t: (float(sig.loc[t, "score"]) if t in sig.index and np.isfinite(sig.loc[t, "score"]) else 0.0)
                  for t in held}
            raw = {t: held[t] * math.exp(strength * sc[t]) for t in held}
            tot = sum(raw.values())
            for t, r_ in raw.items():
                tw[t] = tw.get(t, 0.0) + w_c * r_ / tot
        else:
            px_ = _proxy(cls, cons)
            if px_:
                tw[px_] = tw.get(px_, 0.0) + w_c
    notes.append(("quant", f"Lignes conservées et pondérées par le signal (force {strength:.2f}, "
                           f"{'signal significatif' if ev.get('significatif') else 'signal non significatif : poids faible'}) ; "
                           "classes sans ligne : ETF indiciel de la classe."))

    # Plafond par ligne : l'excédent part vers l'ETF de la classe (ou les liquidités)
    for t in list(tw):
        cap = 0.70 if _broad(t) else lim_line
        if tw[t] > cap:
            ex = tw[t] - cap
            tw[t] = cap
            px_ = _proxy(A.classify_ticker(t) or "Actions US", cons)
            if px_ and px_ != t:
                tw[px_] = tw.get(px_, 0.0) + ex
    # 3. De Marge : la perte potentielle doit rester sous la perte maximale acceptable
    from utils.risk_hull import portfolio_risk
    R2 = line_returns(list(tw))

    def _risk(weights):
        vals = {t: w * nav for t, w in weights.items() if w > 0}
        return portfolio_risk(vals, nav - sum(vals.values()), R2, ctx["cov"], cons["perte_max"])

    rk = _risk(tw)
    if rk and rk.get("var95_1an", 0) > cons["perte_max"] and rk["var95_1an"] > 0:
        k = max(0.3, cons["perte_max"] / rk["var95_1an"] * 0.97)
        risky = {t for t in tw if A.classify_ticker(t) not in ("Liquidités", "Oblig. moyen terme")}
        for t in risky:
            tw[t] *= k
        notes.append(("cro", f"Perte potentielle {rk['var95_1an']:.0%} > limite {cons['perte_max']:.0%} : "
                             f"exposition risquée ramenée à {k:.0%} de la cible (excédent en liquidités)."))
        rk = _risk(tw)
    else:
        notes.append(("cro", "Perte potentielle de l'allocation cible sous votre limite : aucune réduction nécessaire."))

    # 4. Ordres avec bandes de tolérance (on ne traite que les vraies dérives)
    cur_w = {t: v / nav for t, v in values.items()} if nav else {}
    orders = []
    kept = 0
    for t in sorted(set(tw) | set(values)):
        target_v = tw.get(t, 0.0) * nav
        diff = target_v - values.get(t, 0.0)
        p = float((live.get(t) or (0, 0))[0]) if t in live else 0.0
        if p <= 0:
            continue
        excluded = bool(excluded_reason(t, cons["exclusions"])) or ("PEA" in cons["enveloppe"] and not pea_eligible(t))
        rel = abs(diff) / values[t] if values.get(t) else 1.0
        if not excluded and abs(diff) / nav < band and rel < 0.20:
            kept += 1
            continue
        if abs(diff) < 100:
            continue
        q = abs(diff) / p
        if diff < 0:
            q = min(q, values.get(t, 0.0) / p)
        orders.append(dict(ticker=t, action="BUY" if diff > 0 else "SELL", qty=round(q, 6 if t.endswith("-USD") else 4),
                           price=p, montant=q * p,
                           motif=("exclusion / éligibilité" if excluded else
                                  "renforcement" if diff > 0 and values.get(t) else
                                  "nouvelle ligne" if diff > 0 else
                                  "sortie" if tw.get(t, 0) == 0 else "allègement")))
    od = pd.DataFrame(orders)
    if not od.empty:
        od = od[od["qty"] > 0]
        sells, buys = od[od.action == "SELL"], od[od.action == "BUY"]
        avail = cash + sells["montant"].sum()
        if buys["montant"].sum() > avail > 0:
            k = avail / buys["montant"].sum() * 0.995
            buys = buys.assign(qty=(buys["qty"] * k).round(4))
            buys = buys.assign(montant=buys["qty"] * buys["price"])
        od = pd.concat([sells, buys], ignore_index=True)
    notes.append(("cio", f"Bandes de tolérance : {kept} ligne(s) laissée(s) telle(s) quelle(s) (écart < {band:.0%} "
                         "du portefeuille) pour éviter des frais inutiles."))

    projected = dict(values)
    for _, o in od.iterrows() if not od.empty else []:
        projected[o["ticker"]] = projected.get(o["ticker"], 0.0) + (o["montant"] if o["action"] == "BUY" else -o["montant"])
    projected = {t: v for t, v in projected.items() if v > 1}
    cash_after = nav - sum(projected.values())
    return dict(cible_classes=target_cls, checks=checks, allowed=allowed and not ctx.get("data_sim", False),
                cible_lignes=pd.Series(tw, dtype=float).sort_values(ascending=False),
                actuel_lignes=pd.Series(cur_w, dtype=float), ordres=od, projete=projected,
                cash_apres=cash_after, notes=notes, signaux=sig, preuve=ev, contraintes=cons, nav=nav)
