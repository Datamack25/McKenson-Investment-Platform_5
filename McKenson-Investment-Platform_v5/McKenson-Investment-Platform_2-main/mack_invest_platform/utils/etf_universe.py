# utils/etf_universe.py  —  MAM v5.1 · Univers ETF pour les petits investisseurs
"""
Métadonnées des ETF (classe d'actifs, zone, frais, UCITS, PEA, diversification)
et portefeuilles modèles « tout ETF » par profil de risque.

* Les ETF eux-mêmes sont déclarés dans data/assets_etf.csv, chargé automatiquement
  par utils.data.load_assets() (tous les fichiers data/assets*.csv sont fusionnés).
* ETF_CLASS complète la classification des ETF déjà présents dans data/assets.csv,
  pour que l'analyse de risque et les contrôles de conformité ne les traitent pas
  tous comme des « actions US ».

Les frais (TER) sont indicatifs : ils doivent être vérifiés dans le document
d'informations clés (DIC PRIIPs) de chaque fonds.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

ETF_FILE = Path(__file__).parent.parent / "data" / "assets_etf.csv"

# Classe d'actifs (nomenclature du moteur de risque utils.advisor.CLASSES)
# pour les ETF déjà présents dans data/assets.csv
ETF_CLASS: dict[str, str] = {
    "SPY": "Actions US", "QQQ": "Actions US", "IWM": "Actions US", "ARKK": "Actions US",
    "XLE": "Actions US", "XLF": "Actions US", "XLK": "Actions US", "XLV": "Actions US",
    "XLI": "Actions US", "XLP": "Actions US", "XLY": "Actions US", "XLU": "Actions US",
    "XLB": "Actions US", "ITA": "Actions US",
    "XLRE": "Actions US", "VNQ": "Actions US",
    "EFA": "Actions Europe", "VGK": "Actions Europe", "EWG": "Actions Europe",
    "EEM": "Actions Asie & émergents", "EWJ": "Actions Asie & émergents",
    "FXI": "Actions Asie & émergents", "EWZ": "Actions Asie & émergents",
    "EWY": "Actions Asie & émergents",
    "TLT": "Oblig. long terme", "IEF": "Oblig. moyen terme", "SHY": "Oblig. moyen terme",
    "TIP": "Oblig. moyen terme", "MBB": "Oblig. moyen terme", "BNDX": "Oblig. moyen terme",
    "LQD": "Crédit IG", "HYG": "High yield", "EMB": "High yield",
    "GLD": "Or", "SLV": "Or",
    "USO": "Matières premières", "UNG": "Matières premières", "DBA": "Matières premières",
    "DBB": "Matières premières", "PDBC": "Matières premières", "DBC": "Matières premières",
    "BIL": "Liquidités",
}

# ETF larges et diversifiés déjà présents dans assets.csv (indices de plusieurs centaines de titres)
_BROAD_EXISTING = {"SPY", "IWM", "EFA", "VGK", "EEM", "TLT", "IEF", "SHY", "TIP", "MBB",
                   "BNDX", "LQD", "HYG", "EMB", "BIL", "DBC", "PDBC"}

# Correspondance vers les classes simplifiées de utils.market_intel
_TO_INTEL_CLASS = {
    "Actions US": "Actions", "Actions Europe": "Actions", "Actions Asie & émergents": "Actions",
    "Oblig. long terme": "Obligations", "Oblig. moyen terme": "Obligations",
    "Crédit IG": "Obligations", "High yield": "Obligations",
    "Or": "Or & métaux", "Matières premières": "Matières premières",
    "Crypto": "Crypto", "Liquidités": "Monétaire",
}


@lru_cache(maxsize=1)
def etf_table() -> pd.DataFrame:
    """Table des ETF ajoutés (data/assets_etf.csv)."""
    try:
        df = pd.read_csv(ETF_FILE)
        df["ticker"] = df["ticker"].astype(str).str.strip()
        return df.set_index("ticker", drop=False)
    except Exception:
        return pd.DataFrame(columns=["ticker", "name", "category", "contract_mult", "currency",
                                     "ter_pct", "classe_actif", "zone", "ucits", "pea",
                                     "diversifie", "description"]).set_index("ticker", drop=False)


def etf_meta(ticker: str) -> dict | None:
    """Fiche d'un ETF ajouté, ou None."""
    df = etf_table()
    if ticker in df.index:
        return df.loc[ticker].to_dict()
    return None


