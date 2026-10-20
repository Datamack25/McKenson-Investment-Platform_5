# utils/data_quality.py  —  MAM v5.4 · Contrôle continu de la qualité des données
"""
Vérifie chaque jour (traitement planifié) et à la demande (Administration) que les
données qui alimentent le desk sont exploitables :

Cours (Yahoo Finance)
* série remplacée par du simulé (source indisponible)             → important / critique
* dernière cotation trop ancienne par rapport aux autres séries     → important
* cours figé (5 dernières valeurs identiques)                      → info
* saut suspect récent (> 8 écarts-types et > 25 % en une séance)   → important
* cours nul ou négatif                                             → critique
* trous dans l'historique récent (> 20 % de valeurs manquantes)    → info
Actualité (Google News)
* veille simulée (flux indisponibles)                              → important
* thème sans aucun titre                                           → info

Le résultat est enregistré (hedge_fund_state, clé « data_quality ») et, s'il contient
un problème important ou critique, transformé en alerte « Données ».
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

CRITICAL = {"SPY", "^VIX", "^TNX", "^IRX"}
RANK = {"critique": 3, "important": 2, "info": 1}
STATE_KEY = "data_quality"


def _issue(serie, probleme, gravite, detail):
    return dict(serie=serie, probleme=probleme, gravite=gravite, detail=detail)


def check_prices(px: pd.DataFrame, missing: list | None = None, tickers=None) -> list[dict]:
    missing = set(missing or [])
    out = []
    if px is None or px.empty:
        return [_issue("Toutes", "Aucune donnée de marché", "critique", "Le téléchargement n'a rien renvoyé.")]
    tickers = list(tickers or px.columns)
    ref_end = px.dropna(how="all").index.max()
    for t in tickers:
        if t in missing or t not in px.columns:
            out.append(_issue(t, "Source indisponible (repli simulé)", "critique" if t in CRITICAL else "important",
                              "Série remplacée par des valeurs simulées : exécution bloquée et convictions abaissées."))
            continue
        s = px[t].dropna()
        if s.empty:
            out.append(_issue(t, "Série vide", "important", "Aucune cotation valide."))
            continue
        lag = len(pd.bdate_range(s.index.max(), ref_end)) - 1
        if lag > 3 and not t.endswith("-USD"):
            out.append(_issue(t, "Cotation ancienne", "important",
                              f"Dernier cours le {s.index.max():%d/%m/%Y}, {lag} séances de retard sur les autres séries."))
        if (s <= 0).any() and not t.startswith("^"):
            out.append(_issue(t, "Cours nul ou négatif", "critique", f"{int((s <= 0).sum())} valeur(s) ≤ 0."))
            continue
        tail = s.tail(5)
        if len(tail) == 5 and tail.nunique() == 1 and t not in ("BIL", "SGOV", "^IRX"):
            out.append(_issue(t, "Cours figé", "info", f"Cinq dernières valeurs identiques ({tail.iloc[-1]:.4g})."))
        if len(s) > 60 and not t.startswith("^"):
            r = np.log(s).diff().dropna()
            sd = r.iloc[:-10].tail(250).std()
            recent = r.tail(10)
            bad = recent[(recent.abs() > 8 * sd) & (recent.abs() > 0.25)] if sd and np.isfinite(sd) else recent.iloc[:0]
            for d, v in bad.items():
                out.append(_issue(t, "Saut suspect", "important",
                                  f"{np.expm1(v):+.0%} le {d:%d/%m/%Y} ({abs(v) / sd:.0f} écarts-types) : erreur de "
                                  "données, division d'action ou événement réel à vérifier."))
        win = px[t].loc[px.index >= ref_end - pd.Timedelta(days=90)]
        if len(win) and win.isna().mean() > 0.20 and not t.endswith("-USD"):
            out.append(_issue(t, "Trous dans l'historique", "info", f"{win.isna().mean():.0%} de valeurs manquantes sur 3 mois."))
    return out


def check_news(news: dict, news_sim: bool) -> list[dict]:
    if news_sim:
        return [_issue("Actualité", "Veille simulée", "important",
                       "Les flux Google News n'ont pas répondu : intensités simulées, aucune alerte d'actualité.")]
    out = []
    empty = [th.get("label", k) for k, th in (news or {}).items() if not th.get("count")]
    if empty:
        out.append(_issue("Actualité", "Thèmes sans titre", "info", ", ".join(empty) + "."))
    return out


def run_checks(px, missing, news, news_sim, tickers=None) -> dict:
    issues = check_prices(px, missing, tickers) + check_news(news, news_sim)
    worst = max((RANK[i["gravite"]] for i in issues), default=0)
    status = {0: "OK", 1: "OK (remarques)", 2: "À SURVEILLER", 3: "PROBLÈME"}[worst]
    n_series = len(tickers or (px.columns if px is not None else []))
    return dict(date=datetime.now().strftime("%Y-%m-%d %H:%M"), statut=status, gravite_max=worst,
                n_series=int(n_series), n_problemes=len(issues), problemes=issues)


def to_alert(report: dict) -> dict | None:
    """Alerte « Données » si un problème important ou critique est détecté."""
    if report.get("gravite_max", 0) < 2:
        return None
    from utils.alerts import _alert
    top = [i for i in report["problemes"] if RANK[i["gravite"]] >= 2]
    sev = "critique" if report["gravite_max"] >= 3 else "important"
    return _alert("donnees", "qualite", sev, "Données", "baisse",
                  f"Qualité des données : {len(top)} problème(s) — " + ", ".join(sorted({i['serie'] for i in top})[:5]),
                  "Des données erronées ou manquantes faussent les facteurs, le régime, les alertes et la "
                  "valorisation : " + " ; ".join(f"{i['serie']} : {i['probleme'].lower()}" for i in top[:4]) + ".",
                  "Recommandations moins fiables tant que le problème persiste (le repli simulé bloque l'exécution).",
                  "Vérifier la source (Yahoo Finance / Google News) ; le contrôle est refait chaque jour ouvré.")


def save(report: dict) -> bool:
    try:
        from utils.alerts import set_state
        return bool(set_state(STATE_KEY, report))
    except Exception:
        return False


def last() -> dict | None:
    try:
        from utils.alerts import get_state
        return get_state(STATE_KEY)
    except Exception:
        return None
