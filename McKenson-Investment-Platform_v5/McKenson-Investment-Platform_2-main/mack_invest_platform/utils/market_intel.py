# utils/market_intel.py  —  MAM v5 · Intelligence de marché
"""
Collecte et mise en forme des informations qui font bouger les marchés :

* univers d'actifs multi-classes (actions, obligations, or, matières premières,
  immobilier, crypto, monétaire) avec leur sous-classe de risque ;
* historiques de prix en lot (Yahoo Finance) avec repli sur des données
  SIMULÉES clairement signalées quand le flux est indisponible ;
* indicateurs macro-économiques de marché (VIX, courbe des taux, dollar,
  pétrole, cuivre/or, spreads de crédit, tendance S&P 500) ;
* lecture des actualités (Google News RSS) : thèmes géopolitiques et
  économiques, sentiment, indice de risque géopolitique et inclinaison
  (« tilt ») attendue par classe d'actifs via une matrice d'impact.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone

import numpy as np
import pandas as pd

try:
    import streamlit as st
    _cache = st.cache_data
except Exception:  # pragma: no cover - utilisation hors Streamlit
    def _cache(*a, **k):
        def deco(f):
            return f
        return deco if not (a and callable(a[0])) else a[0]

try:
    import logging as _logging
    import yfinance as yf
    _logging.getLogger("yfinance").setLevel(_logging.CRITICAL)
    _YF = True
except ImportError:
    _YF = False


# ══════════════════════════════════════════════════════════════════════════════
#  UNIVERS
# ══════════════════════════════════════════════════════════════════════════════

# ticker: (nom, classe, sous-classe)
UNIVERSE: dict[str, tuple[str, str, str]] = {
    "SPY":     ("S&P 500",                        "Actions",            "us_eq"),
    "QQQ":     ("Nasdaq 100 (tech)",              "Actions",            "tech"),
    "IWM":     ("Russell 2000 (small caps)",      "Actions",            "us_small"),
    "VGK":     ("Actions Europe",                 "Actions",            "intl_eq"),
    "EWJ":     ("Actions Japon",                  "Actions",            "intl_eq"),
    "EEM":     ("Actions émergentes",             "Actions",            "em_eq"),
    "XLF":     ("Financières US",                 "Actions",            "financials"),
    "XLE":     ("Énergie US",                     "Actions",            "energy_eq"),
    "XLV":     ("Santé US",                       "Actions",            "defensive_eq"),
    "XLU":     ("Services publics US",            "Actions",            "defensive_eq"),
    "ITA":     ("Défense & aéronautique US",      "Actions",            "defense"),
    "TLT":     ("Treasuries 20 ans +",            "Obligations",        "gov_long"),
    "IEF":     ("Treasuries 7-10 ans",            "Obligations",        "gov_int"),
    "SHY":     ("Treasuries 1-3 ans",             "Obligations",        "gov_short"),
    "TIP":     ("Obligations indexées inflation", "Obligations",        "tips"),
    "LQD":     ("Crédit Investment Grade",        "Obligations",        "ig"),
    "HYG":     ("Crédit High Yield",              "Obligations",        "hy"),
    "GLD":     ("Or",                             "Or & métaux",        "gold"),
    "SLV":     ("Argent",                         "Or & métaux",        "silver"),
    "DBC":     ("Panier matières premières",      "Matières premières", "commo"),
    "USO":     ("Pétrole WTI",                    "Matières premières", "oil"),
    "VNQ":     ("Immobilier coté US",             "Immobilier",         "reit"),
    "BTC-USD": ("Bitcoin",                        "Crypto",             "crypto"),
    "ETH-USD": ("Ethereum",                       "Crypto",             "crypto"),
    "BIL":     ("T-Bills 1-3 mois (cash)",        "Monétaire",          "cash"),
}

ASSET_CLASSES = ["Actions", "Obligations", "Or & métaux", "Matières premières",
                 "Immobilier", "Crypto", "Monétaire"]

CLASS_COLORS = {
    "Actions": "#00d4ff", "Obligations": "#7c3aed", "Or & métaux": "#ffd700",
    "Matières premières": "#ff8c00", "Immobilier": "#00ff88", "Crypto": "#ff3b6b",
    "Monétaire": "#94a3b8",
}

MACRO_TICKERS = {
    "^VIX": "VIX", "^TNX": "US10Y", "^IRX": "US3M", "DX-Y.NYB": "DXY",
    "CL=F": "WTI", "GC=F": "GOLD", "HG=F": "COPPER",
}


def asset_name(t: str) -> str:
    return UNIVERSE.get(t, (t, "", ""))[0]


def asset_class(t: str) -> str:
    if t in UNIVERSE:
        return UNIVERSE[t][1]
    if t.endswith("-USD"):
        return "Crypto"
    if t in ("GC=F", "SI=F"):
        return "Or & métaux"
    if t.endswith("=F"):
        return "Matières premières"
    return "Actions"


def asset_subclass(t: str) -> str:
    if t in UNIVERSE:
        return UNIVERSE[t][2]
    return {"Crypto": "crypto", "Or & métaux": "gold",
            "Matières premières": "commo"}.get(asset_class(t), "us_eq")


# ══════════════════════════════════════════════════════════════════════════════
#  PRIX — téléchargement en lot + repli simulé
# ══════════════════════════════════════════════════════════════════════════════

_PERIOD_DAYS = {"1y": 252, "2y": 504, "3y": 756, "5y": 1260, "10y": 2520, "max": 5000}


def _download(tickers: list[str], period: str) -> pd.DataFrame:
    if not _YF or not tickers:
        return pd.DataFrame()
    try:
        raw = yf.download(" ".join(tickers), period=period, auto_adjust=True,
                          progress=False, threads=True)
    except Exception:
        return pd.DataFrame()
    if raw is None or raw.empty:
        return pd.DataFrame()
    closes = raw["Close"] if "Close" in raw else raw
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(name=tickers[0])
    closes = closes.copy()
    if getattr(closes.index, "tz", None) is not None:
        closes.index = closes.index.tz_localize(None)
    closes.index = pd.to_datetime(closes.index).normalize()
    return closes.sort_index()


# Paramètres du simulateur (rendement annuel, vol annuelle, bêta « risque »,
# bêta « taux », bêta « inflation ») — uniquement pour le mode hors-ligne.
_SIM = {
    "us_eq": (.09, .17, 1.0, -.1, 0), "tech": (.12, .23, 1.2, -.3, -.1),
    "us_small": (.08, .22, 1.15, -.1, 0), "intl_eq": (.06, .17, .9, -.1, 0),
    "em_eq": (.06, .21, 1.0, -.1, .1), "financials": (.08, .21, 1.1, .2, 0),
    "energy_eq": (.07, .26, .8, .1, .8), "defensive_eq": (.07, .14, .6, -.2, 0),
    "defense": (.09, .19, .7, 0, .2), "gov_long": (.03, .15, -.3, -1.3, -.4),
    "gov_int": (.03, .07, -.15, -.7, -.2), "gov_short": (.025, .02, 0, -.15, 0),
    "tips": (.03, .06, 0, -.5, .3), "ig": (.04, .08, .2, -.6, -.1),
    "hy": (.05, .09, .5, -.2, 0), "gold": (.06, .15, -.1, -.2, .5),
    "silver": (.05, .28, .3, -.2, .6), "commo": (.04, .19, .4, 0, 1.0),
    "oil": (.03, .35, .5, 0, 1.4), "reit": (.07, .21, .8, -.5, 0),
    "crypto": (.35, .70, 1.4, -.3, 0), "cash": (.03, .005, 0, 0, 0),
}


def _simulate(tickers: list[str], n_days: int, seed: int = 7) -> pd.DataFrame:
    """Prix simulés (modèle à 3 facteurs + régimes de volatilité).
    Sert uniquement de démonstration quand Yahoo Finance est injoignable."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n_days)
    # Régime de volatilité (chaîne de Markov calme / stress)
    stress = np.zeros(n_days)
    s = 0
    for i in range(n_days):
        if s == 0 and rng.random() < 0.006:
            s = 1
        elif s == 1 and rng.random() < 0.03:
            s = 0
        stress[i] = s
    vol_mult = np.where(stress == 1, 2.3, 0.85)
    f_risk = rng.standard_t(5, n_days) * 0.010 * vol_mult - stress * 0.0025
    f_rate = rng.normal(0, 0.004, n_days) + np.sin(np.arange(n_days) / 180) * 0.0004
    f_infl = rng.normal(0, 0.006, n_days) + np.cos(np.arange(n_days) / 260) * 0.0006
    out = {}
    for t in tickers:
        sub = asset_subclass(t)
        mu, vol, b_r, b_rate, b_inf = _SIM.get(sub, _SIM["us_eq"])
        sys = b_r * f_risk + b_rate * f_rate + b_inf * f_infl
        sys_var = np.var(sys) * 252
        idio_vol = math.sqrt(max(vol ** 2 - sys_var, (vol * 0.3) ** 2)) / math.sqrt(252)
        r = mu / 252 + sys + rng.normal(0, idio_vol, n_days) * vol_mult ** .5
        start = {"BTC-USD": 20000, "ETH-USD": 1500}.get(t, 50 + rng.random() * 150)
        out[t] = start * np.exp(np.cumsum(np.clip(r, -0.5, 0.5)))
    return pd.DataFrame(out, index=idx)


