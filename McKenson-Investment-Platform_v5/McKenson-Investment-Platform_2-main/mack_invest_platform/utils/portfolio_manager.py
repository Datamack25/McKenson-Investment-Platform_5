"""
utils/portfolio_manager.py — Le « gérant de portefeuille » du Hedge Fund Agent
================================================================================

Reproduit la démarche d'un gérant professionnel lors d'une revue de portefeuille :

    1. Lire l'ÉVOLUTION du contexte (pas seulement la photo du jour) :
       facteurs économiques, monétaires, géopolitiques… il y a 3 mois, 1 mois,
       1 semaine et aujourd'hui, et changements depuis la dernière revue.
    2. Formuler des VUES par classe d'actifs avec un niveau de CONVICTION
       (forte / moyenne / faible) selon l'intensité et la cohérence des signaux.
    3. Analyser CHAQUE LIGNE : poids, contribution au risque, bêta, tendance,
       momentum, drawdown → avis Conserver / Renforcer / Alléger / Surveiller.
    4. Construire un PLAN D'AJUSTEMENT chiffré : bandes de tolérance (pas de
       trading pour des écarts mineurs), ordres ligne par ligne, rotation,
       coûts estimés, calendrier d'exécution.
    5. Fixer des DÉCLENCHEURS de révision (« si le VIX dépasse 30, alors… »).
    6. Rédiger une NOTE DE GESTION structurée, comme pour un comité
       d'investissement (option : reformulation par un LLM).

Outil pédagogique : ne constitue pas un conseil en investissement.
"""
from __future__ import annotations

import json
from datetime import datetime

import numpy as np
import pandas as pd

from utils import advisor as A

try:
    import streamlit as st
    _cache = st.cache_data
except Exception:
    st = None

    def _cache(*a, **k):
        def deco(f):
            return f
        return deco


# ══════════════════════════════════════════════════════════════════════════════
# 1. Évolution des facteurs
# ══════════════════════════════════════════════════════════════════════════════
HORIZONS = {"Il y a 3 mois": 63, "Il y a 1 mois": 21, "Il y a 1 semaine": 5, "Aujourd'hui": 0}


def factor_history(px: pd.DataFrame, news: dict) -> pd.DataFrame:
    """Facteurs recalculés à plusieurs dates passées.
    Les actualités ne sont disponibles qu'aujourd'hui : leur composante est tenue
    constante, l'évolution reflète donc les données de marché."""
    rows = {}
    for label, lag in HORIZONS.items():
        sub = px.iloc[: len(px) - lag] if lag else px
        if len(sub) < 260:
            continue
        m = A.compute_macro(sub, news)
        rows[label] = pd.concat([pd.Series(m.factors, dtype=object),
                                 pd.Series({"Régime": m.regime}, dtype=object)])
    df = pd.DataFrame(rows)
    return df


def factor_moves(hist: pd.DataFrame, ref: str = "Il y a 1 mois", threshold: float = 0.35) -> list[dict]:
    """Mouvements significatifs d'un facteur entre une date de référence et aujourd'hui."""
    if ref not in hist.columns or "Aujourd'hui" not in hist.columns:
        return []
    out = []
    for k in A.F_KEYS:
        a, b = float(hist.loc[k, ref]), float(hist.loc[k, "Aujourd'hui"])
        if abs(b - a) >= threshold:
            out.append(dict(facteur=k, label=A.FACTORS[k][0], avant=a, maintenant=b, delta=b - a))
    return sorted(out, key=lambda d: -abs(d["delta"]))


def describe_move(mv: dict) -> str:
    k, d = mv["facteur"], mv["delta"]
    sens = "se renforce" if d > 0 else "se détend"
    if k in ("croissance", "credit"):
        sens = "s'améliore" if d > 0 else "se dégrade"
    impact = A.sensitivity()[k] * np.sign(d)
    gagnants = ", ".join(impact.sort_values(ascending=False).index[:2])
    perdants = ", ".join(impact.sort_values().index[:2])
    return (f"{mv['label']} {sens} ({mv['avant']:+.1f} → {mv['maintenant']:+.1f}). "
            f"Historiquement favorable à : {gagnants} ; défavorable à : {perdants}.")


