# pages/smart_money.py  —  MAM v5.11 · « 🐋 Tracking Best AM »
"""
Où et comment investissent les meilleurs gérants (formulaires 13F de la SEC, mêmes données que Dataroma,
WhaleWisdom ou TIKR) ; comparaison avec les portefeuilles MIP ; analyse et interprétation du comité ;
rapports d'analyse sectorielle (PDF avec graphiques, Excel).
"""
from __future__ import annotations

import html as _h
from datetime import datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from components import smart_money_ui as UI
from components.ai_shared import PLOT, kpi, kpi_row, page_header
from components.ui import section_title
from utils import smart_money as SM


def render():
    page_header("🐋 TRACKING BEST AM", "Où investissent les meilleurs gérants (13F · SEC) · consensus et mouvements · "
                "secteurs · comparaison avec vos portefeuilles · analyse du comité · rapports", "#00d4ff")
    UI.limits_box()
    snap, codes = UI.loader("sm")
    if not snap:
        st.info("Chargez les formulaires 13F des gérants (bouton 📡 ci-dessus) ou importez un fichier pour commencer.")
        _tab_platforms()
        return
    tabs = st.tabs(["🔥 CONSENSUS & MOUVEMENTS", "📋 DÉTENUS · VENDUS · ÉQUIVALENTS", "🏛️ GÉRANTS", "🏭 SECTEURS",
                    "⚖️ MON PORTEFEUILLE VS GÉRANTS", "🧠 ANALYSE DU COMITÉ", "📄 RAPPORTS", "🔗 PLATEFORMES & MÉTHODE"])
    with tabs[0]:
        _tab_consensus(snap, codes)
    with tabs[1]:
        _tab_assets(snap, codes)
    tabs = tabs[1:]      # les onglets suivants gardent leur numérotation d'origine
    with tabs[1]:
        _tab_managers(snap, codes)
    with tabs[2]:
        _tab_sectors(snap, codes)
    with tabs[3]:
        section_title("COMPARER MES PORTEFEUILLES AUX ALLOCATIONS DES MEILLEURS GÉRANTS", "⚖️")
        UI.render_comparison(snap, codes, "smp", _imported())
    with tabs[4]:
        _tab_committee(snap, codes)
    with tabs[5]:
        _tab_reports(snap, codes)
    with tabs[6]:
        _tab_platforms()


def _imported() -> dict:
    """Portefeuille importé dans « Conseil portefeuille » (s'il existe) : comparable lui aussi."""
    res = st.session_state.get("upa_res")
    if not res or not res.get("ok"):
        return {}
    vals = dict(zip(res["lignes"]["Ticker"], res["lignes"]["Valeur"]))
    return {"fichier": (f"📥 Fichier importé · {res.get('fichier', '')}", dict(values=vals, cash=res.get("cash", 0.0)))}


