# utils/scenarios.py  —  MAM v5.12 · Scénarios probabilisés, note de synthèse du comité, remédiation
"""
Les marchés bougent sur des chiffres ET sur des hypothèses. Le comité :

  1. SIGNAUX — résume l'état du marché en signaux normalisés (≈ −1 … +1) : ampleur du mouvement,
     tendance, RSI (contrarien), peur (VIX), crédit, actualités / réseaux sociaux, dynamique intraday 6 h,
     et CATALYSEURS (hypothèses qualitatives : probabilité de survenue × sens × force, modifiables en admin) ;
  2. SCORE — combinaison des signaux par une formule (modifiable en admin, évaluée de façon sécurisée) ;
  3. PROBABILITÉS — haussier / central / baissier : probabilités a priori déformées par le score
     (logit), totalisant 100 % ; l'administrateur peut forcer les probabilités à la main ;
  4. CE QUI FERAIT BASCULER — sensibilité des probabilités à chaque catalyseur (s'il se réalise / s'il
     est écarté) et à chaque signal ;
  5. SECTEURS — impact attendu de chaque scénario par secteur / actif et impact pondéré par les probabilités ;
  6. REMÉDIATION — plans par scénario, complétés par les constats propres au portefeuille (concentration
     États-Unis / tech-IA / ligne vs plafonds personnels, bêta, efficacité des couvertures) ;
  7. COUVERTURE — diagnostic : pourquoi les options n'ont pas protégé à hauteur de l'exposition
     (notionnel delta-ajusté, strike trop hors de la monnaie, mauvais sous-jacent, échéance) ;
  8. GROSSE PERTE — détection selon les seuils admin, utilisée par les rapports.

Fonctions pures (testées hors réseau). Estimations éducatives, pas des prévisions.
"""
from __future__ import annotations

import math
from datetime import datetime

import numpy as np
import pandas as pd

from utils import core_params as CP

SIG_LABELS = {
    "momentum": "Ampleur du mouvement récent",
    "tendance": "Tendance de fond (vs moyenne longue)",
    "rsi": "RSI (survente = rebond possible)",
    "peur": "Peur (VIX)",
    "credit": "Marché du crédit",
    "sentiment": "Actualités et réseaux sociaux",
    "intraday": "Dynamique intraday (6 h)",
    "catalyseurs": "Catalyseurs / hypothèses",
}


def _clip(x, lo=-1.0, hi=1.0):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if not math.isfinite(x) else max(lo, min(hi, x))


# ══════════════════════════════════════════════════════════════════════════════
#  1. SIGNAUX
# ══════════════════════════════════════════════════════════════════════════════
def catalyst_score(cats: list[dict] | None = None) -> float:
    cats = [c for c in (cats if cats is not None else CP.catalysts()) if c.get("actif", True)]
    tot = sum(float(c.get("force", 0) or 0) for c in cats)
    if not cats or tot <= 0:
        return 0.0
    return _clip(sum(float(c["sens"]) * float(c["proba"]) * float(c["force"]) for c in cats) / tot)


