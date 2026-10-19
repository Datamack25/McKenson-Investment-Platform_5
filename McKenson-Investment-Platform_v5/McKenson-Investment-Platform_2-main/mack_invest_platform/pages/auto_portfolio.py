# pages/auto_portfolio.py  —  MAM v5 · Auto-Portefeuille IA
"""
La plateforme construit automatiquement un portefeuille selon les conditions de
marché (régime, macro, géopolitique, signaux ML), le backteste, mesure ses
risques, génère PDF / images et peut l'exécuter dans un portefeuille MAM.
"""
from __future__ import annotations

import html as _h

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ai_shared import (PLOT, all_portfolios, df_download, get_intel, kpi, kpi_row, md_bold,
                                  page_header, refresh_button, source_banner)
from components.ui import section_title
from utils.auto_portfolio import (METHODS, PROFILES, backtest, benchmarks, build_allocation,
                                  explain_allocation, fmt_metric, historical_worst, monte_carlo,
                                  perf_metrics, plan_orders, execute_orders, stress_test)
from utils.market_intel import ASSET_CLASSES, CLASS_COLORS, UNIVERSE, asset_class, asset_name
from utils.ml_engine import REGIME_COLORS


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_backtest(tickers: tuple, profile: str, method: str, smoothing: float, cost: float, _prices, _macro):
    return backtest(_prices[list(tickers)], _macro, profile, method, smoothing=smoothing, cost_bps=cost)


