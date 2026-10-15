# pages/reports.py  —  MAM v5 · Rapports PDF & images de performance
from __future__ import annotations

import pandas as pd
import streamlit as st

from components.ai_shared import all_portfolios, kpi, kpi_row, page_header
from components.ui import section_title


@st.cache_data(ttl=1800, show_spinner=False)
def _history(tickers: tuple):
    from utils.market_intel import fetch_prices
    return fetch_prices(tickers, "1y")


def render():
    from utils import reporting as R
    from utils.data import get_multi_prices
    from utils.report_builders import portfolio_context, portfolio_images, portfolio_pdf

    page_header("📄 RAPPORTS", "Rapports PDF et images de performance de vos portefeuilles", "#ffd700")
    ports = all_portfolios()
    if not ports:
        st.info("Aucun portefeuille à analyser — créez-en un depuis le Dashboard.")
        return
    keys = list(ports)
    active = st.session_state.get("active_portfolio")
    c1, c2, c3 = st.columns([2, 1.2, 1])
    with c1:
        pid = st.selectbox("Portefeuille", keys, index=keys.index(active) if active in keys else 0,
                           format_func=lambda k: ports[k][0], key="rep_port")
    with c2:
        theme = st.radio("Thème des images", ["Clair", "Sombre"], horizontal=True, key="rep_theme")
    with c3:
        with_ml = st.checkbox("Inclure l'avis du modèle ML", value=True, key="rep_ml",
                              help="Utilise les signaux de la page IA Marchés (entraînement mis en cache)")
    port = ports[pid][1]
    holdings = tuple(sorted((port.get("holdings") or {}).keys()))

    if st.button("🧾 Générer le rapport", use_container_width=True, key="rep_go"):
        with st.spinner("Valorisation, historiques et graphiques…"):
            live = get_multi_prices(tuple(sorted(set(holdings) | {"SPY"}))) if holdings else {}
            hist, src = _history(tuple(sorted(set(holdings) | {"SPY"}))) if holdings else (pd.DataFrame(), "—")
            signals = None
            if with_ml and holdings:
                try:
                    from components.ai_shared import load_intel
                    intel = load_intel()
                    if intel["res"].get("ok"):
                        signals = intel["res"]["signals"]
                except Exception:
                    signals = None
            ctx = portfolio_context(port, live, hist, signals)
            th = "light" if theme == "Clair" else "dark"
            imgs = portfolio_images(ctx, th)
            ctx["images"] = imgs if th == "light" else portfolio_images(ctx, "light")
            pdf = portfolio_pdf(ctx)
        st.session_state["rep_out"] = {"pid": pid, "ctx": ctx, "imgs": imgs, "pdf": pdf, "src": src, "theme": th}

    out = st.session_state.get("rep_out")
    if not out or out["pid"] != pid:
        st.caption("Le rapport contient : positions et P&L, performance simulée des positions actuelles sur 1 an vs "
                   "S&P 500, drawdowns, rendements mensuels, stress tests, projection Monte Carlo, avis ML et "
                   "derniers ordres.")
        return
    ctx = out["ctx"]
    if out["src"] == "simulé":
        st.warning("⚠️ Historiques Yahoo Finance indisponibles : les courbes de performance utilisent des données simulées.")
    m = ctx.get("metrics", {})
    init = float(port.get("initial_cash", ctx["nav"]) or ctx["nav"])
    kpi_row([
        kpi("Valeur totale", f"{ctx['nav']:,.0f} $"),
        kpi("Depuis l'origine", f"{ctx['nav'] / init - 1:+.2%}", color="#00ff88" if ctx["nav"] >= init else "#ff3b6b"),
        kpi("Positions", str(len(ctx["pos"]))),
        kpi("Volatilité 1 an (simulée)", f"{m['Volatilité']:.1%}" if m else "—"),
        kpi("Drawdown max 1 an", f"{m['Drawdown max']:.1%}" if m else "—", color="#ff3b6b"),
    ])
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Télécharger le PDF", out["pdf"],
                           file_name=f"MAM_rapport_{port.get('name', 'portefeuille').replace(' ', '_')}_{pd.Timestamp.today():%Y%m%d}.pdf",
                           mime="application/pdf", use_container_width=True, key="rep_dl_pdf")
    with c2:
        if out["imgs"]:
            st.download_button("⬇️ Toutes les images (.zip)", R.zip_images(out["imgs"]),
                               file_name=f"MAM_images_{port.get('name', 'portefeuille').replace(' ', '_')}.zip",
                               mime="application/zip", use_container_width=True, key="rep_dl_zip")
    if not out["imgs"]:
        st.info("Portefeuille sans position : le PDF ne contient que le récapitulatif.")
        return
    section_title("APERÇU DES IMAGES", "🖼️")
    names = list(out["imgs"])
    cols = st.columns(2)
    for i, n in enumerate(names):
        with cols[i % 2]:
            st.image(out["imgs"][n], use_container_width=True)
            st.download_button(f"⬇️ {n}.png", out["imgs"][n], file_name=f"{n}.png", mime="image/png",
                               key=f"rep_img_{n}")
