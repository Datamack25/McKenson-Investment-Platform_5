# pages/events.py  —  MAM Events & News
"""
Live financial & geopolitical news fetched from public RSS feeds (Reuters, FT, Bloomberg, BBC).
Falls back to curated market_events.csv when network is unavailable.
Timezone-safe datetime comparisons throughout.
"""
from __future__ import annotations

import json
import os
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import Optional

import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

from components.ui import section_title, metric_row

# ── Constants ─────────────────────────────────────────────────────────────────
_EVENTS_CSV = os.path.join(os.path.dirname(__file__), "..", "data", "market_events.csv")
_CACHE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "_news_cache.json")
_CACHE_TTL  = 3600  # 1 hour

_P = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94a3b8", family="Share Tech Mono"),
    margin=dict(l=8, r=8, t=28, b=8),
)

# RSS feeds — public, no auth required
_RSS_FEEDS = {
    "Reuters Markets":      "https://feeds.reuters.com/reuters/businessNews",
    "Reuters Tech":         "https://feeds.reuters.com/reuters/technologyNews",
    "FT Markets":           "https://www.ft.com/markets?format=rss",
    "BBC Business":         "https://feeds.bbci.co.uk/news/business/rss.xml",
    "CNBC Top News":        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "Yahoo Finance":        "https://finance.yahoo.com/news/rssindex",
    "Investing.com Crypto": "https://www.investing.com/rss/news_301.rss",
    "Seeking Alpha":        "https://seekingalpha.com/market_currents.xml",
}

_IMPACT_COLOR = {
    "high":   "#ff3b6b",
    "medium": "#ffd700",
    "low":    "#00ff88",
}

