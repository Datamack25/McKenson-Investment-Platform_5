📈 McKenson Investment Platform - MIP — version 5.11.0
A full-featured investment simulation platform built with Streamlit + yfinance.

Plateforme créée par **Mackenson CINEUS**, diplômé d'un MBA Finance de marché — version 5.11.0 (octobre 2026).

> ⚠️ **Avertissement** — Plateforme purement éducative : aucune opération n'est exécutée sur un marché réel et
> rien de ce qui y est présenté (signaux, allocations, stratégies, rapports, alertes) ne constitue un conseil en
> investissement, une recommandation personnalisée ou une sollicitation. Mackenson CINEUS n'est pas responsable
> des décisions prises par les utilisateurs et n'est pas engagé par les décisions ou les conseils issus de cette
> plateforme. Les performances passées ne préjugent pas des performances futures.

Nouveautés v5.11 — Tracking Best AM, comparaison avec les meilleurs gérants, analyse complète du marché

🐋 **Tracking Best AM** (nouvel onglet) : où et comment investissent les meilleurs gérants, à partir de leurs formulaires
**13F** téléchargés directement auprès de la **SEC (EDGAR)** — la source officielle de Dataroma, WhaleWisdom ou TIKR.
41 gérants préconfigurés (Buffett, Ackman, Klarman, Li Lu, Druckenmiller, Tepper, Burry, Dalio, Coatue, Tiger, Viking,
Renaissance, Norges Bank, Amundi…) en 5 styles, ou n'importe quel gérant par son n° CIK ; trimestre aligné sur la majorité ;
mouvements du trimestre (nouvelles, renforcées, allégées, soldées) ; tickers (SEC + OpenFIGI) et secteurs (GICS simplifié,
code SIC) mis en cache (data/smart_money/). Import CSV / Excel (export Dataroma, WhaleWisdom…) si la SEC est injoignable.
- 🔥 Consensus & mouvements : top 5 secteurs / actifs / achats / ventes, titres les plus partagés (score), carte partage ×
  conviction, évolution depuis la fin du trimestre (effet du délai de 45 jours), les 4 filtres de la méthode 13F
  (convictions ≥ 5 %, achats groupés, nouvelles entrées dans le top 10, fortes hausses de poids) ;
- 📋 Détenus · vendus · équivalents : **les actifs les plus détenus** (nombre de gérants, poids moyen, poids max, part de
  la valeur, **détenu depuis** quel trimestre, plus ancien détenteur) et **les plus vendus** (vendeurs, soldé / allégé par
  qui, **part des actions vendues**, montant vendu estimé, **ventes depuis** quel trimestre), grâce à l'historique de 2 à 8
  trimestres par gérant ; pour chaque actif, **comment investir dans le même actif** : achat direct (compte-titres) et
  équivalents ETF sectoriels US, UCITS et PEA ;
- 🧺 **Les actifs des gérants alimentent les CSV de MIP** : `data/assets_best_am.csv` (même format que `assets.csv`, plus
  secteur, gérants, poids, mouvements, équivalents) est écrit à chaque chargement et fusionné automatiquement dans tout MIP ;
  nouvel univers **« 🐋 Best AM »** dans le Trading Desk (actifs des gérants + ETF sectoriels UCITS équivalents). Sur
  Streamlit Cloud, télécharger le fichier et le déposer dans `data/` du dépôt pour le rendre permanent ;
- 🏛️ Gérants : concentration, rotation, secteur dominant, options déclarées, zoom par gérant (avec « détenu depuis ») ;
- 🏭 Secteurs : allocation moyenne et pondérée, flux du trimestre, carte de chaleur gérants × secteurs, allocation par style,
  zoom sur un secteur ;
- ⚖️ Mon portefeuille vs gérants : un ou plusieurs portefeuilles (ou le fichier importé) face à la moyenne des gérants, à un
  gérant ou à un style ; ETF décomposés par secteur ; recouvrement, part active ; **pourquoi ces différences** (ce que les
  13F ne montrent pas, actions hors US, ETF, écarts sectoriels expliqués par les flux des gérants et le régime officiel du
  comité, concentration vs plafond par ligne de votre profil) ; **pistes du comité à valider** (enregistrées dans le
  journal du portefeuille, aucun ordre passé) ;