def changes_since_review(macro_now, last_review: dict | None) -> list[str]:
    if not last_review or not last_review.get("facteurs"):
        return []
    old = last_review["facteurs"]
    out = []
    for k in A.F_KEYS:
        if k in old and abs(macro_now.factors[k] - old[k]) >= 0.35:
            out.append(f"{A.FACTORS[k][0]} : {old[k]:+.1f} → {macro_now.factors[k]:+.1f}")
    if last_review.get("regime") and last_review["regime"] != macro_now.regime:
        out.insert(0, f"Changement de régime : {last_review['regime']} → {macro_now.regime}")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 2. Vues par classe d'actifs et conviction
# ══════════════════════════════════════════════════════════════════════════════
def class_views(macro, target: pd.Series, profile: str, data_simulated: bool) -> pd.DataFrame:
    strat = pd.Series(A.PROFILES[profile], index=A.CLASSES)
    f = pd.Series(macro.factors)[A.F_KEYS]
    rows = []
    for c in A.CLASSES:
        contrib = A.sensitivity().loc[c] * f
        score = float(contrib.sum())
        nz = contrib[contrib.abs() > 0.05]
        agree = float((np.sign(nz) == np.sign(score)).mean()) if len(nz) else 0.0
        strength = abs(np.tanh(score / 3))
        if data_simulated:
            conv = "Faible"
        elif strength > 0.45 and agree >= 0.65:
            conv = "Forte"
        elif strength > 0.2 and agree >= 0.55:
            conv = "Moyenne"
        else:
            conv = "Faible"
        if score > 0.6:
            view = "Surpondérer"
        elif score < -0.6:
            view = "Sous-pondérer"
        else:
            view = "Neutre"
        rows.append({"Classe": c, "Vue": view, "Conviction": conv, "Score": score,
                     "Cohérence des signaux": agree, "Poids stratégique": strat[c],
                     "Poids cible": float(target.get(c, 0.0)),
                     "Arguments": " ; ".join(A.explain_class(c, macro.factors, top=2))})
    return pd.DataFrame(rows).set_index("Classe")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Analyse ligne par ligne
# ══════════════════════════════════════════════════════════════════════════════
@_cache(ttl=3600, show_spinner=False)
def load_line_prices(tickers: tuple):
    """Prix réels des lignes détenues (sans simulation). Renvoie (prix, manquants)."""
    tickers = tuple(t for t in tickers if A.classify_ticker(t) and t.upper() != "CASH"
                    and not t.upper().endswith("=X"))
    if not tickers:
        return pd.DataFrame(), []
    try:
        import yfinance as yf
        raw = yf.download(list(tickers), period="2y", auto_adjust=True, progress=False, threads=True)
        px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        if isinstance(px, pd.Series):
            px = px.to_frame(tickers[0])
        if "Close" in px.columns and len(tickers) == 1:
            px = px[["Close"]].rename(columns={"Close": tickers[0]})
        px = px.dropna(how="all").ffill()
        ok = [t for t in tickers if t in px.columns and px[t].notna().sum() > 60]
        return px[ok], [t for t in tickers if t not in ok]
    except Exception:
        return pd.DataFrame(), list(tickers)


