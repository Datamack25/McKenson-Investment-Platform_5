# utils/data.py  —  MAM v4.0  Supabase-backed persistence
"""
Remplace utils/data.py.
- get_or_init_state()  : charge depuis Supabase si user connecté, sinon local
- persist()            : sauvegarde dans Supabase ET localement
- save_snapshot()      : snapshot automatique à chaque persist()
"""
from __future__ import annotations
import json, math, glob, base64, zlib
from pathlib import Path
from datetime import datetime

import pandas as pd
import numpy as np
import streamlit as st

try:
    import yfinance as yf
    _YF = True
except ImportError:
    _YF = False

try:
    from utils.db import (
        init_db, save_portfolio, load_portfolios_for_user,
        load_all_portfolios, upsert_team, get_all_teams,
        save_snapshot, is_db_available,
    )
    _DB = True
except ImportError:
    _DB = False

ROOT       = Path(__file__).parent.parent
DATA_DIR   = ROOT / "data"
STATE_FILE = DATA_DIR / "game_state.json"
INITIAL_CASH = 1_000_000.0

STRATEGIES = [
    {"id":"growth","name":"Growth","emoji":"📈","desc":"High-growth tech & momentum"},
    {"id":"value","name":"Value","emoji":"💎","desc":"Undervalued assets"},
    {"id":"momentum","name":"Momentum","emoji":"🚀","desc":"Trend-following"},
    {"id":"income","name":"Income","emoji":"💰","desc":"Dividends & yield"},
    {"id":"macro","name":"Global Macro","emoji":"🌍","desc":"Multi-asset macro"},
    {"id":"hedging","name":"Hedging","emoji":"🛡️","desc":"Options & inverse"},
    {"id":"balanced","name":"Balanced 60/40","emoji":"⚖️","desc":"Classic 60/40"},
    {"id":"commodity","name":"Commodities","emoji":"🛢️","desc":"Raw materials"},
    {"id":"crypto","name":"Crypto Alpha","emoji":"₿","desc":"Digital assets"},
    {"id":"arbitrage","name":"Arbitrage","emoji":"🔁","desc":"Market-neutral"},
]

_FB: dict[str,float] = {
    "AAPL":211.0,"MSFT":415.0,"NVDA":875.0,"AMZN":195.0,"GOOGL":175.0,
    "META":520.0,"TSLA":175.0,"NFLX":680.0,"JPM":210.0,"GS":490.0,
    "BAC":42.0,"V":285.0,"MA":490.0,"XOM":118.0,"CVX":162.0,
    "GC=F":2385.0,"SI=F":32.0,"CL=F":81.4,"BZ=F":85.1,"NG=F":2.35,
    "BTC-USD":63450.0,"ETH-USD":3250.0,"BNB-USD":610.0,"SOL-USD":165.0,
    "XRP-USD":0.62,"EURUSD=X":1.0812,"GBPUSD=X":1.2650,"USDJPY=X":155.40,
    "SPY":562.0,"QQQ":480.0,"IWM":205.0,"VTI":255.0,
    "GLD":220.0,"TLT":88.0,"HYG":77.0,"LQD":108.0,
    "^GSPC":5620.0,"^IXIC":17850.0,"^DJI":40210.0,"^VIX":16.5,
    "^FCHI":7932.0,"^GDAXI":18450.0,"^STOXX50E":4887.0,"^FTSE":8320.0,
    "^N225":38500.0,"^HSI":18200.0,"^TNX":4.38,
}
_FB_PCT: dict[str,float] = {
    "AAPL":0.42,"MSFT":0.67,"NVDA":2.30,"AMZN":1.12,"TSLA":-1.45,
    "GC=F":0.55,"CL=F":-0.73,"BTC-USD":1.24,"ETH-USD":2.10,
    "EURUSD=X":0.08,"SPY":0.42,"QQQ":0.67,"^GSPC":0.42,"^VIX":-2.50,
}


# ── Price fetching ─────────────────────────────────────────────────────────────

PRICE_LIVE = "live"        # cours Yahoo Finance (différé)
PRICE_FALLBACK = "repli"   # prix de secours codé en dur : jamais utilisé pour exécuter un ordre


