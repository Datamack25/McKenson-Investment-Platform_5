# CLAUDE.md — McKenson Investment Platform (MIP / MAM)

Instructions lues au début de chaque session de travail sur ce dépôt. À mettre à jour quand une règle change.

## Le projet
- Plateforme **Streamlit** éducative de simulation d'investissement : portefeuilles, trading, optimiseur, options,
  comité de gestion virtuel, Analyse Marché, rapports PDF / e-mail, classement d'équipes. Base : Supabase / PostgreSQL.
- Nom : **McKenson Investment Platform** (MIP) / **MAM — McKenson Asset Management**. Jamais « ESLSCA platform ».
- Version dans `utils/legal.py` (`APP_VERSION`, `APP_RELEASE`) et en tête du `README.md` : les incrémenter ensemble.
- Lancer les tests : `python -m pytest -q` (tous hors réseau ; Yahoo Finance n'est jamais appelé dans les tests).

## Règles de livraison
- Modifier le code et livrer les fichiers. **Ne jamais pousser ni publier sur GitHub** (la propriétaire s'en charge).
- Ne pas refondre : renforcer l'existant, garder le style visuel (fond sombre, Rajdhani / Share Tech Mono, cyan #00d4ff).
- Les améliorations inspirées de projets ou d'articles externes ne mentionnent pas leur origine dans la plateforme.

## Textes et présentation
- Mention « Plateforme éducative créée par Mackenson CINEUS, diplômé d'un MBA Finance de marché » + version + absence
  de responsabilité : **uniquement en pied de page et sur les rapports**, pas partout.
- Le **Dashboard** reste léger : les tableaux supplémentaires vont dans les autres onglets.
- Rapports : une **synthèse en langage simple** (sur / sous-performance, actif ou stratégie en cause) ; ne jamais
  supposer que l'investisseur comprend le jargon.
- Rien n'est exécuté automatiquement : toute proposition (remédiation, plan, couverture) est « à valider ».
- Interface et textes en français.

## Comité de gestion (noms fictifs, à garder tels quels)
Jean-Michel TAUX-BAS (économiste, macro & régimes) · Mc Henson ALGO-RITHME (quant, signaux & ML) ·
Thierry BALANCEMENT (gérant, ordres & stratégie) · Aline DE MARGE (risque, garde-fou & limites) ·
Marc ETING-FINANCIER (CPM, reporting, biais, autocritique) · Constance Probité (conformité).
Chaque portefeuille est validé par le comité (IPS) : bloquant à la création et pour « Optimiser », consultatif au Trading Desk.

## Données de marché — règles impératives
- **Tout téléchargement de cours passe par `utils/prices.py`** (`download_closes`, `extract_closes`).
- **Jamais de `ffill()` sur un tableau mêlant des calendriers différents** (indices US, pétrole / dollar quasi continus,
  bitcoin le week-end) avant de calculer une variation : c'est la cause des faux « +0,0 % » de la v5.11.
  Pour une variation : `prices.change(serie, n)` (deux clôtures réelles). Pour un tableau valorisé :
  `prices.drop_sparse_rows(px).ffill()`.
- Une donnée manquante s'affiche **« indisponible »** (`prices.fmt_pct`), jamais 0 %. Afficher la date de la séance.
- Yahoo Finance gratuit ≈ 15 min de différé en intraday : le dire à l'écran.

## Cœur paramétrable (Admin → Paramètres financiers)
- Seuils, fenêtres, plafonds, formules, scénarios, catalyseurs, lignes figées, compositions des indices :
  **`utils/core_params.py`** (46 paramètres bornés, onglets dans `components/core_params_ui.py`).
  Lire une valeur avec `core_params.get("cle")` — ne pas recoder un seuil en dur dans un module.
- Nouveau paramètre = une entrée dans `PARAMS` (défaut, bornes, groupe, libellé) ; il apparaît seul dans l'admin.
- Formules évaluées par `safe_eval` (aucun `eval`). Chaque modification est historisée ; les rapports signalent
  les paramètres personnalisés (`custom_note()`).

## Carte des modules principaux
- `utils/market_drivers.py` : Analyse Marché (facteurs, technique, rotation, carte de chaleur, social, PDF).
- `utils/scenarios.py` : scénarios probabilisés, sensibilités, remédiation, diagnostic des options, grosse perte.
- `utils/am_process.py` : stress des scénarios sur le portefeuille, plan par phases, lignes figées, autocritique,
  état du processus d'investissement.
- `utils/intraday.py` : prix et sentiment sur 1 h / 6 h.
- `utils/committee.py`, `utils/committee_report.py` : comité, IPS, rapport hebdomadaire (PDF + e-mail).
- `components/market_committee_ui.py`, `components/core_params_ui.py` : écrans correspondants.
- `jobs/weekly_report.py` : job GitHub Actions du lundi (envoi depuis l'adresse personnelle de la propriétaire).

## Décisions récentes
- v5.12 (nov. 2026) : « IA Marchés » → « Analyse Marché » ; fin des faux 0,0 % ; scénarios ; admin paramètres.
- v5.13 (nov. 2026) : processus de gestion (stress, plan par phases, lignes figées, autocritique) ; tous les
  téléchargements de cours unifiés sur `utils/prices.py` ; ce fichier.
- Pistes non traitées : fiscalité par enveloppe (PEA / CTO / assurance-vie) dans les plans ; double authentification.