def render():
    c1, c2 = st.columns([6, 1])
    with c1:
        page_header("🤖 AUTO-PORTEFEUILLE IA",
                    "Construction automatique selon les conditions de marché · backtest · stress tests · "
                    "exports PDF & images · exécution en un clic", "#00ff88")
    with c2:
        st.markdown("<div style='padding-top:10px'></div>", unsafe_allow_html=True)
        refresh_button("auto_refresh")

    intel, news = get_intel()
    res = intel["res"]
    if not res.get("ok"):
        st.error(f"Modèle indisponible : {res.get('error')}")
        return
    source_banner(intel, news)
    reg = res["regimes"]
    regime = reg["current"] if reg.get("ok") else "Ralentissement"

    # ── Paramètres ────────────────────────────────────────────────────────────
    section_title("PARAMÈTRES", "⚙️")
    prof_names = list(PROFILES)
    default_prof = st.session_state.get("auto_profile", "Équilibré")
    cards = ""
    for p in prof_names:
        d = PROFILES[p]
        cards += (f'<div style="flex:1;min-width:170px;border:1px solid rgba(0,212,255,.15);border-radius:8px;'
                  f'padding:8px 12px;background:rgba(0,10,25,.4);"><b style="font-family:Rajdhani,sans-serif;color:#e2e8f0;">'
                  f'{d["emoji"]} {p}</b><div style="font-size:.66rem;color:#7a93b0;">{d["desc"]}</div></div>')
    st.markdown(f'<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:6px;">{cards}</div>',
                unsafe_allow_html=True)
    with st.form("auto_form"):
        c1, c2, c3 = st.columns([1.2, 1, 1.4])
        with c1:
            profile = st.selectbox("Profil de risque", prof_names, index=prof_names.index(default_prof)
                                   if default_prof in prof_names else 1)
            capital = st.number_input("Capital ($)", 10_000, 100_000_000, 1_000_000, 50_000)
        with c2:
            method = st.selectbox("Méthode", list(METHODS), format_func=lambda k: METHODS[k])
            max_w = st.slider("Poids max par ligne", 0.10, 0.50, PROFILES[profile]["max_w"], 0.05)
        with c3:
            classes = st.multiselect("Classes d'actifs autorisées", ASSET_CLASSES, default=ASSET_CLASSES)
            excl = st.multiselect("Exclure des actifs", list(UNIVERSE), format_func=lambda t: f"{t} — {asset_name(t)}")
        c4, c5, c6 = st.columns(3)
        with c4:
            do_bt = st.checkbox("Backtest walk-forward (≈ 20–60 s)", value=True)
        with c5:
            smoothing = st.slider("Lissage des rééquilibrages", 0.0, 0.8, 0.5, 0.1,
                                  help="Part de l'ancienne allocation conservée chaque mois (réduit rotation et frais)")
        with c6:
            cost = st.number_input("Frais de transaction (pb)", 0.0, 100.0, 10.0, 1.0)
        go_btn = st.form_submit_button("⚡ CONSTRUIRE LE PORTEFEUILLE", use_container_width=True)

    if go_btn:
        px_all = intel["prices"]
        tickers = [t for t in px_all.columns if asset_class(t) in classes and t not in excl]
        if len(tickers) < 3:
            st.error("Sélectionnez au moins 3 actifs.")
            return
        with st.spinner("Optimisation de l'allocation…"):
            alloc = build_allocation(px_all[tickers], res["signals"], regime, reg.get("inflation_flag", False),
                                     profile, method, intel["conf"], news, max_w=max_w)
        ctx = {"alloc": alloc, "signals": res["signals"], "capital": float(capital),
               "validation": res["validation"], "regimes": reg, "macro_rows": intel["macro_rows"],
               "macro_score": intel["macro_score"], "news": news, "source": intel["source"],
               "spy": px_all["SPY"].dropna() if "SPY" in px_all else None}
        ctx["explanation"] = explain_allocation(alloc, res["signals"],
                                                float(reg["current_proba"][regime]) if reg.get("ok") else None,
                                                intel["macro_score"], news["gpr"])
        ctx["stress"] = stress_test(alloc["weights"])
        ctx["worst"] = historical_worst(alloc["weights"], px_all)
        bt = {"ok": False}
        if do_bt:
            bar = st.progress(0.0, text="Backtest walk-forward…")
            bt = _cached_backtest(tuple(tickers), profile, method, float(smoothing), float(cost),
                                  px_all, intel["macro"])
            bar.empty()
            if not bt.get("ok"):
                st.warning(f"Backtest impossible : {bt.get('error')}")
        ctx["bt"] = bt
        if bt.get("ok"):
            ctx["bench"] = benchmarks(px_all, bt["start"], bt["end"])
            ctx["metrics"] = perf_metrics(bt["returns"], ctx["bench"].iloc[:, 0] if len(ctx["bench"].columns) else None)
            ctx["mc"] = monte_carlo(bt["returns"], float(capital))
        else:
            hist_r = alloc["daily"][alloc["weights"].index].fillna(0) @ alloc["weights"].values
            ctx["mc"] = monte_carlo(hist_r, float(capital))
        st.session_state["auto_ctx"] = ctx
        st.session_state.pop("auto_pdf", None)
        st.session_state.pop("auto_zip", None)

    ctx = st.session_state.get("auto_ctx")
    if not ctx:
        st.info("Choisissez vos paramètres puis cliquez sur **⚡ Construire le portefeuille**. L'algorithme "
                f"tiendra compte du régime actuel (**{regime}**), du contexte macro, des actualités "
                f"géopolitiques et des signaux du modèle ML.")
        return

    alloc = ctx["alloc"]
    st_ = alloc["stats"]
    bt = ctx.get("bt") or {}
    m = ctx.get("metrics", {})
    kpi_row([
        kpi("Profil", f"{PROFILES[alloc['profile']]['emoji']} {alloc['profile']}", METHODS[alloc["method"]][:34]),
        kpi("Régime pris en compte", alloc["regime"], "inflation ⚠️" if alloc["inflation"] else "",
            REGIME_COLORS.get(alloc["regime"], "#e2e8f0")),
        kpi("Rendement attendu", f"{st_['return']:+.1%}", "Black-Litterman, annuel",
            "#00ff88" if st_["return"] > 0 else "#ff3b6b"),
        kpi("Volatilité estimée", f"{st_['volatility']:.1%}",
            f"cible {PROFILES[alloc['profile']]['target_vol']:.0%}"),
        kpi("Backtest · rdt annualisé", f"{m['Rendement annualisé']:+.1%}" if m else "—",
            f"Sharpe {m['Sharpe']:.2f} · DD {m['Drawdown max']:.0%}" if m else "non calculé"),
    ])

    tabs = st.tabs(["📊 ALLOCATION", "📈 BACKTEST", "⚠️ RISQUES", "📄 EXPORTS PDF & IMAGES", "✅ APPLIQUER"])
    with tabs[0]:
        _tab_alloc(ctx)
    with tabs[1]:
        _tab_backtest(ctx)
    with tabs[2]:
        _tab_risk(ctx)
    with tabs[3]:
        _tab_exports(ctx)
    with tabs[4]:
        _tab_apply(ctx)