@st.cache_data(ttl=180, show_spinner=False)
def get_quote(ticker: str) -> tuple[float, float, str]:
    """(prix, variation % vs clôture précédente, source). source = 'live' ou 'repli'."""
    if _YF:
        try:
            info  = yf.Ticker(ticker).fast_info
            price = float(info.last_price)
            if math.isnan(price) or price <= 0:
                raise ValueError
            try:
                prev = float(info.previous_close)
            except Exception:
                prev = float("nan")
            pct = (price - prev) / prev * 100 if prev and prev == prev and prev > 0 else 0.0
            return price, pct, PRICE_LIVE
        except Exception:
            pass
    return _FB.get(ticker, 100.0), _FB_PCT.get(ticker, 0.0), PRICE_FALLBACK


def get_price(ticker: str) -> float:
    return get_quote(ticker)[0]


def get_price_change(ticker: str) -> tuple[float,float]:
    p, pct, _ = get_quote(ticker)
    return p, pct


def get_price_source(ticker: str) -> str:
    """'live' si le cours vient de Yahoo Finance, 'repli' si c'est un prix de secours."""
    return get_quote(ticker)[2]


@st.cache_data(ttl=180, show_spinner=False)
def _multi_quotes(tickers: tuple) -> dict[str, tuple[float, float, str]]:
    result: dict[str, tuple[float, float, str]] = {}
    if not tickers: return result
    if _YF:
        try:
            raw = yf.download(" ".join(tickers), period="5d",
                              auto_adjust=True, progress=False, threads=True)
            closes = raw.get("Close", pd.DataFrame())
            if not closes.empty:
                if isinstance(closes, pd.Series):
                    closes = closes.to_frame(name=tickers[0])
                for t in tickers:
                    if t in closes.columns:
                        s = closes[t].dropna()
                        if len(s)>=2:
                            p,prv = float(s.iloc[-1]),float(s.iloc[-2])
                            result[t] = (p,(p-prv)/prv*100 if prv else 0.0, PRICE_LIVE)
                        elif len(s)==1:
                            result[t] = (float(s.iloc[-1]),0.0, PRICE_LIVE)
        except Exception: pass
    for t in tickers:
        if t not in result:
            result[t] = (_FB.get(t,100.0), _FB_PCT.get(t,0.0), PRICE_FALLBACK)
    return result


def get_multi_prices(tickers: tuple) -> dict[str,tuple[float,float]]:
    return {t: (p, pct) for t, (p, pct, _) in _multi_quotes(tuple(tickers)).items()}


def get_multi_sources(tickers: tuple) -> dict[str, str]:
    """Source du cours de chaque ticker ('live' / 'repli')."""
    return {t: src for t, (_, _, src) in _multi_quotes(tuple(tickers)).items()}


# Compatibilité : le bouton 🔄 du Dashboard appelle get_multi_prices.clear() / get_price_change.clear()
def _clear_quotes():
    get_quote.clear()
    _multi_quotes.clear()
    market_data_status.clear()


get_price.clear = _clear_quotes
get_price_change.clear = _clear_quotes
get_multi_prices.clear = _clear_quotes


@st.cache_data(ttl=300, show_spinner=False)
def market_data_status() -> str:
    """'live' si Yahoo Finance répond (test sur le S&P 500), sinon 'repli'."""
    return get_quote("SPY")[2]

@st.cache_data(ttl=300, show_spinner=False)
def get_history(ticker: str, period: str="1y") -> pd.DataFrame:
    if not _YF: return pd.DataFrame()
    try:
        df = yf.Ticker(ticker).history(period=period, auto_adjust=True)
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        return df
    except Exception:
        return pd.DataFrame()


# ── Assets / Events ───────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def load_assets() -> pd.DataFrame:
    files = sorted(glob.glob(str(DATA_DIR/"assets*.csv")))
    dfs = []
    for f in files:
        try: dfs.append(pd.read_csv(f))
        except Exception: pass
    if not dfs:
        return pd.DataFrame(columns=["ticker","name","category","type"])
    df = pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["ticker"])
    if "type" not in df.columns and "category" in df.columns:
        df["type"] = df["category"]
    elif "category" not in df.columns and "type" in df.columns:
        df["category"] = df["type"]
    return df.reset_index(drop=True)

