# utils/market_drivers.py  —  MAM v5.11 · Analyse complète du marché par le comité
"""
« Le Nasdaq est négatif : pourquoi ? quel impact ? comment s'adapter ? »

Le comité décompose le mouvement d'un marché (indice, or, pétrole, bitcoin) sur l'horizon choisi :
  1. FACTEURS — régression ridge des rendements quotidiens du marché sur les variations des facteurs
     (taux 10 ans US, dollar, VIX, pétrole, crédit, et selon le marché : euro, yen, Wall Street) sur ~2 ans,
     puis contribution de chaque facteur au mouvement observé (β × variation du facteur) ; le reste =
     facteurs propres au marché (résultats d'entreprises, actualités spécifiques, flux) ;
  2. SECTEURS ET GÉANTS — rotation sectorielle (ETF SPDR) et mouvement des plus grosses capitalisations ;
  3. TECHNIQUE — tendance (moyennes 50/200 j), recul depuis le plus haut, RSI, ampleur inhabituelle (z-score) ;
  4. ACTUALITÉS — titres Google News liés au marché, thèmes et tonalité ;
  5. RÉSEAUX SOCIAUX — Reddit (r/wallstreetbets, r/stocks, r/investing, r/StockMarket) et StockTwits
     (messages « Bullish / Bearish ») : humeur des investisseurs particuliers, titres les plus cités ;
  6. IMPACT — sur les classes d'actifs et sur le portefeuille MIP choisi (bêta, contribution par ligne) ;
  7. ADAPTATION — pistes selon le facteur dominant, la tendance, le régime officiel du comité et le profil,
     à valider par l'utilisateur (aucun ordre n'est passé) ;
  8. AVIS DES MEMBRES DU COMITÉ + rapport PDF.

Les fonctions d'analyse sont pures (DataFrames en entrée) : testées hors réseau.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import numpy as np
import pandas as pd

MD_VERSION = "1.0"

MARKETS = {
    "Nasdaq 100": dict(t="^NDX", proxy="QQQ", region="us",
                       kw=r"nasdaq|tech|\bai\b|artificial intelligence|chip|semiconductor|nvidia|apple|microsoft|meta|"
                          r"amazon|alphabet|google|tesla|broadcom|software|big tech|magnificent|data cent"),
    "S&P 500": dict(t="^GSPC", proxy="SPY", region="us",
                    kw=r"s&p|stocks|wall street|equities|fed|federal reserve|treasury|yields|earnings|economy|jobs|cpi"),
    "Dow Jones": dict(t="^DJI", proxy="DIA", region="us", kw=r"dow|wall street|industrials|stocks|fed|earnings"),
    "Russell 2000": dict(t="^RUT", proxy="IWM", region="us",
                         kw=r"russell|small[- ]cap|regional bank|rate cut|fed|economy"),
    "CAC 40": dict(t="^FCHI", proxy="EWQ", region="eu",
                   kw=r"cac|bourse de paris|paris|france|français|luxe|luxury|lvmh|totalenergies|bce|ecb|euro"),
    "Euro Stoxx 50": dict(t="^STOXX50E", proxy="FEZ", region="eu",
                          kw=r"stoxx|europe|european|euro|ecb|bce|zone euro|eurozone"),
    "DAX": dict(t="^GDAXI", proxy="EWG", region="eu", kw=r"dax|germany|german|allemagne|ecb|bce|europe"),
    "Nikkei 225": dict(t="^N225", proxy="EWJ", region="jp", kw=r"nikkei|japan|japon|yen|boj|bank of japan|tokyo"),
    "Marchés émergents": dict(t="EEM", proxy="EEM", region="em",
                              kw=r"emerging|émergent|china|chine|india|inde|brazil|brésil|yuan"),
    "Or": dict(t="GC=F", proxy="GLD", region="cmd", kw=r"gold|\bor\b|precious|métaux précieux|bullion"),
    "Pétrole WTI": dict(t="CL=F", proxy="USO", region="cmd", kw=r"oil|crude|opec|pétrole|brent|wti|energy"),
    "Bitcoin": dict(t="BTC-USD", proxy="BTC-USD", region="crypto", kw=r"bitcoin|crypto|btc|ether|blockchain"),
}
HORIZONS = {"1 jour": 1, "1 semaine": 5, "1 mois": 21, "3 mois": 63}

FACTORS = {
    "rates": dict(label="Taux 10 ans US", t="^TNX", kind="diff", fmt=lambda v: f"{v * 100:+.0f} pb"),
    "dollar": dict(label="Dollar (indice DXY)", t="DX-Y.NYB", kind="ret", fmt=lambda v: f"{v:+.1%}"),
    "vix": dict(label="Peur — VIX", t="^VIX", kind="ret", fmt=lambda v: f"{v:+.0%}"),
    "oil": dict(label="Pétrole WTI", t="CL=F", kind="ret", fmt=lambda v: f"{v:+.1%}"),
    "credit": dict(label="Crédit (haut rendement / Trésor)", t=("HYG", "IEF"), kind="ratio", fmt=lambda v: f"{v:+.1%}"),
    "eur": dict(label="Euro / dollar", t="EURUSD=X", kind="ret", fmt=lambda v: f"{v:+.1%}"),
    "jpy": dict(label="Dollar / yen", t="JPY=X", kind="ret", fmt=lambda v: f"{v:+.1%}"),
    "us": dict(label="Wall Street (S&P 500)", t="^GSPC", kind="ret", fmt=lambda v: f"{v:+.1%}"),
    "gold": dict(label="Or", t="GC=F", kind="ret", fmt=lambda v: f"{v:+.1%}"),
}
FACTOR_SET = {"us": ["rates", "dollar", "vix", "oil", "credit"],
              "eu": ["us", "rates", "eur", "vix", "oil"],
              "jp": ["us", "jpy", "rates", "vix"],
              "em": ["us", "dollar", "rates", "oil", "vix"],
              "cmd": ["dollar", "rates", "vix", "us"],
              "crypto": ["us", "dollar", "rates", "vix", "gold"]}
SECTOR_ETFS = {"XLK": "Technologie", "SOXX": "Semi-conducteurs", "XLC": "Communication & médias",
               "XLY": "Consommation discrétionnaire", "XLP": "Consommation de base", "XLF": "Finance",
               "XLV": "Santé", "XLE": "Énergie", "XLI": "Industrie", "XLB": "Matériaux", "XLU": "Services publics",
               "XLRE": "Immobilier"}
LEADERS = {
    "us": ["AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "AVGO", "TSLA", "COST", "NFLX", "JPM", "LLY"],
    "eu": ["MC.PA", "TTE.PA", "SAN.PA", "OR.PA", "AIR.PA", "SU.PA", "BNP.PA", "ASML.AS", "SAP.DE", "SIE.DE"],
    "jp": ["7203.T", "6758.T", "9984.T", "8306.T", "6861.T"],
    "em": ["TSM", "BABA", "0700.HK", "RELIANCE.NS", "005930.KS"],
}

# Ce qu'implique chaque facteur quand il MONTE (impact sur les classes d'actifs)
IMPACT_UP = {
    "rates": "Taux longs en hausse : obligations longues en baisse, valeurs de croissance (tech) pénalisées car leurs "
             "bénéfices lointains valent moins aujourd'hui ; banques et assureurs plutôt soutenus.",
    "dollar": "Dollar en hausse : marchés émergents et matières premières sous pression, bénéfices des multinationales "
              "américaines rognés ; pour un investisseur en euros, gain de change sur les actifs en dollars.",
    "vix": "Peur en hausse : actifs risqués vendus, corrélations qui montent (la diversification protège moins), "
           "options plus chères (se couvrir coûte plus).",
    "oil": "Pétrole en hausse : secteur de l'énergie soutenu ; transport, chimie et consommation pénalisés ; "
           "pression sur l'inflation donc sur les taux.",
    "credit": "Crédit qui se détend : appétit pour le risque, obligations à haut rendement en hausse ; l'inverse "
              "(crédit qui se tend) annonce souvent un ralentissement.",
    "eur": "Euro en hausse : exportateurs européens (luxe, aéronautique, automobile) pénalisés, importations moins chères.",
    "jpy": "Dollar en hausse face au yen : exportateurs japonais soutenus (Toyota, Sony).",
    "us": "Wall Street en hausse : effet d'entraînement sur les autres places mondiales.",
    "gold": "Or en hausse : recherche de valeur refuge, inquiétudes sur l'inflation ou la géopolitique.",
}
IMPACT_DOWN = {
    "rates": "Taux longs en baisse : obligations longues en hausse, valeurs de croissance (tech) soutenues ; marges des "
             "banques sous pression. Si la baisse traduit une peur de récession, les actions peuvent baisser quand même.",
    "dollar": "Dollar en baisse : marchés émergents, or et matières premières soutenus ; pour un investisseur en euros, "
              "perte de change sur les actifs en dollars non couverts.",
    "vix": "Peur en baisse : retour de l'appétit pour le risque, couvertures moins chères (bon moment pour se protéger).",
    "oil": "Pétrole en baisse : énergie pénalisée ; transport, chimie et consommation soulagés ; moins de pression sur "
           "l'inflation.",
    "credit": "Crédit qui se tend (haut rendement en retard sur le Trésor) : prudence, signal fréquent de ralentissement ; "
              "privilégier la qualité.",
    "eur": "Euro en baisse : exportateurs européens soutenus, importations (énergie) plus chères.",
    "jpy": "Yen en hausse face au dollar : exportateurs japonais pénalisés, débouclage possible des positions financées en yen.",
    "us": "Wall Street en baisse : effet d'entraînement négatif sur les autres places mondiales.",
    "gold": "Or en baisse : moindre recherche de valeur refuge ou hausse des taux réels.",
}
THEME_DRIVER = {
    "hawkish": "discours restrictif des banques centrales (taux élevés plus longtemps)",
    "dovish": "espoirs de baisse des taux",
    "inflation": "inflation plus forte que prévu",
    "disinflation": "inflation qui ralentit",
    "recession": "craintes de ralentissement économique",
    "growth": "bons chiffres économiques ou résultats d'entreprises",
    "tech_ai": "actualité de l'IA et des semi-conducteurs",
    "geo_conflict": "tensions géopolitiques",
    "sanctions_trade": "droits de douane / guerre commerciale",
    "peace_deal": "désescalade / accords",
    "energy_supply": "choc d'offre énergétique",
    "crypto_pos": "adoption des cryptos",
    "crypto_neg": "régulation ou stress sur les cryptos",
}


# ══════════════════════════════════════════════════════════════════════════════
#  DONNÉES (réseau) — appelées par l'interface, mises en cache côté Streamlit
# ══════════════════════════════════════════════════════════════════════════════
def needed_tickers(market: str) -> list[str]:
    m = MARKETS[market]
    ts = {m["t"], "^GSPC"}
    for k in FACTOR_SET[m["region"]]:
        f = FACTORS[k]["t"]
        ts.update(f if isinstance(f, tuple) else [f])
    ts.update(SECTOR_ETFS)
    ts.update(LEADERS.get(m["region"], []))
    return sorted(ts)


def fetch_closes(tickers: tuple, period: str = "2y") -> pd.DataFrame:
    try:
        import yfinance as yf
        raw = yf.download(list(tickers), period=period, interval="1d", auto_adjust=True, progress=False, threads=True)
        px = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]].rename(columns={"Close": tickers[0]})
        if px.index.tz is not None:
            px.index = px.index.tz_localize(None)
        return px.sort_index().ffill(limit=3)
    except Exception:
        return pd.DataFrame()


def _get(url: str, headers: dict | None = None, timeout: int = 8) -> bytes:
    import urllib.request
    h = {"User-Agent": "Mozilla/5.0 (McKenson Investment Platform; education)"}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout) as r:
        return r.read()


def fetch_google_news(query: str, n: int = 20, lang: str = "en") -> list[dict]:
    import urllib.parse
    from xml.etree import ElementTree as ET
    loc = "&hl=fr&gl=FR&ceid=FR:fr" if lang == "fr" else "&hl=en&gl=US&ceid=US:en"
    try:
        root = ET.fromstring(_get("https://news.google.com/rss/search?q=" + urllib.parse.quote(query + " when:3d") + loc))
    except Exception:
        return []
    out = []
    for item in root.findall(".//item")[:n]:
        raw = (item.findtext("title") or "").strip()
        title, src = (raw.rsplit(" - ", 1) + [""])[:2] if " - " in raw else (raw, "")
        out.append(dict(title=title.strip(), source=src.strip(), link=item.findtext("link") or "",
                        pubdate=item.findtext("pubDate") or "", category="Marché"))
    return out


def fetch_reddit(subs=("wallstreetbets", "stocks", "investing", "StockMarket"), limit: int = 40) -> tuple[list[dict], str]:
    posts, ok = [], 0
    for s in subs:
        try:
            d = json.loads(_get(f"https://www.reddit.com/r/{s}/hot.json?limit={limit}&raw_json=1",
                                {"User-Agent": "python:mip-education:v1.0 (educational research)"}))
            ok += 1
            for c in d.get("data", {}).get("children", []):
                p = c.get("data", {})
                if p.get("stickied"):
                    continue
                posts.append(dict(sub=s, title=p.get("title", ""), score=int(p.get("score", 0) or 0),
                                  comments=int(p.get("num_comments", 0) or 0), flair=p.get("link_flair_text") or "",
                                  link="https://www.reddit.com" + p.get("permalink", "")))
        except Exception:
            continue
    return posts, ("ok" if ok else "indisponible")


def fetch_stocktwits(symbol: str) -> tuple[list[dict], str]:
    sym = symbol.replace("^", "").replace("=F", "").replace("-USD", ".X")
    try:
        d = json.loads(_get(f"https://api.stocktwits.com/api/2/streams/symbol/{sym}.json"))
    except Exception:
        return [], "indisponible"
    out = []
    for m in d.get("messages", []):
        lab = ((m.get("entities") or {}).get("sentiment") or {}) or {}
        out.append(dict(body=m.get("body", ""), sentiment=lab.get("basic", ""), created=m.get("created_at", "")))
    return out, "ok"


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYSES (pures)
# ══════════════════════════════════════════════════════════════════════════════
def _factor_series(px: pd.DataFrame, key: str) -> pd.Series | None:
    f = FACTORS[key]
    t = f["t"]
    if isinstance(t, tuple):
        if not all(x in px for x in t):
            return None
        return np.log(px[t[0]] / px[t[1]]).diff()
    if t not in px:
        return None
    s = px[t]
    return s.diff() if f["kind"] == "diff" else np.log(s).diff()


def attribution(px: pd.DataFrame, market: str, horizon: int = 5, lookback: int = 500, ridge: float = 2.0) -> dict:
    """Décomposition du mouvement du marché par facteur (régression ridge sur rendements quotidiens)."""
    m = MARKETS[market]
    if m["t"] not in px or px[m["t"]].dropna().shape[0] < 120:
        return dict(ok=False, error="historique du marché indisponible")
    y_all = np.log(px[m["t"]]).diff()
    keys = [k for k in FACTOR_SET[m["region"]] if FACTORS[k]["t"] != m["t"]]
    X_all = pd.DataFrame({k: _factor_series(px, k) for k in keys})
    X_all = X_all.dropna(axis=1, how="all")
    data = pd.concat([y_all.rename("y"), X_all], axis=1, sort=True).dropna()
    if len(data) < 120 or X_all.shape[1] == 0:
        return dict(ok=False, error="facteurs indisponibles")
    fit = data.iloc[-lookback:]
    X, y = fit.drop(columns="y"), fit["y"]
    mu, sd = X.mean(), X.std().replace(0, np.nan)
    Z = ((X - mu) / sd).fillna(0.0).values
    yc = (y - y.mean()).values
    lam = ridge * len(Z) / 100.0
    b_std = np.linalg.solve(Z.T @ Z + lam * np.eye(Z.shape[1]), Z.T @ yc)
    beta = pd.Series(b_std / sd.values, index=X.columns)
    pred = Z @ b_std
    r2 = float(1 - ((yc - pred) ** 2).sum() / (yc ** 2).sum()) if (yc ** 2).sum() > 0 else 0.0
    win = data.iloc[-horizon:]
    move = float(win["y"].sum())
    fmove = win.drop(columns="y").sum()
    contrib = beta * fmove
    roll = y_all.dropna().rolling(horizon).sum().dropna()
    typ = float(roll.std()) if len(roll) > 30 else np.nan
    rows = []
    for k in beta.index:
        rows.append(dict(key=k, label=FACTORS[k]["label"], move=float(fmove[k]), move_txt=FACTORS[k]["fmt"](float(fmove[k])),
                         beta=float(beta[k]), contrib=float(contrib[k])))
    rows.sort(key=lambda r: -abs(r["contrib"]))
    explained = float(contrib.sum())
    return dict(ok=True, market=market, horizon=horizon, move=move, move_pct=float(np.expm1(move)),
                factors=rows, explained=explained, residual=move - explained, r2=r2, typical=typ,
                z=move / typ if typ and typ == typ else np.nan, start=str(win.index[0].date()), end=str(win.index[-1].date()),
                n_obs=len(fit))


def technical(px: pd.Series) -> dict:
    s = px.dropna()
    if len(s) < 60:
        return dict(ok=False)
    last = float(s.iloc[-1])
    ma50, ma200 = float(s.rolling(50).mean().iloc[-1]), float(s.rolling(200).mean().iloc[-1]) if len(s) >= 200 else np.nan
    hi = float(s.iloc[-252:].max())
    d = s.diff()
    up, dn = d.clip(lower=0).ewm(alpha=1 / 14).mean(), (-d.clip(upper=0)).ewm(alpha=1 / 14).mean()
    rsi = float(100 - 100 / (1 + up.iloc[-1] / dn.iloc[-1])) if dn.iloc[-1] > 0 else 100.0
    r = lambda n: float(s.iloc[-1] / s.iloc[-n - 1] - 1) if len(s) > n else np.nan  # noqa: E731
    trend = ("haussière" if last > ma50 > ma200 else "baissière" if last < ma50 < ma200 else
             "en correction dans une tendance haussière" if ma50 > ma200 else "en rebond dans une tendance baissière") \
        if ma200 == ma200 else ("haussière" if last > ma50 else "baissière")
    return dict(ok=True, last=last, ma50=ma50, ma200=ma200, vs_ma200=last / ma200 - 1 if ma200 == ma200 else np.nan,
                drawdown=last / hi - 1, rsi=rsi, r1=r(1), r5=r(5), r21=r(21), r63=r(63), trend=trend)


def rotation(px: pd.DataFrame, horizon: int, bench: str = "^GSPC") -> pd.DataFrame:
    rows = []
    b = px[bench].dropna() if bench in px else None
    rb = float(b.iloc[-1] / b.iloc[-horizon - 1] - 1) if b is not None and len(b) > horizon else np.nan
    for t, lab in SECTOR_ETFS.items():
        if t in px and px[t].dropna().shape[0] > horizon:
            s = px[t].dropna()
            r = float(s.iloc[-1] / s.iloc[-horizon - 1] - 1)
            rows.append(dict(ETF=t, Secteur=lab, Rendement=r, **{"Écart vs S&P 500": r - rb if rb == rb else np.nan}))
    return pd.DataFrame(rows).sort_values("Rendement", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()


def leaders_moves(px: pd.DataFrame, market: str, horizon: int) -> pd.DataFrame:
    rows = []
    for t in LEADERS.get(MARKETS[market]["region"], []):
        if t in px and px[t].dropna().shape[0] > horizon:
            s = px[t].dropna()
            rows.append(dict(Titre=t, Rendement=float(s.iloc[-1] / s.iloc[-horizon - 1] - 1)))
    return pd.DataFrame(rows).sort_values("Rendement").reset_index(drop=True) if rows else pd.DataFrame()


def news_view(market: str, rows: list[dict]) -> dict:
    """Titres liés au marché : thèmes dominants et tonalité."""
    from utils.market_intel import score_headline
    kw = re.compile(MARKETS[market]["kw"], re.I)
    sel, seen = [], set()
    for r in rows:
        t = r.get("title", "")
        k = t.lower()[:70]
        if not t or k in seen:
            continue
        if kw.search(t) or r.get("category") == "Marché":
            seen.add(k)
            sel.append({**r, **score_headline(t)})
    themes: dict[str, int] = {}
    for r in sel:
        for th in r.get("themes", []):
            themes[th] = themes.get(th, 0) + 1
    tone = float(np.mean([r["sentiment"] for r in sel])) if sel else 0.0
    top = sorted(themes.items(), key=lambda x: -x[1])[:4]
    return dict(rows=sel[:30], n=len(sel), tone=tone, themes=top,
                drivers=[THEME_DRIVER.get(k, k) for k, _ in top])


_TICK = re.compile(r"\$([A-Z]{1,5})\b|\b(NVDA|AAPL|MSFT|TSLA|AMZN|META|GOOGL|AMD|PLTR|SPY|QQQ|SMCI|AVGO|NFLX|COIN|MSTR|"
                   r"INTC|MU|ARM|TSM|IWM|GME|HOOD|SOFI|RDDT|BTC|ETH)\b")


def social_view(market: str, reddit: list[dict], twits: list[dict]) -> dict:
    """Humeur des réseaux sociaux : StockTwits (Bullish/Bearish) + Reddit (tonalité des titres pondérée par l'engagement)."""
    from utils.sentiment import score_title
    from utils.market_intel import score_headline
    kw = re.compile(MARKETS[market]["kw"], re.I)
    bull = sum(1 for m in twits if m.get("sentiment") == "Bullish")
    bear = sum(1 for m in twits if m.get("sentiment") == "Bearish")
    st_score = (bull - bear) / (bull + bear) if bull + bear else np.nan
    rel = [p for p in reddit if kw.search(p.get("title", ""))] or reddit
    sc, wt, mentions = [], [], {}
    for p in rel:
        s1 = score_title(p["title"])["score"]
        s2 = score_headline(p["title"])["sentiment"]
        sc.append((s1 + s2) / 2)
        wt.append(np.log1p(p.get("score", 0)) + 1)
    for p in reddit:
        for a, b in _TICK.findall(p.get("title", "")):
            t = a or b
            mentions[t] = mentions.get(t, 0) + 1
    rd_score = float(np.average(sc, weights=wt)) if sc else np.nan
    parts = [x for x in (st_score, rd_score) if x == x]
    score = float(np.mean(parts)) if parts else np.nan
    top = sorted(rel, key=lambda p: -(p.get("score", 0) + 2 * p.get("comments", 0)))[:8]
    return dict(score=score, stocktwits=dict(bull=bull, bear=bear, score=st_score), reddit_score=rd_score,
                n_reddit=len(rel), mentions=sorted(mentions.items(), key=lambda x: -x[1])[:10], top_posts=top,
                label=("euphorique" if score > 0.45 else "optimiste" if score > 0.12 else "paniqué" if score < -0.45
                       else "inquiet" if score < -0.12 else "partagé") if score == score else "indisponible")


def portfolio_impact(rets: pd.DataFrame, weights: dict, market_ret: pd.Series, move: float) -> dict:
    """Bêta du portefeuille (poids actuels) au marché analysé et impact estimé du mouvement."""
    w = pd.Series({k: v for k, v in weights.items() if k in rets.columns and v > 0})
    if w.empty or market_ret is None or market_ret.dropna().empty:
        return dict(ok=False)
    data = pd.concat([rets[w.index], market_ret.rename("_m")], axis=1, sort=True).dropna().iloc[-500:]
    if len(data) < 60:
        return dict(ok=False)
    var = float(data["_m"].var())
    betas = {k: float(data[k].cov(data["_m"]) / var) if var > 0 else 0.0 for k in w.index}
    invested = float(w.sum())
    pb = float(sum(w[k] * betas[k] for k in w.index))
    port = (data[w.index] * w).sum(axis=1)
    corr = float(port.corr(data["_m"]))
    contrib = sorted(((k, w[k] * betas[k] * move) for k in w.index), key=lambda x: x[1])
    return dict(ok=True, beta=pb, corr=corr, invested=invested, impact=pb * move, betas=betas, contrib=contrib)


def adaptation(att: dict, tech: dict, regime: str | None, profile: str, social: dict | None = None,
               smart: dict | None = None, port: dict | None = None) -> list[dict]:
    """Pistes d'adaptation (à valider par l'utilisateur)."""
    out = []
    move, z = att.get("move", 0.0), att.get("z", np.nan)
    neg = move < 0
    dom = att["factors"][0] if att.get("factors") else None
    if z == z and abs(z) < 1.2:
        out.append(dict(qui="Marc ETING-FINANCIER", texte=f"Mouvement dans la norme (z = {z:+.1f} : moins de 1,2 écart-type) : "
                                                         "pas de décision dans l'urgence, le plan d'investissement reste valable."))
    elif z == z:
        out.append(dict(qui="Aline DE MARGE", texte=f"Mouvement inhabituel (z = {z:+.1f}) : vérifier que la perte potentielle du "
                                                    "portefeuille reste sous votre limite, rééquilibrer plutôt que tout vendre."))
    if dom and abs(dom["contrib"]) > 0.25 * abs(move) and np.sign(dom["contrib"]) == np.sign(move):
        k = dom["key"]
        if k == "rates" and dom["move"] > 0:
            out.append(dict(qui="Jean-Michel TAUX-BAS", texte="Facteur dominant : la hausse des taux. Réduire la sensibilité aux taux "
                            "(obligations courtes plutôt que longues), privilégier les entreprises rentables et peu endettées, "
                            "éviter les valeurs de croissance sans bénéfices."))
        elif k == "rates":
            out.append(dict(qui="Jean-Michel TAUX-BAS", texte="Facteur dominant : la baisse des taux. Les obligations longues et les "
                            "valeurs de croissance en profitent ; ne pas sur-réagir si la baisse traduit une peur de récession."))
        elif k == "vix" and dom["move"] > 0:
            out.append(dict(qui="Aline DE MARGE", texte="Facteur dominant : la peur (VIX en hausse). Garder des liquidités pour "
                            "acheter par paliers, envisager une couverture (option de vente sur l'indice) si votre profil "
                            "l'autorise, éviter l'effet de levier."))
        elif k == "dollar":
            out.append(dict(qui="Jean-Michel TAUX-BAS", texte="Facteur dominant : le dollar. Surveiller l'exposition aux émergents et "
                            "aux matières premières ; pour un investisseur en euros, envisager des ETF couverts contre le change."))
        elif k == "oil":
            out.append(dict(qui="Jean-Michel TAUX-BAS", texte="Facteur dominant : le pétrole. Une petite poche énergie ou matières "
                            "premières amortit ce type de choc ; attention à l'effet sur l'inflation et les taux."))
        elif k == "credit":
            out.append(dict(qui="Aline DE MARGE", texte="Facteur dominant : le crédit. Réduire le haut rendement, monter en qualité "
                            "(obligations d'État, entreprises solides)."))
        elif k in ("us", "eur", "jpy"):
            out.append(dict(qui="Jean-Michel TAUX-BAS", texte=f"Facteur dominant : {dom['label'].lower()}. Le marché suit surtout "
                            "un mouvement mondial : la diversification géographique protège peu à court terme."))
    if abs(att.get("residual", 0)) > 0.5 * abs(move) and abs(move) > 1e-4:
        out.append(dict(qui="Mc Henson ALGO-RITHME", texte="Plus de la moitié du mouvement n'est pas expliquée par les facteurs macro : "
                        "il vient du marché lui-même (résultats d'entreprises, actualités de quelques géants, flux). "
                        "Vérifier votre exposition aux titres concernés plutôt qu'à tout le marché."))
    if tech.get("ok"):
        if tech["vs_ma200"] == tech["vs_ma200"] and tech["vs_ma200"] < 0:
            out.append(dict(qui="Mc Henson ALGO-RITHME", texte=f"Le marché est sous sa moyenne 200 jours ({tech['vs_ma200']:+.1%}) : "
                            "tendance de fond fragilisée, préférer des achats progressifs et des positions plus petites."))
        if tech["rsi"] < 30:
            out.append(dict(qui="Thierry BALANCEMENT", texte=f"RSI {tech['rsi']:.0f} : zone de survente. Pour un horizon long, "
                            "renforcer par paliers (investissement programmé) plutôt qu'en une fois."))
        elif tech["rsi"] > 70:
            out.append(dict(qui="Thierry BALANCEMENT", texte=f"RSI {tech['rsi']:.0f} : zone de surachat. Prendre une partie des gains "
                            "sur les lignes qui dépassent leur poids cible."))
    try:
        from utils.smart_money import REGIME_SECTORS
        fav, pen = REGIME_SECTORS.get(regime or "", (set(), set()))
        if fav:
            out.append(dict(qui="Jean-Michel TAUX-BAS", texte=f"Régime officiel « {regime} » : secteurs plutôt favorisés "
                            f"{', '.join(sorted(fav)).lower()} ; plutôt pénalisés {', '.join(sorted(pen)).lower()}."))
    except Exception:
        pass
    if social and social.get("score") == social.get("score") and social.get("score") is not None:
        s = social["score"]
        if s < -0.35 and neg:
            out.append(dict(qui="Marc ETING-FINANCIER", texte="Les réseaux sociaux sont très pessimistes : historiquement, la "
                            "panique des particuliers coïncide souvent avec des points bas. Ne pas vendre sous le coup de l'émotion."))
        elif s > 0.35 and not neg:
            out.append(dict(qui="Marc ETING-FINANCIER", texte="Les réseaux sociaux sont euphoriques : prudence sur les titres les plus "
                            "cités (« mèmes »), l'euphorie précède souvent les replis."))
    if smart and smart.get("ok"):
        out.append(dict(qui="Thierry BALANCEMENT", texte="Ce que font les meilleurs gérants (13F) : premiers secteurs "
                        + ", ".join(s[0].lower() for s in smart["sectors"][:3]) + " — à confronter au contexte actuel."))
    if port and port.get("ok"):
        out.append(dict(qui="Aline DE MARGE", texte=f"Votre portefeuille a un bêta de {port['beta']:.2f} à ce marché : un mouvement "
                        f"de {np.expm1(att['move']):+.1%} lui coûte ou lui rapporte environ {port['impact']:+.1%}. "
                        + ("Bêta élevé : réduire les lignes les plus sensibles si cela dépasse votre tolérance."
                           if port["beta"] > 1.1 else "Exposition mesurée.")))
    out.append(dict(qui="Constance Probité", texte=f"Toute modification reste soumise à votre profil {profile}, à votre politique "
                    "d'investissement et aux contrôles de conformité : rien n'est exécuté automatiquement."))
    return out


def analyse(market: str, horizon: int, px: pd.DataFrame, news_rows: list[dict] | None = None,
            reddit: list[dict] | None = None, twits: list[dict] | None = None, regime: str | None = None,
            profile: str = "Équilibré", port_impact: dict | None = None, smart: dict | None = None,
            sources: dict | None = None) -> dict:
    """Analyse complète : pourquoi, impact, adaptation, avis des membres du comité."""
    att = attribution(px, market, horizon)
    if not att.get("ok"):
        return dict(ok=False, error=att.get("error"))
    tech = technical(px[MARKETS[market]["t"]])
    rot = rotation(px, horizon)
    lead = leaders_moves(px, market, horizon)
    nv = news_view(market, news_rows or [])
    so = social_view(market, reddit or [], twits or [])
    mv, z = att["move_pct"], att["z"]
    hz = {1: "sur la dernière séance", 5: "sur la semaine", 21: "sur le mois", 63: "sur 3 mois"}.get(horizon, f"sur {horizon} séances")
    direction = "stable" if abs(z) < 0.3 else ("en hausse" if mv > 0 else "en baisse") if z == z else ("en hausse" if mv > 0 else "en baisse")
    force = "" if z != z else (" (mouvement fort)" if abs(z) >= 2 else " (mouvement marqué)" if abs(z) >= 1.2 else " (dans la norme)")
    headline = f"{market} {direction} de {mv:+.1%} {hz}{force}."
    why = []
    for f in att["factors"][:4]:
        if abs(f["contrib"]) < max(0.0008, 0.12 * abs(att["move"])):
            continue
        why.append(f"{f['label']} : {f['move_txt']} → contribution estimée {np.expm1(f['contrib']):+.1%}"
                   + (" (pousse dans le même sens)" if np.sign(f["contrib"]) == np.sign(att["move"]) else " (amortit le mouvement)"))
    if abs(att["residual"]) > 0.0015:
        why.append(f"Facteurs propres au marché (résultats, actualités d'entreprises, flux) : {np.expm1(att['residual']):+.1%}")
    if len(rot):
        why.append(f"Rotation sectorielle : en tête {rot.iloc[0]['Secteur']} ({rot.iloc[0]['Rendement']:+.1%}), "
                   f"en queue {rot.iloc[-1]['Secteur']} ({rot.iloc[-1]['Rendement']:+.1%}).")
    if len(lead):
        lo, hi = lead.iloc[0], lead.iloc[-1]
        why.append(f"Grandes capitalisations : la plus forte baisse {lo['Titre']} ({lo['Rendement']:+.1%}), la plus forte hausse "
                   f"{hi['Titre']} ({hi['Rendement']:+.1%}) ; {int((lead['Rendement'] > 0).sum())}/{len(lead)} en hausse.")
    if nv["drivers"]:
        why.append(f"Actualités ({nv['n']} titre(s), tonalité {nv['tone']:+.2f}) : {', '.join(nv['drivers'])}.")
    if so["label"] != "indisponible":
        why.append(f"Réseaux sociaux : humeur {so['label']} (score {so['score']:+.2f})"
                   + (f", titres les plus cités {', '.join(t for t, _ in so['mentions'][:5])}" if so["mentions"] else "") + ".")
    impact = []
    for f in att["factors"][:3]:
        if abs(f["move"]) > 0 and f["key"] in IMPACT_UP:
            txt = IMPACT_UP[f["key"]] if f["move"] > 0 else IMPACT_DOWN.get(f["key"], IMPACT_UP[f["key"]])
            impact.append(f"{f['label']} ({f['move_txt']}) — {txt}")
    if port_impact and port_impact.get("ok"):
        worst = [f"{k} ({v:+.1%})" for k, v in port_impact["contrib"][:3]]
        impact.append(f"Votre portefeuille : bêta {port_impact['beta']:.2f}, impact estimé {port_impact['impact']:+.1%} "
                      f"(lignes les plus touchées : {', '.join(worst)}).")
    adapt = adaptation(att, tech, regime, profile, so, smart, port_impact)
    dom = att["factors"][0] if att["factors"] else None
    voices = [
        dict(id="eco", titre="Les causes macro", points=[
            headline,
            (f"Facteur macro dominant : {dom['label'].lower()} ({dom['move_txt']}), contribution {np.expm1(dom['contrib']):+.1%}."
             if dom else "Aucun facteur macro dominant."),
            f"Régime officiel du comité : « {regime or '—'} »."] + ([f"Actualités : {', '.join(nv['drivers'])}."] if nv["drivers"] else [])),
        dict(id="quant", titre="Ce que disent les chiffres", points=[
            f"Les facteurs macro expliquent {att['r2']:.0%} des variations quotidiennes de ce marché sur {att['n_obs']} séances "
            f"(régression ridge) ; part expliquée du mouvement actuel : {np.expm1(att['explained']):+.1%}, part propre : "
            f"{np.expm1(att['residual']):+.1%}.",
            (f"Ampleur : {z:+.1f} écart-type par rapport aux mouvements habituels sur cet horizon." if z == z else "Ampleur : —"),
            (f"Tendance {tech['trend']} ; {tech['vs_ma200']:+.1%} vs moyenne 200 j ; recul depuis le plus haut {tech['drawdown']:+.1%} ; "
             f"RSI {tech['rsi']:.0f}." if tech.get("ok") and tech["vs_ma200"] == tech["vs_ma200"] else "Indicateurs techniques partiels.")]),
        dict(id="cio", titre="Que faire du portefeuille", points=[a["texte"] for a in adapt if a["qui"] == "Thierry BALANCEMENT"]
             or ["Pas d'action particulière : rester fidèle à l'allocation cible et rééquilibrer si un poids sort de sa bande."]),
        dict(id="cro", titre="Les risques", points=[a["texte"] for a in adapt if a["qui"] == "Aline DE MARGE"]
             or ["Aucun signal de risque exceptionnel sur cet horizon."]),
        dict(id="cpm", titre="En mots simples", points=[
            headline,
            "Pourquoi : " + ("; ".join(w.split(" → ")[0] for w in why[:2]) if why else "pas de cause unique identifiable") + ".",
            "Pour vous : " + (impact[-1] if port_impact and port_impact.get("ok") else
                              "l'effet sur votre portefeuille dépend de votre exposition à ce marché."),
            "Les réseaux sociaux amplifient les émotions : une décision d'investissement se prend sur votre horizon, pas sur une séance."]),
    ]
    try:
        from utils.committee import MEMBER
        for v in voices:
            m = MEMBER.get(v["id"], {})
            v.update(nom=m.get("nom", v["id"]), emoji=m.get("emoji", ""), couleur=m.get("couleur", "#94a3b8"))
    except Exception:
        pass
    return dict(ok=True, market=market, horizon=horizon, headline=headline, attribution=att, technique=tech,
                rotation=rot, leaders=lead, news=nv, social=so, why=why, impact=impact, adapt=adapt, voices=voices,
                regime=regime, profile=profile, sources=sources or {}, built=datetime.now().strftime("%d/%m/%Y %H:%M"))


def llm_prompt(an: dict) -> str:
    d = dict(marche=an["market"], resume=an["headline"], pourquoi=an["why"], impact=an["impact"],
             adaptation=[a["texte"] for a in an["adapt"]], regime=an.get("regime"),
             actualites=[r["title"] for r in an["news"]["rows"][:12]],
             reseaux_sociaux=[p["title"] for p in an["social"]["top_posts"][:8]])
    return ("Tu es le comité d'investissement d'une société de gestion. À partir des données ci-dessous (n'invente aucun "
            "chiffre absent), rédige en français une analyse de marché de 200 à 280 mots en trois parties : « Pourquoi », "
            "« Quel impact », « Comment s'adapter ». Langage simple, termine par une phrase rappelant qu'il ne s'agit pas "
            "d'un conseil en investissement.\n\n" + json.dumps(d, ensure_ascii=False, indent=1))


def llm_commentary(an: dict) -> str | None:
    """Commentaire rédigé par un LLM si le secret [llm] est configuré (Groq ou Gemini)."""
    try:
        from utils import advisor as A
        if not A.llm_available():
            return None
        import requests
        import streamlit as st
        cfg = st.secrets["llm"]
        prompt = llm_prompt(an)
        if cfg.get("provider", "groq").lower() == "gemini":
            r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{cfg.get('model', 'gemini-3.5-flash-lite')}:generateContent",
                              params={"key": cfg["api_key"]}, timeout=40, json={"contents": [{"parts": [{"text": prompt}]}]})
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
        r = requests.post("https://api.groq.com/openai/v1/chat/completions", timeout=40,
                          headers={"Authorization": f"Bearer {cfg['api_key']}"},
                          json={"model": cfg.get("model", "llama-3.3-70b-versatile"), "temperature": 0.3,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  RAPPORT PDF
# ══════════════════════════════════════════════════════════════════════════════
def charts(an: dict, px: pd.DataFrame) -> dict[str, bytes]:
    import matplotlib
    matplotlib.use("Agg")
    from utils import reporting as R
    out = {}
    att = an["attribution"]
    labels = [f["label"] for f in att["factors"]] + ["Propre au marché"]
    vals = [np.expm1(f["contrib"]) * 100 for f in att["factors"]] + [np.expm1(att["residual"]) * 100]
    fig, ax, t = R._fig("light", 9, 3.8)
    ax.barh(labels[::-1], vals[::-1], color=["#16a34a" if v > 0 else "#dc2626" for v in vals[::-1]])
    ax.axvline(0, color=t["muted"], lw=0.8)
    R._title(ax, t, f"Pourquoi le {an['market']} bouge : contribution des facteurs",
             f"mouvement total {att['move_pct']:+.1%} du {att['start']} au {att['end']} (points de %)")
    out["01_facteurs"] = R._png(fig)
    s = px[MARKETS[an["market"]]["t"]].dropna().iloc[-260:]
    if len(s) > 30:
        fig, ax, t = R._fig("light", 9, 3.6)
        ax.plot(s.index, s.values, color="#0077b6", lw=1.4, label=an["market"])
        ax.plot(s.index, s.rolling(50).mean(), color="#f59e0b", lw=1, label="Moyenne 50 j")
        ax.plot(s.index, px[MARKETS[an["market"]]["t"]].dropna().rolling(200).mean().reindex(s.index), color="#7c3aed", lw=1,
                label="Moyenne 200 j")
        ax.legend(fontsize=7, frameon=False)
        R._title(ax, t, f"{an['market']} sur un an", "cours et moyennes mobiles")
        out["02_cours"] = R._png(fig)
    rot = an["rotation"]
    if len(rot):
        fig, ax, t = R._fig("light", 9, 3.8)
        r = rot.iloc[::-1]
        ax.barh(r["Secteur"], r["Rendement"] * 100, color=["#16a34a" if v > 0 else "#dc2626" for v in r["Rendement"]])
        ax.axvline(0, color=t["muted"], lw=0.8)
        R._title(ax, t, "Rotation sectorielle (ETF SPDR, marché américain)", "rendement sur l'horizon (%)")
        out["03_secteurs"] = R._png(fig)
    return out


def build_pdf(an: dict, px: pd.DataFrame, llm_text: str | None = None) -> bytes:
    from utils import reporting as R
    from utils import legal as L
    imgs = charts(an, px)
    att, tech = an["attribution"], an["technique"]
    b: list[tuple] = [("h", "En bref"), ("p", f"**{an['headline']}**")]
    b.append(("kpis", [("Mouvement", f"{att['move_pct']:+.1%}"), ("Ampleur (z)", f"{att['z']:+.1f}" if att["z"] == att["z"] else "—"),
                       ("Part macro expliquée", f"{np.expm1(att['explained']):+.1%}"), ("Régime du comité", str(an.get("regime") or "—")),
                       ("Tendance", tech.get("trend", "—") if tech.get("ok") else "—"),
                       ("RSI 14", f"{tech['rsi']:.0f}" if tech.get("ok") else "—"),
                       ("Humeur réseaux sociaux", an["social"]["label"]), ("Titres d'actualité", str(an["news"]["n"]))]))
    b += [("h", "1. Pourquoi ?"), ("bullets", an["why"]), ("img", imgs["01_facteurs"], 17)]
    rows = [["Facteur", "Variation", "Sensibilité (β)", "Contribution"]]
    for f in att["factors"]:
        rows.append([f["label"], f["move_txt"], f"{f['beta']:+.3f}", f"{np.expm1(f['contrib']):+.2%}"])
    rows.append(["Propre au marché (résultats, actualités, flux)", "—", "—", f"{np.expm1(att['residual']):+.2%}"])
    b.append(("table", rows, [7.5, 3.0, 3.2, 3.5]))
    for k in ("02_cours", "03_secteurs"):
        if k in imgs:
            b.append(("img", imgs[k], 16))
    b += [("h", "2. Quel impact ?"), ("bullets", an["impact"] or ["—"])]
    b += [("h", "3. Comment s'adapter ? (pistes à valider, aucun ordre n'est passé)"),
          ("table", [["Proposé par", "Piste"]] + [[a["qui"], a["texte"]] for a in an["adapt"]], [3.8, 13.6])]
    b.append(("h", "4. Avis des membres du comité"))
    for v in an["voices"]:
        b.append(("p", f"**{v.get('nom', '')} — {v['titre']}**"))
        b.append(("bullets", v["points"]))
    if llm_text:
        b += [("h", "Commentaire rédigé (modèle de langage)"), ("p", llm_text.replace("\n", " "))]
    if an["news"]["rows"]:
        b.append(("h", "Actualités analysées"))
        b.append(("table", [["Titre", "Source", "Tonalité"]] + [[r["title"], r.get("source", ""), f"{r['sentiment']:+.2f}"]
                                                              for r in an["news"]["rows"][:15]], [12.0, 3.4, 2.0]))
    if an["social"]["top_posts"]:
        b.append(("h", "Réseaux sociaux — publications les plus suivies"))
        b.append(("table", [["Forum", "Publication", "Votes"]] + [[f"r/{p['sub']}", p["title"], str(p["score"])]
                                                                for p in an["social"]["top_posts"][:8]], [3.0, 12.4, 2.0]))
    src = an.get("sources") or {}
    b.append(("note", "Méthode : régression ridge des rendements quotidiens du marché sur les variations des facteurs "
                      f"({att['n_obs']} séances) ; contribution = sensibilité × variation du facteur sur l'horizon. "
                      "Corrélation n'est pas causalité : la décomposition est une lecture statistique. Sources : Yahoo Finance "
                      f"(cours), Google News ({src.get('news', '—')}), Reddit ({src.get('reddit', '—')}), "
                      f"StockTwits ({src.get('stocktwits', '—')})."))
    b.append(("note", L.DISCLAIMER))
    return R.make_pdf(f"Analyse de marché du comité — {an['market']}",
                      f"McKenson Asset Management · {an['built']} · horizon {an['horizon']} séance(s)", b)
