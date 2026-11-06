# utils/am_process.py  —  MAM v5.13 · Processus de gestion d'actifs du comité
"""
Inspiré des standards de la gestion d'actifs : processus d'investissement en boucle (politique
d'investissement → allocation et limites → budget de risque → mise en œuvre → suivi et revue), gouvernance
des données et des méthodes (une source, des règles documentées, une trace des décisions), présentation des
performances avec méthode et limites explicites (esprit GIPS).

  1. STRESS DES SCÉNARIOS SUR LE PORTEFEUILLE — chaque ligne est ventilée par secteur / actif, l'impact de
     chaque scénario est appliqué : perte ou gain attendu en % et en $, comparé à la perte maximale de l'IPS ;
  2. PLAN D'ACTION PAR PHASES — « cette semaine », « ce mois-ci (par paliers) », « chaque trimestre » :
     action, montant, lignes concernées, raison, membre du comité ; jamais exécuté automatiquement ;
  3. LIGNES FIGÉES — exclues des achats / ventes proposés, mais leur exposition est prise en compte pour
     ajuster le reste du portefeuille ;
  4. AUTOCRITIQUE — Marc ETING-FINANCIER note l'analyse sur 10 et liste ses faiblesses et améliorations ;
  5. PROCESSUS — état de chaque étape du processus d'investissement (✅ / ⚠️) pour le rapport.
Fonctions pures, sans réseau.
"""
from __future__ import annotations

import numpy as np

from utils import core_params as CP

# ══════════════════════════════════════════════════════════════════════════════
#  1. VENTILATION DES LIGNES PAR SECTEUR / ACTIF (clés = CP.SECTORS)
# ══════════════════════════════════════════════════════════════════════════════
_SP500 = {"Technologie": 0.24, "Semi-conducteurs": 0.10, "Communication & médias": 0.10,
          "Consommation discrétionnaire": 0.10, "Finance": 0.13, "Santé": 0.10, "Industrie": 0.08,
          "Consommation de base": 0.055, "Énergie": 0.03, "Matériaux": 0.02, "Services publics": 0.025,
          "Immobilier": 0.02}
_NDX = {"Technologie": 0.36, "Semi-conducteurs": 0.17, "Communication & médias": 0.16,
        "Consommation discrétionnaire": 0.14, "Santé": 0.05, "Consommation de base": 0.06, "Industrie": 0.04,
        "Services publics": 0.01, "Finance": 0.01}


def _mix(*parts) -> dict:
    out: dict[str, float] = {}
    for w, d in parts:
        for k, v in (d.items() if isinstance(d, dict) else [(d, 1.0)]):
            out[k] = out.get(k, 0.0) + w * v
    return out


_WORLD = _mix((0.72, _SP500), (0.28, "Actions Europe"))
_WORLD_ALL = _mix((0.63, _SP500), (0.25, "Actions Europe"), (0.12, "Actions émergentes"))
_SEMIS = {"NVDA", "AMD", "AVGO", "TSM", "ASML", "ASML.AS", "MU", "INTC", "QCOM", "AMAT", "LRCX", "KLAC", "ARM",
          "SMCI", "MRVL", "TXN", "STMPA.PA", "000660.KS", "005930.KS", "SOXX", "SMH"}