def line_analytics(holdings: dict, line_px: pd.DataFrame, market_px: pd.DataFrame) -> pd.DataFrame:
    """Tableau d'analyse des lignes (poids, risque, tendance, avis)."""
    h = pd.Series({k: float(v) for k, v in holdings.items() if v and float(v) > 0})
    if h.empty:
        return pd.DataFrame()
    w = h / h.sum()
    spy = market_px["SPY"] if "SPY" in market_px else None

    series, source = {}, {}
    for t in w.index:
        cls = A.classify_ticker(t) or "Liquidités"
        if t in line_px.columns:
            series[t], source[t] = line_px[t], "ligne"
        elif cls == "Liquidités":
            series[t], source[t] = None, "cash"
        else:  # pas de cours : on utilise l'ETF représentatif de la classe
            prox = A.CLASS_PROXY[cls]
            series[t] = market_px[prox] if prox in market_px else None
            source[t] = f"proxy {prox}"

    rets = {}
    for t, s in series.items():
        if s is not None:
            rets[t] = np.log(s.dropna()).diff()
    R = pd.DataFrame(rets).dropna(how="all").tail(252).fillna(0.0)
    risky = [t for t in w.index if t in R.columns]
    cov = R[risky].cov() * 252 if risky else pd.DataFrame()

    wr = w.reindex(risky).fillna(0.0)
    port_var = float(wr @ cov @ wr) if risky else 0.0
    mrc = (cov @ wr) if risky else pd.Series(dtype=float)

    rows = []
    for t in w.index:
        cls = A.classify_ticker(t) or "Liquidités"
        s = series[t]
        row = {"Ligne": t, "Classe": cls, "Poids": w[t], "Valeur": h[t], "Source": source[t]}
        if s is not None and len(s.dropna()) > 30:
            s = s.dropna()
            r = np.log(s).diff().dropna().tail(252)
            row["Volatilité"] = float(r.std() * np.sqrt(252))
            row["Perf. 1 mois"] = A._chg(s, 21)
            row["Perf. 3 mois"] = A._chg(s, 63)
            row["Perf. 12 mois"] = A._chg(s, 252) if len(s) > 252 else np.nan
            hi = s.tail(252).max()
            row["Drawdown"] = float(s.iloc[-1] / hi - 1)
            ma = s.rolling(200).mean().iloc[-1] if len(s) > 200 else np.nan
            row["Tendance"] = "Haussière" if np.isfinite(ma) and s.iloc[-1] > ma else (
                "Baissière" if np.isfinite(ma) else "n.d.")
            if spy is not None:
                rs = np.log(spy.dropna()).diff().reindex(r.index)
                ok = rs.notna() & r.notna()
                row["Bêta"] = float(np.cov(r[ok], rs[ok])[0, 1] / rs[ok].var()) if ok.sum() > 30 else np.nan
            row["Contribution au risque"] = (float(wr[t] * mrc[t] / port_var)
                                             if port_var > 0 and t in mrc.index else 0.0)
        else:
            row.update({"Volatilité": 0.0, "Perf. 1 mois": np.nan, "Perf. 3 mois": np.nan,
                        "Perf. 12 mois": np.nan, "Drawdown": 0.0, "Tendance": "n.d.",
                        "Bêta": 0.0, "Contribution au risque": 0.0})
        rows.append(row)
    df = pd.DataFrame(rows).set_index("Ligne")
    df["Avis"], df["Motif"] = zip(*[_line_opinion(r) for _, r in df.iterrows()])
    return df.sort_values("Poids", ascending=False)


def _line_opinion(r) -> tuple[str, str]:
    if r["Classe"] == "Liquidités":
        return "Réserve", "Liquidités / devises"
    reasons, score = [], 0
    rc, w = r.get("Contribution au risque", 0) or 0, r["Poids"]
    if w > 0.20:
        score -= 2
        reasons.append(f"concentration ({w:.0%} du portefeuille)")
    if w > 0 and rc > 1.6 * w and rc > 0.10:
        score -= 1
        reasons.append(f"pèse {rc:.0%} du risque pour {w:.0%} du capital")
    if r.get("Tendance") == "Baissière":
        score -= 1
        reasons.append("sous sa moyenne 200 jours")
    elif r.get("Tendance") == "Haussière":
        score += 1
    p3 = r.get("Perf. 3 mois")
    if p3 is not None and np.isfinite(p3):
        if p3 < -0.10:
            score -= 1
            reasons.append(f"momentum 3 mois négatif ({p3:+.0%})")
        elif p3 > 0.10:
            score += 1
            reasons.append(f"momentum 3 mois positif ({p3:+.0%})")
    dd = r.get("Drawdown", 0) or 0
    if dd < -0.25:
        reasons.append(f"à {dd:.0%} de son plus haut annuel")
    if score <= -2:
        return "Alléger", " ; ".join(reasons)
    if score == -1:
        return "Surveiller", " ; ".join(reasons) or "signaux mitigés"
    if score >= 2 and w < 0.15:
        return "Renforcer", " ; ".join(reasons) or "tendance et momentum favorables"
    return "Conserver", " ; ".join(reasons) or "pas de signal d'alerte"