def signals(an: dict, px: pd.DataFrame | None = None, intraday: dict | None = None,
            cats: list[dict] | None = None) -> dict:
    """Signaux normalisés (positif = favorable à la hausse) + valeurs brutes pour l'affichage."""
    from utils import prices as P
    att, tech = an.get("attribution", {}), an.get("technique", {})
    raw, sig = {}, {}
    z = att.get("z", np.nan)
    raw["momentum"] = f"z = {z:+.1f}" if z == z else "—"
    sig["momentum"] = float(np.tanh(z / 2)) if z == z else 0.0
    vs = tech.get("vs_ma200", np.nan) if tech.get("ok") else np.nan
    raw["tendance"] = f"{vs:+.1%} vs MM {tech.get('mm_longue', 200)}" if vs == vs else "—"
    sig["tendance"] = _clip(vs / 0.05) if vs == vs else 0.0
    rsi = tech.get("rsi", np.nan) if tech.get("ok") else np.nan
    raw["rsi"] = f"RSI {rsi:.0f}" if rsi == rsi else "—"
    sig["rsi"] = _clip((50 - rsi) / 25) if rsi == rsi else 0.0
    fmoves = {f["key"]: f["move"] for f in att.get("factors") or []}
    vix = np.nan
    if px is not None and "^VIX" in px:
        v = P.true_closes(px["^VIX"])
        if att.get("end"):                       # niveau du VIX à la même date que le marché analysé
            v = v[v.index <= pd.Timestamp(att["end"])]
        vix = float(v.iloc[-1]) if len(v) else np.nan
    dv = fmoves.get("vix", np.nan)               # variation du VIX sur l'horizon (log), mêmes dates
    raw["peur"] = (f"VIX {vix:.1f}" if vix == vix else "VIX —") + (f" ({np.expm1(dv):+.0%})" if dv == dv else "")
    lvl_s = -_clip((vix - 20) / 10) if vix == vix else 0.0
    chg_s = -_clip(dv / 0.10) if dv == dv else 0.0
    sig["peur"] = 0.6 * lvl_s + 0.4 * chg_s      # niveau (stress de fond) + variation (dynamique)
    cr = fmoves.get("credit", np.nan)            # même mesure et mêmes dates que « Pourquoi ? »
    if cr != cr and px is not None and "HYG" in px and "IEF" in px:
        a, b = P.true_closes(px["HYG"]), P.true_closes(px["IEF"])
        j = pd.concat([a, b], axis=1, sort=True).dropna()
        h = max(1, int(an.get("horizon", 5)))
        if len(j) > h:
            ratio = np.log(j.iloc[:, 0] / j.iloc[:, 1])
            cr = float(ratio.iloc[-1] - ratio.iloc[-h - 1])
    raw["credit"] = f"haut rendement vs Trésor {cr:+.1%}" if cr == cr else "—"
    sig["credit"] = _clip(cr / 0.01) if cr == cr else 0.0
    tone = float((an.get("news") or {}).get("tone", 0.0) or 0.0)
    so = (an.get("social") or {}).get("score", np.nan)
    so_adj = (so if abs(so) <= 0.45 else -0.5 * so) if so == so else 0.0   # euphorie / panique extrêmes : contrarien
    raw["sentiment"] = f"actualités {tone:+.2f}" + (f" · réseaux {so:+.2f}" if so == so else "")
    sig["sentiment"] = _clip(0.6 * tone * 2 + 0.4 * so_adj)
    w6 = (intraday or {}).get("w6") or {}
    if w6.get("ok"):
        raw["intraday"] = f"{w6['ret']:+.2%} sur 6 h"
        sig["intraday"] = float(np.tanh(w6["ret"] / max(1e-4, CP.get("intra_alerte"))))
    else:
        raw["intraday"], sig["intraday"] = "—", 0.0
    cs = catalyst_score(cats)
    raw["catalyseurs"] = f"{cs:+.2f}"
    sig["catalyseurs"] = cs
    return dict(signals=sig, raw=raw, vix=vix)


# ══════════════════════════════════════════════════════════════════════════════
#  2-3. SCORE ET PROBABILITÉS
# ══════════════════════════════════════════════════════════════════════════════
def score(sig: dict, expr: str | None = None) -> float:
    expr = expr or CP.formula("score_scenario")
    env = {**{k: float(sig.get(k, 0.0)) for k in CP.SCORE_VARS}, **{k: CP.get(k) for k in CP.PARAMS if k.startswith("w_")}}
    try:
        return float(CP.safe_eval(expr, env))
    except Exception:
        return float(CP.safe_eval(CP.FORMULAS["score_scenario"]["default"], env))


def probabilities(s: float, scs: list[dict] | None = None, k: float | None = None) -> dict:
    """{id: probabilité} totalisant 1. Logit : haussier +k·S, baissier −k·S, central −k·|S|/2."""
    scs = scs or CP.scenarios()
    k = CP.get("sc_sensibilite") if k is None else k
    shift = {"haussier": k * s, "baissier": -k * s, "central": -0.5 * k * abs(s)}
    lg = {x["id"]: math.log(max(1e-6, float(x["prior"]))) + shift.get(x["id"], 0.0) for x in scs}
    m = max(lg.values())
    e = {i: math.exp(v - m) for i, v in lg.items()}
    tot = sum(e.values())
    p = {i: v / tot for i, v in e.items()}
    forced = {x["id"]: float(x["prob_forcee"]) for x in scs if x.get("prob_forcee") not in (None, "")}
    if forced:
        fs = sum(forced.values())
        rest = [i for i in p if i not in forced]
        if not rest or fs >= 1:
            return {i: forced.get(i, 0.0) / fs if fs else 0.0 for i in p}
        rp = sum(p[i] for i in rest)
        p = {i: forced[i] if i in forced else (1 - fs) * p[i] / rp for i in p}
    return p