# ─────────────────────────────────────────────────────────────────────────────
def _tab_consensus(snap, codes):
    section_title("ACTUELLEMENT : OÙ INVESTISSENT LES MEILLEURS GÉRANTS", "🔥")
    UI.top5_cards(snap, codes)
    cs = SM.consensus(snap, codes)
    if cs.empty:
        return
    perf = UI.perf_since(snap, codes, 25)
    cs = cs.copy()
    cs["Depuis la fin du trimestre"] = cs["Titre"].map(perf)
    c1, c2 = st.columns([1.25, 1])
    with c1:
        st.markdown("**Consensus : les titres les plus partagés**")
        show = cs.head(40)[["Titre", "Secteur", "Gérants", "Poids dans la moyenne des gérants", "Poids max", "Nouvelles",
                            "Renforcées", "Allégées", "Soldées", "Depuis la fin du trimestre", "Score"]]
        st.dataframe(show.style.format({"Poids dans la moyenne des gérants": "{:.2%}", "Poids max": "{:.1%}",
                                        "Depuis la fin du trimestre": "{:+.1%}", "Score": "{:.0f}"}, na_rep="—"),
                     hide_index=True, use_container_width=True, height=470)
    with c2:
        top = cs.head(40)
        fig = px.scatter(top, x="Gérants", y=top["Poids moyen (détenteurs)"] * 100, size="Valeur totale ($)",
                         color="Secteur", text="Titre", color_discrete_map=SM.SECTOR_COLORS, size_max=38,
                         hover_data={"Détenu par": True})
        fig.update_traces(textposition="top center", textfont_size=9)
        fig.update_layout(**PLOT, height=470, title="Partage (nb de gérants) × conviction (poids chez les détenteurs, %)",
                          legend=dict(font=dict(size=9)))
        st.plotly_chart(fig, use_container_width=True, key="sm_bubble")
    st.caption("Score = 45 % part des gérants qui détiennent le titre + 40 % poids dans l'allocation moyenne + 15 % achats "
               "nets du trimestre. « Depuis la fin du trimestre » : variation du cours depuis la date des positions déclarées.")

    section_title("LES 4 FILTRES DE LA MÉTHODE 13F", "🎯")
    sg = SM.signals(snap, codes)
    ren = {"fund": "Gérant", "label": "Titre", "sector": "Secteur", "weight": "Poids", "d_weight": "Δ poids",
           "status": "Mouvement", "rank": "Rang"}
    a, b = st.columns(2)
    with a:
        st.markdown("**① Convictions : positions ≥ 5 % d'un portefeuille**")
        st.dataframe(sg["conviction"].rename(columns=ren).style.format({"Poids": "{:.1%}", "Δ poids": "{:+.1%}"}, na_rep="—"),
                     hide_index=True, use_container_width=True, height=260)
        st.markdown("**③ Nouvelles positions entrées directement dans le top 10**")
        st.dataframe(sg["new_top10"].rename(columns=ren).style.format({"Poids": "{:.1%}", "Δ poids": "{:+.1%}"}, na_rep="—"),
                     hide_index=True, use_container_width=True, height=220)
    with b:
        st.markdown("**② Achats groupés : au moins 2 gérants le même trimestre**")
        st.dataframe(sg["cluster"].rename(columns={"Poids_moyen": "Poids moyen"}).style.format({"Poids moyen": "{:.1%}"}),
                     use_container_width=True, height=260)
        st.markdown("**④ Fortes hausses de poids (≥ 2 points)**")
        st.dataframe(sg["big_increase"].rename(columns=ren).style.format({"Poids": "{:.1%}", "Δ poids": "{:+.1%}"}, na_rep="—"),
                     hide_index=True, use_container_width=True, height=220)


