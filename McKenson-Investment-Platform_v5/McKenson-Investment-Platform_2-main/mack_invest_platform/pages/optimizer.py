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

    page_header("📈 OPTIMISEUR", "Markowitz · CVaR · parité de risque · HRP · frontière efficiente", "#7c3aed")
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