@st.cache_data(ttl=60, show_spinner=False)  # TTL court pour news fraîches
def load_events() -> pd.DataFrame:
    try:
        df = pd.read_csv(DATA_DIR/"market_events.csv")
        if "active" in df.columns:
            df["active"] = df["active"].astype(str).str.lower().isin(["true","1","yes"])
        return df
    except Exception:
        return pd.DataFrame(columns=["event_id","date","headline","category",
                                      "scope","impact","active","description"])


# ── Strip / Indices / News ────────────────────────────────────────────────────

_STRIP_TICKERS = [
    ("^GSPC","S&P 500"),("^IXIC","NASDAQ"),("^DJI","DOW"),
    ("^FCHI","CAC 40"),("^GDAXI","DAX"),("^FTSE","FTSE"),
    ("GC=F","GOLD"),("CL=F","WTI"),("BTC-USD","BTC"),
    ("ETH-USD","ETH"),("EURUSD=X","EUR/USD"),("^VIX","VIX"),
]
_INDICES_DEF = [
    ("^GSPC","S&P 500","🇺🇸"),("^IXIC","NASDAQ","💻"),("^DJI","DOW","🏭"),
    ("^VIX","VIX","😱"),("^FCHI","CAC 40","🇫🇷"),("^GDAXI","DAX","🇩🇪"),
    ("^STOXX50E","STOXX 50","🇪🇺"),("^FTSE","FTSE 100","🇬🇧"),
    ("^N225","NIKKEI","🇯🇵"),("^HSI","HANG SENG","🇭🇰"),
    ("GC=F","GOLD","🥇"),("CL=F","WTI OIL","🛢️"),
    ("BTC-USD","BTC","₿"),("EURUSD=X","EUR/USD","💱"),("^TNX","US 10Y","📊"),
]

@st.cache_data(ttl=180, show_spinner=False)
def get_strip_data() -> list[dict]:
    tickers = tuple(t for t,_ in _STRIP_TICKERS)
    prices  = get_multi_prices(tickers)
    return [{"ticker":name,
             "price":prices.get(sym,(_FB.get(sym,0),0))[0],
             "pct":  prices.get(sym,(0,_FB_PCT.get(sym,0)))[1]}
            for sym,name in _STRIP_TICKERS]

@st.cache_data(ttl=180, show_spinner=False)
def get_indices_data() -> list[dict]:
    tickers = tuple(s for s,_,_ in _INDICES_DEF)
    prices  = get_multi_prices(tickers)
    return [{"symbol":sym,"name":name,"emoji":emoji,
             "price":prices.get(sym,(_FB.get(sym,0),0))[0],
             "pct":  prices.get(sym,(0,_FB_PCT.get(sym,0)))[1]}
            for sym,name,emoji in _INDICES_DEF]

@st.cache_data(ttl=300, show_spinner=False)  # 5 min — news rafraîchies souvent
def fetch_news_headlines(max_items: int=20) -> list[dict]:
    """Fetch depuis Google News RSS — TTL 5 min pour rafraîchir à chaque reload."""
    feeds = [
        ("https://news.google.com/rss/search?q=stock+market+financial&hl=en&gl=US&ceid=US:en","Markets"),
        ("https://news.google.com/rss/search?q=central+bank+federal+reserve+ECB&hl=en&gl=US&ceid=US:en","Central Banks"),
        ("https://news.google.com/rss/search?q=geopolitics+conflict+sanctions&hl=en&gl=US&ceid=US:en","Geopolitics"),
        ("https://news.google.com/rss/search?q=oil+gold+commodities+prices&hl=en&gl=US&ceid=US:en","Commodities"),
        ("https://news.google.com/rss/search?q=bitcoin+crypto+ethereum+market&hl=en&gl=US&ceid=US:en","Crypto"),
    ]
    out = []
    try:
        import urllib.request
        from xml.etree import ElementTree as ET
        for url, cat in feeds:
            try:
                req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as r: xml=r.read()
                root = ET.fromstring(xml)
                for item in root.findall(".//item")[:4]:
                    title = (item.findtext("title") or "").split(" - ")[0].strip()
                    pubdate = item.findtext("pubDate","")
                    if title: out.append({"title":title,"category":cat,
                                          "pubdate":pubdate,"link":""})
            except Exception: continue
    except Exception: pass
    if len(out) < 5:
        out = _static_news()
    return out[:max_items]