_CAT_ICON = {
    "Central Banks": "🏦",
    "Earnings":      "📊",
    "Commodities":   "🛢️",
    "Geopolitics":   "🌍",
    "Crypto":        "₿",
    "Macro":         "📈",
    "Tech":          "💻",
    "Live":          "📡",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _parse_rss_date(date_str: str) -> Optional[datetime]:
    """Parse RFC-2822 or ISO dates into timezone-aware UTC datetime."""
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _fetch_rss(url: str, timeout: int = 6) -> list[dict]:
    """Fetch and parse one RSS feed. Returns list of news items."""
    items = []
    try:
        resp = requests.get(url, timeout=timeout,
                            headers={"User-Agent": "MAM-NewsBot/1.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        ns   = {"atom": "http://www.w3.org/2005/Atom"}

        # Handle both RSS 2.0 (<item>) and Atom (<entry>)
        entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
        for entry in entries[:8]:  # max 8 per feed
            title = (
                getattr(entry.find("title"), "text", None)
                or getattr(entry.find("atom:title", ns), "text", None)
                or ""
            ).strip()
            link = (
                getattr(entry.find("link"), "text", None)
                or getattr(entry.find("atom:link", ns), "attrib", {}).get("href", "")
                or ""
            ).strip()
            pub = (
                getattr(entry.find("pubDate"), "text", None)
                or getattr(entry.find("dc:date", {"dc": "http://purl.org/dc/elements/1.1/"}), "text", None)
                or getattr(entry.find("atom:published", ns), "text", None)
                or ""
            ).strip()
            desc = (
                getattr(entry.find("description"), "text", None)
                or getattr(entry.find("atom:summary", ns), "text", None)
                or ""
            )
            if desc:
                import re
                desc = re.sub(r"<[^>]+>", "", desc).strip()[:200]

            dt = _parse_rss_date(pub) if pub else _now_utc()

            if title:
                items.append({
                    "title":       title,
                    "link":        link,
                    "published":   dt.isoformat() if dt else _now_utc().isoformat(),
                    "description": desc,
                    "source":      url,
                })
    except Exception:
        pass
    return items


def _load_cached_news() -> list[dict]:
    """Load news from disk cache if not stale."""
    try:
        if os.path.exists(_CACHE_FILE):
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            ts = datetime.fromisoformat(data.get("timestamp", "2000-01-01T00:00:00+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if (_now_utc() - ts).total_seconds() < _CACHE_TTL:
                return data.get("items", [])
    except Exception:
        pass
    return []


def _save_news_cache(items: list[dict]) -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_FILE), exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"timestamp": _now_utc().isoformat(), "items": items}, f, ensure_ascii=False)
    except Exception:
        pass


@st.cache_data(ttl=_CACHE_TTL)
def fetch_live_news() -> list[dict]:
    """Fetch from all RSS feeds, merge, deduplicate, sort by date."""
    # Try cache first (cross-session on disk)
    cached = _load_cached_news()
    if cached:
        return cached

    all_items: list[dict] = []
    for source_name, url in _RSS_FEEDS.items():
        items = _fetch_rss(url)
        for it in items:
            it["feed_name"] = source_name
        all_items.extend(items)

    if not all_items:
        return []

    # Deduplicate by title similarity
    seen: set[str] = set()
    unique: list[dict] = []
    for it in all_items:
        key = it["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(it)

    # Sort: most recent first (timezone-aware)
    def _sortkey(x):
        try:
            dt = datetime.fromisoformat(x["published"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return _now_utc() - timedelta(days=365)

    unique.sort(key=_sortkey, reverse=True)
    _save_news_cache(unique)
    return unique


def _load_static_events() -> pd.DataFrame:
    """Load curated events from CSV (always timezone-naive safe)."""
    try:
        df = pd.read_csv(_EVENTS_CSV, parse_dates=["date"])
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"], utc=False).dt.tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


def _category_icon(cat: str) -> str:
    for k, v in _CAT_ICON.items():
        if k.lower() in cat.lower():
            return v
    return "📌"


def _impact_badge(impact: str) -> str:
    col = _IMPACT_COLOR.get(impact.lower(), "#7a93b0")
    return (
        f'<span style="background:rgba(255,255,255,.06);border:1px solid {col};'
        f'border-radius:3px;padding:1px 7px;font-size:.62rem;font-family:Rajdhani;'
        f'color:{col};font-weight:700;letter-spacing:.08em;text-transform:uppercase;">'
        f'{impact.upper()}</span>'
    )


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    st.markdown(
        '<h1 style="font-family:Rajdhani,sans-serif;font-size:2rem;letter-spacing:.12em;'
        'color:#00d4ff;margin:0 0 2px;text-shadow:0 0 30px rgba(0,212,255,.4);">'
        '📡 EVENTS & NEWS — MAM</h1>',
        unsafe_allow_html=True,
    )

    tab_live, tab_calendar, tab_impact = st.tabs([
        "📡 LIVE NEWS FEED",
        "📅 ÉVÉNEMENTS MARCHÉ",
        "📊 ANALYSE D'IMPACT",
    ])

    with tab_live:
        _live_news_tab()
    with tab_calendar:
        _market_events_tab()
    with tab_impact:
        _impact_analysis_tab()


# ── Tab 1 — Live RSS news ─────────────────────────────────────────────────────

def _live_news_tab():
    section_title("ACTUALITÉS FINANCIÈRES EN DIRECT", "📡")

    col_ref, col_filter = st.columns([1, 3])
    with col_ref:
        if st.button("🔄 Actualiser", key="news_refresh"):
            st.cache_data.clear()
            st.rerun()
    with col_filter:
        feed_filter = st.multiselect(
            "Sources",
            list(_RSS_FEEDS.keys()),
            default=list(_RSS_FEEDS.keys())[:4],
            key="news_src_filter",
        )

    with st.spinner("📡 Chargement des actualités…"):
        news_items = fetch_live_news()

    if not news_items:
        st.warning(
            "⚠️ Impossible de récupérer les actualités en direct. "
            "Vérifiez la connexion réseau. Les données statiques sont affichées ci-dessous."
        )
        _show_static_fallback()
        return

    # Filter by selected feeds
    if feed_filter:
        filtered = [it for it in news_items if it.get("feed_name", "") in feed_filter]
    else:
        filtered = news_items

    st.markdown(
        f'<div style="font-family:Share Tech Mono;font-size:.7rem;color:#7a93b0;'
        f'margin-bottom:12px;">'
        f'📊 {len(filtered)} articles • '
        f'Mis à jour : {_now_utc().strftime("%H:%M UTC")}'
        f'</div>',
        unsafe_allow_html=True,
    )

    keyword = st.text_input("🔍 Filtrer les titres", "", key="news_kw",
                             placeholder="ex: Fed, NVIDIA, Bitcoin, inflation…")

    if keyword:
        filtered = [it for it in filtered
                    if keyword.lower() in it["title"].lower()
                    or keyword.lower() in it.get("description", "").lower()]

    _render_news_cards(filtered[:40])


def _render_news_cards(items: list[dict]):
    """Render news as styled cards with source, date, link."""
    if not items:
        st.info("Aucun article trouvé.")
        return

    for it in items:
        title = it.get("title", "—")
        link  = it.get("link", "")
        desc  = it.get("description", "")
        feed  = it.get("feed_name", "")

        try:
            dt = datetime.fromisoformat(it.get("published", ""))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            age_h = (_now_utc() - dt).total_seconds() / 3600
            if age_h < 1:
                age_str = f"{int(age_h * 60)}min"
            elif age_h < 24:
                age_str = f"{int(age_h)}h"
            else:
                age_str = f"{int(age_h/24)}j"
            date_disp = dt.strftime("%d %b %H:%M UTC")
        except Exception:
            age_str   = "—"
            date_disp = "—"

        # Color by recency
        border_col = "#00d4ff" if age_str.endswith("min") else \
                     "#ffd700"  if age_str.endswith("h")   else "#2a3a52"

        link_tag = (f'<a href="{link}" target="_blank" style="color:#00d4ff;'
                    f'text-decoration:none;font-size:.65rem;font-family:Rajdhani;">'
                    f'🔗 Lire l\'article</a>') if link else ""

        st.markdown(
            f'<div style="background:rgba(0,0,0,.25);border-left:3px solid {border_col};'
            f'border-radius:0 6px 6px 0;padding:12px 16px;margin-bottom:8px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">'
            f'<div style="font-family:Rajdhani;font-size:.95rem;font-weight:700;color:#e2e8f0;'
            f'line-height:1.4;flex:1;">{title}</div>'
            f'<div style="font-family:Share Tech Mono;font-size:.6rem;color:{border_col};'
            f'white-space:nowrap;padding-top:2px;">{age_str}</div>'
            f'</div>'
            f'<div style="font-family:Share Tech Mono;font-size:.68rem;color:#7a93b0;'
            f'margin:4px 0 6px;">{desc[:160] + "…" if len(desc) > 160 else desc}</div>'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-family:Share Tech Mono;font-size:.6rem;color:#475569;">'
            f'📰 {feed} · {date_disp}</span>'
            f'{link_tag}'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def _show_static_fallback():
    """Show curated static events when RSS unavailable."""
    df = _load_static_events()
    if df.empty:
        st.info("Aucun événement statique disponible.")
        return
    section_title("ÉVÉNEMENTS RÉCENTS (données statiques)", "📋")
    for _, row in df.iterrows():
        cat  = str(row.get("category", ""))
        icon = _category_icon(cat)
        impact = str(row.get("impact", "medium"))
        st.markdown(
            f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.06);'
            f'border-radius:6px;padding:10px 14px;margin-bottom:6px;">'
            f'{icon} <b style="color:#e2e8f0;">{row.get("headline","")}</b> '
            f'{_impact_badge(impact)}'
            f'<div style="font-family:Share Tech Mono;font-size:.68rem;color:#7a93b0;margin-top:4px;">'
            f'{row.get("description","")}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Tab 2 — Market events calendar ───────────────────────────────────────────

def _market_events_tab():
    section_title("CALENDRIER DES ÉVÉNEMENTS DE MARCHÉ", "📅")

    df = _load_static_events()
    if df.empty:
        st.info("Aucun événement trouvé dans market_events.csv.")
        return

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        cats = ["Tous"] + sorted(df["category"].dropna().unique().tolist())
        cat_sel = st.selectbox("Catégorie", cats, key="evt_cat")
    with col2:
        impacts = ["Tous", "high", "medium", "low"]
        imp_sel = st.selectbox("Impact", impacts, key="evt_imp")
    with col3:
        active_sel = st.radio("Statut", ["Tous", "Actif", "Passé"], horizontal=True, key="evt_active")

    df_f = df.copy()
    if cat_sel != "Tous":
        df_f = df_f[df_f["category"] == cat_sel]
    if imp_sel != "Tous":
        df_f = df_f[df_f["impact"] == imp_sel]
    if active_sel == "Actif":
        df_f = df_f[df_f.get("active", pd.Series(True, index=df_f.index)).astype(bool)]
    elif active_sel == "Passé":
        df_f = df_f[~df_f.get("active", pd.Series(True, index=df_f.index)).astype(bool)]

    st.markdown(
        f'<div style="font-family:Share Tech Mono;font-size:.7rem;color:#7a93b0;margin-bottom:10px;">'
        f'{len(df_f)} événements</div>',
        unsafe_allow_html=True,
    )

    # Sort by date desc (timezone-naive safe)
    if "date" in df_f.columns:
        df_f = df_f.sort_values("date", ascending=False)

    for _, row in df_f.iterrows():
        cat      = str(row.get("category", ""))
        impact   = str(row.get("impact", "medium"))
        icon     = _category_icon(cat)
        imp_col  = _IMPACT_COLOR.get(impact, "#7a93b0")
        is_active = bool(row.get("active", True))
        status_badge = (
            '<span style="background:rgba(0,255,136,.12);border:1px solid #00ff88;'
            'border-radius:3px;padding:1px 6px;font-size:.6rem;color:#00ff88;">ACTIF</span>'
            if is_active else
            '<span style="background:rgba(148,163,184,.08);border:1px solid #475569;'
            'border-radius:3px;padding:1px 6px;font-size:.6rem;color:#475569;">PASSÉ</span>'
        )

        try:
            date_raw = row.get("date", "")
            if hasattr(date_raw, "strftime"):
                date_str = date_raw.strftime("%d %b %Y")
            else:
                date_str = str(date_raw)[:10]
        except Exception:
            date_str = "—"

        st.markdown(
            f'<div style="background:rgba(0,0,0,.2);border-left:4px solid {imp_col};'
            f'border-radius:0 8px 8px 0;padding:12px 16px;margin-bottom:8px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;'
            f'margin-bottom:6px;">'
            f'<div style="font-family:Rajdhani;font-size:1rem;font-weight:700;color:#e2e8f0;">'
            f'{icon} {row.get("headline","")}</div>'
            f'<div style="display:flex;gap:6px;align-items:center;">'
            f'{_impact_badge(impact)} {status_badge}</div>'
            f'</div>'
            f'<div style="font-family:Share Tech Mono;font-size:.7rem;color:#7a93b0;'
            f'margin-bottom:6px;">{row.get("description","")}</div>'
            f'<div style="display:flex;gap:16px;">'
            f'<span style="font-family:Share Tech Mono;font-size:.62rem;color:#475569;">'
            f'📅 {date_str}</span>'
            f'<span style="font-family:Share Tech Mono;font-size:.62rem;color:#475569;">'
            f'🏷️ {cat}</span>'
            f'<span style="font-family:Share Tech Mono;font-size:.62rem;color:#475569;">'
            f'🌐 {row.get("scope","Global")}</span>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ── Tab 3 — Impact analysis ───────────────────────────────────────────────────

def _impact_analysis_tab():
    section_title("ANALYSE D'IMPACT DES ÉVÉNEMENTS", "📊")

    df = _load_static_events()
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    # Impact distribution
    col_a, col_b = st.columns(2)
    with col_a:
        section_title("RÉPARTITION PAR IMPACT", "🎯")
        impact_counts = df["impact"].value_counts()
        fig_pie = go.Figure(go.Pie(
            labels=impact_counts.index.tolist(),
            values=impact_counts.values.tolist(),
            hole=0.55,
            marker=dict(colors=["#ff3b6b", "#ffd700", "#00ff88"]),
            textfont=dict(family="Share Tech Mono", size=10),
            hovertemplate="<b>%{label}</b><br>%{value} événements<extra></extra>",
        ))
        fig_pie.update_layout(**_P, height=250, showlegend=True,
            legend=dict(font=dict(size=9, family="Share Tech Mono"), bgcolor="rgba(0,0,0,0)"))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_b:
        section_title("RÉPARTITION PAR CATÉGORIE", "📋")
        cat_counts = df["category"].value_counts()
        fig_bar = go.Figure(go.Bar(
            x=cat_counts.values.tolist(),
            y=cat_counts.index.tolist(),
            orientation="h",
            marker_color="rgba(0,212,255,.6)",
            hovertemplate="%{y}: %{x} événements<extra></extra>",
        ))
        fig_bar.update_layout(**_P, height=250,
            xaxis=dict(title="Nombre", showgrid=False),
            yaxis=dict(gridcolor="rgba(255,255,255,.04)"))
        st.plotly_chart(fig_bar, use_container_width=True)

    # Timeline
    if "date" in df.columns:
        section_title("TIMELINE DES ÉVÉNEMENTS", "📅")
        df_tl = df.dropna(subset=["date"]).copy()
        # All dates as naive for comparison
        df_tl["date_naive"] = pd.to_datetime(df_tl["date"]).dt.tz_localize(None)
        df_tl = df_tl.sort_values("date_naive")

        imp_color_map = {"high": "#ff3b6b", "medium": "#ffd700", "low": "#00ff88"}
        colors_tl = [imp_color_map.get(str(i), "#7a93b0") for i in df_tl["impact"]]

        fig_tl = go.Figure()
        for i, (_, row) in enumerate(df_tl.iterrows()):
            col_tl = imp_color_map.get(str(row.get("impact", "")), "#7a93b0")
            fig_tl.add_trace(go.Scatter(
                x=[row["date_naive"]],
                y=[i],
                mode="markers+text",
                marker=dict(size=10, color=col_tl, symbol="circle"),
                text=[str(row.get("headline", ""))[:50] + "…"],
                textposition="middle right",
                textfont=dict(size=9, color="#94a3b8", family="Share Tech Mono"),
                showlegend=False,
                hovertemplate=(
                    f'<b>{row.get("headline","")}</b><br>'
                    f'Date: {row["date_naive"].strftime("%d %b %Y") if hasattr(row["date_naive"], "strftime") else "—"}<br>'
                    f'Impact: {row.get("impact","")}<br>'
                    f'Catégorie: {row.get("category","")}<extra></extra>'
                ),
            ))

        fig_tl.update_layout(
            **_P,
            height=max(300, len(df_tl) * 32),
            xaxis=dict(title="Date", gridcolor="rgba(255,255,255,.04)"),
            yaxis=dict(showticklabels=False, showgrid=False),
        )
        st.plotly_chart(fig_tl, use_container_width=True)

    # Live news sentiment overview
    section_title("VOLUME D'ACTUALITÉS EN DIRECT (par source)", "📡")
    news = fetch_live_news()
    if news:
        from collections import Counter
        src_counts = Counter(it.get("feed_name", "Other") for it in news)
        fig_src = go.Figure(go.Bar(
            x=list(src_counts.keys()),
            y=list(src_counts.values()),
            marker_color="rgba(0,212,255,.55)",
            hovertemplate="%{x}<br>%{y} articles<extra></extra>",
        ))
        fig_src.update_layout(**_P, height=220,
            xaxis=dict(showgrid=False, tickangle=-25),
            yaxis=dict(title="Articles", gridcolor="rgba(255,255,255,.04)"))
        st.plotly_chart(fig_src, use_container_width=True)

        metric_row([
            {"label": "Articles live",   "value": str(len(news)),     "color": ""},
            {"label": "Sources actives", "value": str(len(src_counts)), "color": ""},
            {"label": "Dernière MAJ",    "value": _now_utc().strftime("%H:%M UTC"), "color": ""},
            {"label": "Cache TTL",       "value": f"{_CACHE_TTL//60} min", "color": ""},
        ])
    else:
        st.info("Données live non disponibles. Activez la connexion réseau.")
