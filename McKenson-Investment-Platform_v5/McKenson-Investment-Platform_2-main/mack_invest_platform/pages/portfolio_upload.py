# pages/portfolio_upload.py  —  MAM v5.5 · « 📥 Conseil portefeuille » : le comité analyse un fichier importé
"""
L'utilisateur importe son portefeuille (CSV ou Excel au format indiqué AVANT l'import) ; le comité MAM
l'analyse au regard de son profil, de sa politique d'investissement et du contexte de marché, propose une
réallocation optimisée, des scénarios, les secteurs et régions qui performent le mieux, puis l'analyse se
télécharge en Excel (avec graphiques), CSV ou image. Après chaque analyse et dans chaque fichier :
avertissement « ce n'est pas un conseil financier » et non-responsabilité de l'auteur.
"""
from __future__ import annotations

import html as _h
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st

from components.ui import section_title
from utils import upload_advisor as U


def _warning_box():
    st.markdown(
        '<div style="border:1px solid rgba(255,59,107,.55);background:rgba(255,59,107,.08);border-radius:8px;'
        'padding:10px 14px;margin:10px 0;font-family:Share Tech Mono,monospace;font-size:.74rem;color:#fecdd3;'
        f'line-height:1.6">⚠️ <b style="color:#ff3b6b">AVERTISSEMENT</b> — {_h.escape(U.WARNING)}</div>',
        unsafe_allow_html=True)


def _pct(v, d=1, sign=False):
    return "—" if v is None or (isinstance(v, float) and not np.isfinite(v)) else (f"{v:+.{d}%}" if sign else f"{v:.{d}%}")


# ── ① Profil et politique d'investissement ─────────────────────────────────────
def _profile_block() -> tuple[dict, str]:
    from components.committee_ui import ips_summary, render_ips_form
    from utils import committee as CM
    from utils.compliance import get_profile
    from utils.data import get_or_init_state

    section_title("① VOTRE PROFIL ET VOTRE POLITIQUE D'INVESTISSEMENT", "👤")
    prof = get_profile()
    user = st.session_state.get("mam_user") or {}
    st.markdown(
        f'<div style="font-family:Share Tech Mono;font-size:.76rem;color:#94a3b8;line-height:1.7">'
        f'Compte : <b style="color:#e2e8f0">{_h.escape(str(user.get("username", "invité")))}</b> · profil investisseur : '
        f'<b style="color:#00d4ff">{prof["risque"]}</b>'
        f'{"" if prof.get("defini") else " (par défaut — questionnaire non rempli dans le Trading Desk)"} · '
        f'produits dérivés : {"autorisés (test réussi)" if prof.get("options_ok") else "fermés"}</div>',
        unsafe_allow_html=True)
    state = get_or_init_state()
    with_ips = {f'Politique du portefeuille « {p["name"]} »': p["ips"]
                for t in state.get("teams", {}).values() for p in t.get("portfolios", {}).values()
                if p.get("ips") and p.get("name")}
    opts = [f"Mon profil investisseur ({prof['risque']})"] + list(with_ips) + ["Saisir une politique pour ce fichier"]
    choice = st.radio("Politique appliquée par le comité", opts, key="upa_ips_src", horizontal=False)
    if choice.startswith("Mon profil"):
        ips, src = CM.default_ips(prof["risque"]), f"profil investisseur {prof['risque']}"
    elif choice in with_ips:
        ips, src = with_ips[choice], choice.lower()
    else:
        new = render_ips_form("upa", st.session_state.get("upa_ips") or CM.default_ips(prof["risque"]),
                              "💾 Utiliser cette politique")
        if new:
            st.session_state["upa_ips"] = new
        ips = st.session_state.get("upa_ips") or CM.default_ips(prof["risque"])
        src = "politique saisie pour ce fichier"
    st.markdown("**Politique retenue :** " + ips_summary(ips))
    return ips, src