def sensitivity(sig: dict, scs: list[dict] | None = None, cats: list[dict] | None = None) -> list[dict]:
    """Ce qui ferait monter / baisser les probabilités : chaque catalyseur réalisé ou écarté."""
    scs = scs or CP.scenarios()
    cats = cats if cats is not None else CP.catalysts()
    base = probabilities(score(sig), scs)
    out = []
    for i, c in enumerate(cats):
        if not c.get("actif", True):
            continue
        res = {}
        for lab, pv in (("se réalise", 1.0), ("est écarté", 0.0)):
            cc = [dict(x) for x in cats]
            cc[i]["proba"] = pv
            sg = {**sig, "catalyseurs": catalyst_score(cc)}
            p = probabilities(score(sg), scs)
            res[lab] = {k: p[k] - base[k] for k in p}
        out.append(dict(catalyseur=c["nom"], proba=float(c["proba"]), sens=int(c["sens"]),
                        si_realise=res["se réalise"], si_ecarte=res["est écarté"]))
    out.sort(key=lambda r: -abs(r["si_realise"].get("baissier", 0)))
    return out


def contributions(sig: dict) -> list[dict]:
    rows = []
    for k in CP.SCORE_VARS:
        w = CP.get(f"w_{k}") if f"w_{k}" in CP.PARAMS else 1.0
        rows.append(dict(cle=k, signal=SIG_LABELS.get(k, k), valeur=float(sig.get(k, 0.0)), poids=w,
                         contribution=w * float(sig.get(k, 0.0))))
    rows.sort(key=lambda r: -abs(r["contribution"]))
    return rows


# ══════════════════════════════════════════════════════════════════════════════
#  5. SECTEURS : IMPACT ATTENDU PAR SCÉNARIO
# ══════════════════════════════════════════════════════════════════════════════
def sector_expectations(probs: dict, scs: list[dict] | None = None) -> pd.DataFrame:
    scs = scs or CP.scenarios()
    rows = []
    for sec in CP.SECTORS:
        r = {"Secteur / actif": sec}
        exp = 0.0
        for s in scs:
            v = float(s["impacts"].get(sec, 0.0)) / 100
            r[s["id"]] = v
            exp += probs.get(s["id"], 0.0) * v
        r["Impact pondéré"] = exp
        rows.append(r)
    return pd.DataFrame(rows)


# ══════════════════════════════════════════════════════════════════════════════
#  EXPOSITION DU PORTEFEUILLE (plafonds personnels)
# ══════════════════════════════════════════════════════════════════════════════
_NON_US_SUFFIX = (".PA", ".DE", ".AS", ".MI", ".MC", ".BR", ".LS", ".L", ".SW", ".T", ".HK", ".KS", ".NS", ".TO",
                  ".AX", ".ST", ".CO", ".OL", ".HE", ".IR", ".VI")
_NON_US_ETF = {"VGK", "EZU", "FEZ", "EWQ", "EWG", "EWJ", "EEM", "VWO", "IEMG", "EWU", "EWZ", "INDA", "MCHI", "FXI"}
_TECH_AI = {"SOXX", "SMH", "XLK", "QQQ", "VGT", "IGV", "ARKK", "BOTZ", "AIQ", "NVDA", "AMD", "AVGO", "TSM", "ASML",
            "MU", "ARM", "SMCI", "INTC", "QCOM", "MSFT", "GOOGL", "GOOG", "META", "AMZN", "AAPL", "ORCL", "PLTR",
            "CRM", "ADBE", "TSLA", "NFLX", "ASML.AS", "PANX.PA"}


def exposure_profile(vals: dict[str, float], cash: float = 0.0) -> dict:
    """Parts des actions américaines, de la tech / IA et de la plus grosse ligne dans l'actif net."""
    from utils import hedging as H
    nav = float(cash) + sum(v for v in vals.values() if v and v > 0)
    if nav <= 0:
        return dict(ok=False)
    us = tech = 0.0
    for t, v in vals.items():
        if not v or v <= 0:
            continue
        T = t.upper()
        b = H.bucket_of(T)
        is_eq_us = b in ("us", "tech") and not T.endswith(_NON_US_SUFFIX) and T not in _NON_US_ETF
        if is_eq_us:
            us += v
        if T in _TECH_AI or b == "tech":
            tech += v
    top = max(((t, v) for t, v in vals.items() if v and v > 0), key=lambda x: x[1], default=(None, 0.0))
    return dict(ok=True, nav=nav, us=us / nav, tech=tech / nav, top=top[0], top_w=top[1] / nav)


# ══════════════════════════════════════════════════════════════════════════════
#  7. DIAGNOSTIC DE COUVERTURE PAR OPTIONS
# ══════════════════════════════════════════════════════════════════════════════
def _ret_over(s: pd.Series | None, n: int) -> float:
    from utils import prices as P
    return P.change(s, n)["ret"] if s is not None else np.nan