# ─────────────────────────────────────────────────────────────────────────────
def _tab_alloc(ctx):
    alloc, sig, cap = ctx["alloc"], ctx["signals"], ctx["capital"]
    w = alloc["weights"][alloc["weights"] > 0]
    c1, c2 = st.columns([1, 1.3])
    with c1:
        bc = alloc["by_class"][alloc["by_class"] > 0.001]
        fig = go.Figure(go.Pie(labels=bc.index, values=bc.values, hole=.55, sort=False,
                               marker=dict(colors=[CLASS_COLORS.get(c, "#888") for c in bc.index]),
                               textinfo="label+percent"))
        fig.update_layout(**{k: v for k, v in PLOT.items() if k not in ("xaxis", "yaxis")}, height=330,
                          showlegend=False, title="Par classe d'actifs")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = go.Figure(go.Bar(x=w.values, y=[f"{t} · {asset_name(t)}" for t in w.index], orientation="h",
                               marker_color=[CLASS_COLORS.get(asset_class(t), "#888") for t in w.index],
                               text=[f"{v:.1%}" for v in w.values], textposition="auto"))
        fig.update_layout(**PLOT, height=330, title="Par ligne")
        fig.update_yaxes(autorange="reversed")
        fig.update_xaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    section_title("POURQUOI CETTE ALLOCATION ?", "🧠")
    st.markdown("".join(f'<div style="padding:5px 0 5px 12px;border-left:2px solid rgba(0,255,136,.4);margin:4px 0;'
                        f'font-size:.82rem;color:#cbd5e1;line-height:1.55;">{md_bold(x)}</div>'
                        for x in ctx["explanation"]), unsafe_allow_html=True)

    section_title("DÉTAIL DES LIGNES", "📋")
    rows = []
    for t, v in w.items():
        s = sig.loc[t] if t in sig.index else None
        rows.append({"Ticker": t, "Actif": asset_name(t), "Classe": asset_class(t), "Poids": v,
                     "Montant ($)": v * cap, "Rdt a priori": alloc["pi"].get(t, np.nan),
                     "Vue ML": alloc["views"].get(t, np.nan), "Rdt Black-Litterman": alloc["mu_bl"].get(t, np.nan),
                     "P(hausse 1 m)": s["p_up"] if s is not None else np.nan,
                     "Signal": s["signal"] if s is not None else "—",
                     "Contribution au risque": alloc["risk_contrib"].get(t, np.nan)})
    df = pd.DataFrame(rows)
    st.dataframe(df.style.format({"Poids": "{:.1%}", "Montant ($)": "{:,.0f}", "Rdt a priori": "{:+.1%}",
                                  "Vue ML": "{:+.1%}", "Rdt Black-Litterman": "{:+.1%}", "P(hausse 1 m)": "{:.0%}",
                                  "Contribution au risque": "{:.1%}"}, na_rep="—"),
                 use_container_width=True, hide_index=True)
    st.caption("Bornes appliquées (profil ajusté au régime) : " +
               " · ".join(f"{c} {lo:.0%}–{hi:.0%}" for c, (lo, hi) in alloc["bounds"].items()))


