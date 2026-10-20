# utils/sectors.py  —  MAM v5.3.1 · Secteur de chaque actif (colonne « Secteur » des tableaux)
"""
sector_of(ticker)         → secteur d'un actif au comptant (action, ETF, crypto, matière première…)
option_sector(o)          → « Option PUT sur Technologie / Nasdaq (QQQ) »
Les contrats à terme (=F) sont présentés comme des dérivés : « Dérivé — future sur … ».
Classification GICS simplifiée pour les actions ; secteur ou exposition principale pour les ETF.
"""
from __future__ import annotations

_EQUITY = {
    # Technologie
    **dict.fromkeys(["AAPL", "MSFT", "NVDA", "AMD", "INTC", "QCOM", "AVGO", "CRM", "ORCL", "IBM", "ASML.AS",
                     "SAP.DE", "STMPA.PA", "TCS.NS", "005930.KS", "000660.KS", "6758.T"], "Technologie"),
    # Communication / médias / internet
    **dict.fromkeys(["GOOGL", "GOOG", "META", "NFLX", "DIS", "T", "VZ", "CMCSA", "0700.HK", "9432.T",
                     "9984.T", "7974.T"], "Communication & médias"),
    # Consommation discrétionnaire
    **dict.fromkeys(["AMZN", "TSLA", "MCD", "SBUX", "NKE", "MC.PA", "7203.T", "3690.HK", "9988.HK"],
                    "Consommation discrétionnaire"),
    # Consommation de base
    **dict.fromkeys(["WMT", "COST", "PG", "KO", "PEP", "OR.PA", "NESN.SW"], "Consommation de base"),
    # Finance
    **dict.fromkeys(["BRK-B", "JPM", "BAC", "GS", "MS", "C", "WFC", "AXP", "BLK", "BNP.PA", "CS.PA", "ALV.DE",
                     "MUV2.DE", "UBSG.SW", "HSBA.L", "UCG.MI", "SAN.MC", "1299.HK"], "Finance"),
    # Paiements / fintech
    **dict.fromkeys(["V", "MA", "PYPL", "SQ", "HOOD"], "Finance — paiements & fintech"),
    **dict.fromkeys(["COIN", "MSTR"], "Finance — écosystème crypto"),
    # Santé
    **dict.fromkeys(["UNH", "JNJ", "PFE", "ABBV", "LLY", "MRK", "SAN.PA", "ROG.SW", "NOVN.SW", "AZN.L"], "Santé"),
    # Énergie
    **dict.fromkeys(["XOM", "CVX", "COP", "TTE.PA", "BP.L", "SHEL.L", "ENI.MI", "RELIANCE.NS"], "Énergie"),
    # Services publics
    **dict.fromkeys(["NEE", "DUK", "ENEL.MI", "IBE.MC"], "Services publics"),
    # Industrie / défense
    **dict.fromkeys(["CAT", "GE", "MMM", "HON", "SIE.DE", "ADANIENT.NS"], "Industrie"),
    **dict.fromkeys(["BA", "LMT", "RTX", "AIR.PA", "RHM.DE"], "Industrie — aéronautique & défense"),
    # Immobilier / matériaux
    **dict.fromkeys(["SPG", "AMT", "PLD"], "Immobilier"),
    **dict.fromkeys(["RIO.L"], "Matériaux"),
}

_ETF = {
    "SPY": "ETF — actions US diversifiées (S&P 500)", "VOO": "ETF — actions US diversifiées (S&P 500)",
    "CSPX.L": "ETF — actions US diversifiées (S&P 500)", "SXR8.DE": "ETF — actions US diversifiées (S&P 500)",
    "VTI": "ETF — marché actions US total", "IWM": "ETF — petites capitalisations US",
    "QQQ": "ETF — Technologie / Nasdaq 100", "PANX.PA": "ETF — Technologie / Nasdaq 100",
    "XLK": "ETF sectoriel — Technologie", "SOXX": "ETF sectoriel — Semi-conducteurs",
    "XLV": "ETF sectoriel — Santé", "XLF": "ETF sectoriel — Finance", "XLE": "ETF sectoriel — Énergie",
    "XLU": "ETF sectoriel — Services publics", "XLI": "ETF sectoriel — Industrie",
    "XLP": "ETF sectoriel — Consommation de base", "XLY": "ETF sectoriel — Consommation discrétionnaire",
    "XLB": "ETF sectoriel — Matériaux", "XLRE": "ETF sectoriel — Immobilier", "VNQ": "ETF — Immobilier coté US",
    "ITA": "ETF sectoriel — Aéronautique & défense", "ICLN": "ETF thématique — Énergies propres",
    "ARKK": "ETF thématique — Innovation", "SCHD": "ETF — actions US à dividendes",
    "VIG": "ETF — actions US à dividendes", "VYM": "ETF — actions US à dividendes",
    "USMV": "ETF — actions US faible volatilité", "QUAL": "ETF — actions US qualité", "ESGU": "ETF — actions US ESG",
    "VGK": "ETF — actions Europe diversifiées", "EFA": "ETF — actions pays développés hors US",
    "VEA": "ETF — actions pays développés hors US", "VXUS": "ETF — actions internationales hors US",
    "EWG": "ETF — actions Allemagne", "EWJ": "ETF — actions Japon", "FXI": "ETF — actions Chine",
    "EWZ": "ETF — actions Brésil", "EWY": "ETF — actions Corée du Sud",
    "EEM": "ETF — actions émergentes", "VWO": "ETF — actions émergentes", "IEMG": "ETF — actions émergentes",
    "EIMI.L": "ETF — actions émergentes", "PAEEM.PA": "ETF — actions émergentes",
    "IWDA.AS": "ETF — actions monde développé", "EUNL.DE": "ETF — actions monde développé",
    "XDWD.DE": "ETF — actions monde développé", "CW8.PA": "ETF — actions monde développé",
    "EWLD.PA": "ETF — actions monde développé", "SUSW.L": "ETF — actions monde ISR",
    "VWCE.DE": "ETF — actions monde (développés + émergents)", "VT": "ETF — actions monde",
    "ACWI": "ETF — actions monde", "IUSN.DE": "ETF — petites capitalisations monde",
    "C40.PA": "ETF — actions France (CAC 40)", "EXS1.DE": "ETF — actions Allemagne (DAX)",
    "TLT": "ETF — obligations d'État US 20 ans +", "IEF": "ETF — obligations d'État US 7-10 ans",
    "SHY": "ETF — obligations d'État US 1-3 ans", "IBTS.L": "ETF — obligations d'État US 1-3 ans",
    "GOVT": "ETF — obligations d'État US", "TIP": "ETF — obligations indexées sur l'inflation",
    "BND": "ETF — obligations US diversifiées", "AGG": "ETF — obligations US diversifiées",
    "BNDX": "ETF — obligations internationales", "MBB": "ETF — obligations hypothécaires US",
    "LQD": "ETF — obligations d'entreprises (Investment Grade)", "IEAC.L": "ETF — obligations d'entreprises € (IG)",
    "HYG": "ETF — obligations à haut rendement (High Yield)", "EMB": "ETF — dette émergente",
    "BIL": "ETF — monétaire (T-Bills)", "SGOV": "ETF — monétaire (T-Bills)", "XEON.DE": "ETF — monétaire € (€STR)",
    "GLD": "ETF — or", "IAU": "ETF — or", "SGLD.L": "ETC — or physique", "SLV": "ETF — argent",
    "USO": "ETF — pétrole (WTI)", "UNG": "ETF — gaz naturel", "DBC": "ETF — panier matières premières",
    "PDBC": "ETF — panier matières premières", "DBA": "ETF — matières premières agricoles",
    "DBB": "ETF — métaux industriels",
}

