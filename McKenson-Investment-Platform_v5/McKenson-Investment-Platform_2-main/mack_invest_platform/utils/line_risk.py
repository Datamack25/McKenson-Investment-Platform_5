# utils/line_risk.py  —  MAM v5.6 · Fiche de risques par ligne et thèse d'investissement
"""
Deux disciplines de gérant, sans interface :

1. FICHE DE RISQUES FONDAMENTAUX par ligne : pour chaque titre détenu, les risques
   propres à l'entreprise (taux, juridique, dette, change…), leur niveau et la façon
   dont l'entreprise les couvre. Pré-remplie selon le secteur, complétée par l'utilisateur.
   Stockée dans port["fiches_risque"][ticker].

2. THÈSE D'INVESTISSEMENT obligatoire avant chaque ordre manuel : pourquoi, quels
   dangers, ce qui ferait changer d'avis, horizon. Horodatée et rattachée à l'ordre
   (port["trades"][…]["these"]) : c'est le journal de décisions qui permet de montrer,
   des mois plus tard, quand et pourquoi chaque décision a été prise.
"""
from __future__ import annotations

from datetime import datetime

# ══════════════════════════════════════════════════════════════════════════════
#  1. FICHE DE RISQUES FONDAMENTAUX
# ══════════════════════════════════════════════════════════════════════════════
RISK_TYPES: dict[str, str] = {
    "taux": "Taux d'intérêt — une hausse des taux renchérit la dette et pèse sur la valorisation",
    "juridique": "Juridique et réglementaire — procès, amendes, changement de réglementation",
    "dette": "Endettement — capacité à rembourser et à refinancer sa dette",
    "clients": "Dépendance à quelques clients ou fournisseurs",
    "change": "Change — revenus ou coûts dans d'autres devises",
    "matieres": "Prix des matières premières et de l'énergie",
    "geopolitique": "Géopolitique — sanctions, conflits, droits de douane, chaînes d'approvisionnement",
    "valorisation": "Valorisation — le cours anticipe déjà beaucoup de croissance",
    "cycle": "Cycle économique — activité très sensible à la conjoncture",
    "technologie": "Rupture technologique — un concurrent ou une innovation rend le produit obsolète",
}
LEVELS = ["Faible", "Moyen", "Élevé"]
COVERAGE = ["Couvert", "Partiellement couvert", "Non couvert", "Inconnu"]

# Risques à examiner en priorité selon le secteur (pré-remplissage, que l'utilisateur ajuste)
SECTOR_RISKS: dict[str, list[str]] = {
    "Technologie": ["valorisation", "technologie", "geopolitique", "clients"],
    "Communication & médias": ["juridique", "valorisation", "technologie"],
    "Consommation discrétionnaire": ["cycle", "valorisation", "change"],
    "Consommation de base": ["matieres", "change", "taux"],
    "Finance": ["taux", "juridique", "cycle"],
    "Finance — paiements & fintech": ["juridique", "technologie", "valorisation"],
    "Finance — écosystème crypto": ["juridique", "valorisation", "cycle"],
    "Santé": ["juridique", "technologie", "clients"],
    "Énergie": ["matieres", "geopolitique", "juridique"],
    "Services publics": ["taux", "dette", "juridique"],
    "Industrie": ["cycle", "matieres", "geopolitique"],
    "Industrie — équipements électriques": ["cycle", "valorisation", "clients"],
    "Industrie — aéronautique & défense": ["geopolitique", "juridique", "clients"],
    "Immobilier": ["taux", "dette", "cycle"],
    "Matériaux": ["matieres", "cycle", "geopolitique"],
}


def _sector(ticker: str) -> str:
    try:
        from utils.sectors import sector_of
        return sector_of(ticker)
    except Exception:
        return "Actions — secteur non classé"


def needs_sheet(ticker: str) -> bool:
    """Une fiche de risques fondamentaux a du sens pour une action (pas pour un ETF large,
    une devise, un future ou un crypto-actif, dont le risque se lit au niveau du marché)."""
    s = _sector(ticker)
    return not s.startswith(("ETF", "ETC", "Dérivé", "Crypto", "Devises", "Indice"))


def suggested_risks(ticker: str) -> list[str]:
    s = _sector(ticker)
    for k, v in SECTOR_RISKS.items():
        if s == k:
            return list(v)
    for k, v in SECTOR_RISKS.items():
        if s.startswith(k):
            return list(v)
    return ["valorisation", "cycle", "juridique"]


def blank_sheet(ticker: str) -> dict:
    """Fiche pré-remplie (niveau Moyen, couverture Inconnue) à partir du secteur."""
    return dict(ticker=ticker, secteur=_sector(ticker), maj=None, auteur=None,
                risques={k: dict(niveau="Moyen", couverture="Inconnu", note="") for k in suggested_risks(ticker)},
                synthese="")