_SPECIAL = {
    **dict.fromkeys(["SPY", "VOO", "CSPX.L", "SXR8.DE", "VTI", "IVV", "ES=F", "MES=F", "^GSPC", "RSP", "SCHD", "VIG",
                     "VYM", "USMV", "QUAL", "ESGU", "IWM", "RTY=F"], _SP500),
    **dict.fromkeys(["QQQ", "PANX.PA", "NQ=F", "MNQ=F", "^NDX", "QQQM"], _NDX),
    **dict.fromkeys(["IWDA.AS", "EUNL.DE", "XDWD.DE", "CW8.PA", "EWLD.PA", "SUSW.L", "EFA", "VEA"], _WORLD),
    **dict.fromkeys(["VWCE.DE", "VT", "ACWI", "IUSN.DE"], _WORLD_ALL),
    **dict.fromkeys(["VGK", "EZU", "FEZ", "EWG", "EWQ", "EWU", "C40.PA", "EXS1.DE", "^FCHI", "^GDAXI", "^STOXX50E"],
                    {"Actions Europe": 1.0}),
    **dict.fromkeys(["EEM", "VWO", "IEMG", "EIMI.L", "PAEEM.PA", "FXI", "MCHI", "EWZ", "INDA", "EWY"],
                    {"Actions émergentes": 1.0}),
    **dict.fromkeys(["EWJ", "^N225", "NIY=F"], _mix((0.6, _SP500), (0.4, "Actions Europe"))),
    **dict.fromkeys(["TLT", "IEF", "GOVT", "BND", "AGG", "TIP", "BNDX", "MBB", "LQD", "IEAC.L", "ZB=F", "ZN=F"],
                    {"Obligations longues": 1.0}),
    "HYG": {"Obligations longues": 0.4, "Finance": 0.3, "Industrie": 0.3},
    "EMB": {"Obligations longues": 0.5, "Actions émergentes": 0.5},
    **dict.fromkeys(["SHY", "IBTS.L", "BIL", "SGOV", "XEON.DE"], {}),      # quasi-monétaire : impact ≈ 0
    **dict.fromkeys(["GLD", "IAU", "SGLD.L", "GC=F", "MGC=F"], {"Or": 1.0}),
    **dict.fromkeys(["USO", "CL=F", "MCL=F", "BZ=F", "NG=F", "UNG"], {"Énergie": 1.0}),
    **dict.fromkeys(["DBC", "PDBC", "DBB", "SLV", "SI=F", "HG=F"], {"Matériaux": 1.0}),
    **dict.fromkeys(["XLK", "VGT", "IGV"], {"Technologie": 0.75, "Semi-conducteurs": 0.25}),
    "XLC": {"Communication & médias": 1.0}, "XLY": {"Consommation discrétionnaire": 1.0},
    "XLP": {"Consommation de base": 1.0}, "XLF": {"Finance": 1.0}, "XLV": {"Santé": 1.0}, "XLE": {"Énergie": 1.0},
    "XLI": {"Industrie": 1.0}, "ITA": {"Industrie": 1.0}, "XLB": {"Matériaux": 1.0},
    "XLU": {"Services publics": 1.0}, "XLRE": {"Immobilier": 1.0}, "VNQ": {"Immobilier": 1.0},
    "ARKK": {"Technologie": 0.6, "Communication & médias": 0.2, "Santé": 0.2},
}
_LABEL_TO_KEY = [("Semi-conducteurs", "Semi-conducteurs"), ("Technologie", "Technologie"),
                 ("Communication", "Communication & médias"), ("discrétionnaire", "Consommation discrétionnaire"),
                 ("de base", "Consommation de base"), ("Finance", "Finance"), ("Santé", "Santé"), ("Énergie", "Énergie"),
                 ("Industrie", "Industrie"), ("Matériaux", "Matériaux"), ("Services publics", "Services publics"),
                 ("Immobilier", "Immobilier")]
_EU_SUFFIX = (".PA", ".DE", ".AS", ".MI", ".MC", ".BR", ".LS", ".L", ".SW", ".IR", ".VI", ".HE", ".ST", ".CO", ".OL")
_EM_SUFFIX = (".NS", ".HK", ".KS", ".SA", ".SS", ".SZ")


def _comp(name: str) -> dict:
    try:
        return CP.compositions()[name]
    except Exception:
        return dict(_SP500 if name == "sp500" else _NDX)


_SP_SET = {"SPY", "VOO", "CSPX.L", "SXR8.DE", "VTI", "IVV", "ES=F", "MES=F", "^GSPC", "RSP", "SCHD", "VIG", "VYM", "USMV",
           "QUAL", "ESGU", "IWM", "RTY=F"}
_NDX_SET = {"QQQ", "PANX.PA", "NQ=F", "MNQ=F", "^NDX", "QQQM"}