# ── ② Format du fichier (affiché AVANT l'import) ───────────────────────────────
def _format_block():
    section_title("② FORMAT DU FICHIER À IMPORTER (CSV OU EXCEL)", "📋")
    st.markdown("Avant l'analyse, préparez votre fichier **exactement** sur ce modèle (une ligne par position) :")
    st.dataframe(pd.DataFrame(U.FORMAT_ROWS, columns=["Colonne", "Statut", "Contenu", "Exemple"]),
                 use_container_width=True, hide_index=True)
    st.markdown("\n".join(f"- {r}" for r in U.FORMAT_RULES))
    with st.expander("Exemple de fichier conforme", expanded=False):
        st.dataframe(U.template_frame(), use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    c1.download_button("⬇️ Modèle CSV", U.template_csv(), "modele_portefeuille_MAM.csv", "text/csv",
                       use_container_width=True, key="upa_tpl_csv")
    c2.download_button("⬇️ Modèle Excel", U.template_xlsx(), "modele_portefeuille_MAM.xlsx",
                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                       use_container_width=True, key="upa_tpl_xlsx")


# ── ③ Analyse ──────────────────────────────────────────────────────────────────
def _run(parsed: dict, fname: str, ips: dict, src: str, intensity: float, band: float) -> dict:
    from components.committee_ui import get_context
    from utils import committee as CM
    from utils import performance as PF
    from utils.compliance import get_profile
    from utils.data import get_multi_prices, get_multi_sources

    ctx = get_context()
    tickers = tuple(sorted(parsed["lignes"]["ticker"]))
    universe = set(tickers) | set(CM.A.CLASS_PROXY.values()) | set(CM.UCITS_PROXY.values()) | set(CM.PEA_PROXY.values())
    live = get_multi_prices(tuple(sorted(universe)))
    try:
        sources = get_multi_sources(tickers)
    except Exception:
        sources = {}
    lines, notes = U.value_lines(parsed, live, sources)
    if lines.empty:
        return dict(ok=False, notes=notes)
    values = dict(zip(lines["Ticker"], lines["Valeur"]))
    cash = float(parsed.get("cash", 0.0))
    nav = cash + sum(values.values())
    opts_ok = get_profile().get("options_ok", False)
    before = CM.review_portfolio(values, cash, ips, ctx, options_ok=opts_ok, label=fname)
    opt = CM.committee_optimize(values, cash, ips, ctx, live, intensity, band)
    after = CM.review_portfolio(opt["projete"], opt["cash_apres"], ips, ctx, options_ok=opts_ok,
                                label=f"{fname} — après réallocation")
    hist = PF.price_history(U.board_tickers(), (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d"))
    w_b = U.class_weights(values, cash)
    w_a = U.class_weights(opt["projete"], opt["cash_apres"])
    return dict(ok=True, fichier=fname, date=datetime.now().strftime("%d/%m/%Y %H:%M"), devise=parsed.get("devise", "USD"),
                lignes=lines, cash=cash, nav=nav, notes=notes, avant=before, apres=after, opt=opt,
                classes_avant=w_b, classes_apres=w_a, secteurs=U.sector_board(hist, ctx["macro"]),
                regions=U.region_board(hist, ctx["macro"]), perf_dispo=bool(hist is not None and not hist.empty),
                data_sim=bool(ctx.get("data_sim")), source_profil=src,
                scenarios=U.scenarios(w_b, w_a, None, nav))


def _show(res: dict):
    import plotly.graph_objects as go
    from components.committee_ui import render_review

    _warning_box()
    if res["data_sim"]:
        st.error("Données de marché simulées (sources indisponibles) : les résultats ne sont pas fiables.")
    for n in res["notes"]:
        st.caption("ℹ️ " + n)
    rb, ra = res["avant"].get("risque") or {}, res["apres"].get("risque") or {}
    k = st.columns(5)
    k[0].metric("Valeur du portefeuille", f"{res['nav']:,.0f} {res['devise']}".replace(",", " "))
    k[1].metric("Lignes", f"{len(res['lignes'])}")
    k[2].metric("Verdict actuel", res["avant"]["verdict_label"].split(" ", 1)[-1].capitalize())
    k[3].metric("Verdict après réallocation", res["apres"]["verdict_label"].split(" ", 1)[-1].capitalize())
    k[4].metric("Perte potentielle 1 an", _pct(rb.get("var95_1an"), 0),
                delta=None if not ra.get("var95_1an") or not rb.get("var95_1an") else
                f"{(ra['var95_1an'] - rb['var95_1an']) * 100:+.1f} pt après", delta_color="inverse")

    # Tableau importé + à côté : secteurs et régions qui performent le mieux
    section_title("PORTEFEUILLE IMPORTÉ · SECTEURS ET RÉGIONS QUI PERFORMENT LE MIEUX", "📊")
    left, right = st.columns([1.45, 1])
    with left:
        st.markdown("**Votre portefeuille**")
        show = res["lignes"][["Ticker", "Nom", "Secteur", "Région", "Quantité", "Cours", "Valeur", "Poids",
                              "Plus-value %"]]
        st.dataframe(show.style.format({"Quantité": "{:,.4g}", "Cours": "{:,.2f}", "Valeur": "{:,.0f}",
                                        "Poids": "{:.1%}", "Plus-value %": "{:+.1%}"}, na_rep="—"),
                     use_container_width=True, hide_index=True, height=420)
        st.caption(f"Liquidités : {res['cash']:,.0f} {res['devise']}".replace(",", " "))
    with right:
        st.markdown("**🏭 Secteurs qui performent le mieux**")
        s = res["secteurs"][["Perf. 3 mois", "Perf. 12 mois", "Lecture du contexte", "Score"]].head(8)
        st.dataframe(s.style.format({"Perf. 3 mois": "{:+.1%}", "Perf. 12 mois": "{:+.1%}", "Score": "{:.0f}"},
                                    na_rep="—"), use_container_width=True, height=250)
        st.markdown("**🌍 Régions qui performent le mieux**")
        r = res["regions"][["Zone", "Perf. 3 mois", "Lecture du contexte", "Score"]].head(8)
        st.dataframe(r.style.format({"Perf. 3 mois": "{:+.1%}", "Score": "{:.0f}"}, na_rep="—"),
                     use_container_width=True, height=250)
    st.caption(("Classement : 40 % performance sur 3 mois, 20 % sur 12 mois, 40 % lecture du contexte (régime « "
                f"{res['avant']['regime']} » pour les secteurs, scores macro du desk pour les régions). Secteurs : indices "
                "sectoriels américains (ETF SPDR) ; régions : ETF pays.")
               + ("" if res["perf_dispo"] else " Cours historiques indisponibles : classement fondé sur le contexte seul."))
    reg = res["regions"].reset_index()
    fig = go.Figure(go.Choropleth(
        locations=reg["ISO3"], z=reg["Score"], text=reg["Région"], zmin=0, zmax=100,
        colorscale=[[0, "#ff3b6b"], [0.5, "#ffd700"], [1, "#00ff88"]], marker_line_color="#0b1220",
        colorbar=dict(title=dict(text="Score", font=dict(color="#94a3b8")), tickfont=dict(color="#94a3b8")),
        hovertemplate="%{text} · score %{z:.0f}/100<extra></extra>"))
    fig.update_geos(bgcolor="rgba(0,0,0,0)", showframe=False, showcoastlines=False, landcolor="#1e293b",
                    showcountries=True, countrycolor="#334155", projection_type="natural earth")
    fig.update_layout(height=360, margin=dict(l=0, r=0, t=30, b=0), paper_bgcolor="rgba(0,0,0,0)",
                      title=dict(text="Carte des régions qui performent le mieux (contexte inclus)",
                                 font=dict(color="#e2e8f0", size=13)))
    st.plotly_chart(fig, use_container_width=True, key="upa_map")

    # Avis du comité
    section_title("AVIS DU COMITÉ MAM", "🧑‍⚖️")
    t1, t2 = st.tabs(["Portefeuille actuel", "Après réallocation"])
    with t1:
        render_review(res["avant"])
    with t2:
        render_review(res["apres"])

    # Réallocation
    section_title("RÉALLOCATION ET OPTIMISATION PROPOSÉES", "⚖️")
    cmp_cls = pd.DataFrame({"Actuel": res["classes_avant"], "Après réallocation": res["classes_apres"]})
    cmp_cls = cmp_cls[cmp_cls.abs().sum(axis=1) > 0.0005]
    fig = go.Figure()
    fig.add_bar(name="Actuel", y=cmp_cls.index, x=cmp_cls["Actuel"] * 100, orientation="h", marker_color="#64748b")
    fig.add_bar(name="Après réallocation", y=cmp_cls.index, x=cmp_cls["Après réallocation"] * 100, orientation="h",
                marker_color="#00d4ff")
    fig.update_layout(barmode="group", height=60 + 34 * len(cmp_cls), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8"), margin=dict(l=8, r=8, t=10, b=8),
                      xaxis=dict(title="%", gridcolor="#1e293b"), yaxis=dict(autorange="reversed"),
                      legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, use_container_width=True, key="upa_cls")
    for who, txt in res["opt"]["notes"]:
        st.caption(f"• {txt}")
    rl = U._realloc_frame(res)
    st.dataframe(rl.style.format({"Poids actuel": "{:.1%}", "Poids cible": "{:.1%}", "Écart": "{:+.1%}"}),
                 use_container_width=True)
    od = res["opt"]["ordres"]
    if od is not None and not od.empty:
        st.markdown("**Ordres proposés** (aucun n'est exécuté : à passer vous-même chez votre intermédiaire, après réflexion)")
        st.dataframe(od.rename(columns={"ticker": "Ticker", "action": "Sens", "qty": "Quantité", "price": "Cours",
                                        "montant": "Montant", "motif": "Motif"})
                     .style.format({"Quantité": "{:,.4f}", "Cours": "{:,.2f}", "Montant": "{:,.0f}"}),
                     use_container_width=True, hide_index=True)
    else:
        st.info("Aucun ordre nécessaire : le portefeuille reste dans les bandes de tolérance du comité.")

    # Scénarios
    section_title("SCÉNARIOS DE MARCHÉ", "🌪️")
    with st.expander("🎛️ Scénario personnalisé", expanded=False):
        cc = st.columns(5)
        custom = {g: cc[i].slider(g, -60, 60, d, 5, format="%d %%", key=f"upa_sc_{i}") / 100
                  for i, (g, d) in enumerate(zip(U.CUSTOM_GROUPS, [-20, 5, 8, -10, -40]))}
    res["scenarios"] = U.scenarios(res["classes_avant"], res["classes_apres"], custom, res["nav"])
    scn = res["scenarios"]
    fig = go.Figure()
    fig.add_bar(name="Actuel", y=scn.index, x=scn["Portefeuille actuel"] * 100, orientation="h", marker_color="#ff3b6b")
    fig.add_bar(name="Après réallocation", y=scn.index, x=scn["Après réallocation"] * 100, orientation="h",
                marker_color="#00ff88")
    fig.update_layout(barmode="group", height=60 + 40 * len(scn), paper_bgcolor="rgba(0,0,0,0)",
                      plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8"), margin=dict(l=8, r=8, t=10, b=8),
                      xaxis=dict(title="Variation de la valeur (%)", gridcolor="#1e293b"),
                      yaxis=dict(autorange="reversed"), legend=dict(orientation="h", y=1.08))
    st.plotly_chart(fig, use_container_width=True, key="upa_scn")
    st.dataframe(scn.style.format({"Portefeuille actuel": "{:+.1%}", "Après réallocation": "{:+.1%}",
                                   "Écart": "{:+.1%}", "Perte / gain actuel ($)": "{:+,.0f}"}),
                 use_container_width=True)
    inv = rb.get("stress_inverse")
    if inv:
        st.caption("Stress test inversé : " + inv["texte"])

    # Téléchargements
    section_title("TÉLÉCHARGER L'ANALYSE", "⬇️")
    stem = f"MAM_conseil_{datetime.now():%Y%m%d_%H%M}"
    d1, d2, d3 = st.columns(3)
    try:
        d1.download_button("📗 Excel (avec graphiques)", U.build_excel(res), f"{stem}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True, key="upa_dl_xlsx")
    except Exception as e:
        d1.caption(f"Excel indisponible ({type(e).__name__}).")
    d2.download_button("📄 CSV", U.build_csv(res), f"{stem}.csv", "text/csv", use_container_width=True, key="upa_dl_csv")
    try:
        d3.download_button("🖼️ Image (PNG)", U.build_png(res), f"{stem}.png", "image/png", use_container_width=True,
                           key="upa_dl_png")
    except Exception as e:
        d3.caption(f"Image indisponible ({type(e).__name__}).")
    _warning_box()


def render():
    st.markdown(
        '<h1 style="font-family:Rajdhani,sans-serif;font-size:1.9rem;letter-spacing:.1em;color:#00d4ff;margin:0">'
        '📥 CONSEIL PORTEFEUILLE — LE COMITÉ ANALYSE VOTRE FICHIER</h1>'
        '<div style="font-family:Share Tech Mono;font-size:.74rem;color:#94a3b8;margin:4px 0 10px">Importez un '
        'portefeuille (CSV ou Excel) : le comité MAM l\'analyse selon votre profil, votre objectif et le contexte de '
        'marché, propose une réallocation optimisée, des scénarios, les secteurs et régions porteurs, puis vous '
        'téléchargez l\'analyse (Excel, CSV ou image). Aucun ordre n\'est passé.</div>', unsafe_allow_html=True)
    ips, src = _profile_block()
    _format_block()
    section_title("③ IMPORTER ET ANALYSER", "📥")
    up = st.file_uploader("Fichier du portefeuille (.csv ou .xlsx)", type=["csv", "xlsx"], key="upa_file")
    if up is None:
        st.info("Importez un fichier au format ci-dessus pour lancer l'analyse du comité.")
        return
    parsed = U.parse_file(up.getvalue(), up.name)
    for e in parsed["erreurs"]:
        st.error(e)
    for n in parsed["remarques"]:
        st.caption("ℹ️ " + n)
    if not parsed["ok"]:
        st.warning("Corrigez le fichier selon le format indiqué, puis importez-le à nouveau.")
        return
    st.success(f"{len(parsed['lignes'])} ligne(s) lue(s)" + (f" + {parsed['cash']:,.0f} de liquidités".replace(",", " ")
                                                             if parsed["cash"] else "") + ".")
    c1, c2, c3 = st.columns([1, 1, 1.2])
    intensity = c1.slider("Intensité tactique", 0.0, 1.0, 0.5, 0.1, key="upa_int",
                          help="0 = allocation stratégique du profil ; 1 = inclinaisons macro maximales")
    band = c2.slider("Bande de tolérance", 0.0, 0.05, 0.02, 0.005, format="%.3f", key="upa_band")
    if c3.button("🧑‍⚖️ LANCER L'ANALYSE DU COMITÉ", key="upa_run", type="primary", use_container_width=True):
        with st.spinner("Le comité analyse votre portefeuille…"):
            st.session_state["upa_res"] = _run(parsed, up.name, ips, src, intensity, band)
            st.session_state["upa_res_file"] = up.name
    res = st.session_state.get("upa_res")
    if not res or st.session_state.get("upa_res_file") != up.name:
        return
    if not res.get("ok"):
        for n in res.get("notes", []):
            st.error(n)
        st.warning("Aucune ligne n'a pu être valorisée : ajoutez la colonne « montant ».")
        return
    _show(res)
