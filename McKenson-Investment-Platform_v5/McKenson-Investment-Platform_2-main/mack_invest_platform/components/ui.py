"""
components/ui.py  —  MAM v3.5
Exports : inject_css, render_indices_banner, render_ticker_strip,
          render_news_banner, section_title, metric_row, pnl_cell, pct_cell
"""
import streamlit as st

DARK_THEME_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@300;400;500;600;700&family=Exo+2:wght@200;300;400;600;700&display=swap');

:root {
    --bg-primary:#030712; --bg-secondary:#0d1117; --bg-card:#111827; --bg-card2:#1a2332;
    --accent:#00d4ff; --accent2:#7c3aed; --green:#00ff88; --red:#ff3b6b;
    --yellow:#ffd700; --orange:#ff8c00;
    --text-primary:#e2e8f0; --text-secondary:#94a3b8;
    --border:rgba(0,212,255,0.15); --glow:0 0 20px rgba(0,212,255,0.3);
    --bh:26px;
}
html,body,.stApp{background-color:var(--bg-primary)!important;font-family:'Exo 2',sans-serif;color:var(--text-primary)}
/* Push content under the 3 fixed banners (3×26px = 78px) */
.block-container{padding-top:calc(78px + 1rem)!important;max-width:1400px}
.block-container>div:first-child{padding-top:0!important}
::-webkit-scrollbar{width:5px;height:5px}
::-webkit-scrollbar-track{background:var(--bg-secondary)}
::-webkit-scrollbar-thumb{background:var(--accent);border-radius:3px}
h1,h2,h3{font-family:'Rajdhani',sans-serif;letter-spacing:.05em}
section[data-testid="stSidebar"]{background:var(--bg-secondary)!important;border-right:1px solid var(--border)}
div[data-testid="metric-container"]{background:var(--bg-card)!important;border:1px solid var(--border);border-radius:8px;padding:12px!important;box-shadow:var(--glow)}
.stButton>button{background:linear-gradient(135deg,var(--accent),var(--accent2))!important;color:#fff!important;border:none!important;border-radius:6px!important;font-family:'Rajdhani',sans-serif!important;font-weight:600!important;letter-spacing:.08em!important;transition:all .2s!important}
.stButton>button:hover{box-shadow:0 0 25px rgba(0,212,255,.5)!important;transform:translateY(-1px)!important}
.stSelectbox>div>div,.stNumberInput>div>div>input,.stTextInput>div>div>input{background:var(--bg-card2)!important;border:1px solid var(--border)!important;color:var(--text-primary)!important;font-family:'Share Tech Mono',monospace!important}
.stTabs [data-baseweb="tab-list"]{background:var(--bg-secondary)!important;border-bottom:1px solid var(--border)}
.stTabs [data-baseweb="tab"]{color:var(--text-secondary)!important;font-family:'Rajdhani',sans-serif!important;font-weight:600;letter-spacing:.05em}
.stTabs [aria-selected="true"]{color:var(--accent)!important;border-bottom:2px solid var(--accent)!important}
.stDataFrame{border:1px solid var(--border)!important;border-radius:8px}
.metric-card{background:var(--bg-card);border:1px solid var(--border);border-radius:10px;padding:16px;text-align:center;box-shadow:var(--glow)}
.metric-value{font-family:'Share Tech Mono',monospace;font-size:1.5rem;color:var(--accent);font-weight:bold}
.metric-label{font-family:'Rajdhani',sans-serif;font-size:.75rem;color:var(--text-secondary);letter-spacing:.1em;text-transform:uppercase}
.positive{color:var(--green)!important}.negative{color:var(--red)!important}.neutral{color:var(--yellow)!important}
.mam-table-wrap{overflow-x:auto;border-radius:8px;border:1px solid rgba(0,212,255,.12);margin-bottom:12px}
.mam-table{width:100%;border-collapse:collapse;font-family:'Share Tech Mono',monospace;font-size:.78rem;color:#cbd5e1;background:rgba(13,17,23,.8)}
.mam-table tr:hover{background:rgba(0,212,255,.04)}
.section-title{font-family:'Rajdhani',sans-serif;font-size:1.05rem;font-weight:700;letter-spacing:.15em;text-transform:uppercase;color:var(--accent);border-left:3px solid var(--accent);padding-left:10px;margin:16px 0 10px;display:flex;align-items:center;gap:8px}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-family:'Rajdhani',sans-serif;font-size:.75rem;font-weight:700;letter-spacing:.08em}
.badge-green{background:rgba(0,255,136,.15);color:var(--green);border:1px solid var(--green)}
.badge-red{background:rgba(255,59,107,.15);color:var(--red);border:1px solid var(--red)}
.badge-blue{background:rgba(0,212,255,.15);color:var(--accent);border:1px solid var(--accent)}
div[data-testid="stVerticalBlock"]{gap:.4rem}
/* ══ BANDEAUX FIXES ══ */
.mam-banner{position:fixed;left:0;right:0;z-index:9999;overflow:hidden;white-space:nowrap;height:var(--bh);line-height:var(--bh);display:flex;align-items:center}
.mam-banner-idx {top:0;   background:#020810;border-bottom:1px solid rgba(0,212,255,.22)}
.mam-banner-tkr {top:26px;background:#030d15;border-bottom:1px solid rgba(0,212,255,.16)}
.mam-banner-news{top:52px;background:#08030e;border-bottom:1px solid rgba(255,60,60,.22)}
.ban-label{flex-shrink:0;font-family:'Rajdhani',sans-serif;font-weight:700;font-size:.60rem;letter-spacing:.18em;height:var(--bh);line-height:var(--bh);padding:0 10px;white-space:nowrap;border-right:1px solid rgba(255,255,255,.07)}
.ban-label-idx {background:rgba(0,212,255,.1); color:#00d4ff}
.ban-label-tkr {background:rgba(0,212,255,.05);color:#5a7a90}
.ban-label-news{background:#ff3b6b;            color:#fff}
.ban-scroll{overflow:hidden;flex:1;height:var(--bh);white-space:nowrap}
.ban-strip{display:inline-block;white-space:nowrap}
.ban-strip-idx {animation:mam-run 55s linear infinite}
.ban-strip-tkr {animation:mam-run 65s linear infinite}
.ban-strip-news{animation:mam-run 95s linear infinite}
.ban-item{display:inline-block;padding:0 18px;font-family:'Share Tech Mono',monospace;font-size:.71rem;vertical-align:middle}
.ban-sep{color:#0d2030;padding:0 3px}
.tick-up{color:#00ff88}.tick-down{color:#ff3b6b}
@keyframes mam-run{0%{transform:translateX(0)}100%{transform:translateX(-50%)}}
header[data-testid="stHeader"]{z-index:1!important;background:transparent!important}
</style>
"""

def inject_css():
    st.markdown(DARK_THEME_CSS, unsafe_allow_html=True)


def render_indices_banner(indices_data: list[dict]):
    if not indices_data:
        return
    items = ""
    for d in indices_data:
        label = d.get("name") or d.get("label") or d.get("ticker", "")
        emoji = d.get("emoji", "")
        pct   = float(d.get("pct", 0) or 0)
        price = float(d.get("price", 0) or 0)
        cls   = "tick-up" if pct >= 0 else "tick-down"
        arrow = "▲" if pct >= 0 else "▼"
        p_str = f"{price:,.2f}" if price else "—"
        items += (
            f'<span class="ban-item">'
            f'{emoji} <b style="color:#7a93b0;">{label}</b> '
            f'<span style="color:#cbd5e1;">{p_str}</span> '
            f'<span class="{cls}">{arrow}{abs(pct):.2f}%</span>'
            f'</span><span class="ban-sep">│</span>'
        )
    double = items * 2
    st.markdown(
        f'<div class="mam-banner mam-banner-idx">'
        f'<div class="ban-label ban-label-idx">📡 INDICES</div>'
        f'<div class="ban-scroll"><div class="ban-strip ban-strip-idx">{double}</div></div>'
        f'</div>', unsafe_allow_html=True)


def render_ticker_strip(strip_data: list[dict]):
    if not strip_data:
        return
    items = ""
    for d in strip_data:
        t     = d.get("ticker", "")
        price = float(d.get("price", 0) or 0)
        pct   = float(d.get("pct", 0) or 0)
        cls   = "tick-up" if pct >= 0 else "tick-down"
        arrow = "▲" if pct >= 0 else "▼"
        p_str = f"{price:,.2f}" if price else "—"
        items += (
            f'<span class="ban-item">'
            f'<b style="color:#e2e8f0;">{t}</b> '
            f'<span style="color:#5a7a90;">{p_str}</span> '
            f'<span class="{cls}">{arrow}{abs(pct):.2f}%</span>'
            f'</span><span class="ban-sep">·</span>'
        )
    double = items * 2
    st.markdown(
        f'<div class="mam-banner mam-banner-tkr">'
        f'<div class="ban-label ban-label-tkr">LIVE</div>'
        f'<div class="ban-scroll"><div class="ban-strip ban-strip-tkr">{double}</div></div>'
        f'</div>', unsafe_allow_html=True)


def render_news_banner(headlines):
    import pandas as pd
    if headlines is None:
        return
    items = ""
    if isinstance(headlines, pd.DataFrame):
        if headlines.empty:
            return
        for _, row in headlines.iterrows():
            cat  = str(row.get("scope") or row.get("category", ""))
            text = str(row.get("headline") or row.get("title", ""))
            if text:
                cat_html = (f'<span style="color:#ff3b6b;font-weight:bold;margin-right:4px;">[{cat}]</span>'
                            if cat else "")
                items += f'<span class="ban-item">{cat_html}<span style="color:#ff8c00;">{text}</span></span>'
    elif isinstance(headlines, list):
        if not headlines:
            return
        for h in headlines:
            if isinstance(h, dict):
                cat  = h.get("category", "")
                text = h.get("title", "")
            else:
                cat, text = "", str(h)
            if text:
                cat_html = (f'<span style="color:#ff3b6b;font-weight:bold;margin-right:4px;">[{cat}]</span>'
                            if cat else "")
                items += f'<span class="ban-item">{cat_html}<span style="color:#ff8c00;">{text}</span></span>'
    if not items:
        return
    double = items * 2
    st.markdown(
        f'<div class="mam-banner mam-banner-news">'
        f'<div class="ban-label ban-label-news">⚡ NEWS</div>'
        f'<div class="ban-scroll"><div class="ban-strip ban-strip-news">{double}</div></div>'
        f'</div>', unsafe_allow_html=True)


def section_title(title: str, icon: str = ""):
    icon_html = f'<span style="font-size:1rem;">{icon}</span>' if icon else ""
    st.markdown(f'<div class="section-title">{icon_html}{title}</div>', unsafe_allow_html=True)


def metric_row(metrics: list[dict]):
    cols = st.columns(len(metrics))
    for col, m in zip(cols, metrics):
        cls = m.get("color", "")
        with col:
            st.markdown(
                f'<div class="metric-card">'
                f'<div class="metric-label">{m["label"]}</div>'
                f'<div class="metric-value {cls}">{m["value"]}</div>'
                f'</div>', unsafe_allow_html=True)


def pnl_cell(value: float, suffix: str = "") -> str:
    col  = "#00ff88" if value >= 0 else "#ff3b6b"
    sign = "+" if value >= 0 else ""
    return f'<span style="color:{col};font-weight:bold;">{sign}{value:.2f}{suffix}</span>'


def pct_cell(value: float) -> str:
    """Alias de pnl_cell pour les pourcentages — importé par leaderboard.py"""
    col  = "#00ff88" if value >= 0 else "#ff3b6b"
    sign = "+" if value >= 0 else ""
    return f'<span style="color:{col};font-weight:bold;">{sign}{value:.2f}%</span>'