# ══════════════════════════════════════════════════════════════════════════════
# 4. Plan d'ajustement
# ══════════════════════════════════════════════════════════════════════════════
def _class_tag(cw, tw, c):
    return f"{c} {cw[c]:.0%} vs cible {tw[c]:.0%}"


def trade_plan(lines: pd.DataFrame, target: pd.Series, views: pd.DataFrame, macro,
               band: float = 0.03, mode: str = "Complet", cost_bps: float = 10.0,
               max_line: float = 0.15) -> dict:
    """Ordres ligne par ligne, construits comme le ferait un gérant :
    1) réduire les concentrations ; 2) ramener les classes hors bande vers la cible en
    vendant d'abord les lignes fragiles ; 3) ne jamais ouvrir de position dans une classe
    sur laquelle la vue est négative ; 4) arbitrer les lignes fragiles vers un support
    plus diversifié de la même classe ; 5) regrouper les ordres par ligne."""
    total = float(lines["Valeur"].sum())
    cw = lines.groupby("Classe")["Poids"].sum().reindex(A.CLASSES).fillna(0.0)
    tw = target.reindex(A.CLASSES).fillna(0.0)
    factor = 1.0 if mode == "Complet" else 0.5
    trades, notes, buys = [], [], []
    sold = {t: 0.0 for t in lines.index}          # montants déjà vendus par ligne
    weight_avis = {"Alléger": 3.0, "Surveiller": 2.0, "Conserver": 1.0, "Renforcer": 0.3}

    def add(ordre, ligne, classe, montant, motif, prio, conv):
        trades.append(dict(Ordre=ordre, Ligne=ligne, Classe=classe, Montant=montant,
                           Motif=motif, Priorité=prio, Conviction=conv))

    # 1) Concentration
    for t, r in lines.iterrows():
        if r["Classe"] != "Liquidités" and r["Poids"] > max_line + 0.02:
            amt = (r["Poids"] - max_line) * total
            sold[t] += amt
            add("Alléger", t, r["Classe"], -amt,
                f"Concentration : ramener de {r['Poids']:.0%} à {max_line:.0%} du portefeuille", 1, "Forte")

    # 2) Classes hors bande de tolérance
    for c in A.CLASSES:
        if c == "Liquidités":
            continue  # le cash est le solde des autres ordres
        already = sum(v for t, v in sold.items() if lines.loc[t, "Classe"] == c) / total
        d = (cw[c] - already) - tw[c]
        if abs(d) <= band:
            continue
        amt = abs(d) * factor * total
        view, conv = views.loc[c, "Vue"], views.loc[c, "Conviction"]
        why = views.loc[c, "Arguments"] or "rééquilibrage vers la cible"
        prio = 2 if conv == "Forte" else 3

        if d > 0:  # surpondérée : vendre en priorité les lignes fragiles, au prorata
            cand = lines[lines["Classe"] == c].copy()
            cand["avail"] = (cand["Valeur"] - cand.index.map(sold)) * 0.95
            cand["w"] = cand["avail"] * cand["Avis"].map(weight_avis).fillna(1.0)
            cand = cand[cand["avail"] > 1]
            left = amt
            for _ in range(3):  # répartition avec plafonds, redistribuée si besoin
                if left <= 1 or cand.empty:
                    break
                share = cand["w"] / cand["w"].sum() * left
                for t, x in share.items():
                    x = min(x, cand.loc[t, "avail"])
                    if x <= 1:
                        continue
                    sold[t] += x
                    cand.loc[t, "avail"] -= x
                    left -= x
                    fragile = lines.loc[t, "Avis"] in ("Alléger", "Surveiller")
                    add("Alléger", t, c, -x,
                        f"Classe surpondérée ({_class_tag(cw, tw, c)}) — {why}"
                        + (f" ; ligne fragile : {lines.loc[t, 'Motif']}" if fragile else ""), prio, conv)
                cand = cand[cand["avail"] > 1]
                cand["w"] = cand["avail"] * cand["Avis"].map(weight_avis).fillna(1.0)
        else:      # sous-pondérée : intention d'achat, financée plus bas
            if view == "Sous-pondérer":
                notes.append(f"{c} : sous la cible ({cw[c]:.0%} vs {tw[c]:.0%}) mais vue négative, "
                             "pas d'achat — la sous-pondération est assumée.")
                continue
            buys.append(dict(c=c, amt=amt, conv=conv, prio=prio,
                             motif=f"Classe sous-pondérée ({_class_tag(cw, tw, c)}) — {why}"))

    # 3) Arbitrages intra-classe : ligne fragile non traitée → support diversifié de la classe
    for t, r in lines.iterrows():
        if r["Avis"] == "Alléger" and sold[t] < 0.2 * r["Valeur"] and r["Classe"] != "Liquidités":
            proxy = A.CLASS_PROXY[r["Classe"]]
            if proxy == t:
                continue
            x = r["Valeur"] / 3
            sold[t] += x
            add("Alléger", t, r["Classe"], -x, f"Arbitrage : {r['Motif']}", 2, "Moyenne")
            add("Acheter", proxy, r["Classe"], x,
                f"Arbitrage intra-classe : même exposition « {r['Classe']} », risque spécifique réduit", 2, "Moyenne")

    # 4) Financement des achats : on n'achète qu'avec les liquidités disponibles
    #    au-dessus de la cible de cash (ventes du plan comprises)
    if buys:
        cash_now = cw["Liquidités"] * total + sum(-t["Montant"] for t in trades)
        available = cash_now - tw["Liquidités"] * total
        wanted = sum(b["amt"] for b in buys)
        scale = 0.0 if available <= 0 else min(1.0, available / wanted)
        if scale < 0.999:
            notes.append(f"Achats ramenés à {scale:.0%} des besoins : ils sont financés uniquement par les "
                         "ventes et l'excédent de liquidités, sans descendre sous la cible de cash.")
        for b in buys:
            amt = b["amt"] * scale
            if amt < 0.005 * total:
                continue
            c, proxy = b["c"], A.CLASS_PROXY[b["c"]]
            held = lines[(lines["Classe"] == c) & (lines["Avis"].isin(["Renforcer", "Conserver"]))
                         & (lines["Poids"] < max_line)]
            if len(held):
                best = held.sort_values("Perf. 3 mois", ascending=False, na_position="last").index[0]
                add("Renforcer", best, c, amt * 0.5, b["motif"], b["prio"], b["conv"])
                add("Acheter", proxy, c, amt * 0.5, "Diversification de la classe via un ETF large",
                    b["prio"], b["conv"])
            else:
                add("Acheter", proxy, c, amt, b["motif"], b["prio"], b["conv"])

    df = pd.DataFrame(trades)
    if df.empty:
        msg = ("Aucun ajustement nécessaire : toutes les classes sont dans leur bande de tolérance "
               f"(±{band:.0%}) et aucune ligne n'est en alerte.")
        return dict(trades=df, turnover=0.0, cost=0.0, cash_flow=0.0, after=cw, total=total,
                    timing=msg, notes=notes)

    # Regroupement : un seul ordre par ligne et par sens
    df["Sens"] = np.sign(df["Montant"])
    order_rank = {"Alléger": 0, "Renforcer": 1, "Acheter": 2}
    g = []
    for (ligne, sens), grp in df.groupby(["Ligne", "Sens"]):
        grp = grp.sort_values("Priorité")
        montant = grp["Montant"].sum()
        ordre = grp["Ordre"].iloc[0]
        if sens < 0 and ligne in lines.index and -montant >= 0.97 * lines.loc[ligne, "Valeur"]:
            ordre = "Vendre en totalité"
        motifs = list(dict.fromkeys(grp["Motif"]))
        g.append(dict(Ordre=ordre, Ligne=ligne, Classe=grp["Classe"].iloc[0], Montant=montant,
                      Priorité=int(grp["Priorité"].min()), Conviction=grp["Conviction"].iloc[0],
                      Motif=" | ".join(motifs), _r=order_rank.get(grp["Ordre"].iloc[0], 3)))
    df = pd.DataFrame(g).sort_values(["Priorité", "_r", "Montant"]).drop(columns="_r").reset_index(drop=True)
    df["% du portefeuille"] = df["Montant"] / total

    after = cw.copy()
    for _, r in df.iterrows():
        after[r["Classe"]] += r["Montant"] / total
    cash_flow = -df["Montant"].sum()
    after["Liquidités"] += cash_flow / total

    turnover = df["Montant"].abs().sum() / total / 2
    cost = df["Montant"].abs().sum() * cost_bps / 1e4
    stressed = macro.factors["stress"] > 1.0 or macro.factors["geopolitique"] > 1.2
    if stressed:
        timing = ("Marché sous tension : exécuter d'abord les réductions de risque (priorité 1), "
                  "puis étaler les achats en 3 tranches sur 2 à 3 semaines pour lisser le point d'entrée.")
    elif turnover > 0.15:
        timing = ("Rotation importante : exécuter en 2 tranches sur une à deux semaines, ventes avant "
                  "achats, pour limiter l'impact et le risque d'exécution.")
    else:
        timing = "Rotation modérée : exécution possible en une fois, ventes avant achats."
    if cash_flow > 0.02 * total:
        timing += f" Les ventes nettes ({cash_flow / total:.0%}) renforcent la poche de liquidités."
    elif cash_flow < -0.02 * total:
        timing += f" Les achats nets ({-cash_flow / total:.0%}) sont financés par les liquidités."
    return dict(trades=df, turnover=turnover, cost=cost, cash_flow=cash_flow, after=after,
                total=total, timing=timing, notes=notes)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Déclencheurs de révision