def sector_weights(ticker: str) -> tuple[dict, bool]:
    """(ventilation par secteur / actif, classée ?). Non classée → S&P 500 par défaut (signalé).
    Les compositions S&P 500 / Nasdaq 100 sont modifiables dans Admin → Paramètres financiers."""
    t = str(ticker or "").upper().strip()
    if t in _SP_SET:
        return _comp("sp500"), True
    if t in _NDX_SET:
        return _comp("nasdaq100"), True
    if t in _SPECIAL:
        return dict(_SPECIAL[t]), True
    if t in _SEMIS:
        return {"Semi-conducteurs": 1.0}, True
    if t.endswith(("-USD", "-EUR")):
        return {"Bitcoin": 1.0}, True
    try:
        from utils.sectors import sector_of
        lab = sector_of(t)
    except Exception:
        lab = ""
    for needle, key in _LABEL_TO_KEY:
        if needle in lab:
            return {key: 1.0}, True
    if t.endswith(_EU_SUFFIX):
        return {"Actions Europe": 1.0}, True
    if t.endswith(_EM_SUFFIX):
        return {"Actions émergentes": 1.0}, True
    return _comp("sp500"), False


def portfolio_scenarios(vals: dict, cash: float, scs: list[dict], probs: dict, perte_max: float | None = None) -> dict:
    """Gain / perte attendu du portefeuille dans chaque scénario (impacts par secteur du comité)."""
    nav = float(cash) + sum(v for v in vals.values() if v and v > 0)
    if nav <= 0 or not vals:
        return dict(ok=False)
    out, unclassified = {}, []
    by_line: dict[str, dict] = {}
    for t, v in vals.items():
        if not v or v <= 0:
            continue
        w, ok = sector_weights(t)
        if not ok:
            unclassified.append(t)
        by_line[t] = {s["id"]: v * sum(wk * float(s["impacts"].get(k, 0.0)) / 100 for k, wk in w.items()) for s in scs}
    for s in scs:
        pnl = sum(d[s["id"]] for d in by_line.values())
        out[s["id"]] = dict(pnl=pnl, pct=pnl / nav,
                            contrib=sorted(((t, d[s["id"]]) for t, d in by_line.items()), key=lambda x: x[1]))
    exp = sum(probs.get(i, 0) * out[i]["pct"] for i in out)
    worst = min(out, key=lambda i: out[i]["pct"])
    breach = perte_max is not None and out[worst]["pct"] < -abs(perte_max)
    return dict(ok=True, nav=nav, scen=out, expected=exp, worst=worst, perte_max=perte_max, breach=bool(breach),
                unclassified=unclassified)


# ══════════════════════════════════════════════════════════════════════════════
#  2-3. PLAN D'ACTION PAR PHASES (avec lignes figées)
# ══════════════════════════════════════════════════════════════════════════════
PHASES = ("1 · Cette semaine", "2 · Ce mois-ci (par paliers)", "3 · Chaque trimestre")


def _fmt(x: float) -> str:
    return f"{x:,.0f} $".replace(",", " ")