def _static_news() -> list[dict]:
    """Repli quand le flux d'actualités est indisponible : messages d'information
    de la plateforme (aucune fausse actualité datée présentée comme réelle)."""
    return [
        {"title":"Flux d'actualités momentanément indisponible — réessayez dans quelques minutes","category":"Info","link":""},
        {"title":"Cours Yahoo Finance différés : vérifiez l'indicateur de données en haut de page","category":"Info","link":""},
        {"title":"Contrôles de conformité actifs sur chaque ordre : concentration, crypto, liquidités, dérivés","category":"Conformité","link":""},
        {"title":"Plateforme éducative : aucun ordre n'est exécuté sur un marché réel","category":"Info","link":""},
        {"title":"Les performances passées ne préjugent pas des performances futures","category":"Info","link":""},
    ]


# ══════════════════════════════════════════════════════════════════════════════
#  STATE MANAGEMENT — Supabase-backed
# ══════════════════════════════════════════════════════════════════════════════

def _build_state_from_db(user_id: int) -> dict:
    """Reconstruit le dict state depuis Supabase pour un utilisateur."""
    portfolios_db = load_portfolios_for_user(user_id)
    teams_db      = get_all_teams()

    state = {"version":"4.0","created":datetime.now().isoformat(),"teams":{}}

    # Reconstruire les équipes
    for team in teams_db:
        tid = team["id"]
        state["teams"][tid] = {
            "id":tid, "name":team["name"], "emoji":team.get("emoji","🏢"),
            "portfolios":{},
        }

    # Une équipe solo par défaut si pas de teams
    if not state["teams"]:
        state["teams"]["__solo__"] = {
            "id":"__solo__","name":"Solo","emoji":"👤","portfolios":{}
        }

    # Placer les portefeuilles dans leurs équipes
    for p in portfolios_db:
        tid = p.get("team_id") or "__solo__"
        if tid not in state["teams"]:
            state["teams"][tid] = {"id":tid,"name":"Solo","emoji":"👤","portfolios":{}}
        pid = p["id"]
        state["teams"][tid]["portfolios"][pid] = {
            "id":pid, "name":p["name"], "emoji":p.get("emoji","📁"),
            "strategy":p.get("strategy","Libre"),
            "asset_types":p.get("asset_types",[]),
            "cash":float(p.get("cash",0)),
            "initial_cash":float(p.get("initial_cash",INITIAL_CASH)),
            "holdings":p.get("holdings",{}),
            "options":p.get("options",[]),
            "trades":p.get("trades",[]),
            "history":p.get("history",[]),
        }

    return state


def get_or_init_state() -> dict:
    """
    Charge l'état :
    1. Depuis Supabase si user connecté et DB disponible  ← priorité absolue
    2. Depuis le fichier local sinon (fallback éphémère)

    NOTE: on recharge depuis Supabase même si mam_state est déjà en session
    mais qu'il est vide (cas du rechargement Streamlit avec un état vierge).
    """
    user = st.session_state.get("mam_user")

    # Supabase d'abord quand l'utilisateur est connecté : on charge UNE fois par
    # connexion (le flag est remis à zéro au login), puis la session fait foi.
    if user and _DB and is_db_available():
        if st.session_state.get("mam_db_loaded_for") != user["id"]:
            try:
                state = _build_state_from_db(user["id"])
                st.session_state["mam_state"] = state
                st.session_state["mam_db_loaded_for"] = user["id"]
                return state
            except Exception as e:
                st.warning(f"Supabase: chargement local (DB: {e})")

    # Si déjà en session avec des données, on retourne directement
    if "mam_state" in st.session_state:
        return st.session_state["mam_state"]

    # Fallback fichier local (éphémère sur Streamlit Cloud, utile en local)
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE) as f:
                state = json.load(f)
            if state.get("teams"):
                st.session_state["mam_state"] = state
                return state
    except Exception:
        pass

    state = {"version":"4.0","created":datetime.now().isoformat(),"teams":{}}
    st.session_state["mam_state"] = state
    return state