def hedge_effectiveness(port: dict, vals: dict[str, float], hist: pd.DataFrame | None, horizon: int = 5,
                        rate: float = 0.04) -> dict:
    """Pourquoi les options n'ont pas protégé à hauteur de l'exposition (sur l'horizon analysé).

    Pour chaque option : delta actuel (Black-Scholes), notionnel delta-ajusté, gain estimé sur l'horizon
    (revalorisation au cours d'avant / d'après). Exposition couverte = actions du même panier que le
    sous-jacent (tech → QQQ…). Constats et pistes de correction."""
    from utils import hedging as H
    from utils import prices as P
    from utils.options import bs_greeks, bs_price, remaining_days
    opts = [o for o in (port.get("options") or []) if int(o.get("n_contracts", 0) or 0) > 0]
    expo = H.exposures_from_values(vals)
    tot_eq = sum(e["montant"] for k, e in expo.items() if k in ("us", "tech", "europe", "em"))
    loss_eq = 0.0
    for t, v in vals.items():
        r = _ret_over(hist[t] if hist is not None and t in hist else None, horizon)
        if r == r and H.bucket_of(t) in ("us", "tech", "europe", "em"):
            loss_eq += v * r
    target, gap_tol, otm_max = CP.get("couverture_cible"), CP.get("couverture_ecart"), CP.get("put_otm_max")
    lines, causes, fixes = [], [], []
    hedge_gain, delta_notional = 0.0, 0.0
    for o in opts:
        und = str(o.get("ticker") or o.get("underlying") or "").upper()
        typ = str(o.get("type", "put")).lower()
        sgn = 1 if str(o.get("action", "BUY")).upper() == "BUY" else -1
        n, mult = int(o.get("n_contracts", 0)), float(o.get("contract_mult", 100) or 100)
        K, sig = float(o.get("strike", 0) or 0), float(o.get("sigma", 0.25) or 0.25)
        s_und = hist[und] if hist is not None and und in hist else None
        c = P.true_closes(s_und) if s_und is not None else pd.Series(dtype=float)
        S1 = float(c.iloc[-1]) if len(c) else np.nan
        r_u = _ret_over(s_und, horizon)
        T1 = max(remaining_days(o), 0.5) / 365
        if not (S1 == S1 and K > 0):
            lines.append(dict(Option=f"{typ.upper()} {und} {K:g}", Sens="achat" if sgn > 0 else "vente", Contrats=n,
                              Delta=np.nan, **{"Notionnel delta $": np.nan, "Gain estimé $": np.nan,
                                               "Moneyness": "—", "Jours restants": round(remaining_days(o))}))
            continue
        S0 = S1 / (1 + r_u) if r_u == r_u else S1
        T0 = T1 + horizon / 252
        v1, v0 = bs_price(S1, K, T1, rate, sig, typ), bs_price(S0, K, T0, rate, sig, typ)
        gain = sgn * n * mult * (v1 - v0)
        d = bs_greeks(S1, K, T1, rate, sig, typ)["delta"]
        dn = sgn * n * mult * d * S1
        hedge_gain += gain
        if typ == "put" and sgn > 0:
            delta_notional += -dn
        mny = K / S1 - 1
        lines.append(dict(Option=f"{typ.upper()} {und} {K:g}", Sens="achat" if sgn > 0 else "vente", Contrats=n,
                          Delta=d, **{"Notionnel delta $": dn, "Gain estimé $": gain,
                                      "Moneyness": f"{mny:+.1%}", "Jours restants": round(remaining_days(o))}))
        if typ == "put" and sgn > 0 and mny < -otm_max:
            causes.append(f"Put {und} {K:g} trop hors de la monnaie ({mny:+.1%} sous le cours) : il ne protège "
                          "qu'après une baisse importante.")
        if remaining_days(o) < CP.get("option_jours_min"):
            causes.append(f"Option {und} {K:g} à moins de {CP.get('option_jours_min')} jours de l'échéance : "
                          "protection quasi épuisée.")
        b_und = H.bucket_of(und)
        if typ == "put" and sgn > 0 and b_und == "us" and expo.get("tech", {}).get("montant", 0) > 0.3 * max(tot_eq, 1):
            r_tech = np.nan
            for proxy in ("SOXX", "QQQ", "XLK"):
                if hist is not None and proxy in hist:
                    r_tech = _ret_over(hist[proxy], horizon)
                    break
            if r_tech == r_tech and r_u == r_u and abs(r_tech) > 1.3 * abs(r_u):
                causes.append(f"Mauvais sous-jacent : la couverture est sur {und} ({r_u:+.1%}) alors que votre "
                              f"exposition tech a bougé de {r_tech:+.1%} — risque de base.")
    n_unvalued = sum(1 for ln in lines if ln.get("Delta") != ln.get("Delta"))
    n_long_puts = sum(1 for o in opts if str(o.get("type", "")).lower() == "put"
                      and str(o.get("action", "BUY")).upper() == "BUY")
    if n_unvalued:
        causes.append(f"{n_unvalued} option(s) non valorisée(s) : cours du sous-jacent indisponible — elles ne sont pas "
                      "comptées dans la part protégée.")
    if opts and n_long_puts == 0:
        causes.append("Aucun put acheté parmi vos options (calls ou ventes uniquement) : elles ne protègent pas "
                      "contre une baisse.")
    covered_ratio = delta_notional / tot_eq if tot_eq > 0 else np.nan
    coverage_real = (hedge_gain / -loss_eq) if loss_eq < 0 else np.nan
    if not opts:
        causes.append("Aucune option vivante dans le portefeuille : aucune protection en place.")
    elif tot_eq > 0 and covered_ratio == covered_ratio and covered_ratio < target:
        causes.append(f"Notionnel couvert insuffisant : le delta des puts achetés protège {covered_ratio:.0%} des "
                      f"actions exposées ({tot_eq:,.0f} $), cible {target:.0%}.".replace(",", " "))
    if any(str(o.get("action", "")).upper() == "SELL" and str(o.get("type", "")).lower() == "put" for o in opts):
        causes.append("Des puts vendus ajoutent du risque à la baisse au lieu d'en retirer.")
    if loss_eq < 0 and coverage_real == coverage_real and coverage_real < target - gap_tol:
        causes.append(f"Sur la période, les options ont compensé {max(coverage_real, 0):.0%} de la perte des actions "
                      f"(cible {target:.0%}).")
    if causes:
        fixes.append(f"Viser un notionnel delta-ajusté d'environ {target:.0%} de l'exposition actions.")
        if expo.get("tech"):
            fixes.append("Couvrir l'exposition tech / semi-conducteurs sur QQQ ou SOXX plutôt que sur le S&P 500.")
        fixes.append("Puts entre 0 % et 5 % sous le cours, échéance 2 à 3 mois ; put spread ou collar si la "
                     "volatilité implicite est chère.")
        fixes.append("Rouler les options proches de l'échéance avant qu'elles perdent leur valeur temps.")
    return dict(ok=True, n_options=len(opts), lines=pd.DataFrame(lines), equity=tot_eq, equity_pnl=loss_eq,
                hedge_gain=hedge_gain, delta_notional=delta_notional, covered_ratio=covered_ratio,
                coverage_real=coverage_real, target=target, causes=list(dict.fromkeys(causes)), fixes=fixes,
                horizon=horizon)