# ─────────────────────────────────────────────────────────────────────────────
def _tab_assets(snap, codes):
    """Les plus détenus, les plus vendus (depuis quand, en quelle proportion) et comment investir dans les mêmes actifs."""
    hq = max((len((m.get("history") or {}).get("periods") or []) for m in snap["managers"].values()), default=0)
    st.caption(f"Historique disponible : {hq} trimestre(s) par gérant" + (" — « avant T… » signifie que la position était "
               "déjà là au début de l'historique (augmentez l'historique au chargement pour remonter plus loin)." if hq else
               " (import de fichier : pas d'historique, « depuis » = trimestre déclaré)."))
    section_title("LES ACTIFS LES PLUS DÉTENUS — DEPUIS QUAND, EN QUELLE PROPORTION", "💎")
    mh = SM.most_held(snap, codes, 30)
    if len(mh):
        st.dataframe(mh.drop(columns=["Émetteur"]).style.format({
            "Poids moyen chez les gérants": "{:.2%}", "Poids max": "{:.1%}", "Part de la valeur suivie": "{:.1%}",
            "Valeur détenue ($)": lambda v: f"{v / 1e9:,.2f} Md$", "Durée moy. (trim.)": "{:.1f}"}, na_rep="—"),
            hide_index=True, use_container_width=True, height=420)
        st.caption("Poids moyen = poids du titre dans l'allocation moyenne des gérants (proportion) ; poids max = la plus forte "
                   "conviction ; part de la valeur suivie = part du titre dans le total des montants déclarés.")
    section_title("LES ACTIFS LES PLUS VENDUS — DEPUIS QUAND, EN QUELLE PROPORTION", "🔻")
    ms = SM.most_sold(snap, codes, 30)
    if len(ms):
        top = ms.head(15).iloc[::-1]
        fig = go.Figure(go.Bar(x=top["Part vendue (moyenne)"] * 100, y=top["Titre"].astype(str), orientation="h",
                               marker_color="#ff3b6b", text=[f"{p:.0%} · {n} vendeur(s) · depuis {d}" for p, n, d in
                                                            zip(top["Part vendue (moyenne)"], top["Vendeurs"], top["Ventes depuis"])],
                               textposition="auto"))
        fig.update_layout(**PLOT, height=120 + 26 * len(top), title="Part des actions vendues par les gérants vendeurs (%)")
        st.plotly_chart(fig, use_container_width=True, key="sm_sold_bar")
        st.dataframe(ms.style.format({"Part vendue (moyenne)": "{:.0%}", "Poids avant (max)": "{:.1%}",
                                      "Montant vendu estimé ($)": lambda v: f"{v / 1e6:,.0f} M$" if v == v else "—"}, na_rep="—"),
                     hide_index=True, use_container_width=True, height=380)
        st.caption("Part vendue = 1 − actions détenues aujourd'hui / actions au plus haut avant les ventes (100 % = position "
                   "soldée). Montant vendu estimé = baisse de la valeur déclarée de la ligne d'un trimestre à l'autre.")
    else:
        st.info("Aucune vente détectée (il faut au moins deux trimestres de données).")

    section_title("INVESTIR DANS LES MÊMES ACTIFS DEPUIS MIP — ÉQUIVALENTS", "🧺")
    af = SM.assets_frame(snap, codes)
    if af.empty:
        return
    show = af[["ticker", "name", "secteur", "gerants", "poids_moyen_gerants", "mouvement", "plus_vendu", "equivalent_etf_us",
               "equivalent_etf_ucits", "equivalent_etf_pea"]].rename(columns={
        "ticker": "Ticker (achat direct, compte-titres)", "name": "Nom", "secteur": "Secteur", "gerants": "Gérants",
        "poids_moyen_gerants": "Poids moyen", "mouvement": "Mouvements", "plus_vendu": "Parmi les plus vendus",
        "equivalent_etf_us": "Équivalent ETF US", "equivalent_etf_ucits": "Équivalent UCITS", "equivalent_etf_pea": "Équivalent PEA"})
    st.dataframe(show.style.format({"Poids moyen": "{:.2%}"}), hide_index=True, use_container_width=True, height=380)
    st.caption("Achat direct : les actions américaines s'achètent sur un compte-titres (pas dans un PEA). Enveloppe UCITS : "
               "ETF sectoriel S&P 500 UCITS ; PEA : seuls des ETF larges sont éligibles (Nasdaq-100 PEA pour la tech, MSCI "
               "World PEA sinon). Un équivalent sectoriel reproduit le secteur, pas le choix de titres du gérant.")
    c1, c2, c3 = st.columns(3)
    if c1.button("➕ Alimenter l'univers MIP avec ces actifs", key="sm_sync", type="primary", use_container_width=True):
        r = SM.sync_assets(snap, codes)
        snap["assets_sync"] = r
        if r.get("ok"):
            st.success(f"{r['n']} actif(s) dans data/assets_best_am.csv ({r.get('new', 0)} nouveau(x) pour MIP) : ils "
                       "apparaissent dans le Trading Desk (univers « 🐋 Best AM »), l'analyse technique et l'optimiseur.")
        else:
            st.error("Écriture impossible sur ce serveur : téléchargez le fichier et ajoutez-le dans data/ du dépôt.")
    c2.download_button("⬇️ assets_best_am.csv (à déposer dans data/)", SM.assets_csv_bytes(snap, codes),
                       "assets_best_am.csv", "text/csv", use_container_width=True, key="sm_assets_dl")
    if c3.button("💼 Ouvrir le Trading Desk", key="sm_to_trading", use_container_width=True):
        st.session_state["spot_universe"] = "🐋 Best AM"
        st.session_state["page"] = "trading"
        st.rerun()
    st.caption("Sur Streamlit Cloud, les fichiers écrits par l'application disparaissent au redémarrage : pour rendre "
               "l'univers permanent, déposez le CSV téléchargé dans le dossier data/ de votre dépôt GitHub. Chaque achat "
               "reste soumis à votre profil, à votre politique d'investissement et aux contrôles de conformité.")


