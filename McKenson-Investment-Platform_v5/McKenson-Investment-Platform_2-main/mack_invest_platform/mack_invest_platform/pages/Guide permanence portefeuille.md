# Guide de persistance — MAM sur Streamlit Cloud

## Pourquoi le portefeuille disparaît

Streamlit Cloud redémarre l'application périodiquement (inactivité, nuit, weekend).
Le fichier `game_state.json` est sur le **filesystem éphémère** → effacé à chaque redémarrage.

## Solution : Streamlit Secrets

Les Streamlit Secrets sont **permanents** (stockés côté Streamlit Cloud, pas sur le filesystem).
On encode l'état JSON en base64 compressé et on le stocke dans les secrets.

## Étapes pour activer la persistance permanente

### Étape 1 — Aller dans Admin Panel de la plateforme
Dans la plateforme MAM → menu "Admin Panel"
Vous verrez un encadré **"💾 SAUVEGARDE PERMANENTE"** avec une clé encodée.

### Étape 2 — Copier la clé dans Streamlit Secrets
1. Allez sur https://share.streamlit.io
2. Cliquez sur votre app → ⋮ → Settings → Secrets
3. Collez exactement ceci dans l'éditeur :

```toml
game_state_b64 = "VOTRE_CLÉ_COPIÉE_DEPUIS_ADMIN"
```

4. Cliquez "Save" → l'app redémarre automatiquement

### Étape 3 — Vérification
Après redémarrage, vos portefeuilles sont rechargés depuis les Secrets.
Désormais, même si l'app redémarre le weekend, vos données sont préservées.

## Workflow de mise à jour

Chaque fois que vous faites un trade ou créez un portefeuille :
1. La plateforme sauvegarde dans `game_state.json` (local, temporaire)
2. ET génère une nouvelle clé base64 dans Admin Panel

**Bonne pratique** : après chaque session de trading importante,
allez dans Admin Panel et mettez à jour la clé dans les Secrets Streamlit.

## Alternative : fichier dans le repo GitHub

Si vous avez accès au repo GitHub, vous pouvez :
1. Récupérer `data/game_state.json` depuis Admin Panel
2. Le commiter dans le repo → il sera rechargé au prochain démarrage

Note : cette méthode ne fonctionne que si le fichier est dans le repo et
que Streamlit Cloud a accès au repo privé.