# ══════════════════════════════════════════════════════════════════════════════
def revision_triggers(macro, news: dict) -> list[str]:
    ind, f = macro.indicators, macro.factors
    out = []
    vix = ind.get("vix")
    if vix and np.isfinite(vix):
        lvl = 30 if vix < 25 else max(35, round(vix + 5))
        out.append(f"VIX au-dessus de {lvl} (actuellement {vix:.0f}) → passage en mode défensif : "
                   "+5 pts de liquidités, réduction des actions et du high yield.")
        if vix > 22:
            out.append(f"VIX qui revient sous 18 → réinvestir progressivement les liquidités en actions.")
    curve = ind.get("curve_10y_3m")
    if curve is not None and np.isfinite(curve):
        if curve < 0:
            out.append(f"Courbe 10 ans – 3 mois qui se ré-pentifie au-dessus de +0,5 pt "
                       f"(actuellement {curve:+.2f}) → signal classique de fin de cycle : allonger la "
                       "duration obligataire, rester sélectif sur les actions cycliques.")
        else:
            out.append(f"Courbe qui s'inverse à nouveau (sous 0, actuellement {curve:+.2f}) → "
                       "réduire les cycliques, renforcer obligations d'État et qualité.")
    trend = ind.get("spy_vs_ma200")
    if trend is not None and np.isfinite(trend):
        if trend > 0:
            out.append("S&P 500 qui clôture sous sa moyenne 200 jours → réduire le bêta du portefeuille.")
        else:
            out.append("S&P 500 qui repasse au-dessus de sa moyenne 200 jours → réduire la sous-pondération actions.")
    if news["conflits"]["intensity"] < 70:
        out.append("Intensité des actualités « conflits armés » au-dessus de 70/100 → renforcer l'or, "
                   "réduire actions européennes et émergentes.")
    else:
        out.append("Désescalade confirmée (actualités « conflits » sous 40/100) → réduire la couverture en or.")
    out.append("Pétrole en hausse de plus de 15 % sur un mois → renforcer matières premières, "
               "réduire obligations longues (risque d'inflation).")
    if f["monetaire"] > 0.5:
        out.append("Premier signal de baisse des taux directeurs → allonger la duration, renforcer actions de croissance.")
    else:
        out.append("Retour d'un discours restrictif des banques centrales → raccourcir la duration.")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# 6. Note de gestion