def action_plan(vals: dict, cash: float, sc: dict, pscen: dict | None, expo: dict | None, hedge: dict | None,
                frozen: set[str] | None = None) -> dict:
    """Plan séquencé : chaque action = phase, action, montant, lignes, raison, membre du comité."""
    from utils import scenarios as SC
    frozen = {t.upper() for t in (frozen or set())}
    acts: list[dict] = []
    nav = float(cash) + sum(v for v in vals.values() if v and v > 0)
    if nav <= 0:
        return dict(ok=False, actions=[], frozen_note=None)
    n_pal = int(CP.get("paliers"))
    movable = {t: v for t, v in vals.items() if v and v > 0 and t.upper() not in frozen}
    fz = {t: v for t, v in vals.items() if v and v > 0 and t.upper() in frozen}
    frozen_note = None
    if fz:
        fexp = SC.exposure_profile(fz, 0.0)
        tot = sum(fz.values())
        frozen_note = (f"Lignes figées ({', '.join(sorted(fz))} = {_fmt(tot)}, {tot / nav:.0%} du portefeuille) : "
                       "aucune vente ni aucun achat proposé sur ces lignes ; elles apportent "
                       f"{fexp['us'] * tot / nav:.0%} d'exposition aux actions américaines et {fexp['tech'] * tot / nav:.0%} "
                       "à la tech / IA, que le reste du portefeuille compense.")

    # ── Phase 1 : budget de risque, couverture, liquidités ──
    pm = (pscen or {}).get("perte_max")
    if pscen and pscen.get("ok") and pm:
        w = pscen["scen"][pscen["worst"]]
        if w["pct"] < -abs(pm):
            excess = (-w["pct"] - abs(pm)) * nav
            losers = [(t, x) for t, x in w["contrib"] if x < 0 and t.upper() not in frozen][:3]
            loss_mov = -sum(x for _, x in losers) or 1.0
            sell_val = sum(movable.get(t, 0) for t, _ in losers)
            amount = min(sell_val, excess / max(loss_mov / max(sell_val, 1), 1e-6)) if sell_val else excess
            acts.append(dict(phase=PHASES[0], action="Ramener la perte du scénario le plus défavorable sous votre limite",
                             montant=amount, lignes=", ".join(t for t, _ in losers) or "—",
                             pourquoi=f"Scénario {pscen['worst']} : {w['pct']:+.1%} contre une perte maximale acceptée de "
                                      f"{-abs(pm):.0%} (IPS). Alléger en priorité les lignes qui perdent le plus dans ce "
                                      "scénario, ou les couvrir.",
                             qui="Aline DE MARGE"))
    pb = sc.get("probs", {}).get("baissier", 0.0)
    if hedge and hedge.get("ok") and hedge.get("causes") and (pb >= CP.get("proba_baisse_couverture") or hedge.get("n_options", 0) == 0):
        target_notional = hedge["target"] * hedge["equity"]
        gap = max(0.0, target_notional - max(hedge.get("delta_notional", 0.0), 0.0))
        if gap > 0:
            acts.append(dict(phase=PHASES[0], action="Corriger la couverture par options", montant=gap,
                             lignes="QQQ / SOXX si l'exposition est tech, sinon SPY",
                             pourquoi=hedge["causes"][0] + f" Notionnel delta-ajusté manquant ≈ {_fmt(gap)} "
                                                           f"(cible {hedge['target']:.0%}).",
                             qui="Thierry BALANCEMENT"))
    cmin = CP.get("liquidites_min")
    if cash / nav < cmin:
        acts.append(dict(phase=PHASES[0], action="Reconstituer un coussin de liquidités", montant=(cmin - cash / nav) * nav,
                         lignes="lignes les plus surpondérées", pourquoi=f"Liquidités {cash / nav:.1%} sous le minimum "
                                                                          f"{cmin:.0%} : marge pour racheter par paliers.",
                         qui="Aline DE MARGE"))

    # ── Phase 2 : plafonds personnels, concentration, déploiement par paliers ──
    if expo and expo.get("ok"):
        mexp = SC.exposure_profile(movable, 0.0) if movable else dict(ok=False)
        mov_val = sum(movable.values())
        for key, cap_key, lab, dest in (("us", "plafond_us", "actions américaines",
                                         "Europe, émergents de qualité, obligations, or"),
                                        ("tech", "plafond_tech_ia", "tech / IA / semi-conducteurs",
                                         "secteurs défensifs, Europe, obligations")):
            cap = CP.get(cap_key)
            if expo[key] > cap + 1e-9:
                need = (expo[key] - cap) * nav
                avail = mexp.get(key, 0) * mov_val if mexp.get("ok") else 0.0
                amount = min(need, avail)
                note = "" if amount >= need - 1 else (f" Les lignes mobiles ne suffisent pas ({_fmt(avail)} disponibles) : "
                                                      "revoir les lignes figées ou relever le plafond.")
                acts.append(dict(phase=PHASES[1], action=f"Réduire l'exposition {lab} en {n_pal} palier(s)",
                                 montant=amount, lignes=f"{_fmt(amount / n_pal)} par palier → {dest}",
                                 pourquoi=f"Exposition {expo[key]:.0%} au-dessus de votre plafond {cap:.0%}." + note,
                                 qui="Marc ETING-FINANCIER"))
        cl = CP.get("plafond_ligne")
        for t, v in sorted(movable.items(), key=lambda x: -x[1]):
            if v / nav > cl + 1e-9:
                acts.append(dict(phase=PHASES[1], action=f"Réduire la concentration sur {t}", montant=v - cl * nav,
                                 lignes=t, pourquoi=f"{v / nav:.0%} du portefeuille sur une seule ligne (plafond {cl:.0%}).",
                                 qui="Aline DE MARGE"))
    main = sc.get("main")
    excess_cash = cash / nav - (cmin + CP.get("marge_cash_deploiement"))
    if excess_cash > 0 and main in ("haussier", "central"):
        acts.append(dict(phase=PHASES[1], action=f"Investir les liquidités excédentaires en {n_pal} palier(s)",
                         montant=excess_cash * nav, lignes=f"{_fmt(excess_cash * nav / n_pal)} par palier, vers l'allocation cible",
                         pourquoi=f"Scénario principal « {main} » : investir progressivement limite le risque de mauvais "
                                  "point d'entrée.", qui="Thierry BALANCEMENT"))

    # ── Phase 3 : suivi et revue ──
    band = CP.get("bande_reequilibrage")
    acts.append(dict(phase=PHASES[2], action="Rééquilibrer vers l'allocation cible", montant=None, lignes="toutes les lignes mobiles",
                     pourquoi=f"Uniquement les lignes qui s'écartent de plus de {band:.0%} de leur poids cible.",
                     qui="Thierry BALANCEMENT"))
    if hedge and hedge.get("ok") and len(hedge.get("lines", [])):
        acts.append(dict(phase=PHASES[2], action="Rouler les options avant la perte de valeur temps", montant=None,
                         lignes=f"options à moins de {CP.get('option_jours_roulement')} jours", pourquoi="Une option proche de l'échéance protège de moins en moins.",
                         qui="Aline DE MARGE"))
    acts.append(dict(phase=PHASES[2], action="Revoir les catalyseurs et réviser les probabilités", montant=None,
                     lignes="Admin → Paramètres financiers", pourquoi="Les hypothèses changent : enregistrer chaque révision "
                                                                      "pour garder la trace du raisonnement.",
                     qui="Jean-Michel TAUX-BAS"))
    acts.append(dict(phase=PHASES[2], action="Vérifier la politique d'investissement (IPS) et les lignes figées", montant=None,
                     lignes="—", pourquoi="Horizon, perte maximale et contraintes peuvent avoir changé.",
                     qui="Marc ETING-FINANCIER"))
    return dict(ok=True, actions=acts, frozen_note=frozen_note)