def _simulate_macro(n_days: int, equity: pd.Series | None, seed: int = 11) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = equity.index if equity is not None else pd.bdate_range(
        end=pd.Timestamp.today().normalize(), periods=n_days)
    n = len(idx)
    if equity is not None:
        rv = equity.pct_change().rolling(21).std().bfill() * np.sqrt(252) * 100
        vix = (rv * 1.1 + 4 + rng.normal(0, 1.2, n)).clip(9, 80)
    else:
        vix = pd.Series(16 + rng.normal(0, 3, n), index=idx).clip(9, 80)
    tnx = 3.0 + np.cumsum(rng.normal(0, 0.05, n))
    tnx = np.clip(tnx, 0.5, 6.5)
    irx = np.clip(tnx + 0.3 + np.cumsum(rng.normal(0, 0.04, n)) * 0.5, 0.05, 6)
    walk = lambda s0, v: s0 * np.exp(np.cumsum(rng.normal(0, v, n)))
    return pd.DataFrame({
        "VIX": np.asarray(vix), "US10Y": tnx, "US3M": irx,
        "DXY": walk(100, 0.004), "WTI": walk(75, 0.022),
        "GOLD": walk(2000, 0.009), "COPPER": walk(4, 0.014),
    }, index=idx)


@_cache(ttl=3600, show_spinner=False)
def fetch_prices(tickers: tuple, period: str = "5y") -> tuple[pd.DataFrame, str]:
    """Clôtures ajustées alignées sur les jours ouvrés.
    Renvoie (DataFrame, source) ; source = 'yahoo' | 'partiel' | 'simulé'."""
    tickers = list(dict.fromkeys(tickers))
    n_days = _PERIOD_DAYS.get(period, 1260)
    df = _download(tickers, period)
    got = [t for t in tickers if t in df.columns and df[t].notna().sum() > 60]
    if len(got) >= max(2, int(0.6 * len(tickers))):
        df = df[got]
        # calendrier = jours ouvrés (les cryptos cotent le week-end)
        df = df[df.index.dayofweek < 5].ffill(limit=5)
        df = df.dropna(how="all")
        missing = [t for t in tickers if t not in got]
        return df, ("partiel" if missing else "yahoo")
    return _simulate(tickers, n_days), "simulé"