- 🧠 Analyse du comité : lecture des investissements des gérants par chacun des six membres + synthèse en mots simples ;
- 📄 Rapports : rapport complet PDF (graphiques, carte de chaleur, consensus, analyse, comparaison), **rapport d'analyse
  sectorielle** (un ou plusieurs secteurs), export Excel ;
- 🔗 Plateformes & méthode : Dataroma, WhaleWisdom, TIKR, SEC EDGAR, HedgeFollow, 13f.info, GuruFocus, OpenInsider, AMF BDIF.

📥 **Conseil portefeuille → sous-onglet « 🐋 Comparer aux meilleurs gérants »** : votre portefeuille actuel, plusieurs
portefeuilles au choix ou le fichier importé, comparés aux allocations des meilleurs gérants.

📄 **Rapports** : section « Où investissent actuellement les meilleurs gérants » (top 5 secteurs, top 5 actifs, plateformes à
regarder) sur la page Rapports et dans les PDF du comité, mensuel et détaillé, ainsi que dans l'e-mail du lundi (le job
hebdomadaire télécharge les 13F une fois par exécution).

🧑‍⚖️ **IA Marchés → « Analyse du comité »** : « le Nasdaq est négatif : pourquoi, quel impact, comment s'adapter ? ». Pour 12
marchés (Nasdaq 100, S&P 500, Dow, Russell 2000, CAC 40, Euro Stoxx 50, DAX, Nikkei, émergents, or, pétrole, bitcoin) et 4
horizons : décomposition du mouvement par facteur (régression ridge sur 2 ans : taux 10 ans, dollar, VIX, pétrole, crédit,
euro, yen, Wall Street), part propre au marché, ampleur inhabituelle (z-score), tendance et RSI, rotation sectorielle, grandes
capitalisations, actualités Google News, **réseaux sociaux** (Reddit : r/wallstreetbets, r/stocks, r/investing,
r/StockMarket ; StockTwits : messages haussiers / baissiers, titres les plus cités), impact sur le portefeuille choisi (bêta,
lignes les plus touchées), pistes d'adaptation, avis de chaque membre du comité, rédaction facultative par LLM (secret
`[llm]`), rapport PDF.

Secrets facultatifs : `[sec] user_agent = "Votre Nom votre@adresse.com"` (recommandé par la SEC), `[openfigi] api_key`.
Tests : 131 (python -m pytest -q).

Nouveautés v5.10 — Logo MAM et plusieurs destinataires