def get_sheet(port: dict, ticker: str) -> dict:
    return (port.get("fiches_risque") or {}).get(ticker) or blank_sheet(ticker)


def save_sheet(port: dict, ticker: str, sheet: dict, author: str | None = None) -> dict:
    sheet = dict(sheet)
    sheet["maj"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    if author:
        sheet["auteur"] = author
    port.setdefault("fiches_risque", {})[ticker] = sheet
    return sheet


def sheet_score(sheet: dict) -> dict:
    """Lecture synthétique : nombre de risques élevés, risques élevés non couverts, complétude."""
    r = (sheet or {}).get("risques") or {}
    eleves = [k for k, v in r.items() if v.get("niveau") == "Élevé"]
    non_couverts = [k for k in eleves if r[k].get("couverture") in ("Non couvert", "Inconnu")]
    inconnus = [k for k, v in r.items() if v.get("couverture") == "Inconnu"]
    complete = bool(sheet and sheet.get("maj")) and not inconnus
    return dict(n=len(r), eleves=eleves, non_couverts=non_couverts, inconnus=inconnus, complete=complete,
                alerte=bool(non_couverts))


def sheets_status(port: dict) -> dict:
    """État des fiches pour les lignes détenues qui en nécessitent une."""
    hold = [t for t, h in (port.get("holdings") or {}).items() if (h or {}).get("qty", 0) > 0 and needs_sheet(t)]
    fiches = port.get("fiches_risque") or {}
    manquantes = [t for t in hold if t not in fiches or not fiches[t].get("maj")]
    alertes = [t for t in hold if t in fiches and sheet_score(fiches[t])["alerte"]]
    return dict(lignes=hold, manquantes=manquantes, alertes=alertes,
                completes=[t for t in hold if t in fiches and sheet_score(fiches[t])["complete"]])


def sheet_text(sheet: dict) -> list[str]:
    """Phrases simples décrivant une fiche (rapports)."""
    out = []
    for k, v in ((sheet or {}).get("risques") or {}).items():
        lab = RISK_TYPES.get(k, k).split(" — ")[0]
        txt = f"{lab} : risque {v.get('niveau', 'Moyen').lower()}, {v.get('couverture', 'Inconnu').lower()}"
        if v.get("note"):
            txt += f" ({v['note']})"
        out.append(txt + ".")
    if sheet and sheet.get("synthese"):
        out.append(sheet["synthese"])
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  2. THÈSE D'INVESTISSEMENT AVANT CHAQUE ORDRE MANUEL
# ══════════════════════════════════════════════════════════════════════════════
THESIS_FIELDS = {
    "pourquoi": "Pourquoi cet ordre ? (ce que vous attendez et sur quoi vous vous appuyez)",
    "risques": "Quels sont les dangers ? (ce qui peut mal tourner)",
    "invalidation": "Qu'est-ce qui vous ferait changer d'avis ? (facultatif)",
}
HORIZONS = ["Quelques jours", "1 à 4 semaines", "1 à 3 mois", "3 à 12 mois", "Plus d'un an"]
MIN_CHARS = 20


def validate_thesis(th: dict | None) -> tuple[bool, list[str]]:
    """La raison et les dangers sont obligatoires (au moins 20 caractères chacun)."""
    th = th or {}
    missing = []
    if len(str(th.get("pourquoi", "")).strip()) < MIN_CHARS:
        missing.append(f"la raison de l'ordre (au moins {MIN_CHARS} caractères)")
    if len(str(th.get("risques", "")).strip()) < MIN_CHARS:
        missing.append(f"les dangers identifiés (au moins {MIN_CHARS} caractères)")
    if th.get("horizon") not in HORIZONS:
        missing.append("l'horizon de la position")
    return (not missing), missing


def stamp_thesis(th: dict, author: str | None = None) -> dict:
    out = {k: str(th.get(k, "")).strip() for k in ("pourquoi", "risques", "invalidation")}
    out["horizon"] = th.get("horizon")
    out["date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if author:
        out["auteur"] = author
    return out


def decision_journal(port: dict, start: str | None = None, end: str | None = None) -> list[dict]:
    """Ordres de la période avec leur thèse (ou la source automatique qui les a décidés)."""
    out = []
    for t in port.get("trades", []) or []:
        d = str(t.get("date", ""))[:10]
        if (start and d < start) or (end and d > end):
            continue
        out.append(dict(date=t.get("date", ""), ticker=t.get("ticker", ""), action=t.get("action", ""),
                        montant=float(t.get("total", 0) or 0), source=t.get("source", "") or "Trading Desk",
                        these=t.get("these")))
    return out


def manual_orders_without_thesis(port: dict) -> int:
    return sum(1 for t in port.get("trades", []) or []
               if (t.get("source") or "") == "Trading Desk" and not t.get("these"))
