"""
utils/advisor.py — Moteur du « Hedge Fund Agent » de MAM
==========================================================

Desk multi-rôles inspiré des « AI trading desks » : chaque rôle fait un seul
travail, sur les mêmes données, et c'est un moteur de risque DÉTERMINISTE qui a
le dernier mot. Aucun ordre n'est exécuté sans validation humaine.

    1. Données      → prix des actifs proxy + indicateurs macro (yfinance)
    2. Veille       → actualités Google News : géopolitique, politique, banques
                      centrales, inflation, récession, énergie, banques, commerce…
    3. Macro        → 8 facteurs notés de -2 à +2 + régime économique
    4. Stratège     → allocation stratégique (profil) + inclinaisons tactiques
                      expliquées facteur par facteur
    5. Risque       → plafonds, cash minimum, volatilité cible : corrige ou bloque
    6. Conseiller   → diagnostic d'un portefeuille existant, stress tests
    7. Commentaire  → texte déterministe, ou LLM optionnel (Groq / Gemini)

Le module est autonome : il ne dépend d'aucun autre fichier de MAM, donc il ne
peut rien casser. Si Yahoo Finance ou Google News sont injoignables, il bascule
sur des données simulées CLAIREMENT signalées, et l'exécution est alors bloquée.

Outil pédagogique : ne constitue pas un conseil en investissement.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import quote_plus
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

try:
    import streamlit as st
    _cache = st.cache_data
except Exception:  # utilisation hors Streamlit (tests)
    st = None

    def _cache(*a, **k):
        def deco(f):
            return f
        return deco


# ══════════════════════════════════════════════════════════════════════════════
# 1. Univers : classes d'actifs et proxies
# ══════════════════════════════════════════════════════════════════════════════
CLASSES = [
    "Actions US", "Actions Europe", "Actions Asie & émergents",
    "Oblig. long terme", "Oblig. moyen terme", "Crédit IG", "High yield",
    "Or", "Matières premières", "Crypto", "Liquidités",
]
EQUITY_CLASSES = ["Actions US", "Actions Europe", "Actions Asie & émergents"]

# Un ETF liquide par classe (sert au calcul de volatilité / corrélations)
CLASS_PROXY = {
    "Actions US": "SPY", "Actions Europe": "VGK", "Actions Asie & émergents": "EEM",
    "Oblig. long terme": "TLT", "Oblig. moyen terme": "IEF", "Crédit IG": "LQD",
    "High yield": "HYG", "Or": "GLD", "Matières premières": "DBC",
    "Crypto": "BTC-USD", "Liquidités": "BIL",
}

# Indicateurs macro / marché
MACRO_TICKERS = {
    "vix": "^VIX", "us10y": "^TNX", "us3m": "^IRX", "dollar": "DX-Y.NYB",
    "oil": "CL=F", "copper": "HG=F", "gold": "GC=F", "eurusd": "EURUSD=X",
}

ALL_TICKERS = sorted(set(CLASS_PROXY.values()) | set(MACRO_TICKERS.values()))

# ══════════════════════════════════════════════════════════════════════════════
# 2. Facteurs et sensibilités (dire d'expert, signe = effet d'une HAUSSE du facteur)
# ══════════════════════════════════════════════════════════════════════════════
FACTORS = {
    "croissance":  ("Croissance économique", "+ = croissance qui accélère"),
    "inflation":   ("Pression inflationniste", "+ = inflation qui accélère"),
    "monetaire":   ("Politique monétaire", "+ = banques centrales restrictives"),
    "credit":      ("Crédit & liquidité", "+ = conditions de financement faciles"),
    "stress":      ("Stress de marché", "+ = volatilité / peur élevées"),
    "dollar":      ("Dollar US", "+ = dollar fort"),
    "geopolitique": ("Risque géopolitique & politique", "+ = tensions élevées"),
    "energie":     ("Choc énergétique", "+ = pétrole / gaz sous tension"),
}
F_KEYS = list(FACTORS)

#            croiss infl  monét crédit stress dollar géopo énergie
SENSITIVITY = pd.DataFrame([
    [ 1.0, -0.4, -0.6,  0.7, -0.9, -0.2, -0.5, -0.3],   # Actions US
    [ 1.0, -0.4, -0.5,  0.6, -0.9,  0.1, -0.7, -0.6],   # Actions Europe
    [ 1.0, -0.2, -0.6,  0.7, -1.0, -0.9, -0.6,  0.0],   # Asie & émergents
    [-0.8, -1.0, -0.9, -0.2,  0.8,  0.0,  0.5, -0.4],   # Oblig. long terme
    [-0.5, -0.7, -0.6,  0.0,  0.6,  0.0,  0.4, -0.3],   # Oblig. moyen terme
    [ 0.2, -0.6, -0.6,  0.5, -0.2,  0.0,  0.0, -0.2],   # Crédit IG
    [ 0.7, -0.3, -0.4,  1.0, -0.8, -0.2, -0.4, -0.1],   # High yield
    [-0.2,  0.7, -0.7, -0.1,  0.6, -0.8,  1.0,  0.3],   # Or
    [ 0.7,  1.0, -0.2,  0.3, -0.4, -0.6,  0.4,  1.0],   # Matières premières
    [ 0.6, -0.1, -0.9,  0.8, -1.0, -0.5, -0.2, -0.2],   # Crypto
    [-0.3,  0.2,  0.8, -0.3,  0.7,  0.0,  0.4,  0.2],   # Liquidités
], index=CLASSES, columns=F_KEYS)

# ══════════════════════════════════════════════════════════════════════════════
# 3. Profils : allocation stratégique + limites du moteur de risque
# ══════════════════════════════════════════════════════════════════════════════
PROFILES = {
    "Prudent":   [.12, .06, .02, .08, .22, .18, .04, .08, .02, .00, .18],
    "Équilibré": [.25, .10, .05, .08, .14, .12, .05, .07, .04, .02, .08],
    "Dynamique": [.35, .13, .08, .05, .07, .07, .06, .06, .05, .04, .04],
    "Agressif":  [.42, .14, .11, .03, .03, .03, .06, .05, .05, .06, .02],
}
LIMITS = {
    #            crypto max, actions max, cash min, vol cible, classe max
    "Prudent":   dict(crypto=0.00, equity=0.30, cash=0.10, vol=0.06, single=0.40),
    "Équilibré": dict(crypto=0.03, equity=0.50, cash=0.04, vol=0.10, single=0.40),
    "Dynamique": dict(crypto=0.06, equity=0.70, cash=0.02, vol=0.14, single=0.45),
    "Agressif":  dict(crypto=0.10, equity=0.85, cash=0.00, vol=0.18, single=0.50),
}

# Scénarios de stress (variations approximatives par classe, en %)
SCENARIOS = pd.DataFrame({
    "Crise financière 2008":   [-50, -55, -55, 25, 12, -5, -30, 5, -45, -70, 0],
    "Covid (fév.–mars 2020)":  [-34, -38, -32, 20, 8, -12, -20, -3, -35, -50, 0],
    "Choc d'inflation 2022":   [-24, -20, -25, -31, -15, -18, -14, -1, 20, -65, 1],
    "Choc géopolitique (hyp.)": [-12, -18, -15, 6, 3, -3, -8, 10, 15, -20, 0],
    "Stagflation (hyp.)":      [-20, -22, -20, -15, -6, -10, -15, 15, 25, -35, 2],
}, index=CLASSES)

# ══════════════════════════════════════════════════════════════════════════════
# 4. Veille actualités : thèmes et mots-clés (FR + EN)
# ══════════════════════════════════════════════════════════════════════════════
NEWS_THEMES = {
    "conflits":    dict(label="Conflits armés", factor="geopolitique",
                        q="guerre OR conflit OR frappes OR missile OR invasion",
                        q_en="war OR military strike OR missile OR invasion"),
    "sanctions":   dict(label="Sanctions & embargos", factor="geopolitique",
                        q="sanctions OR embargo OR gel des avoirs",
                        q_en="sanctions OR embargo OR export controls"),
    "commerce":    dict(label="Guerre commerciale & droits de douane", factor="geopolitique",
                        q="droits de douane OR guerre commerciale OR protectionnisme",
                        q_en="tariffs OR trade war"),
    "politique":   dict(label="Instabilité politique & élections", factor="geopolitique",
                        q="élections OR crise politique OR gouvernement censure OR shutdown",
                        q_en="election OR government shutdown OR political crisis"),
    "banques_c":   dict(label="Banques centrales", factor="monetaire",
                        q="Fed OR BCE taux directeurs",
                        q_en="Federal Reserve OR ECB interest rates"),
    "inflation":   dict(label="Inflation", factor="inflation",
                        q="inflation hausse des prix",
                        q_en="inflation CPI"),
    "recession":   dict(label="Récession & chômage", factor="croissance",
                        q="récession OR chômage hausse OR ralentissement économique",
                        q_en="recession OR layoffs OR slowdown"),
    "croissance":  dict(label="Croissance & reprise", factor="croissance",
                        q="croissance économique OR reprise économique OR PIB hausse",
                        q_en="economic growth OR GDP beats"),
    "energie":     dict(label="Énergie (pétrole, gaz)", factor="energie",
                        q="pétrole OR OPEP OR prix du gaz",
                        q_en="oil prices OR OPEC OR natural gas"),
    "banques":     dict(label="Stress bancaire & dette", factor="credit",
                        q="faillite bancaire OR crise de la dette OR défaut souverain",
                        q_en="bank failure OR debt crisis OR default"),
    "desescalade": dict(label="Désescalade & accords", factor="geopolitique",
                        q="cessez-le-feu OR accord de paix OR désescalade",
                        q_en="ceasefire OR peace deal OR de-escalation"),
}


# ══════════════════════════════════════════════════════════════════════════════
# Rôle 1 — Données
# ══════════════════════════════════════════════════════════════════════════════
def _simulated_prices(tickers, n=520, seed=7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=n)
    out = {}
    for t in tickers:
        base = {"^VIX": 18, "^TNX": 4.2, "^IRX": 4.0, "DX-Y.NYB": 102,
                "EURUSD=X": 1.08}.get(t, 100.0)
        vol = {"^VIX": .06, "BTC-USD": .035, "^TNX": .015, "^IRX": .01}.get(t, .011)
        path = base * np.exp(np.cumsum(rng.normal(0.0002, vol, n)))
        out[t] = path
    return pd.DataFrame(out, index=idx)


@_cache(ttl=3600, show_spinner=False)
def load_prices(tickers: tuple = tuple(ALL_TICKERS), period: str = "2y"):
    """Renvoie (prix de clôture, simulé ?)."""
    try:
        import yfinance as yf
        raw = yf.download(list(tickers), period=period, interval="1d",
                          auto_adjust=True, progress=False, threads=True)
        px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw
        if isinstance(px, pd.Series):
            px = px.to_frame(tickers[0])
        px = px.dropna(how="all").ffill()
        ok = [t for t in tickers if t in px.columns and px[t].notna().sum() > 150]
        if len(ok) >= len(tickers) * 0.6:
            missing = [t for t in tickers if t not in ok]
            if missing:  # complète les manquants par du simulé, signalé
                sim = _simulated_prices(missing, n=len(px)).set_index(px.index)
                px = pd.concat([px[ok], sim], axis=1)
            return px, missing
    except Exception:
        pass
    return _simulated_prices(list(tickers)), list(tickers)


# ══════════════════════════════════════════════════════════════════════════════
# Rôle 2 — Veille actualités
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_rss(query: str, lang: str = "fr") -> list[dict]:
    import requests
    if lang == "fr":
        url = (f"https://news.google.com/rss/search?q={quote_plus(query + ' when:7d')}"
               "&hl=fr&gl=FR&ceid=FR:fr")
    else:
        url = (f"https://news.google.com/rss/search?q={quote_plus(query + ' when:7d')}"
               "&hl=en-US&gl=US&ceid=US:en")
    r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0 MAM-desk"})
    r.raise_for_status()
    root = ET.fromstring(r.content)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        src = (it.findtext("source") or "").strip()
        try:
            dt = parsedate_to_datetime(it.findtext("pubDate"))
        except Exception:
            dt = datetime.now(timezone.utc)
        if title:
            items.append(dict(title=title, link=link, source=src, date=dt))
    return items


@_cache(ttl=1800, show_spinner=False)
def load_news():
    """Intensité 0–100 par thème + titres récents. Renvoie (dict, simulé ?)."""
    now = datetime.now(timezone.utc)
    themes, failures = {}, 0
    for key, th in NEWS_THEMES.items():
        try:
            items = _fetch_rss(th["q"], "fr") + _fetch_rss(th["q_en"], "en")
        except Exception:
            failures += 1
            items = []
        seen, uniq = set(), []
        for it in items:
            k = re.sub(r"\W+", "", it["title"].lower())[:60]
            if k not in seen:
                seen.add(k)
                uniq.append(it)
        score = 0.0
        for it in uniq:
            age_d = max((now - it["date"]).total_seconds() / 86400, 0)
            score += 1.0 if age_d <= 2 else (0.6 if age_d <= 4 else 0.3)
        uniq.sort(key=lambda x: x["date"], reverse=True)
        themes[key] = dict(label=th["label"], factor=th["factor"],
                           intensity=float(min(100, score * 2.2)),
                           count=len(uniq), headlines=uniq[:6])
    simulated = failures >= len(NEWS_THEMES) * 0.7
    if simulated:
        rng = np.random.default_rng(3)
        for key, th in NEWS_THEMES.items():
            themes[key] = dict(label=th["label"], factor=th["factor"],
                               intensity=float(rng.uniform(20, 70)), count=0,
                               headlines=[])
    return themes, simulated


# ══════════════════════════════════════════════════════════════════════════════
# Rôle 3 — Macro : facteurs et régime
# ══════════════════════════════════════════════════════════════════════════════
def _clip(x, lo=-2.0, hi=2.0):
    if x is None or not np.isfinite(x):
        return 0.0
    return float(max(lo, min(hi, x)))


def _chg(s: pd.Series, n: int) -> float:
    s = s.dropna()
    if len(s) <= n or s.iloc[-n - 1] == 0:
        return float("nan")
    return float(s.iloc[-1] / s.iloc[-n - 1] - 1)


def _diff(s: pd.Series, n: int) -> float:
    s = s.dropna()
    return float(s.iloc[-1] - s.iloc[-n - 1]) if len(s) > n else float("nan")


@dataclass
class MacroView:
    factors: dict                 # clé → score [-2, 2]
    evidence: dict                # clé → liste de justifications lisibles
    regime: str
    regime_text: str
    indicators: dict = field(default_factory=dict)


def compute_macro(px: pd.DataFrame, news: dict) -> MacroView:
    g = lambda t: px[t] if t in px.columns else pd.Series(dtype=float)
    spy, vix = g("SPY"), g("^VIX")
    tnx, irx = g("^TNX"), g("^IRX")
    oil, cop, gold = g("CL=F"), g("HG=F"), g("GC=F")
    dxy, hyg, ief = g("DX-Y.NYB"), g("HYG"), g("IEF")

    ev = {k: [] for k in F_KEYS}
    ind = {}

    # Croissance : tendance actions, cuivre/or, pente de courbe, actualités
    trend = float(spy.iloc[-1] / spy.rolling(200).mean().iloc[-1] - 1) if len(spy) > 200 else np.nan
    cg = _chg(cop, 63) - _chg(gold, 63)
    curve = float(tnx.dropna().iloc[-1] - irx.dropna().iloc[-1]) if len(tnx.dropna()) and len(irx.dropna()) else np.nan
    news_g = (news["croissance"]["intensity"] - news["recession"]["intensity"]) / 30
    parts = [_clip(trend / 0.05), _clip(cg / 0.08), _clip(curve / 1.0), _clip(news_g)]
    f_growth = float(np.mean(parts))
    ind.update(spy_vs_ma200=trend, copper_gold_3m=cg, curve_10y_3m=curve)
    ev["croissance"] += [
        f"S&P 500 {'au-dessus' if trend > 0 else 'sous'} sa moyenne 200 j ({trend:+.1%})" if np.isfinite(trend) else "Tendance S&P 500 indisponible",
        f"Cuivre/or sur 3 mois : {cg:+.1%}" if np.isfinite(cg) else "Cuivre/or indisponible",
        f"Pente 10 ans – 3 mois : {curve:+.2f} pt" + (" (courbe inversée)" if np.isfinite(curve) and curve < 0 else "") if np.isfinite(curve) else "Courbe des taux indisponible",
        f"Actualités croissance vs récession : {news['croissance']['intensity']:.0f} / {news['recession']['intensity']:.0f}",
    ]

    # Inflation : pétrole, taux longs, or, actualités
    o3, t3, g3 = _chg(oil, 63), _diff(tnx, 63), _chg(gold, 63)
    f_infl = float(np.mean([_clip(o3 / 0.15), _clip(t3 / 0.5), _clip(g3 / 0.08),
                            _clip((news["inflation"]["intensity"] - 45) / 25)]))
    ev["inflation"] += [f"Pétrole 3 mois : {o3:+.1%}" if np.isfinite(o3) else "Pétrole indisponible",
                        f"Taux 10 ans US sur 3 mois : {t3:+.2f} pt" if np.isfinite(t3) else "Taux 10 ans indisponible",
                        f"Intensité des actualités inflation : {news['inflation']['intensity']:.0f}/100"]

    # Politique monétaire : niveau et variation du taux court
    i6 = _diff(irx, 126)
    lvl = float(irx.dropna().iloc[-1]) if len(irx.dropna()) else np.nan
    f_mon = float(np.mean([_clip(i6 / 0.75), _clip((lvl - 3.0) / 1.5) if np.isfinite(lvl) else 0.0,
                           _clip((news["banques_c"]["intensity"] - 50) / 30) * 0.5]))
    ev["monetaire"] += [f"Taux 3 mois US : {lvl:.2f} %" if np.isfinite(lvl) else "Taux court indisponible",
                        f"Variation sur 6 mois : {i6:+.2f} pt" if np.isfinite(i6) else "",
                        f"Actualités banques centrales : {news['banques_c']['intensity']:.0f}/100"]

    # Crédit & liquidité : high yield vs Treasuries
    ratio = (hyg / ief).dropna() if len(hyg) and len(ief) else pd.Series(dtype=float)
    rc = _chg(ratio, 63)
    f_cred = float(np.mean([_clip(rc / 0.03), _clip(-(news["banques"]["intensity"] - 30) / 25)]))
    ev["credit"] += [f"High yield vs Treasuries sur 3 mois : {rc:+.1%}" if np.isfinite(rc) else "Spread de crédit indisponible",
                     f"Actualités stress bancaire / dette : {news['banques']['intensity']:.0f}/100"]

    # Stress de marché : VIX
    v = float(vix.dropna().iloc[-1]) if len(vix.dropna()) else np.nan
    f_stress = _clip((v - 18) / 6) if np.isfinite(v) else 0.0
    ind["vix"] = v
    ev["stress"] += [f"VIX : {v:.1f}" + (" (élevé)" if v > 25 else " (calme)" if v < 15 else "") if np.isfinite(v) else "VIX indisponible"]

    # Dollar
    d3 = _chg(dxy, 63)
    f_usd = _clip(d3 / 0.04)
    ev["dollar"] += [f"Indice dollar sur 3 mois : {d3:+.1%}" if np.isfinite(d3) else "Indice dollar indisponible"]

    # Géopolitique & politique : actualités
    geo_keys = ["conflits", "sanctions", "commerce", "politique"]
    geo = np.mean([news[k]["intensity"] for k in geo_keys]) - 0.5 * news["desescalade"]["intensity"]
    f_geo = _clip((geo - 25) / 15)
    for k in geo_keys + ["desescalade"]:
        ev["geopolitique"].append(f"{news[k]['label']} : {news[k]['intensity']:.0f}/100")

    # Énergie
    o1 = _chg(oil, 21)
    f_en = float(np.mean([_clip(o1 / 0.10), _clip((news["energie"]["intensity"] - 45) / 25)]))
    ev["energie"] += [f"Pétrole sur 1 mois : {o1:+.1%}" if np.isfinite(o1) else "Pétrole indisponible",
                      f"Actualités énergie : {news['energie']['intensity']:.0f}/100"]

    factors = dict(croissance=f_growth, inflation=f_infl, monetaire=f_mon, credit=f_cred,
                   stress=f_stress, dollar=f_usd, geopolitique=f_geo, energie=f_en)
    ev = {k: [e for e in v if e] for k, v in ev.items()}
    regime, text = classify_regime(factors)
    return MacroView(factors, ev, regime, text, ind)


def classify_regime(f: dict) -> tuple[str, str]:
    if f["stress"] > 1.2 or (f["credit"] < -1.0 and f["stress"] > 0.5):
        return "Aversion au risque", ("Stress de marché élevé : priorité à la protection du capital "
                                       "(liquidités, obligations d'État, or), réduction des actifs risqués.")
    g, i = f["croissance"], f["inflation"]
    if g >= 0 and i < 0.3:
        return "Expansion désinflationniste", ("Croissance solide et inflation contenue : environnement "
                                                "favorable aux actions et au crédit.")
    if g >= 0 and i >= 0.3:
        return "Surchauffe / reflation", ("Croissance et inflation en hausse : matières premières et actions "
                                          "cycliques favorisées, obligations longues pénalisées.")
    if g < 0 and i >= 0.3:
        return "Stagflation", ("Croissance qui ralentit avec une inflation persistante : environnement le "
                               "plus difficile ; or, matières premières et liquidités en défense.")
    return "Ralentissement désinflationniste", ("Croissance qui ralentit et inflation qui reflue : les "
                                                 "obligations d'État redeviennent un amortisseur.")


# ══════════════════════════════════════════════════════════════════════════════
# Rôle 4 — Stratège : allocation proposée
# ══════════════════════════════════════════════════════════════════════════════
def class_scores(factors: dict) -> pd.Series:
    f = pd.Series(factors)[F_KEYS]
    return SENSITIVITY.dot(f)


def explain_class(cls: str, factors: dict, top: int = 3) -> list[str]:
    contrib = SENSITIVITY.loc[cls] * pd.Series(factors)[F_KEYS]
    contrib = contrib[contrib.abs() > 0.05].sort_values(key=lambda s: -s.abs())
    out = []
    for k, c in contrib.head(top).items():
        name = FACTORS[k][0].lower()
        level = "en hausse" if factors[k] > 0 else "en baisse"
        effect = "soutient" if c > 0 else "pèse sur"
        out.append(f"{FACTORS[k][0]} {level} ({factors[k]:+.1f}) → {effect} la classe")
    return out


def propose_allocation(factors: dict, profile: str, intensity: float = 0.5) -> pd.DataFrame:
    w0 = pd.Series(PROFILES[profile], index=CLASSES)
    s = class_scores(factors)
    tilt = np.tanh(s / 3.0)
    w = w0 * (1 + intensity * 0.6 * tilt)
    # une classe à 0 dans le profil peut recevoir un petit poids seulement si le signal est fort
    w = w.clip(lower=0)
    w = w / w.sum()
    return pd.DataFrame({"Stratégique": w0, "Score macro": s, "Proposée (avant risque)": w})


# ══════════════════════════════════════════════════════════════════════════════
# Rôle 5 — Moteur de risque (veto déterministe)
# ══════════════════════════════════════════════════════════════════════════════
def class_covariance(px: pd.DataFrame) -> pd.DataFrame:
    cols = {c: CLASS_PROXY[c] for c in CLASSES if CLASS_PROXY[c] in px.columns}
    rets = np.log(px[list(cols.values())]).diff().dropna().tail(252)
    rets.columns = list(cols.keys())
    cov = rets.cov() * 252
    cov = cov.reindex(index=CLASSES, columns=CLASSES)
    for c in CLASSES:  # classe manquante : vol par défaut, corrélation nulle
        if not np.isfinite(cov.loc[c, c]):
            cov.loc[c, :] = 0.0
            cov.loc[:, c] = 0.0
            cov.loc[c, c] = 0.0001 if c == "Liquidités" else 0.04
    return cov.fillna(0.0)


def port_vol(w: pd.Series, cov: pd.DataFrame) -> float:
    w = w.reindex(CLASSES).fillna(0)
    return float(math.sqrt(max(w @ cov @ w, 0)))


def risk_engine(w: pd.Series, profile: str, factors: dict, cov: pd.DataFrame,
                data_simulated: bool) -> tuple[pd.Series, list[dict], bool]:
    """Applique les limites. Renvoie (poids corrigés, contrôles, exécution autorisée ?)."""
    lim = dict(LIMITS[profile])
    w = w.reindex(CLASSES).fillna(0).copy()
    checks = []

    def log(rule, ok, detail):
        checks.append(dict(Règle=rule, Statut="✅ conforme" if ok else "⚠️ corrigé", Détail=detail))

    stress_mode = factors["stress"] > 1.0 or factors["geopolitique"] > 1.5
    if stress_mode:
        lim["cash"] += 0.05
        lim["equity"] -= 0.10
        checks.append(dict(Règle="Mode stress", Statut="🛡️ activé",
                           Détail="Cash minimum +5 pts, plafond actions -10 pts"))

    # Crypto
    if w["Crypto"] > lim["crypto"] + 1e-9:
        ex = w["Crypto"] - lim["crypto"]
        w["Crypto"] -= ex
        w["Liquidités"] += ex
        log(f"Crypto ≤ {lim['crypto']:.0%}", False, f"{ex:.1%} réalloués en liquidités")
    else:
        log(f"Crypto ≤ {lim['crypto']:.0%}", True, f"{w['Crypto']:.1%}")

    # Actions totales
    eq = w[EQUITY_CLASSES].sum()
    if eq > lim["equity"] + 1e-9:
        scale = lim["equity"] / eq
        ex = eq - lim["equity"]
        w[EQUITY_CLASSES] *= scale
        w["Oblig. moyen terme"] += ex * 0.6
        w["Liquidités"] += ex * 0.4
        log(f"Actions ≤ {lim['equity']:.0%}", False, f"{ex:.1%} basculés vers obligations / cash")
    else:
        log(f"Actions ≤ {lim['equity']:.0%}", True, f"{eq:.1%}")

    # Cash minimum
    if w["Liquidités"] < lim["cash"] - 1e-9:
        need = lim["cash"] - w["Liquidités"]
        others = w.drop("Liquidités")
        w[others.index] -= others / others.sum() * need
        w["Liquidités"] = lim["cash"]
        log(f"Liquidités ≥ {lim['cash']:.0%}", False, f"+{need:.1%} de cash")
    else:
        log(f"Liquidités ≥ {lim['cash']:.0%}", True, f"{w['Liquidités']:.1%}")

    # Concentration par classe
    big = w[w > lim["single"]]
    if len(big):
        for c, v in big.items():
            ex = v - lim["single"]
            w[c] = lim["single"]
            w["Liquidités"] += ex
        log(f"Aucune classe > {lim['single']:.0%}", False, ", ".join(big.index))
    else:
        log(f"Aucune classe > {lim['single']:.0%}", True, f"max {w.max():.1%}")

    # Volatilité cible : mélange avec un portefeuille défensif si besoin
    v = port_vol(w, cov)
    if v > lim["vol"]:
        safe = pd.Series(0.0, index=CLASSES)
        safe["Oblig. moyen terme"], safe["Liquidités"] = 0.5, 0.5
        lo, hi = 0.0, 1.0
        for _ in range(40):
            a = (lo + hi) / 2
            if port_vol(a * w + (1 - a) * safe, cov) > lim["vol"]:
                hi = a
            else:
                lo = a
        w = lo * w + (1 - lo) * safe
        log(f"Volatilité ≤ {lim['vol']:.0%}", False, f"{v:.1%} → {port_vol(w, cov):.1%} (dé-risquage {1-lo:.0%})")
    else:
        log(f"Volatilité ≤ {lim['vol']:.0%}", True, f"{v:.1%} estimée")

    w = (w.clip(lower=0) / w.clip(lower=0).sum())
    allowed = True
    if data_simulated:
        allowed = False
        checks.append(dict(Règle="Qualité des données", Statut="⛔ veto",
                           Détail="Données de marché simulées : validation possible, exécution bloquée"))
    else:
        checks.append(dict(Règle="Qualité des données", Statut="✅ conforme", Détail="Données réelles"))
    return w, checks, allowed


# ══════════════════════════════════════════════════════════════════════════════
# Rôle 6 — Conseiller : diagnostic d'un portefeuille existant
# ══════════════════════════════════════════════════════════════════════════════
_EU_SUFFIX = (".PA", ".DE", ".AS", ".MI", ".MC", ".L", ".SW", ".BR", ".ST", ".CO", ".HE", ".OL", ".LS", ".IR", ".VI")
_ASIA_SUFFIX = (".HK", ".T", ".SS", ".SZ", ".KS", ".TW", ".NS", ".BO", ".SA", ".MX", ".JK")


def classify_ticker(t: str) -> str | None:
    u = t.upper().strip()
    if u in ("CASH", "BIL", "SHV", "SGOV", "EUR", "USD"):
        return "Liquidités"
    if u.endswith("=X"):
        return "Liquidités"
    if u in ("GC=F", "SI=F", "GLD", "IAU", "SLV", "PHYS"):
        return "Or"
    if u.endswith("=F") or u in ("DBC", "USO", "PDBC", "GSG", "BNO", "UNG", "CPER"):
        return "Matières premières"
    if u.endswith("-USD") or u.endswith("-EUR"):
        return "Crypto"
    if u in ("TLT", "EDV", "ZROZ", "VGLT"):
        return "Oblig. long terme"
    if u in ("IEF", "IEI", "SHY", "GOVT", "AGG", "BND", "VGIT"):
        return "Oblig. moyen terme"
    if u in ("LQD", "VCIT", "IGIB"):
        return "Crédit IG"
    if u in ("HYG", "JNK", "USHY"):
        return "High yield"
    if u == "^VIX":
        return None
    if u.endswith(_EU_SUFFIX) or u in ("^FCHI", "^GDAXI", "^FTSE", "^STOXX50E", "VGK", "EZU", "FEZ", "EWG", "EWQ"):
        return "Actions Europe"
    if u.endswith(_ASIA_SUFFIX) or u in ("^N225", "^HSI", "EEM", "VWO", "EWJ", "FXI", "MCHI", "INDA"):
        return "Actions Asie & émergents"
    return "Actions US"


def portfolio_to_classes(holdings: dict) -> tuple[pd.Series, pd.Series]:
    """holdings : {ticker: valeur}. Renvoie (poids par classe, poids par ligne)."""
    h = pd.Series({k: float(v) for k, v in holdings.items() if v and float(v) > 0})
    if h.empty:
        return pd.Series(0.0, index=CLASSES), h
    line_w = h / h.sum()
    cls_w = pd.Series(0.0, index=CLASSES)
    for t, w in line_w.items():
        c = classify_ticker(t)
        if c:
            cls_w[c] += w
    if cls_w.sum() > 0:
        cls_w /= cls_w.sum()
    return cls_w, line_w


def stress_test(cls_w: pd.Series) -> pd.Series:
    return (SCENARIOS.mul(cls_w.reindex(CLASSES).fillna(0), axis=0).sum() / 100).sort_values()


def advise_portfolio(holdings: dict, macro: MacroView, profile: str, target: pd.Series,
                     cov: pd.DataFrame) -> dict:
    cls_w, line_w = portfolio_to_classes(holdings)
    advice = []  # (niveau, titre, détail)

    # 1. Écarts avec l'allocation recommandée
    gap = (target.reindex(CLASSES) - cls_w).sort_values()
    for c, g in gap.items():
        if abs(g) >= 0.05:
            sens = "Alléger" if g < 0 else "Renforcer"
            why = explain_class(c, macro.factors, top=2)
            advice.append(("action", f"{sens} « {c} » ({cls_w[c]:.0%} → {target[c]:.0%})",
                           " ; ".join(why) if why else "Rééquilibrage vers le profil cible"))

    # 2. Concentration
    for t, w in line_w.items():
        if w > 0.20:
            advice.append(("alerte", f"Concentration : {t} pèse {w:.0%} du portefeuille",
                           "Une seule ligne au-delà de 20 % expose à un risque idiosyncratique fort."))
    lim = LIMITS[profile]
    if cls_w["Crypto"] > lim["crypto"]:
        advice.append(("alerte", f"Crypto à {cls_w['Crypto']:.0%} (limite du profil {lim['crypto']:.0%})",
                       "Volatilité extrême et forte sensibilité aux conditions de liquidité."))
    if cls_w[EQUITY_CLASSES].sum() > lim["equity"]:
        advice.append(("alerte", f"Actions à {cls_w[EQUITY_CLASSES].sum():.0%} (limite {lim['equity']:.0%})",
                       "Exposition actions supérieure à ce que le profil tolère."))
    if cls_w["Liquidités"] < lim["cash"]:
        advice.append(("info", f"Liquidités à {cls_w['Liquidités']:.0%} (minimum conseillé {lim['cash']:.0%})",
                       "Garder du cash permet de saisir les opportunités en cas de baisse."))

    # 3. Expositions aux facteurs × situation actuelle = vulnérabilités
    expo = SENSITIVITY.T.dot(cls_w.reindex(CLASSES).fillna(0))
    risk = (expo * pd.Series(macro.factors)).sort_values()
    for k, r in risk.items():
        if r < -0.25:
            advice.append(("risque", f"Vulnérable : {FACTORS[k][0].lower()}",
                           f"Exposition du portefeuille {expo[k]:+.2f} alors que le facteur est à "
                           f"{macro.factors[k]:+.1f} : ce contexte pèse actuellement sur vous."))
        elif r > 0.25:
            advice.append(("atout", f"Bien positionné : {FACTORS[k][0].lower()}",
                           f"Exposition {expo[k]:+.2f} cohérente avec le facteur à {macro.factors[k]:+.1f}."))

    order = {"alerte": 0, "risque": 1, "action": 2, "info": 3, "atout": 4}
    advice.sort(key=lambda a: order[a[0]])
    return dict(class_weights=cls_w, line_weights=line_w, factor_exposure=expo,
                vol=port_vol(cls_w, cov), stress=stress_test(cls_w), advice=advice)


# ══════════════════════════════════════════════════════════════════════════════
# Rôle 7 — Commentaire (déterministe ou LLM optionnel)
# ══════════════════════════════════════════════════════════════════════════════
def deterministic_briefing(m: MacroView, news: dict) -> str:
    f = m.factors
    lines = [f"**Régime : {m.regime}.** {m.regime_text}"]
    ranked = sorted(f.items(), key=lambda kv: -abs(kv[1]))[:3]
    lines.append("Facteurs dominants : " + ", ".join(
        f"{FACTORS[k][0].lower()} ({v:+.1f})" for k, v in ranked) + ".")
    hot = sorted(news.values(), key=lambda t: -t["intensity"])[:3]
    lines.append("Thèmes d'actualité les plus présents : " + ", ".join(
        f"{t['label'].lower()} ({t['intensity']:.0f}/100)" for t in hot) + ".")
    s = class_scores(f).sort_values()
    lines.append(f"Classes favorisées : {', '.join(s.index[-3:][::-1])}. "
                 f"Classes pénalisées : {', '.join(s.index[:3])}.")
    return "\n\n".join(lines)


def llm_available() -> bool:
    try:
        return bool(st and "llm" in st.secrets and st.secrets["llm"].get("api_key"))
    except Exception:
        return False


def llm_briefing(context: str) -> str:
    """Commentaire rédigé par un LLM (Groq ou Gemini, paliers gratuits).
    Secrets Streamlit :  [llm] provider = "groq" | "gemini", api_key = "...", model = "..." """
    import requests
    cfg = st.secrets["llm"]
    provider = cfg.get("provider", "groq").lower()
    prompt = ("Tu es le stratégiste d'une société de gestion. À partir des données ci-dessous, "
              "rédige en français un briefing de marché de 150 à 220 mots : situation économique, "
              "politique et géopolitique, implications pour un portefeuille diversifié, risques à "
              "surveiller. N'invente aucun chiffre absent des données. Termine par une phrase "
              "rappelant qu'il ne s'agit pas d'un conseil en investissement.\n\n" + context)
    if provider == "gemini":
        model = cfg.get("model", "gemini-2.0-flash")
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": cfg["api_key"]}, timeout=40,
            json={"contents": [{"parts": [{"text": prompt}]}]})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    model = cfg.get("model", "llama-3.3-70b-versatile")
    r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=40,
                      headers={"Authorization": f"Bearer {cfg['api_key']}"},
                      json={"model": model, "temperature": 0.3,
                            "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def context_for_llm(m: MacroView, news: dict, alloc: pd.Series | None = None) -> str:
    d = {"regime": m.regime,
         "facteurs": {FACTORS[k][0]: round(v, 2) for k, v in m.factors.items()},
         "justifications": {FACTORS[k][0]: v for k, v in m.evidence.items()},
         "themes_actualite": {t["label"]: dict(intensite=round(t["intensity"]),
                                               titres=[h["title"] for h in t["headlines"][:3]])
                              for t in news.values()}}
    if alloc is not None:
        d["allocation_proposee"] = {k: f"{v:.0%}" for k, v in alloc.items() if v > 0.005}
    return json.dumps(d, ensure_ascii=False, indent=1)


# ══════════════════════════════════════════════════════════════════════════════
# Journal (mémoire du desk)
# ══════════════════════════════════════════════════════════════════════════════
JOURNAL_PATH = Path("data") / "hedge_fund_journal.json"


def load_journal() -> list:
    try:
        return json.loads(JOURNAL_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def append_journal(entry: dict) -> list:
    j = load_journal()
    j.append(entry)
    try:
        JOURNAL_PATH.parent.mkdir(parents=True, exist_ok=True)
        JOURNAL_PATH.write_text(json.dumps(j, ensure_ascii=False, indent=1, default=str),
                                encoding="utf-8")
    except Exception:
        pass
    return j