# ══════════════════════════════════════════════════════════════════════════════
#  4. AUTOCRITIQUE DU COMITÉ
# ══════════════════════════════════════════════════════════════════════════════
def self_critique(an: dict, sc: dict) -> dict:
    """Note sur 10 de l'analyse + faiblesses + améliorations (Marc ETING-FINANCIER, biais et reporting)."""
    note, faibles, ameli = 10.0, [], []
    checks = an.get("checks") or []
    if checks:
        note -= min(2.0, len(checks))
        faibles.append(f"Données incomplètes ({len(checks)} alerte(s) de contrôle).")
        ameli.append("Relancer l'analyse plus tard ou vérifier la source des cours.")
    att = an.get("attribution") or {}
    r2 = att.get("r2", np.nan)
    if r2 == r2 and r2 < CP.get("critique_r2_min"):
        note -= 1.0
        faibles.append(f"Le modèle de facteurs n'explique que {r2:.0%} des variations : la macro n'est pas le moteur principal.")
        ameli.append("Regarder les résultats d'entreprises et l'actualité spécifique (part « propre au marché »).")
    it = an.get("intraday") or {}
    n_items = it.get("n_items", 0) if it else 0
    so = an.get("social") or {}
    if n_items < CP.get("critique_messages_min") and not so.get("n"):
        note -= 1.0
        faibles.append("Sentiment mesuré sur trop peu de messages horodatés.")
        ameli.append("Activer les réseaux sociaux ou attendre davantage d'actualités avant d'en tenir compte.")
    if not it.get("ok"):
        note -= 0.5
        faibles.append("Pas de données intraday : la dynamique des dernières heures n'est pas prise en compte.")
    probs = sc.get("probs") or {}
    if probs and max(probs.values()) < CP.get("critique_proba_min"):
        note -= 0.5
        faibles.append("Scénarios peu tranchés : l'incertitude est élevée, la prudence s'impose sur la taille des positions.")
    if "catalyseurs" not in CP.custom_keys():
        note -= 0.5
        faibles.append("Catalyseurs par défaut, non revus par le gérant.")
        ameli.append("Ajuster les catalyseurs et leurs probabilités dans Admin → Paramètres financiers.")
    if "scénarios" not in CP.custom_keys():
        note -= 0.5
        faibles.append("Impacts par secteur = hypothèses générales du comité, non calibrées sur l'historique.")
        ameli.append("Confronter les impacts aux corrections passées (ex. 2020, 2022) et les ajuster.")
    if not sc.get("portfolio") or not (sc.get("portfolio") or {}).get("ok"):
        note -= 1.0
        faibles.append("Analyse non reliée à un portefeuille : pas de montant ni de priorité d'action.")
        ameli.append("Choisir un portefeuille pour obtenir le stress des scénarios et le plan d'action.")
    else:
        unc = sc["portfolio"].get("unclassified") or []
        if unc:
            note -= 0.5
            faibles.append(f"Lignes non classées par secteur ({', '.join(unc[:5])}) : traitées comme le S&P 500.")
    h = sc.get("hedge")
    if h and h.get("ok") and h.get("causes"):
        note -= 0.5
        faibles.append("Couverture incohérente avec l'exposition (voir le diagnostic des options).")
    note = max(1.0, round(note * 2) / 2)
    verdict = ("analyse solide" if note >= CP.get("critique_note_solide") else "analyse utilisable avec prudence"
               if note >= CP.get("critique_note_prudence")
               else "analyse fragile : ne pas décider sur cette seule base")
    return dict(note=note, verdict=verdict, faiblesses=faibles, ameliorations=list(dict.fromkeys(ameli)),
                qui="Marc ETING-FINANCIER")