def etf_class(ticker: str) -> str | None:
    """Classe d'actifs (nomenclature utils.advisor) si le ticker est un ETF connu."""
    meta = etf_meta(ticker)
    if meta and isinstance(meta.get("classe_actif"), str):
        return meta["classe_actif"]
    return ETF_CLASS.get(ticker)


def intel_class(ticker: str) -> str | None:
    """Classe simplifiée (utils.market_intel.ASSET_CLASSES) si le ticker est un ETF connu."""
    c = etf_class(ticker)
    return _TO_INTEL_CLASS.get(c) if c else None


def is_broad_etf(ticker: str) -> bool:
    """ETF indiciel large et diversifié (plusieurs centaines de titres)."""
    meta = etf_meta(ticker)
    if meta:
        return str(meta.get("diversifie", "")).strip().lower() == "oui"
    return ticker in _BROAD_EXISTING


# ══════════════════════════════════════════════════════════════════════════════
#  PORTEFEUILLES MODÈLES 100 % ETF
# ══════════════════════════════════════════════════════════════════════════════
# Poids en fraction du capital investi. Chaque modèle respecte les limites de
# conformité du profil indiqué (voir utils.compliance).
ETF_MODELS: dict[str, dict] = {
    "Prudent — UCITS": {
        "profil": "Prudent",
        "idee": "Préserver le capital : majorité d'obligations et de monétaire, un quart d'actions mondiales.",
        "poids": {"IWDA.AS": 0.25, "IEAC.L": 0.25, "IBTS.L": 0.20, "XEON.DE": 0.20, "SGLD.L": 0.10},
    },
    "Équilibré — UCITS": {
        "profil": "Équilibré",
        "idee": "Le classique 60/40 modernisé : actions mondiales + émergents, obligations, or.",
        "poids": {"IWDA.AS": 0.45, "EIMI.L": 0.10, "IEAC.L": 0.20, "IBTS.L": 0.10,
                  "SGLD.L": 0.10, "XEON.DE": 0.05},
    },
    "Dynamique — UCITS": {
        "profil": "Dynamique",
        "idee": "Croissance à long terme : 80 % d'actions mondiales diversifiées.",
        "poids": {"IWDA.AS": 0.55, "EIMI.L": 0.15, "IUSN.DE": 0.10, "IEAC.L": 0.10,
                  "SGLD.L": 0.05, "XEON.DE": 0.05},
    },
    "100 % actions — UCITS": {
        "profil": "Agressif",
        "idee": "Horizon long (> 10 ans) : uniquement des actions, diversifiées par zones et tailles.",
        "poids": {"IWDA.AS": 0.60, "EIMI.L": 0.15, "IUSN.DE": 0.10, "PANX.PA": 0.10, "SGLD.L": 0.05},
    },
    "PEA 100 % éligible": {
        "profil": "Dynamique",
        "idee": "Pour une enveloppe PEA : uniquement des ETF éligibles (monde, émergents, France, Nasdaq).",
        "poids": {"EWLD.PA": 0.60, "PAEEM.PA": 0.15, "C40.PA": 0.15, "PANX.PA": 0.10},
    },
    "Trois fonds (US)": {
        "profil": "Équilibré",
        "idee": "La méthode « Bogleheads » : marché US total, international, obligations.",
        "poids": {"VTI": 0.45, "VXUS": 0.25, "BND": 0.25, "SGOV": 0.05},
    },
}


def model_summary(name: str) -> pd.DataFrame:
    """Composition d'un modèle avec ses métadonnées et frais pondérés."""
    model = ETF_MODELS[name]
    rows = []
    for t, w in model["poids"].items():
        meta = etf_meta(t) or {}
        rows.append({
            "ETF": t,
            "Nom": meta.get("name", t),
            "Poids": w,
            "Classe": etf_class(t) or "—",
            "Zone": meta.get("zone", "—"),
            "Frais (TER)": float(meta.get("ter_pct", 0) or 0) / 100,
            "UCITS": meta.get("ucits", "—"),
            "PEA": meta.get("pea", "—"),
        })
    return pd.DataFrame(rows)


def model_ter(name: str) -> float:
    """Frais courants pondérés du modèle (fraction annuelle)."""
    df = model_summary(name)
    return float((df["Poids"] * df["Frais (TER)"]).sum())