@_cache(ttl=3600, show_spinner=False)
def fetch_macro(period: str = "5y") -> tuple[pd.DataFrame, str]:
    """Séries macro de marché (VIX, taux 10 ans / 3 mois, dollar, pétrole, or, cuivre)."""
    df = _download(list(MACRO_TICKERS), period)
    cols = {k: v for k, v in MACRO_TICKERS.items() if k in df.columns and df[k].notna().sum() > 60}
    if len(cols) >= 5:
        df = df[list(cols)].rename(columns=cols)
        df = df[df.index.dayofweek < 5].ffill(limit=5).dropna(how="all")
        for c in MACRO_TICKERS.values():
            if c not in df.columns:
                df[c] = np.nan
        return df, "yahoo"
    eq, _ = fetch_prices(("SPY",), period)
    return _simulate_macro(len(eq), eq["SPY"] if "SPY" in eq else None), "simulé"


# ══════════════════════════════════════════════════════════════════════════════
#  INDICATEURS MACRO
# ══════════════════════════════════════════════════════════════════════════════

def macro_features(macro: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Facteurs macro journaliers utilisés par les modèles (sans regard vers le futur)."""
    idx = prices.index
    m = macro.reindex(idx).ffill(limit=5)
    f = pd.DataFrame(index=idx)
    vix = m["VIX"]
    f["vix"] = vix
    f["vix_chg_21"] = vix - vix.shift(21)
    f["vix_z"] = (vix - vix.rolling(252, min_periods=60).mean()) / vix.rolling(252, min_periods=60).std()
    f["curve"] = m["US10Y"] - m["US3M"]
    f["rate_chg_63"] = m["US10Y"] - m["US10Y"].shift(63)
    f["dxy_63"] = m["DXY"].pct_change(63, fill_method=None)
    f["oil_63"] = m["WTI"].pct_change(63, fill_method=None)
    f["gold_63"] = m["GOLD"].pct_change(63, fill_method=None)
    cg = m["COPPER"] / m["GOLD"]
    f["copper_gold_63"] = cg.pct_change(63, fill_method=None)
    if "HYG" in prices and "IEF" in prices:
        f["credit_63"] = (prices["HYG"] / prices["IEF"]).pct_change(63, fill_method=None)
    else:
        f["credit_63"] = np.nan
    if "SPY" in prices:
        spy = prices["SPY"]
        f["spy_trend"] = spy / spy.rolling(200, min_periods=120).mean() - 1
        f["spy_ret_63"] = spy.pct_change(63, fill_method=None)
        f["spy_vol_63"] = spy.pct_change(fill_method=None).rolling(63).std() * np.sqrt(252)
    else:
        f["spy_trend"] = f["spy_ret_63"] = f["spy_vol_63"] = np.nan
    return f


def _pct_rank(s: pd.Series, v: float) -> float:
    s = s.dropna()
    return float((s < v).mean() * 100) if len(s) else 50.0


def macro_dashboard(macro: pd.DataFrame, mf: pd.DataFrame) -> list[dict]:
    """Tableau d'indicateurs avec lecture : +1 favorable au risque, -1 défavorable."""
    last = mf.dropna(how="all").iloc[-1]
    mlast = macro.dropna(how="all").iloc[-1]
    rows = []

    def add(name, val, fmt, signal, comment):
        rows.append({"indicateur": name, "valeur": val, "format": fmt,
                     "signal": signal, "lecture": comment})

    vix = float(mlast.get("VIX", np.nan))
    pr = _pct_rank(macro["VIX"], vix)
    add("VIX (peur implicite)", vix, "{:.1f}",
        1 if vix < 16 else (-1 if vix > 24 else 0),
        f"{pr:.0f}e centile sur la période — " +
        ("marché serein" if vix < 16 else "stress élevé, couverture recherchée" if vix > 24 else "nervosité modérée"))
    curve = float(last.get("curve", np.nan))
    add("Pente 10 ans – 3 mois (pts)", curve, "{:+.2f}",
        1 if curve > 0.5 else (-1 if curve < 0 else 0),
        "courbe inversée : signal historique de récession" if curve < 0 else
        "courbe positive : cycle sain" if curve > 0.5 else "courbe plate")
    rc = float(last.get("rate_chg_63", np.nan))
    add("Variation taux 10 ans (3 mois, pts)", rc, "{:+.2f}",
        -1 if rc > 0.4 else (1 if rc < -0.3 else 0),
        "hausse rapide des taux : pression sur obligations longues et valorisations" if rc > 0.4 else
        "détente des taux : soutien aux obligations et à la croissance" if rc < -0.3 else "taux stables")
    d = float(last.get("dxy_63", np.nan))
    add("Dollar (DXY, 3 mois)", d, "{:+.1%}",
        -1 if d > 0.03 else (1 if d < -0.03 else 0),
        "dollar fort : vent contraire pour émergents et matières premières" if d > 0.03 else
        "dollar faible : favorable aux émergents et à l'or" if d < -0.03 else "dollar stable")
    o = float(last.get("oil_63", np.nan))
    add("Pétrole WTI (3 mois)", o, "{:+.1%}",
        -1 if o > 0.15 else (0 if o > -0.15 else 1),
        "choc pétrolier : risque inflationniste / géopolitique" if o > 0.15 else
        "pétrole en baisse : désinflation" if o < -0.15 else "pétrole stable")
    cg = float(last.get("copper_gold_63", np.nan))
    add("Ratio cuivre / or (3 mois)", cg, "{:+.1%}",
        1 if cg > 0.03 else (-1 if cg < -0.03 else 0),
        "anticipations de croissance en hausse" if cg > 0.03 else
        "aversion au risque, préférence pour l'or" if cg < -0.03 else "neutre")
    cr = float(last.get("credit_63", np.nan))
    add("Crédit HY vs Treasuries (3 mois)", cr, "{:+.1%}",
        1 if cr > 0.01 else (-1 if cr < -0.02 else 0),
        "spreads qui se resserrent : appétit pour le risque" if cr > 0.01 else
        "spreads qui s'écartent : stress de crédit" if cr < -0.02 else "crédit stable")
    tr = float(last.get("spy_trend", np.nan))
    add("S&P 500 vs moyenne 200 j", tr, "{:+.1%}",
        1 if tr > 0.02 else (-1 if tr < -0.02 else 0),
        "tendance haussière de fond" if tr > 0.02 else
        "sous la moyenne 200 j : tendance baissière" if tr < -0.02 else "au contact de la moyenne")
    return rows


def macro_risk_score(rows: list[dict]) -> float:
    """Score composite -100 (défavorable) … +100 (favorable au risque)."""
    sig = [r["signal"] for r in rows if r["valeur"] == r["valeur"]]
    return float(np.mean(sig) * 100) if sig else 0.0


# ══════════════════════════════════════════════════════════════════════════════
#  ACTUALITÉS — géopolitique & économie
# ══════════════════════════════════════════════════════════════════════════════

_FEEDS = [
    ("geopolitics war conflict sanctions markets", "Géopolitique"),
    ("tariffs trade war export controls", "Géopolitique"),
    ("federal reserve ECB interest rates decision", "Banques centrales"),
    ("inflation CPI jobs report GDP economy", "Économie"),
    ("stock market earnings wall street", "Marchés"),
    ("oil OPEC gas energy supply", "Énergie"),
    ("gold commodities prices", "Matières premières"),
    ("bitcoin crypto regulation ETF", "Crypto"),
    ("marchés financiers bourse BCE", "Marchés"),
]

# Thèmes : mots-clés EN + FR (regex sur titres en minuscules)
THEMES: dict[str, dict] = {
    "geo_conflict": {"label": "Conflits / tensions géopolitiques",
        "kw": r"\b(war|wars|missile|invasion|invade|military|troops|airstrike|strike on|attack|conflict|"
              r"escalat\w*|tension\w*|ceasefire collapse|nuclear|drone|hostage|coup|terror\w*|"
              r"guerre|conflit|attaque|frappe|militaire|escalade|tensions?)\b"},
    "sanctions_trade": {"label": "Sanctions / guerre commerciale",
        "kw": r"\b(sanction\w*|tariff\w*|trade war|embargo|export control\w*|blacklist|retaliat\w*|"
              r"droits de douane|taxes douanières|embargo|représailles)\b"},
    "peace_deal": {"label": "Désescalade / accords",
        "kw": r"\b(ceasefire|peace (deal|talks|agreement)|truce|de-escalat\w*|trade deal|agreement reached|"
              r"cessez-le-feu|accord de paix|trêve|accord commercial)\b"},
    "energy_supply": {"label": "Choc d'offre énergétique",
        "kw": r"\b(opec\+? (cut|cuts)|output cut|supply (disruption|shock)|pipeline|strait of hormuz|"
              r"red sea|refinery|oil (surge|spike|jumps|soars)|pénurie|coupure)\b"},
    "hawkish": {"label": "Banques centrales restrictives",
        "kw": r"\b(rate hike|hikes rates|raise[sd]? rates|hawkish|tighten\w*|higher for longer|"
              r"hausse des taux|relève ses taux|restrictive)\b"},
    "dovish": {"label": "Banques centrales accommodantes",
        "kw": r"\b(rate cut|cuts rates|cut rates|dovish|easing|stimulus|pivot|lower rates|"
              r"baisse des taux|abaisse ses taux|assouplissement|relance)\b"},
    "inflation": {"label": "Inflation",
        "kw": r"\b(inflation (rises|jumps|hot|accelerat\w*|surge\w*)|hot cpi|price pressures|"
              r"inflation (higher|sticky)|inflation repart|flambée des prix)\b"},
    "disinflation": {"label": "Désinflation",
        "kw": r"\b(inflation (cools|eases|slows|falls)|disinflation|cooler cpi|"
              r"inflation (ralentit|recule|baisse))\b"},
    "recession": {"label": "Ralentissement / récession",
        "kw": r"\b(recession|slowdown|contraction|layoffs|job losses|unemployment (rises|jumps)|"
              r"weak (data|demand)|default\w*|bankrupt\w*|downgrade\w*|récession|ralentissement|"
              r"chômage|licenciements|faillite)\b"},
    "growth": {"label": "Croissance solide",
        "kw": r"\b(strong (jobs|growth|data|earnings)|beats? (estimates|expectations)|record high|"
              r"all-time high|rally|surge in (hiring|sales)|soft landing|upgrade\w*|"
              r"croissance (solide|forte)|record|rebond)\b"},
    "tech_ai": {"label": "Tech / IA",
        "kw": r"\b(ai|artificial intelligence|nvidia|chip\w*|semiconductor\w*|data cent(er|re)s?|"
              r"intelligence artificielle|puces)\b"},
    "crypto_pos": {"label": "Crypto : adoption",
        "kw": r"\b(etf (inflows|approval|approved)|adoption|bitcoin (rall\w*|surge\w*|record|jumps)|"
              r"crypto (rall\w*|surge\w*))\b"},
    "crypto_neg": {"label": "Crypto : régulation / stress",
        "kw": r"\b(crypto (crackdown|ban|crash|selloff)|bitcoin (falls|plunge\w*|crash\w*|tumbles)|"
              r"hack\w*|exchange (collapse|outage)|sec (sues|lawsuit))\b"},
}

_POS = r"\b(gain\w*|rise[sn]?|rising|rall\w*|surge\w*|jump\w*|soar\w*|record|beat\w*|strong|optimis\w*|" \
       r"rebound\w*|recover\w*|boost\w*|upgrade\w*|hausse|progresse|rebond|optimisme|record)\b"
_NEG = r"\b(fall\w*|drop\w*|plunge\w*|slump\w*|tumble\w*|crash\w*|fear\w*|worr\w*|risk\w*|weak\w*|" \
       r"loss\w*|cut\w*|warn\w*|crisis|selloff|sell-off|downgrade\w*|baisse|chute|recul|crainte\w*|" \
       r"inquiétude\w*|crise|menace\w*)\b"

# Matrice d'impact : thème -> effet attendu par sous-classe (-1 … +1).
# Hypothèses de marché usuelles, volontairement simples et transparentes.
IMPACT: dict[str, dict[str, float]] = {
    "geo_conflict": {"us_eq": -.5, "tech": -.5, "us_small": -.6, "intl_eq": -.7, "em_eq": -.8,
                     "financials": -.5, "energy_eq": .5, "defense": .8, "defensive_eq": .1,
                     "gov_long": .5, "gov_int": .4, "gov_short": .2, "tips": .2, "ig": -.1,
                     "hy": -.5, "gold": .9, "silver": .4, "commo": .5, "oil": .8, "reit": -.3,
                     "crypto": -.4, "cash": .2},
    "sanctions_trade": {"us_eq": -.4, "tech": -.6, "us_small": -.2, "intl_eq": -.6, "em_eq": -.8,
                        "financials": -.3, "energy_eq": .2, "defense": .3, "defensive_eq": .1,
                        "gov_long": .3, "gov_int": .3, "gov_short": .1, "tips": .2, "ig": -.1,
                        "hy": -.4, "gold": .6, "silver": .2, "commo": .3, "oil": .3, "reit": -.2,
                        "crypto": -.2, "cash": .1},
    "peace_deal": {"us_eq": .4, "tech": .4, "us_small": .5, "intl_eq": .6, "em_eq": .7,
                   "financials": .4, "energy_eq": -.4, "defense": -.5, "defensive_eq": 0,
                   "gov_long": -.2, "gov_int": -.1, "gov_short": 0, "tips": -.1, "ig": .1,
                   "hy": .4, "gold": -.6, "silver": -.2, "commo": -.3, "oil": -.6, "reit": .2,
                   "crypto": .3, "cash": -.1},
    "energy_supply": {"us_eq": -.3, "tech": -.3, "us_small": -.3, "intl_eq": -.5, "em_eq": -.3,
                      "financials": -.1, "energy_eq": .9, "defense": .2, "defensive_eq": 0,
                      "gov_long": -.3, "gov_int": -.2, "gov_short": 0, "tips": .5, "ig": -.1,
                      "hy": -.1, "gold": .4, "silver": .2, "commo": .8, "oil": 1.0, "reit": -.2,
                      "crypto": -.1, "cash": 0},
    "hawkish": {"us_eq": -.4, "tech": -.7, "us_small": -.6, "intl_eq": -.3, "em_eq": -.5,
                "financials": .3, "energy_eq": -.1, "defense": -.1, "defensive_eq": -.2,
                "gov_long": -.8, "gov_int": -.5, "gov_short": -.1, "tips": -.4, "ig": -.5,
                "hy": -.4, "gold": -.4, "silver": -.4, "commo": -.2, "oil": -.1, "reit": -.7,
                "crypto": -.6, "cash": .5},
    "dovish": {"us_eq": .5, "tech": .7, "us_small": .7, "intl_eq": .4, "em_eq": .6,
               "financials": -.1, "energy_eq": .1, "defense": .1, "defensive_eq": .2,
               "gov_long": .8, "gov_int": .5, "gov_short": .2, "tips": .3, "ig": .5,
               "hy": .5, "gold": .6, "silver": .5, "commo": .2, "oil": .1, "reit": .7,
               "crypto": .7, "cash": -.4},
    "inflation": {"us_eq": -.3, "tech": -.5, "us_small": -.3, "intl_eq": -.2, "em_eq": -.1,
                  "financials": .1, "energy_eq": .5, "defense": 0, "defensive_eq": -.1,
                  "gov_long": -.9, "gov_int": -.6, "gov_short": -.1, "tips": .7, "ig": -.5,
                  "hy": -.2, "gold": .6, "silver": .5, "commo": .8, "oil": .6, "reit": -.3,
                  "crypto": .1, "cash": .2},
    "disinflation": {"us_eq": .4, "tech": .6, "us_small": .4, "intl_eq": .3, "em_eq": .3,
                     "financials": 0, "energy_eq": -.3, "defense": 0, "defensive_eq": .2,
                     "gov_long": .8, "gov_int": .6, "gov_short": .1, "tips": -.2, "ig": .5,
                     "hy": .3, "gold": .1, "silver": 0, "commo": -.5, "oil": -.5, "reit": .5,
                     "crypto": .3, "cash": -.2},
    "recession": {"us_eq": -.7, "tech": -.6, "us_small": -.9, "intl_eq": -.7, "em_eq": -.8,
                  "financials": -.8, "energy_eq": -.7, "defense": -.1, "defensive_eq": .3,
                  "gov_long": .9, "gov_int": .7, "gov_short": .3, "tips": .1, "ig": .1,
                  "hy": -.8, "gold": .5, "silver": -.3, "commo": -.7, "oil": -.8, "reit": -.6,
                  "crypto": -.6, "cash": .4},
    "growth": {"us_eq": .7, "tech": .7, "us_small": .8, "intl_eq": .6, "em_eq": .6,
               "financials": .7, "energy_eq": .4, "defense": .2, "defensive_eq": -.1,
               "gov_long": -.4, "gov_int": -.3, "gov_short": 0, "tips": 0, "ig": .1,
               "hy": .6, "gold": -.2, "silver": .3, "commo": .5, "oil": .4, "reit": .4,
               "crypto": .5, "cash": -.3},
    "tech_ai": {"us_eq": .3, "tech": .9, "us_small": .1, "intl_eq": .1, "em_eq": .2,
                "financials": 0, "energy_eq": .1, "defense": 0, "defensive_eq": 0,
                "gov_long": 0, "gov_int": 0, "gov_short": 0, "tips": 0, "ig": 0,
                "hy": 0, "gold": 0, "silver": .2, "commo": .1, "oil": 0, "reit": .1,
                "crypto": .2, "cash": 0},
    "crypto_pos": {k: 0 for k in _SIM} | {"crypto": 1.0, "tech": .1},
    "crypto_neg": {k: 0 for k in _SIM} | {"crypto": -1.0},
}

_STATIC_HEADLINES = [
    ("Géopolitique", "Tensions in the Middle East push oil and gold higher"),
    ("Géopolitique", "New tariffs threaten global trade as talks stall"),
    ("Banques centrales", "Fed signals patience, markets price in rate cut later this year"),
    ("Banques centrales", "ECB holds rates as inflation eases toward target"),
    ("Économie", "US jobs report beats expectations, soft landing hopes rise"),
    ("Économie", "Euro zone factory activity contracts again"),
    ("Marchés", "Wall Street hits record high on strong AI earnings"),
    ("Énergie", "OPEC+ extends output cuts, oil jumps"),
    ("Matières premières", "Gold near record as investors seek safe haven"),
    ("Crypto", "Bitcoin ETF inflows rebound after volatile week"),
]


@_cache(ttl=900, show_spinner=False)
def fetch_news(per_feed: int = 10) -> tuple[list[dict], str]:
    """Titres d'actualité (Google News RSS). Renvoie (liste, source)."""
    out: list[dict] = []
    try:
        import urllib.parse
        import urllib.request
        from xml.etree import ElementTree as ET
        for q, cat in _FEEDS:
            fr = any(w in q for w in ("marchés", "bourse", "BCE"))
            url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q + " when:7d") +
                   ("&hl=fr&gl=FR&ceid=FR:fr" if fr else "&hl=en&gl=US&ceid=US:en"))
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    root = ET.fromstring(r.read())
                for item in root.findall(".//item")[:per_feed]:
                    raw = (item.findtext("title") or "").strip()
                    title = raw.rsplit(" - ", 1)[0].strip()
                    src = raw.rsplit(" - ", 1)[1].strip() if " - " in raw else ""
                    if title:
                        out.append({"title": title, "category": cat, "source": src,
                                    "link": item.findtext("link") or "",
                                    "pubdate": item.findtext("pubDate") or ""})
            except Exception:
                continue
    except Exception:
        pass
    seen, uniq = set(), []
    for n in out:
        k = n["title"].lower()[:80]
        if k not in seen:
            seen.add(k)
            uniq.append(n)
    if len(uniq) >= 8:
        return uniq, "google-news"
    return [{"title": t, "category": c, "source": "exemple", "link": "", "pubdate": ""}
            for c, t in _STATIC_HEADLINES], "exemple"