# ─────────────────────────────────────────────────────────────────────────────
def _tab_backtest(ctx):
    bt = ctx.get("bt") or {}
    if not bt.get("ok"):
        st.info("Backtest non calculé (cochez l'option puis reconstruisez) ou historique insuffisant.")
        return
    st.markdown(
        f'<div style="font-size:.78rem;color:#94a3b8;line-height:1.6;">Backtest <b>walk-forward</b> du '
        f'{bt["start"]:%d/%m/%Y} au {bt["end"]:%d/%m/%Y} : chaque mois, le régime est re-détecté et '
        f'l\'allocation recalculée avec les seules données disponibles à cette date ; le modèle ML est '
        f'ré-entraîné tous les 3 mois. Frais {bt["cost_bps"]:.0f} pb, rotation annuelle {bt["turnover"]:.0%}. '
        f'Les actualités, faute d\'historique fiable, n\'interviennent pas dans le backtest.</div>',
        unsafe_allow_html=True)
    bench = ctx["bench"]
    series = {"Stratégie IA": bt["returns"], **{c: bench[c] for c in bench.columns}}
    colors = ["#00ff88", "#00d4ff", "#7c3aed", "#94a3b8"]
    fig = go.Figure()
    for i, (n, r) in enumerate(series.items()):
        eq = (1 + r.fillna(0)).cumprod() * ctx["capital"]
        fig.add_trace(go.Scatter(x=eq.index, y=eq, name=n, line=dict(color=colors[i % 4], width=2.4 if i == 0 else 1.3)))
    fig.update_layout(**PLOT, height=380, title="Valeur du portefeuille ($)", legend=dict(orientation="h", y=-0.12))
    st.plotly_chart(fig, use_container_width=True)

    mets = {n: (ctx["metrics"] if n == "Stratégie IA" else perf_metrics(r)) for n, r in series.items()}
    keys = ["Performance totale", "Rendement annualisé", "Volatilité", "Sharpe", "Sortino", "Drawdown max",
            "Calmar", "VaR 95 % (1 j)", "CVaR 95 % (1 j)", "Meilleur mois", "Pire mois", "Mois positifs"]
    tab = pd.DataFrame({n: [fmt_metric(k, mm.get(k, np.nan)) for k in keys] for n, mm in mets.items()}, index=keys)
    extra = {k: fmt_metric(k, ctx["metrics"].get(k, np.nan)) for k in ("Bêta", "Alpha (Jensen)", "Tracking error",
                                                                     "Ratio d'information")}
    c1, c2 = st.columns([2.2, 1])
    with c1:
        st.dataframe(tab, use_container_width=True)
    with c2:
        st.markdown("<br>".join(f'<span style="color:#64748b;font-size:.72rem;">{k} vs S&P 500</span> '
                                f'<b style="color:#e2e8f0;font-family:Share Tech Mono,monospace;">{v}</b>'
                                for k, v in extra.items()), unsafe_allow_html=True)

    eq = (1 + bt["returns"]).cumprod()
    dd = eq / eq.cummax() - 1
    fig = go.Figure(go.Scatter(x=dd.index, y=dd, fill="tozeroy", line=dict(color="#ff3b6b", width=1)))
    fig.update_layout(**PLOT, height=220, title="Drawdown de la stratégie")
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

    W = bt["weights"]
    Wc = W.T.groupby(lambda t: asset_class(t)).sum().T
    fig = go.Figure()
    for c in [x for x in ASSET_CLASSES if x in Wc.columns]:
        fig.add_trace(go.Scatter(x=Wc.index, y=Wc[c], name=c, stackgroup="one", mode="none",
                                 fillcolor=CLASS_COLORS.get(c)))
    fig.update_layout(**PLOT, height=280, title="Évolution de l'allocation par classe (choix mensuels)",
                      legend=dict(orientation="h", y=-0.2))
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    st.plotly_chart(fig, use_container_width=True)
    regs = bt["regimes"].value_counts()
    st.caption("Régimes détectés aux dates de rééquilibrage : " + " · ".join(f"{k} {v}" for k, v in regs.items()))


# ─────────────────────────────────────────────────────────────────────────────
def _tab_risk(ctx):
    alloc, cap = ctx["alloc"], ctx["capital"]
    c1, c2 = st.columns(2)
    with c1:
        section_title("CONTRIBUTIONS AU RISQUE", "🧩")
        w = alloc["weights"][alloc["weights"] > 0]
        rc = alloc["risk_contrib"].reindex(w.index).fillna(0)
        fig = go.Figure()
        fig.add_trace(go.Bar(x=w.index, y=w.values, name="Poids", marker_color="#00d4ff"))
        fig.add_trace(go.Bar(x=w.index, y=rc.values, name="Contribution au risque", marker_color="#ffd700"))
        fig.update_layout(**PLOT, height=320, barmode="group", legend=dict(orientation="h", y=1.12))
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        section_title("STRESS TESTS", "💥")
        s = ctx["stress"].sort_values("Impact")
        fig = go.Figure(go.Bar(x=s["Impact"], y=s["Scénario"], orientation="h",
                               marker_color=["#00ff88" if v >= 0 else "#ff3b6b" for v in s["Impact"]],
                               text=[f"{v:+.1%} ({v * cap:+,.0f} $)" for v in s["Impact"]], textposition="auto"))
        fig.update_layout(**PLOT, height=320)
        fig.update_xaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
    wst = ctx.get("worst") or {}
    if wst:
        st.markdown(f'<div style="font-size:.8rem;color:#cbd5e1;">📉 Pire mois historique de cette allocation '
                    f'(rejouée sur la période) : <b style="color:#ff3b6b">{wst["perte"]:+.1%}</b> '
                    f'({wst["perte"] * cap:+,.0f} $) entre le {wst["debut"]:%d/%m/%Y} et le {wst["fin"]:%d/%m/%Y}.</div>',
                    unsafe_allow_html=True)
    st.caption("Scénarios hypothétiques inspirés d'épisodes historiques (2008, mars 2020, 2022, choc pétrolier…), "
               "appliqués par sous-classe d'actifs.")
    mc = ctx.get("mc")
    if mc:
        section_title("PROJECTION MONTE CARLO À 1 AN", "🎲")
        p = mc["percentiles"]
        x = np.arange(len(p))
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x, y=p["p95"], line=dict(width=0), showlegend=False))
        fig.add_trace(go.Scatter(x=x, y=p["p5"], fill="tonexty", fillcolor="rgba(0,212,255,.12)",
                                 line=dict(width=0), name="5 %–95 %"))
        fig.add_trace(go.Scatter(x=x, y=p["p75"], line=dict(width=0), showlegend=False))
        fig.add_trace(go.Scatter(x=x, y=p["p25"], fill="tonexty", fillcolor="rgba(0,212,255,.28)",
                                 line=dict(width=0), name="25 %–75 %"))
        fig.add_trace(go.Scatter(x=x, y=p["p50"], line=dict(color="#00d4ff", width=2), name="Médiane"))
        fig.add_hline(y=cap, line_dash="dot", line_color="rgba(255,255,255,.35)")
        fig.update_layout(**PLOT, height=320, legend=dict(orientation="h", y=1.1), xaxis_title="jours de bourse")
        st.plotly_chart(fig, use_container_width=True)
        kpi_row([kpi("Valeur médiane à 1 an", f"{np.median(mc['final']):,.0f} $"),
                 kpi("Scénario défavorable (5 %)", f"{mc['p5']:,.0f} $", color="#ff3b6b"),
                 kpi("Scénario favorable (95 %)", f"{mc['p95']:,.0f} $", color="#00ff88"),
                 kpi("Probabilité de perte", f"{mc['prob_loss']:.0%}")])