🎨 **Identité visuelle** : nouveau logo MAM (dossier assets/ : logo seul, logo avec « MAM », bannière, icône d'onglet) dans l'en-tête de la plateforme, l'écran de connexion, l'onglet du navigateur, le bandeau et la page de titre des rapports PDF, les rapports PNG (comité, hebdomadaire, portefeuille importé, « En bref ») et chaque graphique exporté (utils/brand.py).

📧 **Plusieurs destinataires** partout, séparés par des virgules : 🔔 → « Autres destinataires » (test, alertes de variation), rapport du comité et suivi du lundi (page Rapports), rapport mensuel investisseur, secret GitHub `REPORT_TO`. Les adresses invalides sont ignorées ; le diagnostic indique combien d'adresses ont été lues.

Nouveautés v5.9 — Avis du comité à la création : analyser, corriger, ajuster

À l'étape 5 de l'assistant, le comité rend son avis et son analyse complète AVANT le bouton de création. Chaque réserve ou veto indique où le corriger, avec un bouton qui ramène directement à l'étape concernée (🎯 stratégie, 📦 classes d'actifs, 📋 politique d'investissement) puis un bouton pour revenir directement à l'avis du comité. En cas de veto, le comité propose un ajustement minimal de vos choix (d'abord les classes d'actifs et la stratégie la plus proche, sans toucher à votre politique ; la politique n'est modifiée qu'en dernier recours, avec un avertissement) : vous l'acceptez ou le refusez. Le bouton « Créer le portefeuille » s'active dès que le comité ne s'oppose plus. L'avis est recalculé automatiquement dès qu'un choix change.

Nouveautés v5.8 — Réalisme des marchés et performance selon GIPS

💱 **Devises** : les titres cotés en EUR, GBP (pence à Londres), CHF, JPY, HKD, KRW, INR… sont convertis en USD (devise des portefeuilles) au taux de change du marché, à l'achat, à la vente, pour la valorisation et pour l'historique (taux historiques jour par jour) (utils/fx.py).

💸 **Coûts de transaction** sur chaque ordre : écart achat-vente, courtage par marché avec minimum, taxe française sur les transactions financières (0,4 %) et droit de timbre britannique (0,5 %) à l'achat d'actions, commissions et écart sur les options. Prix de revient frais inclus ; contrôle de provision C07 frais compris ; les achats automatiques sont ajustés au cash disponible (utils/costs.py).

💰 **Dividendes** versés en liquidités à la date de détachement, nets de la retenue à la source non récupérable (hypothèse : résident fiscal français) ; **intérêts monétaires** quotidiens sur les liquidités au taux des bons du Trésor américain à 13 semaines (^IRX, exact/360), avec rattrapage du passé (utils/income.py). Valorisation aux cours réellement cotés (dividendes versés à part).

🏦 **Apports et retraits** de liquidités par l'administrateur (Administration → Tous les portefeuilles → fiche), inscrits comme flux externes dans le journal des mouvements (utils/ledger.py).

📐 **Performance GIPS** partout (Dashboard, classement, rapports, comité, administration) : rendement pondéré dans le temps (TWR) à valorisation quotidienne, chaînage géométrique, flux externes neutralisés, net des coûts de transaction, revenus inclus, pas d'annualisation sous un an, composites d'équipe pondérés par les capitaux ; contributions par ligne exactement égales au TWR (lissage de Carino), avec lignes « frais » et « intérêts » ; indices de référence en rendement total et en USD (CAC 40 via ETF). Note de méthode dans les rapports.

Tests : 108 (python -m pytest -q).

Nouveautés v5.7 — Portefeuille proposé et ajustable + comparaison de tous les portefeuilles

🧭 **Portefeuille proposé pour vous** (Trading Desk, en haut de page) : le comité construit un portefeuille complet à partir du profil de l'utilisateur, de la politique d'investissement du portefeuille et des conditions de marché réelles (régime officiel, signaux validés hors échantillon, secteurs porteurs selon la performance récente et le régime, hors PEA / UCITS). Chaque ligne est expliquée en mots simples. L'utilisateur modifie les poids, retire ou ajoute des lignes, revient à la proposition s'il le souhaite ; sa version est revue par le comité (veto possible) puis chaque ordre passe par la conformité. Exécution impossible si les cours ne sont pas réels (utils/portfolio_proposal.py, components/proposal_ui.py).

📊 **Administration → Tous les portefeuilles** : tous les portefeuilles de tous les comptes (base Supabase) comparés : valeur, performance, stratégie, profil, avis du comité, liquidités, classe et thème dominants, façon dont ils ont été construits ; filtres ; indicateurs historiques à la demande (volatilité, Sharpe, perte max, bêta, surperformance vs indice) ; comparaisons par stratégie, profil, propriétaire, équipe ; carte risque / rendement ; courbes base 100 ; fiche détaillée avec « En bref » ; export CSV (utils/portfolio_census.py, components/admin_portfolios.py).

Tests : 94 (python -m pytest -q).

Nouveautés v5.6 — Discipline de gestion, rapports en langage simple, comité après création

🗣️ **En bref, en mots simples** en tête de chaque rapport (rapport du comité PNG/PDF/e-mail du lundi, rapport détaillé, rapport mensuel, Auto-Portefeuille, portefeuille importé, note de gestion) : le portefeuille a-t-il fait mieux ou moins bien que son indice, de combien de points, et quelle ligne ou quelle façon d'investir (décisions manuelles, desk, comité, modèles ETF, options) en est la cause ; poids des liquidités (utils/plain_summary.py).

📬 **Rapport mensuel investisseur** (page Rapports) : en bref, chiffres du mois expliqués, décisions du mois avec leur raison et leurs dangers, ce qui a marché ou non, respect des règles, avis du comité, prochaines étapes, lexique ; PDF et envoi par e-mail (utils/investor_report.py).

🧑‍⚖️ **Profil et comité pour toute création** : assistant, Hedge Fund Agent, administration (profil + politique d'investissement + veto), modèles ETF (avis du comité obligatoire avant d'investir) ; Auto-Portefeuille et Hedge Fund Agent prennent par défaut le profil du portefeuille actif. **Après chaque création, le comité propose des améliorations** expliquées une à une, que l'utilisateur coche, valide, reporte ou refuse (components/committee_followup.py).

📝 **Thèse obligatoire avant chaque ordre manuel** (raison, dangers, ce qui ferait changer d'avis, horizon), horodatée et rattachée à l'ordre ; journal des décisions.

🗂️ **Fiche de risques par ligne** (taux, juridique, dette, change, matières premières, géopolitique, valorisation…, niveau et couverture), pré-remplie selon le secteur (utils/line_risk.py).

🔌 **Paniers thématiques et chaînes de valeur** (infrastructure de l'IA, applications de l'IA, transition énergétique, défense) : exposition par segment et alerte quand des lignes de secteurs différents dépendent du même moteur ; univers « 🔌 Thèmes » dans le Trading Desk ; 8 actifs ajoutés (ETN, VRT, SU.PA, CEG, FCX, NUE, TSM, AMAT) (utils/themes.py).

🧾 **Dérogation encadrée au plafond par ligne** (règle D01) : justification écrite, plafond + 10 points au plus, 7 jours maximum, notification préalable, rappel à l'échéance dans chaque ordre et chaque rapport.

📅 **Calendrier des résultats** des actions détenues (30 jours) et avertissement « période de résultats » avant un ordre (utils/earnings.py).

Trading Desk → Mes positions → 🧭 Discipline de gestion. Supabase : nouvelle colonne `extras` (créée automatiquement au démarrage). Tests : 86 (python -m pytest -q).

Nouveautés v5.5 — Conseil sur un portefeuille importé + accès administrateur

**📥 Conseil portefeuille** (nouvel onglet) : l'utilisateur importe son portefeuille en **CSV ou Excel** (format affiché avant l'import, modèles téléchargeables : colonnes `ticker` + `quantite` ou `montant`, facultatif `prix_achat`, `nom`, `devise`, ligne `CASH` pour les liquidités). Le comité MAM l'analyse selon le **profil investisseur** et la **politique d'investissement** retenue (profil, IPS d'un portefeuille existant ou saisie dédiée) et le contexte de marché :
- avis des six membres, réallocation et optimisation (ordres proposés, jamais exécutés) ;
- scénarios de marché (stress tests du desk + scénario personnalisé) et stress test inversé ;
- à côté du tableau importé : **secteurs** et **régions** qui performent le mieux (perf. 3 et 12 mois + lecture du contexte), avec **carte du monde** ;
- téléchargement en **Excel** (7 feuilles, graphiques natifs), **CSV** ou **image PNG**.
Après chaque analyse et dans chaque fichier : « ce n'est pas un conseil financier ; Mackenson CINEUS n'est pas responsable et ne s'engage pas ».

**🛡️ Onglet Administrateur sur l'écran de connexion** : connexion avec son compte et ouverture directe du panneau d'administration (compte de rôle administrateur, ou mot de passe `[admin] password` des secrets). La session garde aussi l'accès utilisateur.

Nouveautés v5.4 — Calibration sur l'historique (lot 1 de la feuille de route)

Onglet **🧪 Calibration** du Hedge Fund Agent : les hypothèses d'expert sont confrontées à 10 ans d'historique réel.

- **Matrice de sensibilité** estimée par régression (ridge) des rendements hebdomadaires des classes sur les variations des facteurs, avec statistiques t, stabilité sur fenêtres de 3 ans et désaccords avec l'expert ; application possible en matrice mixte (poids réglable).
- **Volatilité typique des stratégies** (revue de création du comité) mesurée sur un panier d'ETF représentatif.
- **Couvertures** : multiplicateur de volatilité (vol réalisée / VIX), choc de référence (5 % des pires rendements à 3 mois) et part couverte reliée à la probabilité historique d'une forte baisse (régression logistique).
- **Seuils d'alerte** choisis pour une fréquence cible par gravité.

Jamais de calibration sur données simulées. Seul un administrateur applique une calibration (enregistrée dans `hedge_fund_state`, utilisée aussi par le traitement planifié) ; bouton de retour aux hypothèses d'expert.

Lot 2 — Performance et suivi :
- **Options dans la NAV reconstituée** : prime à l'ouverture, valeur Black-Scholes quotidienne, valeur intrinsèque figée à l'échéance ; la comparaison avec le marché couvre donc tout le portefeuille.
- **Attribution de performance** (Dashboard) par classe d'actifs face à l'allocation stratégique du profil : effets allocation, sélection, interaction (Brinson-Fachler, lissage de Carino), options et négociation ; écart de suivi et ratio d'information.
- **Journal des écarts recommandation / exécution** (onglet Journal) : chaque plan exécuté (Hedge Fund Agent, optimisation du comité, Auto-Portefeuille) est comparé ligne par ligne aux ordres réellement passés (bloqués, partiels, cash), puis à la composition actuelle (dérive).
- **Backtest walk-forward du desk** (onglet Calibration & Backtest) : desk complet vs allocation stratégique vs stratégique + moteur de risque, par régime et par année, coûts inclus.

Lot 3 — Actualité et fiabilité :
- **Tonalité des titres** (lexique financier français / anglais inspiré de Loughran-McDonald, négations, sens des mots « hausse / baisse » selon ce qui monte) : tonalité par thème, par titre et **par classe d'actifs** dans le Briefing ; reprise dans les alertes d'actualité.
- **Contrôle continu des données** (utils/data_quality.py) : séries simulées, cotations anciennes, cours figés, sauts suspects, valeurs nulles, trous, veille indisponible. Exécuté chaque jour ouvré par le traitement planifié (alerte « Données » si problème) et à la demande dans Administration → 🩺 Qualité des données.
- **Tests automatisés** (dossier `tests/`, 60 tests sans réseau ni base) : conformité, comité, risque, calibration, performance et attribution, backtest, journal des écarts, sentiment, qualité des données, secteurs, fumée des pages. Lancement : `python -m pytest -q` ; sur GitHub : workflow `.github/workflows/tests.yml` à chaque envoi de code.

Nouveautés v5.3 — Comité d'investissement virtuel
🧑‍⚖️ Six professionnels VIRTUELS (personnages fictifs) examinent chaque portefeuille (utils/committee.py) :
   🌦️ Jean-Michel TAUX-BAS — Économiste en chef (inspiration Ray Dalio : cycles, diversification par régimes)
   🧮 Mc Henson ALGO-RITHME — Recherche quantitative (inspiration Jim Simons : signaux validés hors échantillon)
   🏛️ Thierry BALANCEMENT — Gérant principal / CIO (inspiration Buffett, Graham, Bogle : marge de sécurité, frais bas)
   🛡️ Aline DE MARGE — Directrice des risques (méthodes de John Hull, Howard Marks) — droit de veto
   ⚖️ Constance Probité — Conformité (MiFID II, AMF, UCITS, MiCA) — droit de veto
   🎙️ Marc ETING-FINANCIER — Relation client (inspiration Peter Lynch) — synthèse et recommandations
📋 Politique d'investissement (IPS) par portefeuille : objectif, horizon, perte maximale acceptable, réaction
   à une baisse, liquidité, part du patrimoine, expérience, ESG, exclusions, enveloppe (ETF US / UCITS / PEA /
   assurance-vie), couvertures. La contrainte la plus prudente fixe le profil ; volatilité cible = perte max / 1,645.
✅ Validation BLOQUANTE par le comité à la création d'un portefeuille (assistant en 5 étapes), au Hedge Fund
   Agent, à l'Auto-Portefeuille et au bouton Optimiser ; CONSULTATIVE pour les ordres manuels du Trading Desk
   (règle P01). Badge « à valider / validé / refusé » sur chaque portefeuille.
📈 Optimizer → « Optimisation par le comité » : correction automatique du portefeuille (régime → allocation
   sous contraintes IPS → choix des lignes par les signaux → contrôle VaR / ES → couvertures → conformité),
   bandes de tolérance, tableau avant / après, avis du comité, exécution en un clic après confirmation.
🛡️ Risques selon John Hull (utils/risk_hull.py) : VaR 99 % 1 j / 10 j (historique et paramétrique), Expected
   Shortfall 97,5 %, volatilité EWMA λ = 0,94, contributions d'Euler, backtesting de Kupiec, stress tests et
   stress test inversé, grecques des options.
📄 Rapport du comité (utils/committee_report.py) : PNG une page (graphique vs indice, avis de chaque
   professionnel, synthèse et recommandations, décisions à prendre) + PDF détaillé ; page Rapports et
   e-mail du lundi (GitHub Actions) pour chaque portefeuille suivi.
🌦️ Régime de marché unifié : le régime à 8 facteurs du comité est OFFICIEL (allocations, couvertures,
   stratégies d'options) ; le mélange gaussien d'IA Marchés sert de contrôle croisé.
🖱️ Ergonomie : bandeaux qui s'arrêtent au survol, barre d'onglets défilante, nouvelles équipes et
   comparaison des performances par équipe, mention légale en pied de page et dans les rapports uniquement.

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
git clone https://github.com/Datamack25/McKenson-Investment-Platform_5.git
cd McKenson-Investment-Platform_5/McKenson-Investment-Platform_v5/McKenson-Investment-Platform_2-main/mack_invest_platform

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
mack_invest_platform/      # McKenson Investment Platform (MIP)
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
│   ├── portfolio_upload.py # 📥 Conseil portefeuille : fichier importé analysé par le comité (v5.5)
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
│   ├── backtest_desk.py    # v5.4 backtest walk-forward du desk complet
│   ├── calibration.py      # v5.4 calibration des hypothèses sur 10 ans d'historique
│   ├── execution_log.py    # v5.4 journal des écarts recommandation / exécution
│   ├── data_quality.py     # v5.4 contrôle continu des données
│   ├── upload_advisor.py   # v5.5 portefeuille importé : lecture, analyse, exports
│   ├── sentiment.py        # v5.4 tonalité des titres et pertinence par classe
│   ├── committee.py        # v5.3 comité virtuel, IPS, avis, validation, optimisation
│   ├── committee_report.py # v5.3 rapport du comité (PNG + PDF + e-mail)
│   ├── risk_hull.py        # v5.3 VaR, ES, EWMA, Euler, Kupiec, stress tests (J. Hull)
│   ├── hedging.py          # v5.2 couvertures par options proposées par le desk
│   ├── performance.py      # v5.2 NAV reconstituée, indicateurs de gestion, indices de référence
│   └── legal.py            # v5.1 auteur, version, avertissements (source unique)
└── components/
    ├── ai_shared.py        # chargement en cache du modèle, KPI, en-têtes des pages IA
    ├── calibration_ui.py   # v5.4 onglet Calibration du Hedge Fund Agent
    ├── committee_ui.py     # v5.3 cartes du comité, questionnaire IPS, panneau de validation
    ├── ui.py               # CSS theme, ticker strip, news banner
    └── webui.py            # Habillage page web : en-tête, onglets, bandeau compte, footer
Admin Password
Définir le mot de passe admin dans Streamlit Cloud → Settings → Secrets :
[admin]
password = "VotreMotDePasseAdmin"
(un compte avec role = 'admin' dans mam_users accède aussi directement au panneau).

Teams
Bears 🐻 | Bulls 🐂 | Whales 🐋 | Raptors 🦅 | Sharpas 🦈 | Strikers ⚡ | Wolves 🐺

© 2026 Mackenson CINEUS — McKenson Asset Management — v5.11.0 — plateforme de simulation pédagogique. Ne constitue pas un conseil en investissement ; l'auteur n'est pas responsable des décisions prises.