def persist():
    """
    Sauvegarde l'état :
    1. Dans Supabase (permanent) si user connecté
    2. Dans le fichier local (fallback)
    3. Snapshot automatique de performance
    """
    state   = st.session_state.get("mam_state", {})
    user    = st.session_state.get("mam_user")
    user_id = user["id"] if user else None

    if not state:
        return

    # ── Supabase ──────────────────────────────────────────────────────────────
    if user_id and not (_DB and is_db_available()):
        st.warning("⚠️ Base de données injoignable : vos changements ne sont PAS sauvegardés de façon permanente.")
    if user_id and _DB and is_db_available():
        try:
            for tid, team in state.get("teams", {}).items():
                # Upsert équipe
                upsert_team(tid, team.get("name",""), team.get("emoji","🏢"))

                for pid, port in team.get("portfolios", {}).items():
                    # Sauvegarde portefeuille
                    save_portfolio(pid, tid, user_id, port)

                    # Snapshot automatique de performance
                    _auto_snapshot(pid, port)
        except Exception as e:
            st.warning(f"⚠️ Supabase persist: {e}")

    # ── Notification email si un portefeuille a bougé ──────────────────────────
    try:
        from utils.notifier import notify_changes
        notify_changes(state)
    except Exception:
        pass

    # ── Fichier local (fallback) ───────────────────────────────────────────────
    try:
        DATA_DIR.mkdir(exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2, default=str)
    except Exception:
        pass


def _auto_snapshot(port_id: str, port: dict):
    """Enregistre un snapshot de performance automatique dans Supabase."""
    if not _DB or not is_db_available():
        return
    try:
        holdings = port.get("holdings", {})
        if not holdings:
            return
        # Prix depuis cache session ou fallback avg
        tickers = list(holdings.keys())
        prices  = get_multi_prices(tuple(tickers))
        spot_val = 0.0
        positions_snap = []
        for tk, pos in holdings.items():
            qty = pos.get("qty", 0)
            avg = pos.get("avg_price", 0)
            p, _ = prices.get(tk, (avg, 0))
            mkt  = qty * (p if p and p==p and p>0 else avg)
            spot_val += mkt
            positions_snap.append({"ticker":tk,"qty":qty,"avg":avg,"price":p,"mkt":mkt})
        cash      = port.get("cash", 0)
        nav       = cash + spot_val
        init      = port.get("initial_cash", INITIAL_CASH)
        total_pnl = nav - init
        pnl_pct   = total_pnl / init * 100 if init else 0

        save_snapshot(
            portfolio_id  = port_id,
            nav           = nav,
            cash          = cash,
            spot_value    = spot_val,
            total_pnl     = total_pnl,
            pnl_pct       = pnl_pct,
            n_positions   = len(holdings),
            positions     = positions_snap,
        )
    except Exception:
        pass


def save_state(state: dict):
    persist()


def load_state() -> dict:
    return get_or_init_state()


# ══════════════════════════════════════════════════════════════════════════════
#  PORTFOLIO CALCULATIONS
# ══════════════════════════════════════════════════════════════════════════════

def value_portfolio(portfolio: dict, prices: dict) -> dict:
    positions = []; spot_val = 0.0
    for ticker, pos in portfolio.get("holdings", {}).items():
        qty  = pos.get("qty", 0); avg = pos.get("avg_price", 0.0)
        raw  = prices.get(ticker, avg)
        curr = raw[0] if isinstance(raw,(list,tuple)) else float(raw)
        if not curr or curr!=curr or curr<=0: curr=avg
        mkt  = qty*curr; cost=qty*avg; pnl=mkt-cost
        positions.append({"ticker":ticker,"qty":qty,"avg_price":avg,
                          "current_price":curr,"market_value":mkt,
                          "cost_basis":cost,"unreal_pnl":pnl,
                          "unrealized_pnl":pnl,
                          "pnl_pct":(pnl/cost*100) if cost else 0.0})
        spot_val += mkt
    cash = portfolio.get("cash", 0.0)
    return {"total":cash+spot_val,"cash":cash,"spot_value":spot_val,"positions":positions}