# ══════════════════════════════════════════════════════════════════════════════
#  6. REMÉDIATION
# ══════════════════════════════════════════════════════════════════════════════
def remediation(probs: dict, scs: list[dict] | None = None, expo: dict | None = None, port_beta: float | None = None,
                hedge: dict | None = None) -> dict:
    """Plans par scénario + constats propres au portefeuille (à valider par l'utilisateur)."""
    scs = scs or CP.scenarios()
    plans = {s["id"]: list(s.get("remediation") or []) for s in scs}
    perso = []
    if expo and expo.get("ok"):
        cu, ct, cl = CP.get("plafond_us"), CP.get("plafond_tech_ia"), CP.get("plafond_ligne")
        if expo["us"] > cu + 1e-9:
            perso.append(f"Exposition aux actions américaines {expo['us']:.0%} au-dessus de votre plafond {cu:.0%} : "
                         f"réduire d'environ {(expo['us'] - cu) * expo['nav']:,.0f} $ au profit de l'Europe, des "
                         "émergents de qualité, d'obligations ou d'or.".replace(",", " "))
        if expo["tech"] > ct + 1e-9:
            perso.append(f"Exposition tech / IA / semi-conducteurs {expo['tech']:.0%} au-dessus de votre plafond "
                         f"{ct:.0%} : alléger d'environ {(expo['tech'] - ct) * expo['nav']:,.0f} $ ou la couvrir."
                         .replace(",", " "))
        if expo.get("top") and expo["top_w"] > cl + 1e-9:
            perso.append(f"Ligne {expo['top']} = {expo['top_w']:.0%} du portefeuille (plafond {cl:.0%}) : risque de "
                         "concentration.")
    if port_beta is not None and port_beta == port_beta and port_beta > CP.get("beta_eleve"):
        perso.append(f"Bêta {port_beta:.2f} au marché : dans le scénario baissier, la perte serait amplifiée.")
    if hedge and hedge.get("ok") and hedge.get("causes"):
        perso.append("Couvertures : " + hedge["causes"][0])
    pb = probs.get("baissier", 0)
    if pb >= CP.get("proba_baisse_alerte") and hedge and hedge.get("ok") and (hedge.get("n_options", 0) == 0 or
                                                     (hedge.get("covered_ratio") or 0) < CP.get("couverture_cible")):
        perso.append(f"Probabilité baissière {pb:.0%} : compléter la protection avant d'en avoir besoin.")
    return dict(plans=plans, perso=perso)