# ─────────────────────────────────────────────────────────────────────────────
def _tab_exports(ctx):
    from utils import reporting as R
    from utils.report_builders import auto_images, auto_pdf

    section_title("RAPPORT PDF", "📄")
    st.caption("Rapport complet : synthèse et justification, allocation, contexte macro & géopolitique, backtest, "
               "risques, signaux ML et méthodologie.")
    if st.button("🧾 Générer le rapport PDF", key="auto_gen_pdf", use_container_width=True):
        with st.spinner("Création des graphiques et du PDF…"):
            ctx["images"] = auto_images(ctx, "light")
            st.session_state["auto_pdf"] = auto_pdf(ctx)
    if st.session_state.get("auto_pdf"):
        st.download_button("⬇️ Télécharger le PDF", st.session_state["auto_pdf"],
                           file_name=f"MAM_auto_portefeuille_{ctx['alloc']['profile']}_{pd.Timestamp.today():%Y%m%d}.pdf",
                           mime="application/pdf", key="auto_dl_pdf", use_container_width=True)

    section_title("IMAGES DE PERFORMANCE (PNG)", "🖼️")
    theme = st.radio("Thème des images", ["Clair (impression)", "Sombre (plateforme)"], horizontal=True, key="auto_theme")
    th = "light" if theme.startswith("Clair") else "dark"
    if st.button("🎨 Générer les images", key="auto_gen_img", use_container_width=True):
        with st.spinner("Rendu des graphiques…"):
            st.session_state["auto_imgs"] = (th, auto_images(ctx, th))
    got = st.session_state.get("auto_imgs")
    if got:
        th_, imgs = got
        st.download_button("⬇️ Télécharger toutes les images (.zip)", R.zip_images(imgs),
                           file_name=f"MAM_auto_portefeuille_images_{th_}.zip", mime="application/zip",
                           key="auto_dl_zip", use_container_width=True)
        names = list(imgs)
        sel = st.selectbox("Aperçu", names, format_func=lambda n: n[3:].replace("_", " ").capitalize(), key="auto_img_sel")
        st.image(imgs[sel], use_container_width=True)
        st.download_button(f"⬇️ {sel}.png", imgs[sel], file_name=f"{sel}.png", mime="image/png", key="auto_dl_one")

    section_title("DONNÉES", "🗂️")
    w = ctx["alloc"]["weights"]
    df = pd.DataFrame({"actif": [asset_name(t) for t in w.index], "classe": [asset_class(t) for t in w.index],
                       "poids": w.values, "montant": w.values * ctx["capital"]}, index=w.index)
    c1, c2 = st.columns(2)
    with c1:
        df_download(df, "allocation.csv", "⬇️ Allocation (CSV)", "auto_dl_alloc")
    with c2:
        bt = ctx.get("bt") or {}
        if bt.get("ok"):
            eq = pd.DataFrame({"strategie": (1 + bt["returns"]).cumprod()})
            for c in ctx["bench"].columns:
                eq[c] = (1 + ctx["bench"][c]).cumprod()
            df_download(eq, "backtest.csv", "⬇️ Backtest (CSV)", "auto_dl_bt")