# ─────────────────────────────────────────────────────────────────────────────
def _tab_managers(snap, codes):
    section_title("LES GÉRANTS SUIVIS", "🏛️")
    ms = SM.manager_stats(snap, codes)
    if ms.empty:
        return
    st.dataframe(ms.drop(columns=["Code"]).style.format({"Valeur 13F ($)": lambda v: f"{v / 1e9:,.1f} Md$" if v == v else "—",
                                                         "Top 10": "{:.0%}", "Poids 1re ligne": "{:.0%}", "Rotation": "{:.0%}",
                                                         "Options ($)": lambda v: f"{v / 1e6:,.0f} M$" if v else "—"}, na_rep="—"),
                 hide_index=True, use_container_width=True)
    st.caption("Top 10 = poids des 10 premières lignes (concentration) · Rotation = ½ Σ |variation des poids| sur le trimestre "
               "(0 % = rien n'a changé) · Options = valeur notionnelle des calls / puts déclarés (couverture ou pari, le 13F ne le dit pas).")
    code = st.selectbox("Zoom sur un gérant", list(ms["Code"]), format_func=lambda c: f"{snap['managers'][c]['manager']} — "
                        f"{snap['managers'][c]['fund']}", key="sm_zoom")
    m = snap["managers"][code]
    h = SM.holdings_frame(snap, [code])
    r = ms[ms["Code"] == code].iloc[0]
    kpi_row([kpi("Valeur déclarée", f"{m['total_value'] / 1e9:,.1f} Md$", f"trimestre {m.get('period')}"),
             kpi("Lignes", str(m["n_positions"]), f"top 10 = {r['Top 10']:.0%}"),
             kpi("1re ligne", r["1re ligne"], f"{r['Poids 1re ligne']:.0%}"),
             kpi("Nouvelles / soldées", f"{r['Nouvelles']} / {r['Soldées']}", f"rotation {r['Rotation']:.0%}" if r["Rotation"] == r["Rotation"] else ""),
             kpi("Style", SM.STYLES.get(m.get("style"), "—"), m.get("entity") or "")])
    c1, c2 = st.columns([1.4, 1])
    with c1:
        top = h.head(20).iloc[::-1]
        col = {"Nouvelle": "#00ff88", "Renforcée": "#7cf0b5", "Allégée": "#ff8c00", "Inchangée": "#00d4ff", "—": "#64748b"}
        fig = go.Figure(go.Bar(x=top["weight"] * 100, y=top["label"], orientation="h",
                               marker_color=[col.get(s, "#64748b") for s in top["status"]],
                               text=[f"{w:.1%} · {s}" for w, s in zip(top["weight"], top["status"])], textposition="auto",
                               hovertext=top["issuer"]))
        fig.update_layout(**PLOT, height=560, title="20 premières positions (couleur = mouvement du trimestre)")
        st.plotly_chart(fig, use_container_width=True, key="sm_mgr_top")
    with c2:
        sec = h.groupby("sector")["weight"].sum().sort_values(ascending=False)
        fig = go.Figure(go.Pie(labels=sec.index, values=sec.values, hole=.55,
                               marker=dict(colors=[SM.SECTOR_COLORS.get(s, "#64748b") for s in sec.index])))
        fig.update_layout(**{k: v for k, v in PLOT.items() if k not in ("xaxis", "yaxis")}, height=330, title="Secteurs")
        st.plotly_chart(fig, use_container_width=True, key="sm_mgr_pie")
        if m.get("sold"):
            st.markdown("**Positions soldées au trimestre**")
            st.dataframe(pd.DataFrame(m["sold"])[[c for c in ("ticker", "issuer", "prev_weight") if c in pd.DataFrame(m["sold"])]]
                         .rename(columns={"ticker": "Ticker", "issuer": "Émetteur", "prev_weight": "Poids avant"})
                         .style.format({"Poids avant": "{:.1%}"}), hide_index=True, use_container_width=True, height=180)
    ph = SM.position_history(snap, [code])
    if len(ph):
        ph = ph[~ph["sold_out"]].drop_duplicates("key").set_index("key")
        h = h.assign(since=[("avant " if ph.loc[k, "before_window"] else "") + SM.quarter_label(ph.loc[k, "since"])
                            if k in ph.index and isinstance(ph.loc[k, "since"], str) and ph.loc[k, "since"] != "—" else "—"
                            for k in h["key"]])
    else:
        h = h.assign(since="—")
    st.dataframe(h[["rank", "label", "issuer", "sector", "weight", "d_weight", "status", "since", "value"]].rename(columns={
        "rank": "Rang", "label": "Titre", "issuer": "Émetteur", "sector": "Secteur", "weight": "Poids", "d_weight": "Δ poids",
        "status": "Mouvement", "since": "Détenu depuis", "value": "Valeur ($)"}).style.format({"Poids": "{:.2%}", "Δ poids": "{:+.2%}", "Valeur ($)": "{:,.0f}"},
                                                                    na_rep="—"), hide_index=True, use_container_width=True, height=320)
    if m.get("options"):
        with st.expander(f"Options déclarées ({len(m['options'])})"):
            st.dataframe(pd.DataFrame(m["options"]), hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
def _tab_sectors(snap, codes):
    section_title("ALLOCATION SECTORIELLE DES GÉRANTS", "🏭")
    sa = SM.sector_allocation(snap, codes)
    if sa.empty:
        return
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        fig.add_bar(name="Moyenne des gérants", y=sa.index, x=sa["Moyenne des gérants"] * 100, orientation="h", marker_color="#00d4ff")
        fig.add_bar(name="Pondérée par les montants", y=sa.index, x=sa["Pondérée par les montants"] * 100, orientation="h",
                    marker_color="#7c3aed")
        fig.update_layout(**PLOT, barmode="group", height=480, legend=dict(orientation="h", y=1.07), title="Poids par secteur (%)")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True, key="sm_sec_bar")
    with c2:
        if "Flux du trimestre (pts)" in sa and sa["Flux du trimestre (pts)"].notna().any():
            fl = sa["Flux du trimestre (pts)"].dropna().sort_values()
            fig = go.Figure(go.Bar(x=fl.values * 100, y=fl.index, orientation="h",
                                   marker_color=["#00ff88" if v > 0 else "#ff3b6b" for v in fl.values],
                                   text=[f"{v * 100:+.1f}" for v in fl.values], textposition="auto"))
            fig.update_layout(**PLOT, height=480, title="Flux du dernier trimestre (points de poids moyen)")
            st.plotly_chart(fig, use_container_width=True, key="sm_sec_flow")
        else:
            st.info("Flux indisponibles (un seul trimestre dans les données).")
    st.caption("« Moyenne des gérants » : chaque gérant compte autant ; « pondérée par les montants » : les plus gros "
               "portefeuilles (Berkshire…) pèsent davantage.")
    mat = SM.sector_matrix(snap, codes)
    fig = go.Figure(go.Heatmap(z=mat.values * 100, x=mat.columns, y=mat.index, colorscale="Blues", zmin=0,
                               text=[[f"{v:.0%}" if v >= 0.03 else "" for v in row] for row in mat.values],
                               texttemplate="%{text}", hovertemplate="%{y} · %{x} : %{z:.1f} %<extra></extra>"))
    fig.update_layout(**PLOT, height=120 + 26 * len(mat), title="Carte de chaleur : poids de chaque secteur chez chaque gérant")
    st.plotly_chart(fig, use_container_width=True, key="sm_heat")

    df = SM.holdings_frame(snap, codes)
    by_style = df.groupby(["style", "sector"])["weight"].sum() / df.groupby("style")["code"].nunique()
    bs = by_style.unstack(fill_value=0.0)
    bs.index = [SM.STYLES.get(i, i) for i in bs.index]
    if len(bs) > 1:
        fig = go.Figure()
        for s in [c for c in SM.SECTORS if c in bs.columns]:
            fig.add_bar(name=s, x=bs.index, y=bs[s] * 100, marker_color=SM.SECTOR_COLORS.get(s))
        fig.update_layout(**PLOT, barmode="stack", height=360, title="Comment chaque style alloue (%)",
                          legend=dict(font=dict(size=9)))
        st.plotly_chart(fig, use_container_width=True, key="sm_style")

    section_title("ZOOM SUR UN SECTEUR", "🔍")
    sec = st.selectbox("Secteur", [s for s in sa.index], key="sm_sec_zoom")
    rep = SM.sector_report(snap, codes, sec, UI.regime())
    for t in rep.get("text", []):
        st.markdown(f"- {t}")
    c1, c2 = st.columns(2)
    with c1:
        bm = rep["by_manager"][rep["by_manager"] > 0]
        fig = go.Figure(go.Bar(x=bm.values * 100, y=bm.index, orientation="h", marker_color=SM.SECTOR_COLORS.get(sec)))
        fig.update_layout(**PLOT, height=80 + 24 * len(bm), title=f"Poids de {sec.lower()} par gérant (%)")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True, key="sm_sec_mgr")
    with c2:
        st.dataframe(rep["names"][["Titre", "Gérants", "Poids dans la moyenne des gérants", "Nouvelles", "Renforcées", "Allégées"]]
                     .style.format({"Poids dans la moyenne des gérants": "{:.2%}"}), hide_index=True, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
def _tab_committee(snap, codes):
    section_title("ANALYSE ET INTERPRÉTATION DU COMITÉ", "🧠")
    reg = UI.regime()
    it = SM.interpret(snap, codes, reg, UI.perf_since(snap, codes, 10))
    if not it.get("ok"):
        st.info("Données insuffisantes.")
        return
    st.markdown(f'<div style="border-left:3px solid #00ff88;background:rgba(0,255,136,.05);border-radius:6px;padding:10px 16px;'
                f'font-family:Share Tech Mono;font-size:.78rem;color:#cbd5e1;line-height:1.6">🗣️ <b style="color:#00ff88">EN BREF</b> — '
                f'{_h.escape(it["synthese"])}</div>', unsafe_allow_html=True)
    UI.avis_cards(it["avis"])


# ─────────────────────────────────────────────────────────────────────────────
def _tab_reports(snap, codes):
    section_title("RAPPORTS D'ANALYSE", "📄")
    reg = UI.regime()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📘 Rapport complet : où investissent les meilleurs gérants**")
        st.caption("Secteurs (graphiques, carte de chaleur, flux), titres préférés, mouvements du trimestre, filtres de la "
                   "méthode 13F, analyse du comité, méthode et limites. Option : comparaison avec le portefeuille actif.")
        with_port = st.checkbox("Inclure la comparaison avec le portefeuille actif", value=True, key="sm_rep_port")
        if st.button("🧾 Générer le rapport complet", key="sm_rep_go", type="primary", use_container_width=True):
            with st.spinner("Rédaction du rapport…"):
                expo = comp = reasons = sugg = None
                name = None
                if with_port:
                    from components.ai_shared import active_portfolio
                    pid, port = active_portfolio()
                    if port:
                        vals, cash, prof, _ = UI._values("mip::x", port)
                        r = UI.analyse_one(snap, codes, vals, cash, prof, "Moyenne des gérants", reg, True)
                        expo, comp, reasons, sugg, name = r["expo"], r["comp"], r["reasons"], r["sugg"], port.get("name")
                st.session_state["sm_pdf"] = SM.build_pdf(snap, codes, reg, name, expo, comp, reasons, sugg,
                                                          UI.perf_since(snap, codes, 20))
        if st.session_state.get("sm_pdf"):
            st.download_button("⬇️ Télécharger le PDF", st.session_state["sm_pdf"],
                               f"MAM_tracking_best_AM_{datetime.now():%Y%m%d}.pdf", "application/pdf",
                               use_container_width=True, key="sm_rep_dl")
        st.download_button("📗 Toutes les données (Excel)", SM.build_excel(snap, codes),
                           f"MAM_tracking_best_AM_{datetime.now():%Y%m%d}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True, key="sm_rep_xlsx")
    with c2:
        st.markdown("**🏭 Rapport d'analyse sectorielle**")
        st.caption("Pour chaque secteur choisi : qui y investit, combien, quels titres, achats du trimestre, lecture du "
                   "régime par le comité, graphiques.")
        sa = SM.sector_allocation(snap, codes)
        default = [s for s in sa.index if s not in ("ETF & fonds indiciels", "Non classé")][:3]
        secs = st.multiselect("Secteurs", list(sa.index), default=default, key="sm_rep_secs")
        if st.button("🧾 Générer le rapport sectoriel", key="sm_rep_sec_go", use_container_width=True, disabled=not secs):
            with st.spinner("Analyse des secteurs…"):
                st.session_state["sm_sec_pdf"] = SM.build_sector_pdf(snap, codes, secs, reg)
        if st.session_state.get("sm_sec_pdf"):
            st.download_button("⬇️ Télécharger le rapport sectoriel", st.session_state["sm_sec_pdf"],
                               f"MAM_analyse_sectorielle_{datetime.now():%Y%m%d}.pdf", "application/pdf",
                               use_container_width=True, key="sm_rep_sec_dl")
    st.info("Les rapports de la page 📄 Rapports (comité, mensuel, détaillé) incluent désormais une section « Où investissent "
            "actuellement les meilleurs gérants » (top 5 secteurs, top 5 actifs, plateformes à regarder), à partir de ces données.")


# ─────────────────────────────────────────────────────────────────────────────
def _tab_platforms():
    section_title("PLATEFORMES À SUIVRE", "🔗")
    UI.platforms_box()
    section_title("LA MÉTHODE EN 5 ÉTAPES", "🧭")
    for i, (t, d) in enumerate(SM.METHOD_STEPS):
        st.markdown(f"**{i + 1}. {t}** — {d}")
    st.caption("Méthode inspirée de l'usage des 13F décrit par TIKR (« How to use 13F filings to find under-the-radar stock "
               "ideas »). Les données de MIP viennent directement de la SEC (EDGAR), source officielle de ces plateformes.")
