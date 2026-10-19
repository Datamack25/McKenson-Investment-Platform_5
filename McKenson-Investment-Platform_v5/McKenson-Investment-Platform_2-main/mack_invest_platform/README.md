📈 McKenson Investment Platform - MIP — version 5.2.0
A full-featured investment simulation platform built with Streamlit + yfinance.

Plateforme créée par **Mackenson CINEUS**, diplômé d'un MBA Finance de marché — version 5.2.0 (octobre 2026).

> ⚠️ **Avertissement** — Plateforme purement éducative : aucune opération n'est exécutée sur un marché réel et
> rien de ce qui y est présenté (signaux, allocations, stratégies, rapports, alertes) ne constitue un conseil en
> investissement, une recommandation personnalisée ou une sollicitation. Mackenson CINEUS n'est pas responsable
> des décisions prises par les utilisateurs et n'est pas engagé par les décisions ou les conseils issus de cette
> plateforme. Les performances passées ne préjugent pas des performances futures.

Nouveautés v5.2 — Hedge Fund Agent exécutable, couvertures par dérivés, performance vs marché
🦅 Hedge Fund Agent → Validation humaine : la proposition du desk peut CRÉER UN NOUVEAU PORTEFEUILLE (nom,
   icône, équipe, capital) ou MODIFIER UN PORTEFEUILLE EXISTANT (investir le cash ou rééquilibrer), ou être
   seulement inscrite au journal. Tous les ordres passent par la conformité.
🛡️ Couvertures par produits dérivés (utils/hedging.py) : pour chaque exposition importante (Nasdaq / tech via
   QQQ, S&P 500 via SPY, Europe via VGK, émergents via EEM, énergie via XLE, pétrole / matières premières via USO,
   obligations longues via TLT), le desk propose un put de protection ou un put spread (si la volatilité est
   élevée), avec un ratio de couverture qui dépend des facteurs macro (stress, géopolitique, croissance,
   politique monétaire, énergie…). Pour chacune : pourquoi, coût, part couverte et perte en cas de baisse
   avec / sans couverture. L'investisseur coche ou retire chaque couverture selon sa tolérance au risque.
   La conformité traite une couverture d'indice dont le nominal ne dépasse pas l'exposition comme une
   « couverture » (autorisée pour tous les profils) ; au-delà, c'est de la spéculation (règle O02).
