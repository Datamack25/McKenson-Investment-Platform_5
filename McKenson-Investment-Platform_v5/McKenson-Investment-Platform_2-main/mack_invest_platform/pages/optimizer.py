# pages/optimizer.py  —  MAM v5 · Optimiseur de portefeuille
"""
Comparaison des méthodes d'optimisation sur une sélection libre d'actifs :
Max Sharpe, variance minimale, CVaR minimale, parité de risque, HRP,
équipondéré ; frontière efficiente, corrélations, contributions au risque.

(Ce fichier contenait auparavant par erreur une copie de la page Classement :
l'onglet « Optimizer » n'optimisait rien.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ai_shared import PLOT, df_download, kpi, kpi_row, page_header
from components.ui import section_title

_DEFAULT = ["SPY", "QQQ", "VGK", "EEM", "TLT", "IEF", "LQD", "GLD", "BTC-USD"]
_COLORS = {"Max Sharpe": "#00ff88", "Variance minimale": "#00d4ff", "CVaR minimale": "#7c3aed",
           "Parité de risque": "#ffd700", "HRP": "#ff8c00", "Équipondéré": "#94a3b8"}


def render():
    from utils.data import load_assets
    from utils.market_intel import UNIVERSE, asset_name, fetch_prices
    from utils.portfolio import (frontier_scipy, hrp_weights, min_cvar_lp, optimize_scipy, portfolio_stats,
                                 risk_contributions, shrink_cov)

    page_header("📈 OPTIMISEUR", "Correction automatique par le comité · Markowitz · CVaR · parité de risque · HRP",
                "#7c3aed")
    _committee_optimizer()
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("LABORATOIRE D'OPTIMISATION — COMPARER LES MÉTHODES", "🔬")
    st.caption("Outil d'étude : compare les méthodes classiques sur une sélection libre d'actifs (n'agit pas sur vos portefeuilles).")
    assets = load_assets()
    names = dict(zip(assets["ticker"], assets["name"])) if not assets.empty else {}
    names.update({t: v[0] for t, v in UNIVERSE.items() if t not in names})
    choices = sorted(names)

    with st.form("opt_form"):
        c1, c2 = st.columns([3, 1])
        with c1:
            tickers = st.multiselect("Actifs (2 à 30)", choices, default=[t for t in _DEFAULT if t in choices],
                                     format_func=lambda t: f"{t} — {names.get(t, '')}")
        with c2:
            period = st.selectbox("Historique", ["1y", "2y", "3y", "5y"], index=2)
        c3, c4, c5 = st.columns(3)
        with c3:
            max_w = st.slider("Poids max par actif", 0.1, 1.0, 0.35, 0.05)
        with c4:
            rf = st.number_input("Taux sans risque (%)", 0.0, 10.0, 3.0, 0.25) / 100
        with c5:
            alpha = st.select_slider("Niveau CVaR", options=[0.01, 0.025, 0.05, 0.10], value=0.05,
                                     format_func=lambda a: f"{1 - a:.1%}")
        run = st.form_submit_button("⚡ OPTIMISER", use_container_width=True)

    if run:
        if not 2 <= len(tickers) <= 30:
            st.error("Choisissez entre 2 et 30 actifs.")
            return
        with st.spinner("Téléchargement des historiques et optimisation…"):
            px, src = fetch_prices(tuple(tickers), period)
            daily = px.pct_change(fill_method=None).dropna(how="all").dropna(axis=1, thresh=60).dropna()
            if daily.shape[1] < 2 or len(daily) < 60:
                st.error("Historique commun insuffisant pour ces actifs.")
                return
            mu = daily.mean() * 252
            cov = shrink_cov(daily)
            mw = max(max_w, 1 / daily.shape[1] + 1e-6)
            W = {
                "Max Sharpe": optimize_scipy(mu, cov, "sharpe", max_w=mw, rf=rf),
                "Variance minimale": optimize_scipy(mu, cov, "min_vol", max_w=mw),
                "CVaR minimale": min_cvar_lp(daily, alpha, mw),
                "Parité de risque": optimize_scipy(mu, cov, "risk_parity", max_w=1.0),
                "HRP": hrp_weights(daily),
                "Équipondéré": pd.Series(1 / daily.shape[1], index=daily.columns),
            }
            front = frontier_scipy(mu, cov, 25, mw)
        st.session_state["opt_out"] = {"W": W, "mu": mu, "cov": cov, "daily": daily, "front": front,
                                       "src": src, "rf": rf, "names": names}

    out = st.session_state.get("opt_out")
    if not out:
        st.info("Sélectionnez des actifs puis cliquez sur **⚡ Optimiser**.")
        return
    W, mu, cov, daily, front, rf = out["W"], out["mu"], out["cov"], out["daily"], out["front"], out["rf"]
    if out["src"] == "simulé":
        st.warning("⚠️ Yahoo Finance injoignable : optimisation réalisée sur des données simulées.")

    rows = []
    for n, w in W.items():
        s = portfolio_stats(w, mu, cov, rf)
        r = daily[w.index] @ w.values
        cvar = -r[r <= r.quantile(.05)].mean()
        eq = (1 + r).cumprod()
        rows.append({"Méthode": n, "Rendement": s["return"], "Volatilité": s["volatility"], "Sharpe": s["sharpe"],
                     "CVaR 95 % (1 j)": cvar, "Drawdown max": float((eq / eq.cummax() - 1).min()),
                     "Lignes > 1 %": int((w > .01).sum())})
    summ = pd.DataFrame(rows).set_index("Méthode")
    best = summ["Sharpe"].idxmax()
    kpi_row([kpi("Meilleur Sharpe historique", best, f"{summ.loc[best, 'Sharpe']:.2f}", "#00ff88"),
             kpi("Volatilité la plus basse", summ["Volatilité"].idxmin(), f"{summ['Volatilité'].min():.1%}"),
             kpi("Actifs", str(daily.shape[1]), f"{len(daily)} séances")])

    c1, c2 = st.columns([1.3, 1])
    with c1:
        section_title("FRONTIÈRE EFFICIENTE", "🎯")
        fig = go.Figure()
        if not front.empty:
            fig.add_trace(go.Scatter(x=front["volatility"], y=front["return"], mode="lines", name="Frontière",
                                     line=dict(color="rgba(0,212,255,.7)", width=2)))
        vols = np.sqrt(np.diag(cov))
        fig.add_trace(go.Scatter(x=vols, y=mu.values, mode="markers+text", text=list(mu.index),
                                 textposition="top center", marker=dict(color="#475569", size=7), name="Actifs"))
        for n, r in summ.iterrows():
            fig.add_trace(go.Scatter(x=[r["Volatilité"]], y=[r["Rendement"]], mode="markers", name=n,
                                     marker=dict(color=_COLORS[n], size=13, symbol="diamond",
                                                 line=dict(color="#fff", width=1))))
        fig.update_layout(**PLOT, height=420, legend=dict(orientation="h", y=-0.15))
        fig.update_xaxes(title="Volatilité annualisée", tickformat=".0%")
        fig.update_yaxes(title="Rendement annualisé (historique)", tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        section_title("COMPARAISON", "📋")
        st.dataframe(summ.style.format({"Rendement": "{:+.1%}", "Volatilité": "{:.1%}", "Sharpe": "{:.2f}",
                                        "CVaR 95 % (1 j)": "{:.2%}", "Drawdown max": "{:.1%}"}),
                     use_container_width=True)
        st.caption("Rendements attendus = moyennes historiques : très instables. Pour une estimation tenant compte "
                   "du contexte de marché et du ML, utilisez 🤖 Auto-Portefeuille (Black-Litterman).")

    section_title("POIDS PAR MÉTHODE", "⚖️")
    Wdf = pd.DataFrame(W).fillna(0)
    fig = go.Figure()
    for t in Wdf.index:
        fig.add_trace(go.Bar(x=Wdf.columns, y=Wdf.loc[t], name=t))
    fig.update_layout(**PLOT, barmode="stack", height=340, legend=dict(orientation="h", y=-0.15))
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(Wdf.style.format("{:.1%}"), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        section_title("CORRÉLATIONS", "🔗")
        cr = daily.corr()
        fig = go.Figure(go.Heatmap(z=cr.values, x=cr.columns, y=cr.index, colorscale="RdBu_r", zmin=-1, zmax=1,
                                   text=np.round(cr.values, 2), texttemplate="%{text}", textfont=dict(size=9)))
        fig.update_layout(**PLOT, height=400)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        section_title("CONTRIBUTIONS AU RISQUE", "🧩")
        m = st.selectbox("Méthode", list(W), key="opt_rc_m")
        rc = risk_contributions(W[m].reindex(cov.index).fillna(0), cov)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=rc.index, y=W[m].reindex(rc.index).values, name="Poids", marker_color="#00d4ff"))
        fig.add_trace(go.Bar(x=rc.index, y=rc.values, name="Risque", marker_color="#ffd700"))
        fig.update_layout(**PLOT, barmode="group", height=360, legend=dict(orientation="h", y=1.12))
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    section_title("EXPORTS", "📤")
    c1, c2 = st.columns(2)
    with c1:
        df_download(Wdf, "optimisation_poids.csv", "⬇️ Poids (CSV)", "opt_dl_w")
    with c2:
        from utils import reporting as R
        if st.button("🖼️ Générer les images (PNG)", key="opt_img", use_container_width=True):
            imgs = {f"allocation_{n.replace(' ', '_').lower()}": R.chart_allocation(w[w > 0.001], "light", n)
                    for n, w in W.items()}
            imgs["correlations"] = R.chart_corr(daily, "light")
            st.session_state["opt_zip"] = R.zip_images(imgs)
        if st.session_state.get("opt_zip"):
            st.download_button("⬇️ Images (.zip)", st.session_state["opt_zip"], file_name="optimisation_images.zip",
                               mime="application/zip", key="opt_dl_zip", use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIMISATION PAR LE COMITÉ — correction automatique d'un portefeuille
# ══════════════════════════════════════════════════════════════════════════════
def _committee_optimizer():
    from components.committee_ui import (get_context, inject_css, ips_summary, portfolio_values, render_ips_form,
                                         render_review)
    from utils import committee as CM
    from utils import hedging as H
    from utils.auto_portfolio import execute_orders
    from utils.compliance import get_profile, normalize_port_type
    from utils.data import get_multi_prices, get_or_init_state, persist

    inject_css()
    section_title("OPTIMISATION PAR LE COMITÉ — CORRECTION AUTOMATIQUE DU PORTEFEUILLE", "🧑‍⚖️")
    st.markdown(
        '<div style="font-family:Share Tech Mono;font-size:.74rem;color:#94a3b8;line-height:1.7;margin-bottom:8px">'
        "🌦️ <b>Jean-Michel TAUX-BAS</b> lit le régime de marché → 🏛️ <b>Thierry BALANCEMENT</b> fixe l'allocation cible "
        "selon votre politique d'investissement → 🧮 <b>Mc Henson ALGO-RITHME</b> choisit et pondère les lignes selon des signaux "
        "validés hors échantillon → 🛡️ <b>Aline DE MARGE</b> vérifie la perte potentielle (VaR, Expected Shortfall, "
        "stress tests — méthodes de John Hull) et propose des couvertures → ⚖️ <b>Constance Probité</b> contrôle les "
        "exclusions et la conformité → 🎙️ <b>Marc ETING-FINANCIER</b> vous présente le plan. "
        "<b style='color:#ffd700'>Rien n'est exécuté sans votre confirmation</b> ; un veto bloque l'exécution.</div>",
        unsafe_allow_html=True)

    state = get_or_init_state()
    ports = {(tid, pid): (f'{p.get("emoji", "📁")} {p["name"]} · {t.get("name", "Solo")}', p)
             for tid, t in state.get("teams", {}).items() for pid, p in t.get("portfolios", {}).items() if p.get("name")}
    if not ports:
        st.info("Aucun portefeuille : créez-en un depuis le Dashboard.")
        return
    keys = list(ports)
    active = (st.session_state.get("active_team"), st.session_state.get("active_portfolio"))
    sel = st.selectbox("Portefeuille à optimiser", keys, format_func=lambda k: ports[k][0],
                       index=keys.index(active) if active in keys else 0, key="cmo_port")
    label, port = ports[sel]

    if not port.get("ips"):
        st.warning("Le comité a besoin de la politique d'investissement de ce portefeuille pour l'optimiser.")
        ips = render_ips_form(f"cmo_{sel[1]}", CM.default_ips(get_profile().get("risque", "Équilibré")))
        if ips:
            port["ips"] = ips
            persist()
            st.rerun()
        return
    st.markdown("**Politique d'investissement :** " + ips_summary(port["ips"]))
    c1, c2, c3 = st.columns([1, 1, 1.2])
    intensity = c1.slider("Intensité tactique", 0.0, 1.0, 0.5, 0.1, key="cmo_int",
                          help="0 = allocation stratégique du profil ; 1 = inclinaisons macro maximales")
    band = c2.slider("Bande de tolérance", 0.0, 0.05, 0.02, 0.005, format="%.3f", key="cmo_band",
                     help="Une ligne n'est ajustée que si elle s'écarte de sa cible de plus de cette part du portefeuille.")
    if c3.button("🧑‍⚖️ RÉUNIR LE COMITÉ ET OPTIMISER", key="cmo_run", use_container_width=True, type="primary"):
        ctx = get_context()
        vals, cash, _ = portfolio_values(port)
        universe = set(vals) | {t for t in list(CM.A.CLASS_PROXY.values()) + list(CM.UCITS_PROXY.values())
                                + list(CM.PEA_PROXY.values())}
        live = get_multi_prices(tuple(sorted(universe)))
        with st.spinner("Le comité délibère…"):
            opt = CM.committee_optimize(vals, cash, port["ips"], ctx, live, intensity, band)
            pref = opt["contraintes"]["couvertures"]
            hedges = []
            if pref != "Jamais d'options":
                hedges = H.propose_hedges(H.exposures_from_values(opt["projete"]), ctx["macro"].factors,
                                          ctx.get("vix"), opt["nav"], prices=live)
                if pref.startswith("Seulement"):
                    hedges = [h for h in hedges if h["recommandee"]]
            common = dict(options=port.get("options", []), options_ok=get_profile().get("options_ok", False),
                          port_type=normalize_port_type(port), label=port.get("name", "Portefeuille"))
            before = CM.review_portfolio(vals, cash, port["ips"], ctx, **common)
            after = CM.review_portfolio(opt["projete"], opt["cash_apres"], port["ips"], ctx, hedges=hedges, **common)
        st.session_state["cmo_out"] = dict(key=sel, opt=opt, before=before, after=after, hedges=hedges,
                                           data_sim=ctx.get("data_sim", False))

    out = st.session_state.get("cmo_out")
    if not out or out["key"] != sel:
        return
    opt, before, after, hedges = out["opt"], out["before"], out["after"], out["hedges"]
    rb, ra = before.get("risque") or {}, after.get("risque") or {}

    def _p(x):
        return "—" if x is None or x != x else f"{x:.1%}"
    vb, va = before["verdict"], after["verdict"]
    k = st.columns(5)
    k[0].metric("Verdict avant", CM.VERDICT_LABEL[vb].split(" ", 1)[1].title())
    k[1].metric("Verdict après", CM.VERDICT_LABEL[va].split(" ", 1)[1].title())
    k[2].metric("Perte potentielle 1 an (VaR 95 %)", _p(ra.get("var95_1an")),
                delta=None if not rb.get("var95_1an") else f"{(ra.get('var95_1an', 0) - rb['var95_1an']) * 100:+.1f} pt",
                delta_color="inverse")
    k[3].metric("Expected Shortfall 97,5 % (10 j)", _p(ra.get("es975_10j")),
                delta=None if not rb.get("es975_10j") else f"{(ra.get('es975_10j', 0) - rb['es975_10j']) * 100:+.1f} pt",
                delta_color="inverse")
    k[4].metric("Ordres proposés", str(len(opt["ordres"])))

    st.markdown("##### 🧭 Comment le comité a construit le plan")
    for who, note in opt["notes"]:
        m = CM.MEMBER[who]
        st.markdown(f'<div class="cm-reco" style="border-color:{m["couleur"]}">{m["emoji"]} <b>{m["nom"]}</b> — '
                    f'{note}</div>', unsafe_allow_html=True)

    c1, c2 = st.columns([1.1, 1])
    with c1:
        st.markdown("##### ⚖️ Avant / après par ligne")
        cmp_ = pd.DataFrame({"Actuel": opt["actuel_lignes"], "Cible du comité": opt["cible_lignes"]}).fillna(0.0)
        cmp_["Écart"] = cmp_["Cible du comité"] - cmp_["Actuel"]
        from utils.sectors import sector_of
        cmp_.insert(0, "Secteur", [sector_of(t) for t in cmp_.index])
        cmp_ = cmp_[(cmp_["Actuel"] > 0.001) | (cmp_["Cible du comité"] > 0.001)].sort_values("Cible du comité", ascending=False)
        st.dataframe(cmp_.style.format("{:+.1%}", subset=["Écart"]).format("{:.1%}", subset=["Actuel", "Cible du comité"]),
                     use_container_width=True)
    with c2:
        st.markdown("##### 📝 Ordres (contrôlés un par un par la conformité)")
        if opt["ordres"].empty:
            st.success("Aucun ordre : le portefeuille est déjà dans ses bandes de tolérance.")
        else:
            from utils.sectors import sector_of
            st.dataframe(opt["ordres"].assign(secteur=[sector_of(t) for t in opt["ordres"]["ticker"]])
                         [["ticker", "secteur", "action", "qty", "price", "montant", "motif"]]
                         .style.format({"qty": "{:,.4f}", "price": "{:,.2f}", "montant": "{:,.0f}"}),
                         use_container_width=True, hide_index=True)

    accepted = []
    if hedges:
        st.markdown("##### 🛡️ Couvertures proposées par Aline DE MARGE")
        from pages.hedge_fund import _hedge_cards
        accepted = _hedge_cards(hedges, get_profile().get("options_ok", False))

    st.markdown("##### 🧑‍⚖️ Avis du comité sur le portefeuille APRÈS optimisation")
    render_review(after)
    with st.expander("Avis du comité sur le portefeuille AVANT optimisation"):
        render_review(before, show_recos=True)

    blocked = va == "veto" or not opt["allowed"] or out["data_sim"]
    if blocked:
        st.error("⛔ Exécution bloquée : " + ("données de marché simulées." if out["data_sim"] or not opt["allowed"]
                                              else "le comité oppose son veto au portefeuille obtenu."))
    ok = st.checkbox("Je confirme l'exécution simulée du plan du comité"
                     + (f" et de {len(accepted)} couverture(s)" if accepted else ""), key="cmo_ok", disabled=blocked)
    if st.button("🚀 APPLIQUER LE PLAN DU COMITÉ", key="cmo_go", disabled=blocked or not ok,
                 use_container_width=True, type="primary"):
        n_before = len(port.get("trades", []) or [])
        errs = execute_orders(port, opt["ordres"].drop(columns=["motif"], errors="ignore"),
                              tag="Comité MAM — optimisation") if not opt["ordres"].empty else []
        done, herrs = [], []
        if accepted:
            vals2, cash2, live2 = portfolio_values(port)
            ctx2 = get_context()
            for h in H.propose_hedges(H.exposures_from_values(vals2), ctx2["macro"].factors,
                                      ctx2.get("vix"), cash2 + sum(vals2.values()), prices=live2):
                if h["cle"] in accepted:
                    e = H.execute_hedge(port, h, tag="Comité MAM")
                    (herrs.append(e) if e else done.append(h.get("ajustement", h["panier"])))
        port["committee"] = CM.summary_for_storage(after)
        persist()
        try:  # journal des écarts recommandation / exécution (v5.4)
            from utils.execution_log import record_execution
            record_execution(port, "Comité MAM — optimisation", opt["ordres"], n_before, errs + herrs,
                             target_weights=opt["cible_lignes"], hedges_done=done)
        except Exception:
            pass
        st.session_state.pop("cmo_out", None)
        st.success(f"✅ Plan appliqué : {len(opt['ordres']) - len(errs)} ordre(s)"
                   + (f", couvertures : {', '.join(done)}" if done else "") + ". Le portefeuille est validé par le comité.")
        if errs or herrs:
            st.warning("Ordres bloqués par la conformité :\n\n- " + "\n- ".join(errs + herrs))