# ══════════════════════════════════════════════════════════════════════════════
#  8. GROSSE PERTE
# ══════════════════════════════════════════════════════════════════════════════
def big_loss(nav: pd.Series | None) -> dict:
    """Détecte une grosse perte (séance, semaine, recul depuis le plus haut) selon les seuils admin."""
    from utils import prices as P
    s = P.true_closes(nav) if nav is not None else pd.Series(dtype=float)
    if len(s) < 3:
        return dict(ok=False, triggered=False)
    d1, w1 = P.change(s, 1)["ret"], P.change(s, min(5, len(s) - 1))["ret"]
    dd = float(s.iloc[-1] / s.max() - 1)
    th = dict(jour=CP.get("perte_jour"), semaine=CP.get("perte_semaine"), drawdown=CP.get("perte_drawdown"))
    hits = []
    if d1 == d1 and d1 <= th["jour"]:
        hits.append(f"perte de {d1:.1%} sur la dernière séance (seuil {th['jour']:.0%})")
    if w1 == w1 and w1 <= th["semaine"]:
        hits.append(f"perte de {w1:.1%} sur la semaine (seuil {th['semaine']:.0%})")
    if dd <= th["drawdown"]:
        hits.append(f"recul de {dd:.1%} depuis le plus haut (seuil {th['drawdown']:.0%})")
    return dict(ok=True, triggered=bool(hits), hits=hits, jour=d1, semaine=w1, drawdown=dd, seuils=th,
                date=str(s.index[-1].date()))


# ══════════════════════════════════════════════════════════════════════════════
#  NOTE DE SYNTHÈSE DU COMITÉ
# ══════════════════════════════════════════════════════════════════════════════
def build(an: dict, px: pd.DataFrame | None = None, intraday: dict | None = None, vals: dict | None = None,
          cash: float = 0.0, port: dict | None = None, hist: pd.DataFrame | None = None,
          port_beta: float | None = None) -> dict:
    """Assemble scénarios, probabilités, sensibilités, secteurs, remédiation et note du comité."""
    scs, cats = CP.scenarios(), CP.catalysts()
    sg = signals(an, px, intraday, cats)
    S = score(sg["signals"])
    probs = probabilities(S, scs)
    sens = sensitivity(sg["signals"], scs, cats)
    contrib = contributions(sg["signals"])
    secx = sector_expectations(probs, scs)
    expo = exposure_profile(vals or {}, cash) if vals else None
    hedge = hedge_effectiveness(port, vals or {}, hist, an.get("horizon", 5)) if port is not None and vals else None
    rem = remediation(probs, scs, expo, port_beta, hedge)
    main = max(probs, key=probs.get)
    # v5.13 : processus de gestion — stress des scénarios sur le portefeuille, plan par phases, autocritique
    from utils import am_process as AM
    pscen, plan = None, None
    if vals:
        pm = (port or {}).get("ips", {}).get("perte_max") if port else None
        if pm is None:
            try:
                from utils.committee import default_ips
                pm = default_ips(an.get("profile", "Équilibré"))["perte_max"]
            except Exception:
                pm = None
        pscen = AM.portfolio_scenarios(vals, cash, scs, probs, pm)
        plan = AM.action_plan(vals, cash, dict(probs=probs, main=main), pscen, expo, hedge,
                              CP.frozen_tickers((port or {}).get("name")))
        if pscen.get("ok") and pscen["breach"]:
            w = pscen["scen"][pscen["worst"]]
            rem["perso"].insert(0, f"Dans le scénario {pscen['worst']}, le portefeuille perdrait environ {w['pct']:.1%} "
                                   f"({w['pnl']:,.0f} $), au-delà de votre perte maximale acceptée "
                                   f"({-abs(pscen['perte_max']):.0%}).".replace(",", " "))
    by_id = {s["id"]: s for s in scs}
    up = [c["signal"].lower() for c in contrib if c["contribution"] > 0.05][:3]
    dn = [c["signal"].lower() for c in contrib if c["contribution"] < -0.05][:3]
    resume = (f"{an.get('headline', '')} Le comité retient le scénario « {by_id[main]['nom']} » comme le plus probable "
              f"({probs[main]:.0%}). " + (f"Plaident pour la hausse : {', '.join(up)}. " if up else "")
              + (f"Plaident pour la baisse : {', '.join(dn)}. " if dn else ""))
    watch = []
    for r in sens[:4]:
        db = r["si_realise"].get("baissier", 0)
        if abs(db) >= 0.01:
            watch.append(f"Si « {r['catalyseur']} » se confirme, la probabilité baissière "
                         f"{'monte' if db > 0 else 'baisse'} de {abs(db) * 100:.0f} pts.")
    out = dict(ok=True, signals=sg["signals"], raw=sg["raw"], vix=sg["vix"], score=S, probs=probs,
               scenarios=scs, catalysts=cats, sensitivity=sens, contributions=contrib, sectors=secx,
               exposure=expo, hedge=hedge, remediation=rem, main=main, resume=resume, watch=watch,
               portfolio=pscen, plan=plan, custom=CP.custom_note(), built=datetime.now().strftime("%d/%m/%Y %H:%M"))
    out["critique"] = AM.self_critique(an, out)
    out["process"] = AM.process_status(port, out)
    return out