# ══════════════════════════════════════════════════════════════════════════════
def _p(x):
    return "n.d." if x is None or not np.isfinite(x) else f"{x:.0%}"


def investment_note(name: str, profile: str, macro, hist: pd.DataFrame, moves: list,
                    since_review: list, views: pd.DataFrame, lines: pd.DataFrame, plan: dict,
                    stress: pd.Series, vol_now: float, vol_after: float, triggers: list,
                    data_simulated: bool) -> str:
    d = datetime.now()
    alerts = lines[lines["Avis"].isin(["Alléger", "Surveiller"])]
    ow = views[views["Vue"] == "Surpondérer"].sort_values("Score", ascending=False)
    uw = views[views["Vue"] == "Sous-pondérer"].sort_values("Score")
    tr = plan["trades"]

    # Synthèse en 3 phrases
    if tr.empty:
        action = "Le portefeuille reste dans ses bandes de tolérance : nous recommandons de conserver le positionnement."
    else:
        sells = list(dict.fromkeys(tr[tr["Montant"] < 0].sort_values("Montant")["Ligne"]))
        buys = list(dict.fromkeys(tr[tr["Montant"] > 0].sort_values("Montant", ascending=False)["Ligne"]))
        action = (f"Nous recommandons une rotation de {plan['turnover']:.0%} du portefeuille"
                  + (f", en allégeant {', '.join(sells[:3])}" if sells else "")
                  + (f" et en renforçant {', '.join(buys[:3])}" if buys else "") + ".")
    risk_line = (f"La volatilité estimée passerait de {vol_now:.1%} à {vol_after:.1%} ; "
                 f"le scénario le plus pénalisant reste « {stress.index[0]} » ({stress.iloc[0]:+.0%}).")

    L = [f"# Note de gestion — {name}",
         f"*Revue du {d:%d/%m/%Y} · profil {profile} · régime : **{macro.regime}***",
         ""]
    if data_simulated:
        L += ["> ⚠️ Données de marché partiellement simulées : recommandations à faible conviction, "
              "à ne pas exécuter en l'état.", ""]
    L += ["## 1. Synthèse", f"{macro.regime_text} {action} {risk_line}", ""]

    L += ["## 2. Contexte et évolution"]
    if "Il y a 1 mois" in hist.columns:
        reg_then = hist.loc["Régime", "Il y a 3 mois"] if "Il y a 3 mois" in hist.columns else None
        if reg_then and reg_then != macro.regime:
            L.append(f"- Le régime est passé de **{reg_then}** (il y a 3 mois) à **{macro.regime}**.")
    for mv in moves[:4]:
        L.append(f"- {describe_move(mv)}")
    if not moves:
        L.append("- Pas de changement marqué des facteurs sur le dernier mois : le contexte est stable.")
    if since_review:
        L.append("- **Depuis votre dernière revue** : " + " ; ".join(since_review) + ".")
    for k in sorted(A.F_KEYS, key=lambda k: -abs(macro.factors[k]))[:3]:
        L.append(f"- {A.FACTORS[k][0]} ({macro.factors[k]:+.1f}) : " + " ; ".join(macro.evidence[k][:2]) + ".")
    L.append("")

    L += ["## 3. Nos vues par classe d'actifs"]
    for c, r in ow.iterrows():
        L.append(f"- **Surpondérer {c}** (conviction {r['Conviction'].lower()}) : {r['Arguments']}.")
    for c, r in uw.iterrows():
        L.append(f"- **Sous-pondérer {c}** (conviction {r['Conviction'].lower()}) : {r['Arguments']}.")
    if ow.empty and uw.empty:
        L.append("- Pas de conviction tactique marquée : allocation proche de la stratégique.")
    L.append("")

    L += ["## 4. Diagnostic du portefeuille"]
    cw = lines.groupby("Classe")["Poids"].sum().sort_values(ascending=False)
    L.append("- Répartition : " + ", ".join(f"{c} {w:.0%}" for c, w in cw.items() if w > 0.005) + ".")
    top_risk = lines.sort_values("Contribution au risque", ascending=False).head(3)
    L.append("- Principales sources de risque : " + ", ".join(
        f"{t} ({r['Contribution au risque']:.0%} du risque pour {r['Poids']:.0%} du capital)"
        for t, r in top_risk.iterrows() if r["Contribution au risque"] > 0) + ".")
    for t, r in alerts.iterrows():
        L.append(f"- **{t}** — {r['Avis'].lower()} : {r['Motif']}.")
    L.append("")

    L += ["## 5. Recommandations et plan d'exécution"]
    if tr.empty:
        L.append(f"- {plan['timing']}")
    else:
        for _, r in tr.iterrows():
            amt = f"{r['Montant']:+,.0f}".replace(",", " ")
            L.append(f"- P{r['Priorité']} · **{r['Ordre']} {r['Ligne']}** : {amt} "
                     f"({r['% du portefeuille']:+.1%}) — conviction {r['Conviction'].lower()}. {r['Motif']}.")
        cost = f"{plan['cost']:,.0f}".replace(",", " ")
        L.append(f"- Rotation : {plan['turnover']:.1%} · coûts estimés : {cost} · {plan['timing']}")
    for n in plan.get("notes", []):
        L.append(f"- *{n}*")
    L.append("")

    L += ["## 6. Risques et scénarios"]
    for sc, v in stress.head(3).items():
        L.append(f"- {sc} : {v:+.1%} sur le portefeuille actuel.")
    L.append("")

    L += ["## 7. Déclencheurs de révision"]
    L += [f"- {x}" for x in triggers]
    L += ["", "---", "*Note générée par le Hedge Fund Agent de McKenson Asset Management. "
                     "Outil pédagogique d'aide à la décision sur une plateforme de simulation : "
                     "ne constitue pas un conseil en investissement.*"]
    return "\n".join(L)