# ══════════════════════════════════════════════════════════════════════════════
#  5. PROCESSUS D'INVESTISSEMENT (état de chaque étape)
# ══════════════════════════════════════════════════════════════════════════════
def process_status(port: dict | None, sc: dict) -> list[dict]:
    ips = (port or {}).get("ips")
    ps = sc.get("portfolio") or {}
    h = sc.get("hedge") or {}
    rem = sc.get("remediation") or {}
    revs = []
    try:
        revs = CP.revisions()
    except Exception:
        pass
    rows = [
        dict(etape="1. Politique d'investissement (IPS)", ok=bool(ips),
             detail="IPS validée par le comité" if ips else "Pas d'IPS : profil par défaut utilisé"),
        dict(etape="2. Allocation et limites personnelles", ok=not rem.get("perso"),
             detail="Plafonds respectés" if not rem.get("perso") else f"{len(rem['perso'])} écart(s) aux plafonds / limites"),
        dict(etape="3. Budget de risque (stress des scénarios)", ok=bool(ps.get("ok")) and not ps.get("breach"),
             detail=("Non calculé (pas de portefeuille)" if not ps.get("ok") else
                     f"Pire scénario {ps['scen'][ps['worst']]['pct']:+.1%}"
                     + (f" vs limite {-abs(ps['perte_max']):.0%}" if ps.get("perte_max") else ""))),
        dict(etape="4. Couverture", ok=bool(h.get("ok")) and not h.get("causes"),
             detail="Cohérente" if h.get("ok") and not h.get("causes") else
             (h.get("causes") or ["Non évaluée"])[0]),
        dict(etape="5. Mise en œuvre (plan par phases)", ok=bool((sc.get("plan") or {}).get("ok")),
             detail=f"{len((sc.get('plan') or {}).get('actions', []))} action(s) proposée(s), à valider"),
        dict(etape="6. Suivi et revue", ok=len(revs) > 0,
             detail=f"Dernière révision des probabilités : {revs[-1]['date']}" if revs else "Aucune révision enregistrée"),
    ]
    return rows