def note_markdown(an: dict, sc: dict) -> str:
    """Note de synthèse du comité, en texte (copiable / téléchargeable)."""
    L = [f"# Note de synthèse du comité — {an.get('market')}", f"_{sc['built']} · horizon {an.get('horizon')} séance(s)_", "",
         "## En bref", sc["resume"], "", "## Scénarios et probabilités"]
    for s in sc["scenarios"]:
        L.append(f"- **{s['nom']}** — {sc['probs'][s['id']]:.0%} : {s['description']}")
    L += ["", "## Ce qui pourrait faire basculer"] + [f"- {w}" for w in sc["watch"] or ["—"]]
    L += ["", "## Plans de remédiation (à valider, aucun ordre n'est passé)"]
    for s in sc["scenarios"]:
        L.append(f"**Si {s['nom'].split(' — ')[0].lower()}**")
        L += [f"- {x}" for x in sc["remediation"]["plans"].get(s["id"], [])]
    if sc["remediation"]["perso"]:
        L += ["", "## Votre portefeuille"] + [f"- {x}" for x in sc["remediation"]["perso"]]
    ps = sc.get("portfolio") or {}
    if ps.get("ok"):
        L += ["", "## Stress des scénarios sur le portefeuille"]
        for s in sc["scenarios"]:
            v = ps["scen"][s["id"]]
            L.append(f"- {s['nom']} : {v['pct']:+.1%} ({v['pnl']:+,.0f} $)".replace(",", " "))
        L.append(f"- Espérance pondérée : {ps['expected']:+.1%}")
    plan = sc.get("plan") or {}
    if plan.get("ok"):
        L += ["", "## Plan d'action par phases (à valider)"]
        if plan.get("frozen_note"):
            L.append(f"_{plan['frozen_note']}_")
        for ph in dict.fromkeys(a["phase"] for a in plan["actions"]):
            L.append(f"**{ph}**")
            for a in plan["actions"]:
                if a["phase"] == ph:
                    m = f" — {a['montant']:,.0f} $".replace(",", " ") if a.get("montant") else ""
                    L.append(f"- {a['action']}{m} ({a['lignes']}) : {a['pourquoi']} — {a['qui']}")
    cr = sc.get("critique") or {}
    if cr:
        L += ["", f"## Autocritique du comité — {cr['note']:g}/10 ({cr['verdict']})"]
        L += [f"- {x}" for x in cr["faiblesses"]] + [f"- À améliorer : {x}" for x in cr["ameliorations"]]
    if sc.get("custom"):
        L += ["", f"_{sc['custom']}_"]
    L += ["", "_Probabilités estimées à partir de signaux de marché et d'hypothèses : lecture éducative, pas une "
              "prévision ni un conseil en investissement._"]
    return "\n".join(L)