_COMMODITY = {
    "GC=F": "or", "SI=F": "argent", "PL=F": "platine", "PA=F": "palladium", "HG=F": "cuivre", "ALI=F": "aluminium",
    "CL=F": "pétrole WTI", "MCL=F": "pétrole WTI (micro)", "BZ=F": "pétrole Brent", "NG=F": "gaz naturel",
    "HO=F": "fioul", "RB=F": "essence", "ZW=F": "blé", "ZC=F": "maïs", "ZS=F": "soja", "ZO=F": "avoine",
    "KC=F": "café", "SB=F": "sucre", "CT=F": "coton", "CC=F": "cacao", "LBS=F": "bois", "GF=F": "bovins",
    "LE=F": "bovins", "HE=F": "porcs",
}
_INDEX_FUT = {
    "ES=F": "indice S&P 500", "NQ=F": "indice Nasdaq 100", "YM=F": "indice Dow Jones", "RTY=F": "indice Russell 2000",
    "NKD=F": "indice Nikkei 225", "ZB=F": "obligations d'État US 30 ans", "ZN=F": "obligations d'État US 10 ans",
    "ZF=F": "obligations d'État US 5 ans", "ZT=F": "obligations d'État US 2 ans", "BTC=F": "bitcoin",
    "MBT=F": "bitcoin (micro)", "ETH=F": "ether",
}
_INDEX = {"^GSPC": "S&P 500", "^DJI": "Dow Jones", "^NDX": "Nasdaq 100", "^IXIC": "Nasdaq", "^FCHI": "CAC 40",
          "^GDAXI": "DAX", "^FTSE": "FTSE 100", "^STOXX50E": "Euro Stoxx 50", "^N225": "Nikkei 225",
          "^HSI": "Hang Seng", "^VIX": "volatilité (VIX)"}


def sector_of(ticker: str) -> str:
    """Secteur (ou exposition principale) d'un actif au comptant."""
    t = str(ticker or "").upper().strip()
    if t in _EQUITY:
        return _EQUITY[t]
    if t in _ETF:
        return _ETF[t]
    if t in _INDEX_FUT:
        return f"Dérivé — future sur {_INDEX_FUT[t]}"
    if t in _COMMODITY:
        return f"Dérivé — future sur matière première ({_COMMODITY[t]})"
    if t.endswith("=F"):
        return "Dérivé — contrat à terme"
    if t.endswith(("-USD", "-EUR")):
        return "Crypto-actif"
    if t.endswith("=X"):
        return "Devises (change)"
    if t in _INDEX:
        return f"Indice — {_INDEX[t]}"
    try:  # ETF ajoutés ou classés dans les fichiers d'actifs
        from utils.etf_universe import etf_meta
        m = etf_meta(t)
        if m:
            return f"ETF — {m.get('zone', '') or m.get('classe_actif', '')}".rstrip(" —")
    except Exception:
        pass
    return "Actions — secteur non classé"


def short_sector(ticker: str) -> str:
    """Secteur sans le préfixe « ETF — » / « Dérivé — » (pour les libellés d'options)."""
    s = sector_of(ticker)
    for p in ("ETF sectoriel — ", "ETF thématique — ", "ETF — ", "ETC — ", "Dérivé — "):
        if s.startswith(p):
            return s[len(p):]
    return s


def option_sector(o: dict) -> str:
    """Libellé d'une position d'option : « Option PUT sur Technologie / Nasdaq 100 (QQQ) »."""
    typ = str(o.get("type", "")).upper()
    und = o.get("ticker", "")
    strat = o.get("strategy")
    txt = f"Option {typ} sur {short_sector(und)} ({und})"
    return f"{txt} · {strat}" if strat else txt
