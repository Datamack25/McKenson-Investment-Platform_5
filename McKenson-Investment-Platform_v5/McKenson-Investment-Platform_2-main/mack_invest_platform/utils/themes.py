# utils/themes.py  —  MAM v5.6 · Paniers thématiques et chaînes de valeur
"""
Une thèse d'investissement se raisonne souvent par CHAÎNE DE VALEUR plutôt que par
classe d'actifs : investir dans les intrants d'une tendance (énergie, réseau
électrique, semi-conducteurs, matériaux) plutôt que dans le produit fini.

Ce module :
* décrit des paniers thématiques découpés en segments (THEMES) ;
* mesure l'exposition d'un portefeuille à chaque thème et à chaque segment ;
* signale quand plusieurs lignes, en apparence diversifiées (secteurs différents),
  dépendent en réalité du même moteur — et donc du même risque (bulle, retournement).

Sans interface : utilisé par le comité, le Trading Desk et les rapports.
"""
from __future__ import annotations

THEMES: dict[str, dict] = {
    "Infrastructure de l'IA — les intrants": dict(
        emoji="🔌",
        idee=("Investir dans ce dont l'intelligence artificielle a besoin pour fonctionner (électricité, réseau, "
              "puces, matériaux) plutôt que dans les applications elles-mêmes : ces entreprises ont aussi des "
              "débouchés hors de l'IA, ce qui amortit une éventuelle bulle."),
        moteur_commun="la croissance des investissements dans les centres de données",
        risque_commun=("un ralentissement brutal des dépenses d'investissement dans l'IA toucherait en même temps "
                       "tous les segments, même s'ils appartiennent à des secteurs différents"),
        segments={
            "Production d'électricité": ["NEE", "DUK", "CEG", "ENEL.MI", "IBE.MC", "XLU", "ICLN"],
            "Énergies conventionnelles": ["XOM", "CVX", "COP", "TTE.PA", "XLE"],
            "Réseau électrique et équipements": ["ETN", "VRT", "SU.PA", "SIE.DE", "GE", "HON"],
            "Semi-conducteurs (fabrication et outillage)": ["TSM", "AMAT", "ASML.AS", "STMPA.PA", "SOXX", "INTC"],
            "Matériaux (cuivre, acier, silicium)": ["FCX", "NUE", "RIO.L", "HG=F", "DBB"],
        },
        seuil_alerte=0.35,
    ),
    "Intelligence artificielle — les applications": dict(
        emoji="🤖",
        idee="Les entreprises qui vendent des puces, des logiciels ou des services d'IA au client final.",
        moteur_commun="l'adoption de l'IA par les entreprises et les particuliers",
        risque_commun=("des valorisations élevées qui anticipent beaucoup de croissance : une déception sur les "
                       "résultats peut faire baisser tout le groupe"),
        segments={
            "Puces d'IA": ["NVDA", "AMD", "AVGO", "QCOM", "000660.KS", "005930.KS"],
            "Plateformes et nuage": ["MSFT", "GOOGL", "AMZN", "META", "ORCL"],
            "Logiciels": ["CRM", "SAP.DE", "IBM"],
            "ETF technologiques": ["QQQ", "XLK", "ARKK"],
        },
        seuil_alerte=0.35,
    ),
    "Transition énergétique": dict(
        emoji="🌱",
        idee="Production d'énergie bas carbone, réseaux et métaux de l'électrification.",
        moteur_commun="les politiques publiques de décarbonation et le prix de l'électricité",
        risque_commun="des taux d'intérêt élevés (projets très financés par la dette) et des subventions révisables",
        segments={
            "Production renouvelable et nucléaire": ["NEE", "CEG", "ENEL.MI", "IBE.MC", "ICLN"],
            "Réseaux et électrification": ["ETN", "SU.PA", "SIE.DE"],
            "Métaux de l'électrification": ["FCX", "HG=F", "RIO.L"],
        },
        seuil_alerte=0.35,
    ),
    "Défense et souveraineté": dict(
        emoji="🛡️",
        idee="Équipementiers de défense et d'aéronautique portés par la hausse des budgets militaires.",
        moteur_commun="les budgets de défense des États",
        risque_commun="une désescalade géopolitique ou une révision des budgets publics",
        segments={
            "Défense": ["LMT", "RTX", "RHM.DE", "ITA"],
            "Aéronautique": ["AIR.PA", "BA", "GE"],
        },
        seuil_alerte=0.30,
    ),
}


def ticker_themes(ticker: str) -> list[tuple[str, str]]:
    """[(thème, segment)] auxquels appartient un actif."""
    t = str(ticker or "").upper()
    out = []
    for name, th in THEMES.items():
        for seg, tickers in th["segments"].items():
            if t in {x.upper() for x in tickers}:
                out.append((name, seg))
    return out


def theme_exposure(values: dict[str, float], nav: float | None = None) -> list[dict]:
    """Exposition du portefeuille à chaque thème (part de l'actif net), triée par poids décroissant.
    values : {ticker: valeur}. Un actif présent dans deux segments du même thème n'est compté qu'une fois."""
    vals = {str(t).upper(): float(v) for t, v in (values or {}).items() if v and float(v) > 0}
    nav = float(nav) if nav else sum(vals.values())
    if nav <= 0:
        return []
    out = []
    for name, th in THEMES.items():
        segs, lines = {}, {}
        for seg, tickers in th["segments"].items():
            w = 0.0
            for t in {x.upper() for x in tickers}:
                if t in vals:
                    w += vals[t] / nav
                    lines[t] = vals[t] / nav
            if w > 0:
                segs[seg] = w
        total = sum(lines.values())
        if total <= 0:
            continue
        alerte = total > th["seuil_alerte"]
        out.append(dict(theme=name, emoji=th["emoji"], poids=total, segments=segs, lignes=lines,
                        n_segments=len(segs), alerte=alerte, seuil=th["seuil_alerte"],
                        moteur=th["moteur_commun"], risque=th["risque_commun"],
                        texte=_sentence(name, th, total, segs, alerte)))
    return sorted(out, key=lambda d: -d["poids"])


def _sentence(name: str, th: dict, total: float, segs: dict, alerte: bool) -> str:
    seg_txt = ", ".join(f"{s.lower()} {w:.0%}" for s, w in sorted(segs.items(), key=lambda kv: -kv[1]))
    base = f"{total:.0%} du portefeuille dépend du thème « {name} » ({seg_txt})."
    if alerte:
        base += (f" C'est au-delà de {th['seuil_alerte']:.0%} : ces lignes paraissent diversifiées, mais elles "
                 f"dépendent toutes de {th['moteur_commun']} — {th['risque_commun']}.")
    return base


def theme_universe(name: str) -> list[str]:
    """Tous les actifs d'un thème (sans doublon, dans l'ordre des segments)."""
    seen, out = set(), []
    for tickers in THEMES.get(name, {}).get("segments", {}).values():
        for t in tickers:
            if t not in seen:
                seen.add(t)
                out.append(t)
    return out
