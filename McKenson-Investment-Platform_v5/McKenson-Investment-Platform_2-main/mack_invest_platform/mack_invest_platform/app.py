import streamlit as st
import pandas as pd
import numpy as np
import time
import threading
from datetime import datetime

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="MAM — McKenson Asset Management · v5.3",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Global CSS ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Share+Tech+Mono&display=swap');

html, body, [data-testid="stApp"] {
    background: #080e1a !important;
    color: #e2e8f0 !important;
    font-family: 'Share Tech Mono', monospace;
}

/* ── Ticker bandeaux ── */
.ticker-wrapper {
    width: 100%;
    margin: 0 0 18px 0;
    background: transparent;
}

.ticker-band {
    width: 100%;
    height: 24px;
    overflow: hidden;
    background: rgba(0,8,18,0.95);
    border: 1px solid rgba(0,212,255,0.14);
    border-radius: 4px;
    display: flex;
    align-items: center;
    margin-bottom: 4px;
}

.ticker-band.news-band {
    background: rgba(4,4,16,0.95);
    border-color: rgba(124,58,237,0.18);
    margin-bottom: 0;
}

.ticker-track {
    display: flex;
    white-space: nowrap;
    animation: ticker-scroll 60s linear infinite;
}

.ticker-track.news-track {
    animation: ticker-scroll 90s linear infinite;
}

/* Pause du défilement au survol : on peut lire un cours ou un titre */
.ticker-band:hover .ticker-track { animation-play-state: paused; }
.ticker-band { cursor: default; }

@keyframes ticker-scroll {
    0%   { transform: translateX(0); }
    100% { transform: translateX(-50%); }
}

.ticker-item {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 0 14px;
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.64rem;
    color: #94a3b8;
    border-right: 1px solid rgba(255,255,255,0.05);
}

.ticker-item .sym {
    color: #00d4ff;
    font-weight: 700;
    font-size: 0.63rem;
    letter-spacing: 0.04em;
}