def llm_rewrite_note(note_md: str) -> str:
    """Reformulation de la note par le LLM configuré (sans ajouter de chiffres)."""
    prompt = ("Tu es gérant de portefeuille senior. Réécris la note de gestion ci-dessous dans un "
              "style professionnel de comité d'investissement, en français, en gardant EXACTEMENT "
              "les mêmes chiffres, ordres et recommandations, sans en ajouter. Garde la structure en "
              "sections Markdown et la mention finale. Note :\n\n" + note_md)
    return _llm_raw(prompt)


def _llm_raw(prompt: str) -> str:
    import requests
    cfg = st.secrets["llm"]
    if cfg.get("provider", "groq").lower() == "gemini":
        model = cfg.get("model", "gemini-3.5-flash-lite")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": cfg["api_key"]}, timeout=60,
            json={"contents": [{"parts": [{"text": prompt}]}]})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    model = cfg.get("model", "llama-3.3-70b-versatile")
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=60,
                      headers={"Authorization": f"Bearer {cfg['api_key']}"},
                      json={"model": model, "temperature": 0.2,
                            "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


# ══════════════════════════════════════════════════════════════════════════════
# 7. Revue complète
# ══════════════════════════════════════════════════════════════════════════════
def last_review_for(journal: list, name: str) -> dict | None:
    rev = [e for e in journal if e.get("type") == "revue" and e.get("portefeuille") == name]
    return rev[-1] if rev else None


def full_review(name: str, holdings: dict, profile: str, ctx: tuple, journal: list | None = None,
                band: float = 0.03, mode: str = "Complet", max_line: float = 0.15) -> dict:
    px, missing, news, news_sim, macro, cov, data_sim = ctx
    target_raw = A.propose_allocation(macro.factors, profile)["Proposée (avant risque)"]
    target, checks, allowed = A.risk_engine(target_raw, profile, macro.factors, cov, data_sim)

    line_px, line_missing = load_line_prices(tuple(sorted(holdings)))
    lines = line_analytics(holdings, line_px, px)
    views = class_views(macro, target, profile, data_sim)
    plan = trade_plan(lines, target, views, macro, band=band, mode=mode, max_line=max_line)

    hist = factor_history(px, news)
    moves = factor_moves(hist)
    last = last_review_for(journal or [], name)
    since = changes_since_review(macro, last)

    cls_now = lines.groupby("Classe")["Poids"].sum().reindex(A.CLASSES).fillna(0)
    vol_now, vol_after = A.port_vol(cls_now, cov), A.port_vol(plan["after"].clip(lower=0), cov)
    stress = A.stress_test(cls_now)
    trig = revision_triggers(macro, news)
    note = investment_note(name, profile, macro, hist, moves, since, views, lines, plan, stress,
                           vol_now, vol_after, trig, data_sim)
    return dict(target=target, lines=lines, line_missing=line_missing, views=views, plan=plan,
                hist=hist, moves=moves, last_review=last, since=since, vol_now=vol_now,
                vol_after=vol_after, stress=stress, stress_after=A.stress_test(plan["after"].clip(lower=0)),
                triggers=trig, note=note, macro=macro, data_sim=data_sim)
