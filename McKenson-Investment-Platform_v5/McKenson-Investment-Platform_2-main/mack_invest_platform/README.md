# 📈 McKenson Investment Platform - MIP

A full-featured investment simulation platform built with **Streamlit** + **yfinance**.

## Features

### Public Side
- 🎞️ **Live ticker strip** — real-time prices for all assets (SPY, AAPL, MSFT, BTC, indices, FX, commodities…)
- 📰 **Breaking news banner** — scrolling market events
- 💼 **Trading Desk** — spot orders + European options (Black-Scholes)
- 📊 **Technical Analysis** — RSI, MACD, Bollinger Bands, GARCH vol forecast, candlestick charts
- 🧮 **Portfolio Optimizer** — Markowitz + CVaR, efficient frontier, correlation heatmap
- 🏆 **Leaderboard** — team rankings, benchmark comparison (SPY/QQQ/CAC40/Gold/BTC), risk-return map

### Nouveautés v5 — Intelligence artificielle
- 🧠 **IA Marchés** — machine learning appliqué aux informations financières, macro-économiques et géopolitiques :
  - régime de marché (mélange gaussien : Crise / Ralentissement / Reprise / Expansion) + alerte inflation ;
  - tableau de bord macro (VIX, courbe 10 ans – 3 mois, taux, dollar, pétrole, cuivre/or, crédit HY, tendance S&P 500) ;
  - lecture des actualités Google News : thèmes géopolitiques (conflits, sanctions, désescalade, choc énergétique) et
    économiques (banques centrales, inflation, récession, croissance), indice de risque géopolitique, matrice d'impact
    thèmes × actifs ;
  - signaux par actif : probabilité de hausse et rendement attendu à 1 mois (Gradient Boosting + régression logistique),
    facteurs explicatifs, validation walk-forward purgée (précision, AUC, IC, calibration) ;
  - conseils pour le portefeuille actif : alertes (concentration, crypto, cash, régime) et écarts vs allocation IA.
- 🤖 **Auto-Portefeuille** — la plateforme construit seule un portefeuille selon les conditions de marché :
  profil (Prudent → Agressif), bornes par classe ajustées au régime, rendements Black-Litterman (vues ML + actualités),
  covariance Ledoit-Wolf, 5 méthodes (utilité, Sharpe, parité de risque inclinée, variance min., HRP) ;
  backtest walk-forward sans biais d'anticipation vs S&P 500 / 60-40 / équipondéré, stress tests (2008, Covid, 2022,
  choc géopolitique, stagflation…), Monte Carlo à 1 an, exécution des ordres en un clic dans un portefeuille.
- 📄 **Rapports** — PDF complets (auto-portefeuille et portefeuilles existants) et images PNG (thème clair ou sombre,
  export .zip) : performance, drawdowns, rendements mensuels, allocation, risques, Monte Carlo, signaux ML.
- 📈 **Optimizer** réparé (le fichier contenait une copie de la page Classement) : Max Sharpe, variance min.,
  CVaR min. (programmation linéaire), parité de risque, HRP, équipondéré, frontière efficiente, corrélations.
- Optimiseurs SciPy : plus de dépendance au solveur ECOS (retiré de cvxpy ≥ 1.6).
- Si Yahoo Finance est injoignable, les pages IA basculent sur des données **simulées clairement signalées**.

> Les signaux et portefeuilles générés sont des outils pédagogiques d'aide à la décision : ils ne constituent pas
> un conseil en investissement.

### Admin Side (password-protected)
- 👥 Manage teams, add/edit/reset
- 📣 Publish live market events
- 💰 Cash injection / penalty
- 🔄 Full game reset
- 📊 Full state view

## Asset Universe
50+ assets including:
- **Equities**: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, GS, BNP.PA, AIR.PA…
- **ETFs**: SPY, QQQ
- **Crypto**: BTC-USD, ETH-USD, BNB-USD, SOL-USD, XRP-USD
- **Indices**: ^DJI, ^GSPC, ^NDX, ^FCHI, ^GDAXI, ^FTSE, ^STOXX50E, ^N225, ^HSI, ^VIX
- **Hong Kong**: 0700.HK, 1299.HK, 3690.HK, 9988.HK
- **Japan**: 6758.T, 7203.T, 7974.T, 9432.T, 9984.T
- **Commodities**: GC=F, SI=F, CL=F, BZ=F, MCL=F, CC=F
- **Forex**: EURUSD=X, JPY=X, GBP=X