def compute_risk_metrics(returns: "pd.Series") -> dict | None:
    if returns is None or len(returns)<5: return None
    r = returns.dropna()
    if len(r)<5: return None
    ann_vol = float(r.std()*np.sqrt(252))
    ann_ret = float((1+r.mean())**252-1)
    sharpe  = ann_ret/ann_vol if ann_vol>0 else 0.0
    cum     = (1+r).cumprod()
    mdd     = float(((cum-cum.cummax())/cum.cummax()).min())
    var99   = float(r.quantile(0.01)); cvar99=float(r[r<=var99].mean()) if (r<=var99).any() else var99
    var95   = float(r.quantile(0.05)); cvar95=float(r[r<=var95].mean()) if (r<=var95).any() else var95
    down_r  = r[r<0]
    sortino = ann_ret/float(down_r.std()*np.sqrt(252)) if len(down_r)>1 else 0.0
    return {"ann_vol":ann_vol,"ann_ret":ann_ret,"sharpe":sharpe,
            "max_drawdown":mdd,"var_99_10d":var99*np.sqrt(10),
            "cvar_99_10d":cvar99*np.sqrt(10),"var_95":abs(var95),
            "cvar_95":abs(cvar95),"calmar":ann_ret/abs(mdd) if mdd else 0.0,
            "sortino":sortino}

compute_portfolio_metrics = compute_risk_metrics


def record_trade(portfolio: dict, ticker: str, action: str,
                 qty: float, price: float, enforce: bool = True, source: str = "") -> str:
    """Exécute un ordre spot simulé. Avec enforce=True (par défaut), l'ordre passe
    d'abord par les contrôles de conformité (utils.compliance) : s'il est bloqué,
    rien n'est exécuté et le message explique la règle en cause."""
    decision = None
    if enforce:
        try:
            from utils.compliance import pre_trade_spot, log_decision
            decision = pre_trade_spot(portfolio, ticker, action, qty, price)
        except Exception as e:  # par prudence, un contrôle en erreur bloque l'ordre
            return f"⛔ Contrôle de conformité indisponible ({e}) : ordre refusé par prudence."
        if not decision.allowed:
            try:
                log_decision(decision, portfolio, ticker, action, qty, price, executed=False, note=source)
            except Exception:
                pass
            return "⛔ Ordre bloqué par la conformité : " + decision.short_reason()
    total=qty*price; h=portfolio.setdefault("holdings",{}); tr=portfolio.setdefault("trades",[])
    if action=="BUY":
        if total>portfolio.get("cash",0)+0.01:
            return f"Fonds insuffisants (cash: ${portfolio.get('cash',0):,.0f})"
        portfolio["cash"]-=total
        if ticker in h:
            oq,oa=h[ticker]["qty"],h[ticker]["avg_price"]; nq=oq+qty
            h[ticker]={"qty":nq,"avg_price":(oq*oa+qty*price)/nq}
        else:
            h[ticker]={"qty":qty,"avg_price":price}
    elif action=="SELL":
        avail=h.get(ticker,{}).get("qty",0)
        if avail<qty-1e-9: return f"Position insuffisante ({avail:.4f} dispo)"
        portfolio["cash"]=portfolio.get("cash",0)+total
        h[ticker]["qty"]-=qty
        if h[ticker]["qty"]<1e-9: del h[ticker]
    else: return f"Action invalide: {action}"
    entry = {"date":datetime.now().strftime("%Y-%m-%d %H:%M"),
             "ticker":ticker,"action":action,
             "qty":round(qty,6),"price":round(price,6),"total":round(total,2)}
    if source:
        entry["source"] = source
    if decision is not None:
        entry["conformite"] = "contrôlé" + (f" ({len(decision.warnings)} alerte(s))" if decision.warnings else "")
        try:
            from utils.compliance import log_decision
            log_decision(decision, portfolio, ticker, action, qty, price, executed=True, note=source)
        except Exception:
            pass
    tr.append(entry)
    persist()
    return ""


def get_contract_mult(ticker: str, assets_df=None) -> int:
    if assets_df is not None:
        try:
            row=assets_df[assets_df["ticker"]==ticker]
            if not row.empty and "contract_mult" in row.columns:
                return int(row["contract_mult"].iloc[0])
        except Exception: pass
    return 1 if any(ticker.endswith(s) for s in ["-USD","=X","=F"]) else 100


def get_currency(ticker: str, assets_df=None) -> str:
    if assets_df is not None:
        try:
            row=assets_df[assets_df["ticker"]==ticker]
            if not row.empty and "currency" in row.columns:
                return str(row["currency"].iloc[0])
        except Exception: pass
    if ticker.endswith("=X"): return "USD"
    if ticker.endswith("-USD"): return "USD"
    if ".PA" in ticker: return "EUR"
    if ".DE" in ticker or ".AS" in ticker: return "EUR"
    if ".L" in ticker: return "GBP"
    return "USD"