def score_headline(title: str) -> dict:
    t = title.lower()
    themes = [k for k, v in THEMES.items() if re.search(v["kw"], t)]
    pos = len(re.findall(_POS, t))
    neg = len(re.findall(_NEG, t))
    sent = (pos - neg) / max(1, pos + neg)
    # Les thèmes de stress dominent la tonalité même sans verbe négatif
    if any(th in themes for th in ("geo_conflict", "recession", "crypto_neg", "sanctions_trade")) and sent >= 0:
        sent = min(sent, -0.25)
    if any(th in themes for th in ("peace_deal", "growth", "crypto_pos", "disinflation")) and sent <= 0:
        sent = max(sent, 0.25)
    return {"themes": themes, "sentiment": float(np.clip(sent, -1, 1))}


def analyse_news(news: list[dict]) -> dict:
    """Agrège les titres : intensité par thème, indice géopolitique, tilt par sous-classe."""
    rows = []
    for n in news:
        s = score_headline(n["title"])
        rows.append({**n, **s})
    total = max(1, len(rows))
    intensity = {k: sum(1 for r in rows if k in r["themes"]) / total for k in THEMES}
    geo_rows = [r for r in rows if {"geo_conflict", "sanctions_trade"} & set(r["themes"])]
    geo_share = len(geo_rows) / total
    peace = intensity["peace_deal"]
    geo_neg = -np.mean([r["sentiment"] for r in geo_rows]) if geo_rows else 0.0
    gpr = float(np.clip(100 * (geo_share / 0.30) * (0.7 + 0.3 * max(geo_neg, 0)) - 60 * peace, 0, 100))
    econ_keys = ["growth", "recession", "inflation", "disinflation", "hawkish", "dovish"]
    econ = (intensity["growth"] + intensity["disinflation"] + intensity["dovish"]
            - intensity["recession"] - intensity["inflation"] - intensity["hawkish"])
    econ_score = float(np.clip(econ / 0.25, -1, 1) * 100)
    sentiment = float(np.mean([r["sentiment"] for r in rows])) if rows else 0.0
    # Tilt par sous-classe : somme pondérée des intensités x matrice d'impact
    # moyenne des impacts pondérée par l'intensité des thèmes, amortie quand
    # peu de titres sont classés (évite de sur-réagir à 2 ou 3 articles)
    tilts = {}
    tot_int = sum(intensity.values())
    for sub in _SIM:
        v = sum(intensity[th] * IMPACT.get(th, {}).get(sub, 0) for th in THEMES)
        tilts[sub] = float(np.clip(v / (tot_int + 0.15), -1, 1))
    return {"rows": rows, "intensity": intensity, "gpr": gpr, "econ_score": econ_score,
            "sentiment": sentiment, "tilts": tilts, "n": len(rows),
            "econ_keys": econ_keys}


def news_tilt_for(tickers: list[str], news_view: dict) -> pd.Series:
    t = news_view.get("tilts", {})
    return pd.Series({tk: t.get(asset_subclass(tk), 0.0) for tk in tickers})


def now_str() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M UTC")
