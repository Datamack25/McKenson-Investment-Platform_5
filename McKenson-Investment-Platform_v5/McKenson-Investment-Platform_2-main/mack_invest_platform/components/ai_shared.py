# components/ai_shared.py  —  MAM v5 · Briques communes aux pages IA
from __future__ import annotations

import html as _h

import pandas as pd
import streamlit as st

from utils.market_intel import (UNIVERSE, analyse_news, fetch_macro, fetch_news, fetch_prices,
                                macro_dashboard, macro_features, macro_risk_score, now_str)
from utils.ml_engine import confidence_from_validation, run_pipeline

PLOT = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#94a3b8", family="Share Tech Mono", size=11),
            margin=dict(l=8, r=8, t=36, b=8),
            xaxis=dict(gridcolor="rgba(255,255,255,.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,.05)"))

STRAT_TO_PROFILE = {"growth": "Dynamique", "momentum": "Dynamique", "value": "Équilibré",
                    "income": "Prudent", "macro": "Équilibré", "hedging": "Prudent",
                    "balanced": "Équilibré", "commodity": "Dynamique", "crypto": "Agressif",
                    "arbitrage": "Prudent"}


@st.cache_data(ttl=3600, show_spinner=False)
def load_intel(period: str = "5y") -> dict:
    """Données + modèle ML entraîné + régimes (mis en cache 1 h)."""
    px, src = fetch_prices(tuple(UNIVERSE), period)
    mac, msrc = fetch_macro(period)
    res = run_pipeline(px, mac)
    mf = macro_features(mac, px)
    rows = macro_dashboard(mac, mf)
    return {"prices": px, "source": src, "macro": mac, "macro_source": msrc, "res": res,
            "macro_rows": rows, "macro_score": macro_risk_score(rows),
            "conf": confidence_from_validation(res.get("validation", {})) if res.get("ok") else 0.1,
            "built_at": now_str()}


@st.cache_data(ttl=900, show_spinner=False)
def load_news() -> dict:
    news, src = fetch_news()
    v = analyse_news(news)
    v["source"] = src
    return v


def get_intel() -> tuple[dict, dict]:
    with st.spinner("🧠 Chargement des marchés et entraînement du modèle (≈ 30 s la première fois)…"):
        intel = load_intel()
    with st.spinner("🛰️ Lecture des actualités…"):
        news = load_news()
    return intel, news


def refresh_button(key: str):
    if st.button("🔄 Ré-entraîner", key=key, help="Recharge les données, les actualités et ré-entraîne le modèle",
                 use_container_width=True):
        load_intel.clear()
        load_news.clear()
        fetch_prices.clear()
        fetch_macro.clear()
        fetch_news.clear()
        st.rerun()


def page_header(title: str, subtitle: str, color: str = "#00d4ff"):
    st.markdown(
        f'<h1 style="font-family:Rajdhani,sans-serif;font-size:2rem;letter-spacing:.12em;'
        f'color:{color};margin:0 0 2px;text-shadow:0 0 30px {color}66;">{title}</h1>'
        f'<div style="font-family:Share Tech Mono,monospace;font-size:.72rem;color:#7a93b0;'
        f'margin-bottom:10px;">{subtitle}</div>', unsafe_allow_html=True)


def source_banner(intel: dict, news: dict):
    src = intel["source"]
    if src == "simulé" or intel["macro_source"] == "simulé":
        st.warning("⚠️ Yahoo Finance est injoignable : les cours affichés sont **simulés** (mode démonstration). "
                   "Les signaux et portefeuilles ne reflètent pas le marché réel. Cliquez sur 🔄 pour réessayer.")
    elif src == "partiel":
        st.info("ℹ️ Certaines séries n'ont pas pu être téléchargées ; les actifs manquants sont exclus.")
    if news.get("source") == "exemple":
        st.caption("📰 Flux d'actualités indisponible — titres d'exemple utilisés pour l'analyse géopolitique.")
    st.caption(f"Données : {src} · macro : {intel['macro_source']} · actualités : {news.get('source')} · "
               f"modèle entraîné le {intel['built_at']}")


def kpi(label: str, value: str, sub: str = "", color: str = "#e2e8f0") -> str:
    return (f'<div style="flex:1;min-width:150px;background:rgba(0,212,255,.04);border:1px solid '
            f'rgba(0,212,255,.14);border-radius:8px;padding:10px 14px;">'
            f'<div style="font-family:Rajdhani,sans-serif;font-size:.62rem;letter-spacing:.16em;color:#64748b;'
            f'text-transform:uppercase;">{_h.escape(label)}</div>'
            f'<div style="font-family:Share Tech Mono,monospace;font-size:1.25rem;color:{color};">{_h.escape(value)}</div>'
            f'<div style="font-family:Share Tech Mono,monospace;font-size:.64rem;color:#7a93b0;">{_h.escape(sub)}</div></div>')


def kpi_row(items: list[str]):
    st.markdown('<div style="display:flex;gap:10px;flex-wrap:wrap;margin:6px 0 14px;">' + "".join(items) +
                "</div>", unsafe_allow_html=True)


def md_bold(text: str) -> str:
    """Les justifications utilisent **gras** : conversion HTML sûre."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b style='color:#e2e8f0'>\1</b>", _h.escape(text))


def active_portfolio() -> tuple[str | None, dict | None]:
    state = st.session_state.get("mam_state", {})
    tid, pid = st.session_state.get("active_team"), st.session_state.get("active_portfolio")
    try:
        return pid, state["teams"][tid]["portfolios"][pid]
    except Exception:
        return None, None


def all_portfolios() -> dict[str, tuple[str, dict]]:
    state = st.session_state.get("mam_state", {})
    out = {}
    for tid, team in state.get("teams", {}).items():
        for pid, p in team.get("portfolios", {}).items():
            out[pid] = (f'{team.get("emoji", "")} {team.get("name", "")} › {p.get("emoji", "📁")} {p.get("name", "")}', p)
    return out


def df_download(df: pd.DataFrame, name: str, label: str, key: str):
    st.download_button(label, df.to_csv(index=True).encode("utf-8-sig"), file_name=name,
                       mime="text/csv", key=key, use_container_width=True)