.ticker-item .px  { color: #e2e8f0; font-size: 0.64rem; }
.ticker-item .up  { color: #00ff88; font-size: 0.61rem; }
.ticker-item .down{ color: #ff3b6b; font-size: 0.61rem; }

.news-item {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 0 18px;
    font-family: 'Rajdhani', sans-serif;
    font-size: 0.68rem;
    color: #7a93b0;
    letter-spacing: 0.03em;
    border-right: 1px solid rgba(255,255,255,0.04);
}

.news-item .tag {
    color: #7c3aed;
    font-weight: 700;
    font-size: 0.61rem;
    letter-spacing: 0.1em;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg,rgba(0,212,255,.12),rgba(124,58,237,.12)) !important;
    border: 1px solid rgba(0,212,255,.3) !important;
    color: #00d4ff !important;
    font-family: 'Rajdhani',sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: .08em !important;
    border-radius: 4px !important;
    transition: all .2s !important;
}
.stButton > button:hover {
    background: linear-gradient(135deg,rgba(0,212,255,.25),rgba(124,58,237,.25)) !important;
    border-color: rgba(0,212,255,.6) !important;
    box-shadow: 0 0 16px rgba(0,212,255,.25) !important;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: transparent !important;
    border-bottom: 1px solid rgba(0,212,255,.1) !important;
}
.stTabs [data-baseweb="tab"] {
    font-family: 'Rajdhani',sans-serif !important;
    font-weight: 700 !important;
    font-size: .78rem !important;
    letter-spacing: .1em !important;
    color: #475569 !important;
    border-bottom: 2px solid transparent !important;
    padding: 8px 16px !important;
}
.stTabs [aria-selected="true"] {
    color: #00d4ff !important;
    border-bottom-color: #00d4ff !important;
    background: rgba(0,212,255,.04) !important;
}

/* PnL colours */
.pnl-pos  { color: #00ff88 !important; }
.pnl-neg  { color: #ff3b6b !important; }
.pnl-zero { color: #94a3b8 !important; }

/* Selectbox / inputs */
[data-testid="stSelectbox"] > div > div,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
    background: rgba(0,10,30,.6) !important;
    border: 1px solid rgba(0,212,255,.2) !important;
    color: #e2e8f0 !important;
    font-family: 'Share Tech Mono',monospace !important;
    border-radius: 4px !important;
}

/* Metric cards */
[data-testid="stMetric"] {
    background: rgba(0,212,255,.04) !important;
    border: 1px solid rgba(0,212,255,.12) !important;
    border-radius: 6px !important;
    padding: 10px 14px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] {
    background: rgba(0,10,25,.5) !important;
    border: 1px solid rgba(0,212,255,.12) !important;
    border-radius: 6px !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: rgba(0,0,0,.2); }
::-webkit-scrollbar-thumb { background: rgba(0,212,255,.3); border-radius: 2px; }

/* Masquer nav auto Streamlit multi-pages */
[data-testid="stSidebarNav"] { display: none !important; }
section[data-testid="stSidebar"] ul { display: none !important; }

/* Sidebar portfolio summary card */
.port-summary-card {
    background: rgba(0,212,255,.04);
    border: 1px solid rgba(0,212,255,.12);
    border-radius: 7px;
    padding: 9px 12px;
    margin: 5px 0;
    font-family: 'Share Tech Mono', monospace;
    font-size: .68rem;
}
.port-summary-card .port-name {
    font-family: 'Rajdhani', sans-serif;
    font-weight: 700;
    font-size: .82rem;
    color: #e2e8f0;
    margin-bottom: 4px;
}
.port-summary-card .port-stat {
    color: #7a93b0;
    line-height: 1.7;
}
.sidebar-section-label {
    font-family: 'Rajdhani', sans-serif;
    font-size: .62rem;
    color: #334155;
    letter-spacing: .16em;
    text-transform: uppercase;
    margin: 10px 0 4px;
}
</style>
""", unsafe_allow_html=True)

# ── Ticker data ────────────────────────────────────────────────────────────────
TICKER_SYMBOLS = [
    "AAPL","MSFT","GOOGL","AMZN","NVDA","TSLA","META","BRK-B","JPM","V",
    "BTC-USD","ETH-USD","GC=F","CL=F","EURUSD=X","^SPX","^IXIC","^DJI",
    "NFLX","AMD","INTC","BAC","WMT","XOM","CVX","LLY","UNH","PFE",
]

# Repli si le flux d'actualités est indisponible : messages d'information de la
# plateforme (et non de fausses actualités datées présentées comme réelles).
NEWS_ITEMS = [
    ("INFO", "Flux d'actualités momentanément indisponible — réessayez dans quelques minutes"),
    ("INFO", "Cours Yahoo Finance différés — voir l'indicateur de données en haut de page"),
    ("CONFORMITÉ", "Chaque ordre est contrôlé : concentration, crypto, liquidités, produits dérivés"),
    ("ETF", "Nouveau : portefeuilles modèles 100 % ETF dans le Trading Desk"),
    ("OPTIONS", "Nouveau : stratégies d'options selon le régime de marché"),
    ("MAM", "Plateforme éducative créée par Mackenson CINEUS — aucun ordre réel n'est exécuté"),
]


@st.cache_data(ttl=60)
def fetch_ticker_prices(symbols):
    try:
        import yfinance as yf
        data = yf.download(symbols, period="2d", interval="1d",
                           auto_adjust=True, progress=False)
        results = {}
        if "Close" in data.columns:
            closes = data["Close"]
            for sym in symbols:
                try:
                    col = closes[sym] if sym in closes.columns else closes
                    vals = col.dropna()
                    if len(vals) >= 2:
                        px   = float(vals.iloc[-1])
                        prev = float(vals.iloc[-2])
                        pct  = (px - prev) / prev * 100 if prev else 0.0
                        results[sym] = (px, pct)
                    elif len(vals) == 1:
                        results[sym] = (float(vals.iloc[-1]), 0.0)
                except Exception:
                    pass
        return results
    except Exception:
        return {}


def build_ticker_html(prices: dict) -> str:
    items = ""
    for sym in TICKER_SYMBOLS:
        if sym not in prices:
            continue
        px, pct = prices[sym]
        arr  = "▲" if pct >= 0 else "▼"
        cls  = "up" if pct >= 0 else "down"
        sign = "+" if pct >= 0 else ""
        disp = sym.replace("-USD","").replace("=X","").replace("=F","").replace("^","")
        if px >= 1000:
            px_str = f"${px:,.0f}"
        elif px >= 1:
            px_str = f"${px:,.2f}"
        else:
            px_str = f"${px:,.4f}"
        items += (
            f'<span class="ticker-item">'
            f'<span class="sym">{disp}</span>'
            f'<span class="px">{px_str}</span>'
            f'<span class="{cls}">{arr}{sign}{abs(pct):.2f}%</span>'
            f'</span>'
        )
    # duplicate for seamless loop
    return items + items


def build_news_html() -> str:
    """Vraies news (Google News RSS, cache 5 min, vidé par le bouton 🔄 du Dashboard).
    Repli sur la liste statique si le flux est indisponible."""
    import html as _h
    items_list = []
    try:
        from utils.data import fetch_news_headlines
        items_list = [(str(n.get("category", "NEWS")).upper(), n.get("title", ""))
                      for n in fetch_news_headlines() if n.get("title")]
    except Exception:
        items_list = []
    if not items_list:
        items_list = NEWS_ITEMS
    items = ""
    for tag, text in items_list:
        items += (
            f'<span class="news-item">'
            f'<span class="tag">[{_h.escape(tag)}]</span>'
            f'{_h.escape(text)}'
            f'</span>'
        )
    return items + items


# ── Render bandeaux ────────────────────────────────────────────────────────────
prices = fetch_ticker_prices(TICKER_SYMBOLS)
ticker_html = build_ticker_html(prices)
news_html   = build_news_html()

st.markdown(f"""
<div class="ticker-wrapper">
  <div class="ticker-band">
    <div class="ticker-track">{ticker_html}</div>
  </div>
  <div class="ticker-band news-band">
    <div class="ticker-track news-track">{news_html}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# ── Habillage « page web » (HTML + CSS) ───────────────────────────────────────
from components.webui import (
    inject_web_css, render_topbar, render_nav, render_account_bar,
    render_portfolio_cards, render_footer,
)
inject_web_css()

# ── Connexion obligatoire : les portefeuilles sont rattachés à un compte et
#    sauvegardés dans la base (permanents, survivent aux redémarrages) ─────────
if not (st.session_state.get("mam_user") or st.session_state.get("mam_guest")):
    from pages.auth import render_auth
    _l, _mid, _r = st.columns([1, 1.2, 1])
    with _mid:
        render_auth()
    st.stop()

# ── Initialise session state ───────────────────────────────────────────────────
from utils.data import get_or_init_state, persist

state = get_or_init_state()

# ── Notifications email (référence + alerte de variation de valeur) ───────────
try:
    from utils.notifier import init_baseline, check_nav_moves
    init_baseline(state)
    check_nav_moves(state)
except Exception:
    pass

# ── En-tête, navigation, compte ───────────────────────────────────────────────
render_topbar()

pages = {
    "🏠 Dashboard":           "dashboard",
    "💼 Trading Desk":        "trading",
    "📊 Technique":           "technical",
    "🧠 IA Marchés":          "ai_markets",
    "🤖 Auto-Portefeuille":   "auto_portfolio",
    "🦅 Hedge Fund Agent":    "hedge_fund",
    "📈 Optimizer":           "optimizer",
    "📄 Rapports":            "reports",
    "🏆 Classement":          "leaderboard",
    "🎓 Éducation":           "education",
    "📅 Événements":          "events",
    "🏢 Administration":      "admin",
}
render_nav(pages)
# Sélection demandée par une autre page (ex. portefeuille créé par le Hedge Fund Agent) :
# appliquée ici, avant la création des sélecteurs équipe / portefeuille.
_sel = st.session_state.pop("_select_portfolio", None)
if _sel and _sel[0] in state.get("teams", {}) and _sel[1] in state["teams"][_sel[0]].get("portfolios", {}):
    st.session_state["active_team"], st.session_state["active_portfolio"] = _sel
sel_team, user_ports = render_account_bar(state)
render_portfolio_cards(user_ports)

# ── Page routing ───────────────────────────────────────────────────────────────
page = st.session_state.get("page", "dashboard")

try:
    if page == "dashboard":
        from pages import dashboard; dashboard.render()
    elif page == "trading":
        from pages import trading; trading.render()
    elif page == "technical":
        from pages import technical; technical.render()
    elif page == "ai_markets":
        from pages import ai_markets; ai_markets.render()
    elif page == "auto_portfolio":
        from pages import auto_portfolio; auto_portfolio.render()
    elif page == "hedge_fund":
        from pages import hedge_fund; hedge_fund.render()
    elif page == "optimizer":
        from pages import optimizer; optimizer.render()
    elif page == "reports":
        from pages import reports; reports.render()
    elif page == "leaderboard":
        from pages import leaderboard; leaderboard.render()
    elif page == "education":
        from pages import education; education.render()
    elif page == "events":
        from pages import events; events.render()
    elif page == "admin":
        from pages import admin; admin.render()
except ImportError as e:
    st.warning(f"Page en cours de construction : `{page}`")
    st.caption(str(e))

render_footer()