📈 Dashboard : un portefeuille → graphique base 100 vs indice (S&P 500, MSCI World, Nasdaq 100, CAC 40,
   60/40) + performance, surperformance, bêta, perte max ; plusieurs portefeuilles → graphique comparatif +
   tableau (volatilité, Sharpe, écart de suivi, ratio d'information). NAV reconstituée à partir des
   transactions et des cours historiques (utils/performance.py).

Nouveautés v5.1 — ETF, conformité, stratégies d'options, sécurité
🧺 Univers ETF élargi (data/assets_etf.csv, chargé automatiquement) : ~40 ETF UCITS (IWDA, VWCE, CSPX, EIMI,
   ETF éligibles PEA, obligations €, monétaire €STR, or physique) et US à bas coût (VOO, VTI, VT, BND…), avec
   frais (TER), zone, UCITS, PEA ; filtre « Univers » et fiche ETF dans le Trading Desk.
🧺 Portefeuilles modèles 100 % ETF par profil (Prudent → 100 % actions, PEA, « trois fonds ») exécutables en un
   clic, avec frais moyens pondérés ; nouvelle stratégie de portefeuille « ETF Core ».
🛡️ Contrôles de conformité pré-négociation (utils/compliance.py) sur TOUS les ordres (spot, options,
   stratégies, Auto-Portefeuille, modèles ETF) : qualité des données (C01), instruments sanctionnés (C02),
   mandat (C03), concentration par ligne (C04), plafond crypto (C05), liquidités minimales (C06),
   provision / pas de vente à découvert (C07), taille inhabituelle (C08), profil (C09), caractère approprié
   des produits complexes (O01), usage des dérivés par profil (O02), interdiction des ventes d'options non
   couvertes (O03), budget de primes (O04), perte maximale couverte (O05), échéance (O06). Chaque blocage est
   expliqué (règle, raison, référence MiFID II / UCITS / MiCA / RTS 6 / sanctions UE) et journalisé
   (table mam_compliance_log, onglet Admin → Conformité).
🧾 Profil investisseur (questionnaire de risque + test de connaissances sur les options, inspiré de MiFID II
   art. 25) qui fixe les limites appliquées aux ordres.
🎯 Stratégies d'options selon le régime de marché (utils/option_strategies.py) : lecture du régime
   (S&P 500 / VIX), stratégies recommandées par régime et niveau de volatilité, construction multi-jambes
   (put de protection, call couvert, collar, spreads, straddle, iron condor, papillon, put couvert par du cash),
   gain / perte max, points morts, grecques agrégées, diagramme de P&L, exécution contrôlée.
🧭 Exposition par classe d'actifs et limites du profil (Trading Desk → Mes positions → Exposition & conformité).
🔒 Sécurité : mots de passe bcrypt (migration automatique des anciens hachages à la connexion), verrouillage
   15 min après 5 échecs, portefeuilles protégés contre l'écrasement par un autre utilisateur, identifiants de
   portefeuilles uniques, indicateur « données live / de repli » dans l'en-tête.

Features
Public Side
🎞️ Live ticker strip — real-time prices for all assets (SPY, AAPL, MSFT, BTC, indices, FX, commodities…)
📰 Breaking news banner — scrolling market events
💼 Trading Desk — spot orders + European options (Black-Scholes)
📊 Technical Analysis — RSI, MACD, Bollinger Bands, GARCH vol forecast, candlestick charts
🧮 Portfolio Optimizer — Markowitz + CVaR, efficient frontier, correlation heatmap
🏆 Leaderboard — team rankings, benchmark comparison (SPY/QQQ/CAC40/Gold/BTC), risk-return map
Nouveautés v5 — Intelligence artificielle
🧠 IA Marchés — machine learning appliqué aux informations financières, macro-économiques et géopolitiques :
régime de marché (mélange gaussien : Crise / Ralentissement / Reprise / Expansion) + alerte inflation ;
tableau de bord macro (VIX, courbe 10 ans – 3 mois, taux, dollar, pétrole, cuivre/or, crédit HY, tendance S&P 500) ;
lecture des actualités Google News : thèmes géopolitiques (conflits, sanctions, désescalade, choc énergétique) et économiques (banques centrales, inflation, récession, croissance), indice de risque géopolitique, matrice d'impact thèmes × actifs ;
signaux par actif : probabilité de hausse et rendement attendu à 1 mois (Gradient Boosting + régression logistique), facteurs explicatifs, validation walk-forward purgée (précision, AUC, IC, calibration) ;
conseils pour le portefeuille actif : alertes (concentration, crypto, cash, régime) et écarts vs allocation IA.
🤖 Auto-Portefeuille — la plateforme construit seule un portefeuille selon les conditions de marché : profil (Prudent → Agressif), bornes par classe ajustées au régime, rendements Black-Litterman (vues ML + actualités), covariance Ledoit-Wolf, 5 méthodes (utilité, Sharpe, parité de risque inclinée, variance min., HRP) ; backtest walk-forward sans biais d'anticipation vs S&P 500 / 60-40 / équipondéré, stress tests (2008, Covid, 2022, choc géopolitique, stagflation…), Monte Carlo à 1 an, exécution des ordres en un clic dans un portefeuille.
🦅 Hedge Fund Agent — desk multi-rôles : données → veille actualités (conflits, sanctions, droits de douane, élections, banques centrales, inflation, récession, énergie, stress bancaire, désescalade) → 8 facteurs macro notés de −2 à +2 et régime (expansion, surchauffe, stagflation, ralentissement, aversion au risque) → stratège (allocation par profil + inclinaisons tactiques expliquées) → moteur de risque déterministe (plafonds crypto / actions, cash minimum, volatilité cible, mode stress, veto si données simulées) → validation humaine et journal. Onglet « Conseils portefeuille » : revue de n'importe quel portefeuille menée comme par un gérant professionnel — évolution des facteurs sur 3 mois et changements depuis la dernière revue enregistrée, vues par classe avec niveau de conviction, analyse ligne par ligne (contribution au risque, bêta, tendance, momentum, drawdown → Conserver / Renforcer / Alléger / Surveiller), plan d'ajustement chiffré (bandes de tolérance, plafond par ligne, arbitrages intra-classe, financement par les liquidités, coûts, calendrier d'exécution), déclencheurs de révision et note de gestion téléchargeable (reformulable par l'IA). Briefing rédigé par IA en option (clé gratuite Groq ou Gemini).
📄 Rapports — PDF complets (auto-portefeuille et portefeuilles existants) et images PNG (thème clair ou sombre, export .zip) : performance, drawdowns, rendements mensuels, allocation, risques, Monte Carlo, signaux ML.
📈 Optimizer réparé (le fichier contenait une copie de la page Classement) : Max Sharpe, variance min., CVaR min. (programmation linéaire), parité de risque, HRP, équipondéré, frontière efficiente, corrélations.
Optimiseurs SciPy : plus de dépendance au solveur ECOS (retiré de cvxpy ≥ 1.6).
Si Yahoo Finance est injoignable, les pages IA basculent sur des données simulées clairement signalées.
Les signaux et portefeuilles générés sont des outils pédagogiques d'aide à la décision : ils ne constituent pas un conseil en investissement.

Admin Side (password-protected)
👥 Manage teams, add/edit/reset
📣 Publish live market events
💰 Cash injection / penalty
🔄 Full game reset
📊 Full state view
Asset Universe
50+ assets including:

Equities: AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, GS, BNP.PA, AIR.PA…
ETFs: SPY, QQQ
Crypto: BTC-USD, ETH-USD, BNB-USD, SOL-USD, XRP-USD
Indices: ^DJI, ^GSPC, ^NDX, ^FCHI, ^GDAXI, ^FTSE, ^STOXX50E, ^N225, ^HSI, ^VIX
Hong Kong: 0700.HK, 1299.HK, 3690.HK, 9988.HK
Japan: 6758.T, 7203.T, 7974.T, 9432.T, 9984.T
Commodities: GC=F, SI=F, CL=F, BZ=F, MCL=F, CC=F
Forex: EURUSD=X, JPY=X, GBP=X
Options
European Black-Scholes pricing:

Contract multiplier = 100 for equities/ETFs, 1 for crypto
No naked shorts — les ventes de calls non couverts sont bloquées par la conformité (règle O03) ; les ventes de puts doivent être couvertes par des liquidités (règle O05)
Full greeks: Δ, Γ, θ, ν, ρ
Quick Start
# Clone
git clone https://github.com/YOUR_USERNAME/eslsca-stock-game.git
cd eslsca-stock-game

# Install
pip install -r requirements.txt

# Run
streamlit run app.py
Portefeuilles permanents (Supabase)
Les portefeuilles sont rattachés à un compte (écran de connexion au démarrage) et sauvegardés dans PostgreSQL (Supabase) à chaque action : ils survivent aux redémarrages de Streamlit Cloud.

Dans Streamlit Cloud → Settings → Secrets :

[supabase]
# Recommandé : Project Settings → Database → Connection string → "Transaction pooler"
database_url = "postgresql://postgres.<ref>:<MOT_DE_PASSE>@aws-0-<region>.pooler.supabase.com:6543/postgres"
(L'ancien mode url + db_password fonctionne toujours, mais la connexion directe Supabase est en IPv6 et peut être refusée par Streamlit Cloud.) Si la base est injoignable, l'écran de connexion affiche l'erreur exacte.

Emails quand le portefeuille bouge
Un email part à l'adresse du compte quand un ordre est exécuté, qu'un portefeuille est créé / réinitialisé / crédité, ou que sa valeur varie de ±nav_alert_pct % (alerte de variation envoyée tant que l'utilisateur est connecté).

[email]
smtp_host     = "smtp.gmail.com"
smtp_port     = 587
smtp_user     = "votre.adresse@gmail.com"
smtp_password = "mot-de-passe-d-application"   # Gmail : mot de passe d'application
security      = "starttls"                     # "starttls" | "ssl" | "none"
nav_alert_pct = 2.0                            # 0 = pas d'alerte de variation
Le bouton 🔔 en haut de page permet de couper les emails et d'envoyer un email de test.

Briefing IA (optionnel, gratuit)
Dans Streamlit Cloud → Settings → Secrets :

[llm]
provider = "groq"            # ou "gemini"
api_key  = "votre-cle"       # console.groq.com ou aistudio.google.com
# model  = "llama-3.3-70b-versatile"   # facultatif

Sans clé, le briefing est rédigé de façon déterministe à partir des données.

Alertes et rapport hebdomadaire automatique
Onglet 🔔 Alertes : le desk surveille les marchés (mouvements anormaux à la hausse ou à la baisse mesurés en écarts-types, franchissement de la moyenne 200 jours), la volatilité (VIX), les taux (10 ans, inversion de courbe), l'économie (facteurs qui bougent vite, changement de régime), la géopolitique et l'actualité financière, et les portefeuilles suivis (forte variation d'une ligne, concentration, dérive d'allocation). Chaque alerte indique sa gravité (critique / important / info) et explique pourquoi elle compte, son impact probable par classe d'actifs et ce qu'il faut surveiller.

Dans une revue de portefeuille → 📬 Rapport & alertes : générer et télécharger le rapport PNG, se l'envoyer par email, et « Suivre ce portefeuille » pour recevoir le rapport chaque lundi et les alertes par email.

Envoi automatique (GitHub Actions, gratuit)
Streamlit Cloud se met en veille : il ne peut rien envoyer seul. L'envoi est donc assuré par GitHub Actions (.github/workflows/weekly_report.yml) :
- du lundi au vendredi vers 7 h 45 (heure de Paris ; 6 h 45 en hiver) : calcul des alertes et envoi des nouvelles alertes importantes ou critiques ;
- chaque lundi : envoi du rapport hebdomadaire PNG en pièce jointe, pour chaque portefeuille suivi (ou rapport du « Desk MAM » si aucun portefeuille n'est suivi).

Le fichier .github/workflows/weekly_report.yml doit se trouver à la RACINE du dépôt. Il retrouve tout seul le dossier de l'application (celui qui contient jobs/weekly_report.py), même si l'application est dans un sous-dossier. Le plus simple pour le créer : onglet Actions → « set up a workflow yourself » → nommer le fichier weekly_report.yml → coller le contenu → Commit changes.

Secrets GitHub (Settings → Secrets and variables → Actions → New repository secret) — 7 obligatoires :

DATABASE_URL     = la même valeur que [supabase] database_url dans Streamlit
SMTP_HOST        = smtp.gmail.com
SMTP_PORT        = 587
SMTP_USER        = l'adresse Gmail d'envoi
SMTP_PASSWORD    = mot de passe d'APPLICATION Gmail (16 lettres minuscules)
SMTP_SECURITY    = starttls
REPORT_TO        = l'adresse qui reçoit les rapports
TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID       (optionnel : rapport et alertes aussi sur Telegram)

Valeurs sans guillemets. Les mêmes réglages SMTP doivent figurer dans les secrets Streamlit (section [email]) pour l'envoi depuis l'application.

Mot de passe d'application Gmail
Le mot de passe Gmail habituel ne fonctionne pas. Sur myaccount.google.com, avec le compte de SMTP_USER : activer la validation en deux étapes, puis rechercher « Mots de passe des applications » → nom « MAM » → Create. Google affiche 16 lettres une seule fois : les copier dans SMTP_PASSWORD (espaces acceptés, ils sont retirés automatiquement).

Test
Onglet Actions → « MAM — rapport hebdomadaire et alertes » → Run workflow → mode weekly. Après 2 à 4 minutes : coche verte = email envoyé (vérifier les spams la première fois) ; croix rouge = échec d'envoi. Les PNG générés restent téléchargeables 30 jours dans l'exécution (section Artifacts).

Dépannage
Le journal de l'étape « Générer et envoyer » commence par un diagnostic des réglages email, qui affiche OK ou PROBLÈME pour chaque secret sans révéler sa valeur (GitHub masque les valeurs secrètes par ***). L'envoi essaie automatiquement STARTTLS sur le port 587 puis SSL sur le port 465, et indique à quelle étape la connexion a échoué.
- « SMTP_PASSWORD fait 16 caractères… (lu : 18) » ou connexion coupée à l'étape « authentification » : ce n'est pas un mot de passe d'application valide → en créer un nouveau et mettre à jour SMTP_PASSWORD.
- « Identifiants refusés » : SMTP_USER et le mot de passe d'application ne correspondent pas au même compte Google.
- Les avertissements « Node.js 20 is deprecated » ou « ubuntu-latest will migrate » sont sans effet.

Nom de l'expéditeur
Les emails partent sous le nom « MAM Hedge Fund Agent ». Quand SMTP_USER et REPORT_TO sont la même adresse, Gmail affiche « moi / me » à la place du nom : c'est un comportement de Gmail. Pour voir le nom, recevoir sur une autre adresse (REPORT_TO), ou mieux, créer une adresse Gmail dédiée à l'envoi (ex. un compte « McKenson AM ») et mettre à jour SMTP_USER et SMTP_PASSWORD.

Deploy on Streamlit Cloud
Push to GitHub
Go to share.streamlit.io
New app → select repo → app.py
Deploy 🚀
Structure
eslsca_platform/
├── app.py                  # Entry point
├── jobs/weekly_report.py   # job planifié : alertes quotidiennes + rapport PNG du lundi
├── .github/workflows/weekly_report.yml   # planification GitHub Actions (gratuit)
├── requirements.txt
├── data/
│   ├── assets.csv          # All tradeable assets
│   ├── assets_etf.csv      # Univers ETF v5.1 (frais, UCITS, PEA, classe)
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
│   ├── hedge_fund.py       # 🦅 Hedge Fund Agent (briefing, allocation du desk, conseils, journal)
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
│   ├── advisor.py          # moteur du Hedge Fund Agent : facteurs, régime, stratège, risque, conseils
│   ├── portfolio_manager.py # revue de gestion : évolution, vues, analyse des lignes, plan d'ajustement, note
│   ├── alerts.py           # moteur d'alertes expliquées, historique, abonnements, email / Telegram
│   ├── report_png.py       # rapport hebdomadaire PNG (matplotlib)
│   ├── reporting.py        # graphiques PNG (matplotlib) + moteur PDF (ReportLab)
│   ├── report_builders.py  # contenu des rapports PDF
│   ├── technical.py        # RSI, MACD, Bollinger, GARCH
│   ├── db.py               # Supabase / PostgreSQL (comptes, portefeuilles)
│   ├── notifier.py         # Emails de notification (SMTP)
│   ├── compliance.py       # v5.1 contrôles de conformité pré-négociation, profil investisseur, journal d'audit
│   ├── option_strategies.py# v5.1 stratégies d'options multi-jambes selon le régime de marché
│   ├── etf_universe.py     # v5.1 métadonnées ETF et portefeuilles modèles 100 % ETF
│   ├── hedging.py          # v5.2 couvertures par options proposées par le desk
│   ├── performance.py      # v5.2 NAV reconstituée, indicateurs de gestion, indices de référence
│   └── legal.py            # v5.1 auteur, version, avertissements (source unique)
└── components/
    ├── ai_shared.py        # chargement en cache du modèle, KPI, en-têtes des pages IA
    ├── ui.py               # CSS theme, ticker strip, news banner
    └── webui.py            # Habillage page web : en-tête, onglets, bandeau compte, footer
Admin Password
Définir le mot de passe admin dans Streamlit Cloud → Settings → Secrets :
[admin]
password = "VotreMotDePasseAdmin"
(un compte avec role = 'admin' dans mam_users accède aussi directement au panneau).

Teams
Bears 🐻 | Bulls 🐂 | Whales 🐋 | Raptors 🦅 | Sharpas 🦈 | Strikers ⚡ | Wolves 🐺

© 2026 Mackenson CINEUS — McKenson Asset Management — v5.2.0 — plateforme de simulation pédagogique. Ne constitue pas un conseil en investissement ; l'auteur n'est pas responsable des décisions prises.
