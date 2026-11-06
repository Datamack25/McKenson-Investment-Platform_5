# components/core_params_ui.py  —  MAM v5.12 · Admin → « 🧮 PARAMÈTRES FINANCIERS »
"""L'administrateur intervient sur le cœur de la plateforme en tant que financier : ratios et seuils, formules,
scénarios (probabilités, impacts par secteur, remédiation), catalyseurs, plafonds personnels.
Chaque valeur est bornée, chaque modification est tracée, et tout se remet par défaut en un clic."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from utils import core_params as CP


def _who() -> str:
    return (st.session_state.get("mam_user") or {}).get("username") or "admin"


def _persist_note():
    if CP.PERSIST.get("ok") is False:
        st.warning("Enregistré pour cette session du serveur uniquement : la base de données est indisponible. "
                   "Exportez la configuration (onglet Historique) pour la conserver.")


def render():
    st.markdown("#### 🧮 Paramètres financiers — le cœur de la plateforme, ajusté par votre jugement d'expert")
    st.caption("Les valeurs par défaut restent le socle. Vos surcharges s'appliquent à l'Analyse Marché, aux scénarios, "
               "aux alertes de grosse perte, aux diagnostics de couverture et aux rapports (qui le mentionnent).")
    keys = CP.custom_keys()
    if keys:
        st.info(f"🧮 {len(keys)} paramètre(s) personnalisé(s) actif(s) : {', '.join(keys[:12])}{' …' if len(keys) > 12 else ''}")
    t1, t2, t3, t4, t6, t7, t5 = st.tabs(["📐 RATIOS & SEUILS", "🧪 FORMULES", "🎲 SCÉNARIOS", "⚡ CATALYSEURS",
                                          "🧊 LIGNES FIGÉES", "🧩 COMPOSITIONS", "📜 HISTORIQUE & EXPORT"])
    with t1:
        _values_tab()
    with t2:
        _formulas_tab()
    with t3:
        _scenarios_tab()
    with t4:
        _catalysts_tab()
    with t6:
        _frozen_tab()
    with t7:
        _compositions_tab()
    with t5:
        _history_tab()


def _values_tab():
    groups: dict[str, list[str]] = {}
    for k, p in CP.PARAMS.items():
        groups.setdefault(p["group"], []).append(k)
    changes = {}
    with st.form("cp_values"):
        for g, ks in groups.items():
            st.markdown(f"**{g}**")
            cols = st.columns(3)
            for i, k in enumerate(ks):
                p, cur = CP.PARAMS[k], CP.get(k)
                lab = p["label"] + (" ✱" if cur != p["default"] else "")
                hint = f"Défaut : {p['default']:.1%}" if p["kind"] == "pct" else f"Défaut : {p['default']:g}"
                with cols[i % 3]:
                    if p["kind"] == "pct":
                        v = st.number_input(lab + " (%)", min_value=float(p["min"] * 100), max_value=float(p["max"] * 100),
                                            value=float(cur * 100), step=float(p["step"] * 100), help=hint, key=f"cp_{k}")
                        changes[k] = v / 100
                    elif p["kind"] == "int":
                        changes[k] = st.number_input(lab, min_value=int(p["min"]), max_value=int(p["max"]), value=int(cur),
                                                     step=int(p["step"]), help=hint, key=f"cp_{k}")
                    else:
                        changes[k] = st.number_input(lab, min_value=float(p["min"]), max_value=float(p["max"]),
                                                     value=float(cur), step=float(p["step"]), help=hint, key=f"cp_{k}")
        c1, c2 = st.columns(2)
        save = c1.form_submit_button("💾 Enregistrer les paramètres", type="primary", use_container_width=True)
        reset = c2.form_submit_button("↩️ Revenir aux valeurs par défaut", use_container_width=True)
    if save:
        diff = {k: v for k, v in changes.items() if abs(float(v) - float(CP.get(k))) > 1e-12}
        if not diff:
            st.info("Aucune modification.")
        else:
            ok, errs = CP.set_values(diff, _who())
            if ok:
                st.success(f"{len(diff)} paramètre(s) mis à jour.")
                _persist_note()
            for e in errs:
                st.error(e)
    if reset:
        CP.reset("values", _who())
        st.success("Valeurs par défaut rétablies.")
        st.rerun()
    st.caption("✱ = valeur personnalisée. Les seuils sont contrôlés : bornes de chaque paramètre et cohérence "
               "(z-score stable < norme < fort < exceptionnel, RSI survente < surachat, moyenne courte < longue).")


def _formulas_tab():
    f = CP.FORMULAS["vol_methode"]
    cur = CP.formula("vol_methode")
    v = st.radio(f["label"], f["choices"], index=f["choices"].index(cur), horizontal=True, help=f["help"], key="cp_volm")
    if v != cur and st.button("💾 Appliquer la méthode de volatilité", key="cp_volm_save"):
        ok, errs = CP.set_formula("vol_methode", v, _who())
        if ok:
            st.success("Méthode appliquée.")
        for e in errs:
            st.error(e)
    st.divider()
    f = CP.FORMULAS["score_scenario"]
    st.markdown(f"**{f['label']}**")
    st.caption(f["help"])
    expr = st.text_area("Formule", CP.formula("score_scenario"), height=90, key="cp_expr")
    err = CP.check_expression(expr)
    if err:
        st.error(err)
    else:
        from utils import scenarios as SC
        demo = {"momentum": -0.8, "tendance": -0.6, "rsi": 0.3, "peur": -0.7, "credit": -0.3, "sentiment": -0.4,
                "intraday": -0.5, "catalyseurs": SC.catalyst_score()}
        s = SC.score(demo, expr)
        p = SC.probabilities(s)
        st.success(f"Formule valide. Exemple (séance de stress) : score {s:+.2f} → haussier {p['haussier']:.0%}, "
                   f"central {p['central']:.0%}, baissier {p['baissier']:.0%}.")
    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer la formule", disabled=bool(err), type="primary", key="cp_expr_save",
                 use_container_width=True):
        ok, errs = CP.set_formula("score_scenario", expr, _who())
        if ok:
            st.success("Formule enregistrée.")
            _persist_note()
        for e in errs:
            st.error(e)
    if c2.button("↩️ Formule par défaut", key="cp_expr_reset", use_container_width=True):
        CP.set_formula("score_scenario", f["default"], _who())
        CP.set_formula("vol_methode", CP.FORMULAS["vol_methode"]["default"], _who())
        st.rerun()
    st.caption("Évaluation sécurisée : seuls les nombres, les opérateurs + − × ÷ ^ et les fonctions listées sont acceptés ; "
               "aucun code n'est exécuté.")


def _scenarios_tab():
    scs = CP.scenarios()
    st.caption("Probabilité a priori = point de départ avant les signaux de marché. « Probabilité forcée » (facultative) "
               "fixe la valeur à la main ; si vous les forcez toutes, elles doivent totaliser 100 %.")
    head = pd.DataFrame([{"id": s["id"], "Scénario": s["nom"], "A priori (%)": float(s["prior"]) * 100,
                          "Forcée (%)": None if s.get("prob_forcee") in (None, "") else float(s["prob_forcee"]) * 100,
                          "Description": s["description"]} for s in scs])
    ed = st.data_editor(head, hide_index=True, use_container_width=True, disabled=["id"], key="cp_sc_head",
                        column_config={"A priori (%)": st.column_config.NumberColumn(min_value=1, max_value=98, step=1),
                                       "Forcée (%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=1)})
    st.markdown("**Impact attendu par secteur / actif (%)**")
    imp = pd.DataFrame({s["id"]: [s["impacts"].get(sec, 0.0) for sec in CP.SECTORS] for s in scs}, index=CP.SECTORS)
    imp.index.name = "Secteur / actif"
    ed_imp = st.data_editor(imp, use_container_width=True, key="cp_sc_imp",
                            column_config={s["id"]: st.column_config.NumberColumn(s["nom"].split(" — ")[0], min_value=-80,
                                                                                  max_value=80, step=0.5) for s in scs})
    st.markdown("**Plans de remédiation (une action par ligne)**")
    rem = {}
    cols = st.columns(len(scs))
    for c, s in zip(cols, scs):
        rem[s["id"]] = c.text_area(s["nom"].split(" — ")[0], "\n".join(s.get("remediation") or []), height=220,
                                   key=f"cp_rem_{s['id']}")
    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer les scénarios", type="primary", key="cp_sc_save", use_container_width=True):
        out = []
        for _, r in ed.iterrows():
            sid = r["id"]
            forced = r["Forcée (%)"]
            out.append(dict(id=sid, nom=r["Scénario"], prior=float(r["A priori (%)"]) / 100,
                            prob_forcee=None if pd.isna(forced) else float(forced) / 100, description=r["Description"],
                            impacts={sec: float(ed_imp.loc[sec, sid]) for sec in ed_imp.index},
                            remediation=[x.strip() for x in rem[sid].splitlines() if x.strip()]))
        tot = sum(x["prior"] for x in out)
        for x in out:   # les a priori sont renormalisés à 100 %
            x["prior"] = x["prior"] / tot if tot else x["prior"]
        ok, errs = CP.set_scenarios(out, _who())
        if ok:
            st.success("Scénarios enregistrés (probabilités a priori ramenées à 100 %).")
            _persist_note()
        for e in errs:
            st.error(e)
    if c2.button("↩️ Scénarios par défaut", key="cp_sc_reset", use_container_width=True):
        CP.reset("scenarios", _who())
        st.rerun()


def _catalysts_tab():
    st.caption("Vos hypothèses qualitatives : ce qui peut faire monter (sens +1) ou baisser (sens −1) le marché, avec votre "
               "probabilité de survenue et sa force (0 à 1). Elles entrent dans le score des scénarios et dans « ce qui "
               "pourrait faire basculer ».")
    df = pd.DataFrame(CP.catalysts())
    df["proba"] = df["proba"].astype(float) * 100
    ed = st.data_editor(df.rename(columns={"nom": "Catalyseur", "proba": "Probabilité (%)", "sens": "Sens",
                                           "force": "Force", "actif": "Actif"}),
                        num_rows="dynamic", hide_index=True, use_container_width=True, key="cp_cat",
                        column_config={"Probabilité (%)": st.column_config.NumberColumn(min_value=0, max_value=100, step=1),
                                       "Sens": st.column_config.SelectboxColumn(options=[1, -1]),
                                       "Force": st.column_config.NumberColumn(min_value=0.0, max_value=1.0, step=0.05),
                                       "Actif": st.column_config.CheckboxColumn()})
    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer les catalyseurs", type="primary", key="cp_cat_save", use_container_width=True):
        rows = []
        for _, r in ed.iterrows():
            if pd.isna(r.get("Catalyseur")) or not str(r.get("Catalyseur")).strip():
                continue
            rows.append(dict(nom=r["Catalyseur"], proba=float(r["Probabilité (%)"] or 0) / 100, sens=int(r["Sens"] or 1),
                             force=float(r["Force"] if not pd.isna(r["Force"]) else 0.5),
                             actif=bool(r["Actif"]) if not pd.isna(r["Actif"]) else True))
        ok, errs = CP.set_catalysts(rows, _who())
        if ok:
            st.success(f"{len(rows)} catalyseur(s) enregistré(s).")
            _persist_note()
        for e in errs:
            st.error(e)
    if c2.button("↩️ Catalyseurs par défaut", key="cp_cat_reset", use_container_width=True):
        CP.reset("catalysts", _who())
        st.rerun()


def _history_tab():
    h = CP.history()
    if h:
        st.dataframe(pd.DataFrame(h).rename(columns={"date": "Date", "qui": "Par", "cle": "Clé", "libelle": "Paramètre",
                                                     "avant": "Avant", "apres": "Après"}),
                     hide_index=True, use_container_width=True, height=320)
    else:
        st.caption("Aucune modification enregistrée : la plateforme utilise ses valeurs par défaut.")
    st.download_button("⬇️ Exporter la configuration (JSON)", CP.export_json(), "mam_parametres_financiers.json",
                       "application/json", key="cp_export")
    up = st.file_uploader("Importer une configuration (JSON)", type=["json"], key="cp_import")
    if up is not None and st.button("Importer", key="cp_import_go"):
        ok, errs = CP.import_json(up.read().decode("utf-8"), _who())
        if ok:
            st.success("Configuration importée.")
        for e in errs:
            st.error(e)
    st.divider()
    if st.button("☢️ Tout remettre par défaut (valeurs, formules, scénarios, catalyseurs)", key="cp_reset_all"):
        CP.reset("all", _who())
        st.success("Cœur de la plateforme remis par défaut.")
        st.rerun()


def _frozen_tab():
    st.caption("Lignes que vous décidez de ne pas toucher (conviction, fiscalité, contrainte personnelle). Le comité ne "
               "propose ni vente ni achat sur ces lignes, mais tient compte de leur exposition pour ajuster le reste du "
               "portefeuille. Portefeuille « * » = tous les portefeuilles.")
    df = pd.DataFrame(CP.frozen() or [dict(ticker="", portefeuille="*", raison="")])
    ed = st.data_editor(df.rename(columns={"ticker": "Ticker", "portefeuille": "Portefeuille", "raison": "Raison"}),
                        num_rows="dynamic", hide_index=True, use_container_width=True, key="cp_frozen")
    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer les lignes figées", type="primary", key="cp_frozen_save", use_container_width=True):
        rows = [dict(ticker=r["Ticker"], portefeuille=r["Portefeuille"], raison=r["Raison"]) for _, r in ed.iterrows()
                if isinstance(r.get("Ticker"), str) and r["Ticker"].strip()]
        ok, errs = CP.set_frozen(rows, _who())
        if ok:
            st.success(f"{len(rows)} ligne(s) figée(s).")
            _persist_note()
        for e in errs:
            st.error(e)
    if c2.button("↩️ Aucune ligne figée", key="cp_frozen_reset", use_container_width=True):
        CP.reset("frozen", _who())
        st.rerun()


def _compositions_tab():
    st.caption("Ventilation sectorielle utilisée par le stress des scénarios pour les ETF et indices larges (SPY, VOO, "
               "IWDA… pour le S&P 500 ; QQQ, PANX… pour le Nasdaq 100). Les lignes non classées sont traitées comme le "
               "S&P 500. Les poids de chaque colonne doivent totaliser 100 %.")
    comp = CP.compositions()
    df = pd.DataFrame({k: [comp[k].get(sec, 0.0) * 100 for sec in CP.SECTORS] for k in CP.COMPOSITION_KEYS},
                      index=CP.SECTORS)
    df.index.name = "Secteur / actif"
    ed = st.data_editor(df, use_container_width=True, key="cp_comp",
                        column_config={k: st.column_config.NumberColumn(lab + " (%)", min_value=0, max_value=100, step=0.5)
                                       for k, lab in CP.COMPOSITION_KEYS.items()})
    st.caption(" · ".join(f"{lab} : {ed[k].sum():.1f} %" for k, lab in CP.COMPOSITION_KEYS.items()))
    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer les compositions", type="primary", key="cp_comp_save", use_container_width=True):
        ok, errs = CP.set_compositions({k: {sec: float(ed.loc[sec, k]) / 100 for sec in ed.index}
                                        for k in CP.COMPOSITION_KEYS}, _who())
        if ok:
            st.success("Compositions enregistrées.")
            _persist_note()
        for e in errs:
            st.error(e)
    if c2.button("↩️ Compositions par défaut", key="cp_comp_reset", use_container_width=True):
        CP.reset("compositions", _who())
        st.rerun()