def pdf_blocks(an: dict, sc: dict) -> list[tuple]:
    """Blocs pour utils.reporting.make_pdf (analyse de marché et rapport de grosse perte)."""
    b: list[tuple] = [("h", "Note de synthèse du comité — scénarios probabilisés"), ("p", sc["resume"])]
    b.append(("table", [["Scénario", "Probabilité", "Description"]] +
              [[s["nom"], f"{sc['probs'][s['id']]:.0%}", s["description"]] for s in sc["scenarios"]], [4.6, 2.2, 10.6]))
    b.append(("table", [["Signal", "Lecture", "Valeur (−1 … +1)", "Contribution au score"]] +
              [[c["signal"], sc["raw"].get(c["cle"], "—"), f"{c['valeur']:+.2f}", f"{c['contribution']:+.2f}"]
               for c in sc["contributions"]], [6.0, 4.6, 3.2, 3.6]))
    if sc["watch"]:
        b += [("p", "**Ce qui pourrait faire basculer**"), ("bullets", sc["watch"])]
    sx = sc["sectors"]
    b.append(("table", [["Secteur / actif"] + [s["nom"].split(" — ")[0] for s in sc["scenarios"]] + ["Pondéré"]] +
              [[r["Secteur / actif"]] + [f"{r[s['id']]:+.0%}" for s in sc["scenarios"]] + [f"{r['Impact pondéré']:+.1%}"]
               for _, r in sx.iterrows()], [5.2] + [2.8] * len(sc["scenarios"]) + [2.8]))
    b.append(("h", "Plans de remédiation (à valider — aucun ordre n'est passé)"))
    for s in sc["scenarios"]:
        b += [("p", f"**{s['nom']} ({sc['probs'][s['id']]:.0%})**"), ("bullets", sc["remediation"]["plans"].get(s["id"]) or ["—"])]
    if sc["remediation"]["perso"]:
        b += [("p", "**Constats sur votre portefeuille**"), ("bullets", sc["remediation"]["perso"])]
    b += process_pdf_blocks(sc)
    h = sc.get("hedge")
    if h and h.get("ok"):
        b.append(("h", "Pourquoi les options n'ont pas protégé à hauteur de l'exposition"))
        cr = h["covered_ratio"]
        b.append(("kpis", [("Actions exposées", f"{h['equity']:,.0f} $".replace(",", " ")),
                           ("Variation des actions", f"{h['equity_pnl']:+,.0f} $".replace(",", " ")),
                           ("Gain estimé des options", f"{h['hedge_gain']:+,.0f} $".replace(",", " ")),
                           ("Part protégée (delta)", f"{cr:.0%}" if cr == cr else "—")]))
        b += [("bullets", h["causes"] or ["Couverture cohérente avec l'exposition."])]
        if h["fixes"]:
            b += [("p", "**Corrections proposées**"), ("bullets", h["fixes"])]
    if sc.get("custom"):
        b.append(("note", sc["custom"]))
    b.append(("note", "Probabilités : probabilités a priori déformées par un score de signaux (logit) — estimations "
                      "éducatives, pas des prévisions."))
    return b


def process_pdf_blocks(sc: dict) -> list[tuple]:
    """v5.13 : stress des scénarios, plan par phases, processus d'investissement, autocritique."""
    b: list[tuple] = []
    ps = sc.get("portfolio") or {}
    if ps.get("ok"):
        b.append(("h", "Stress des scénarios sur le portefeuille"))
        rows = [["Scénario", "Probabilité", "Variation", "Montant", "Ligne la plus touchée"]]
        for s in sc["scenarios"]:
            v = ps["scen"][s["id"]]
            worst = v["contrib"][0] if v["contrib"] else ("—", 0)
            rows.append([s["nom"].split(" — ")[0], f"{sc['probs'][s['id']]:.0%}", f"{v['pct']:+.1%}",
                         f"{v['pnl']:+,.0f} $".replace(",", " "), f"{worst[0]} ({worst[1]:+,.0f} $)".replace(",", " ")])
        b.append(("table", rows, [3.2, 2.4, 2.4, 3.4, 6.0]))
        b.append(("p", f"Espérance pondérée par les probabilités : {ps['expected']:+.1%}"
                       + (f" · perte maximale acceptée (IPS) : {-abs(ps['perte_max']):.0%}" if ps.get("perte_max") else "")
                       + (" — **limite dépassée dans le pire scénario**" if ps.get("breach") else "")))
    plan = sc.get("plan") or {}
    if plan.get("ok") and plan["actions"]:
        b.append(("h", "Plan d'action par phases (à valider — rien n'est exécuté automatiquement)"))
        if plan.get("frozen_note"):
            b.append(("note", plan["frozen_note"]))
        b.append(("table", [["Phase", "Action", "Montant", "Lignes", "Pourquoi", "Qui"]] +
                  [[a["phase"], a["action"], f"{a['montant']:,.0f} $".replace(",", " ") if a.get("montant") else "—",
                    a["lignes"], a["pourquoi"], a["qui"]] for a in plan["actions"]],
                  [2.4, 3.4, 1.9, 2.8, 5.4, 2.1]))
    pr = sc.get("process") or []
    if pr:
        b.append(("h", "Processus d'investissement — où en est-on ?"))
        b.append(("table", [["Étape", "État", "Détail"]] +
                  [[r["etape"], "OK" if r["ok"] else "À traiter", r["detail"]] for r in pr], [5.6, 2.0, 9.8]))
    cr = sc.get("critique") or {}
    if cr:
        b.append(("h", f"Autocritique du comité — {cr['note']:g}/10 ({cr['verdict']})"))
        b.append(("bullets", (cr["faiblesses"] or ["Aucune faiblesse majeure relevée."])
                  + [f"À améliorer : {x}" for x in cr["ameliorations"]]))
    return b