# ─────────────────────────────────────────────────────────────────────────────
def _tab_apply(ctx):
    from utils.data import get_multi_prices, persist

    ports = all_portfolios()
    if not ports:
        st.info("Aucun portefeuille : créez-en un depuis le Dashboard pour y appliquer l'allocation.")
        return
    section_title("EXÉCUTER L'ALLOCATION DANS UN PORTEFEUILLE", "✅")
    active = st.session_state.get("active_portfolio")
    keys = list(ports)
    pid = st.selectbox("Portefeuille cible", keys, index=keys.index(active) if active in keys else 0,
                       format_func=lambda k: ports[k][0], key="auto_apply_port")
    port = ports[pid][1]
    c1, c2 = st.columns(2)
    with c1:
        mode = st.radio("Mode", ["Investir uniquement le cash disponible", "Rééquilibrage complet (vend les lignes hors cible)"],
                        key="auto_apply_mode")
    with c2:
        pct = st.slider("Part à investir", 0.1, 1.0, 1.0, 0.05, key="auto_apply_pct")
    w = ctx["alloc"]["weights"][ctx["alloc"]["weights"] > 0]
    live = get_multi_prices(tuple(sorted(set(w.index) | set(port.get("holdings", {}).keys()))))
    orders = plan_orders(port, w, live, pct, "cash" if mode.startswith("Investir") else "full")
    if "BIL" in w.index:
        st.caption(f"La poche monétaire (BIL, {w['BIL']:.0%}) est conservée en liquidités.")
    if orders.empty:
        st.info("Aucun ordre nécessaire (cash insuffisant ou portefeuille déjà aligné).")
        return
    # Aperçu des contrôles de conformité (chaque ordre est re-contrôlé à l'exécution)
    try:
        from utils.compliance import pre_trade_spot, get_profile
        verdicts = []
        for _, o in orders.iterrows():
            dec = pre_trade_spot(port, o["ticker"], o["action"], float(o["qty"]), float(o["price"]))
            verdicts.append("✅ conforme" if dec.allowed else
                            "⛔ " + ", ".join(f"[{c.code}] {c.title}" for c in dec.blocks))
        orders = orders.assign(conformité=verdicts)
        st.caption(f"🛡️ Contrôles de conformité selon votre profil **{get_profile()['risque']}** "
                   "(détail des règles : Trading Desk → Mes positions → Exposition & conformité). "
                   "Les ordres bloqués ne seront pas exécutés.")
    except Exception:
        pass
    st.dataframe(orders.style.format({"qty": "{:,.4f}", "price": "{:,.2f}", "montant": "{:,.0f}"}),
                 use_container_width=True, hide_index=True)
    buy, sell = orders.loc[orders.action == "BUY", "montant"].sum(), orders.loc[orders.action == "SELL", "montant"].sum()
    st.markdown(f'<div style="font-size:.8rem;color:#cbd5e1;">Achats <b style="color:#00ff88">{buy:,.0f} $</b> · '
                f'Ventes <b style="color:#ff3b6b">{sell:,.0f} $</b> · Cash avant <b>{port.get("cash", 0):,.0f} $</b> → '
                f'après ≈ <b>{port.get("cash", 0) + sell - buy:,.0f} $</b></div>', unsafe_allow_html=True)
    if not mode.startswith("Investir"):
        st.warning("Le rééquilibrage complet vend les positions spot qui ne font pas partie de l'allocation cible.")
    confirm = st.checkbox("Je confirme l'exécution simulée de ces ordres", key="auto_apply_ok")
    if st.button("🚀 EXÉCUTER LES ORDRES", disabled=not confirm, use_container_width=True, key="auto_apply_go"):
        errs = execute_orders(port, orders.drop(columns=["conformité"], errors="ignore"))
        persist()
        if errs:
            st.warning("Ordres partiellement exécutés : " + "; ".join(errs))
        else:
            st.success(f"✅ {len(orders)} ordres exécutés dans {ports[pid][0]}.")
        st.balloons()