## Options
European Black-Scholes pricing:
- Contract multiplier = **100** for equities/ETFs, **1** for crypto
- No naked shorts — BUY opens, SELL closes only
- Full greeks: Δ, Γ, θ, ν, ρ

## Quick Start

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/eslsca-stock-game.git
cd eslsca-stock-game

# Install
pip install -r requirements.txt

# Run
streamlit run app.py
```

## Portefeuilles permanents (Supabase)

Les portefeuilles sont rattachés à un **compte** (écran de connexion au démarrage) et sauvegardés dans
PostgreSQL (Supabase) à chaque action : ils survivent aux redémarrages de Streamlit Cloud.

Dans Streamlit Cloud → Settings → Secrets :

```toml
[supabase]
# Recommandé : Project Settings → Database → Connection string → "Transaction pooler"
database_url = "postgresql://postgres.<ref>:<MOT_DE_PASSE>@aws-0-<region>.pooler.supabase.com:6543/postgres"
```

(L'ancien mode `url` + `db_password` fonctionne toujours, mais la connexion directe Supabase est en IPv6 et
peut être refusée par Streamlit Cloud.) Si la base est injoignable, l'écran de connexion affiche l'erreur exacte.

## Emails quand le portefeuille bouge

Un email part à l'adresse du compte quand un ordre est exécuté, qu'un portefeuille est créé / réinitialisé /
crédité, ou que sa valeur varie de ±`nav_alert_pct` % (alerte de variation envoyée tant que l'utilisateur est connecté).

```toml
[email]
smtp_host     = "smtp.gmail.com"
smtp_port     = 587
smtp_user     = "votre.adresse@gmail.com"
smtp_password = "mot-de-passe-d-application"   # Gmail : mot de passe d'application
security      = "starttls"                     # "starttls" | "ssl" | "none"
nav_alert_pct = 2.0                            # 0 = pas d'alerte de variation
```

Le bouton 🔔 en haut de page permet de couper les emails et d'envoyer un email de test.

## Deploy on Streamlit Cloud

1. Push to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. New app → select repo → `app.py`
4. Deploy 🚀

## Structure

```
eslsca_platform/
├── app.py                  # Entry point
├── requirements.txt
├── data/
│   ├── assets.csv          # All tradeable assets
│   ├── options_positions.csv
│   ├── market_events.csv   # Events / news
│   ├── teams.csv
│   └── game_state.json     # Live game state (auto-created)
├── pages/
│   ├── dashboard.py
│   ├── trading.py
│   ├── technical.py
│   ├── ai_markets.py       # 🧠 IA Marchés (régime, macro, géopolitique, signaux ML, conseils)
│   ├── auto_portfolio.py   # 🤖 Auto-Portefeuille (construction, backtest, risques, exports, exécution)
│   ├── reports.py          # 📄 Rapports PDF / PNG des portefeuilles
│   ├── optimizer.py        # 📈 Optimiseur multi-méthodes
│   ├── leaderboard.py
│   ├── events.py
│   └── admin.py
├── utils/
│   ├── data.py             # yfinance helpers, state mgmt
│   ├── options.py          # Black-Scholes
│   ├── portfolio.py        # Markowitz, CVaR, optimiseurs SciPy, HRP, parité de risque
│   ├── market_intel.py     # univers, prix en lot, macro, actualités & géopolitique
│   ├── ml_engine.py        # features, modèles ML, validation walk-forward, régimes
│   ├── auto_portfolio.py   # profils, Black-Litterman, backtest, stress tests, Monte Carlo, ordres
│   ├── reporting.py        # graphiques PNG (matplotlib) + moteur PDF (ReportLab)
│   ├── report_builders.py  # contenu des rapports PDF
│   ├── technical.py        # RSI, MACD, Bollinger, GARCH
│   ├── db.py               # Supabase / PostgreSQL (comptes, portefeuilles)
│   └── notifier.py         # Emails de notification (SMTP)
└── components/
    ├── ai_shared.py        # chargement en cache du modèle, KPI, en-têtes des pages IA
    ├── ui.py               # CSS theme, ticker strip, news banner
    └── webui.py            # Habillage page web : en-tête, onglets, bandeau compte, footer
```

## Admin Password

Default: `MIP2026` — change it in the Admin Panel after first login.

## Teams

Bears 🐻 | Bulls 🐂 | Whales 🐋 | Raptors 🦅 | Sharpas 🦈 | Strikers ⚡ | Wolves 🐺

---
Built for ESLSCA Stock Market Game · 2026
