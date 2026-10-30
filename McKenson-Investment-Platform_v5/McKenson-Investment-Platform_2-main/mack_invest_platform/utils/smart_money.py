# utils/smart_money.py  —  MAM v5.11 · « 🐋 Tracking Best AM » : où investissent les meilleurs gérants
"""
Suivi des positions déclarées par les grands investisseurs dans leurs formulaires 13F (SEC) et
comparaison avec les portefeuilles MIP.

SOURCE OFFICIELLE ET GRATUITE — SEC EDGAR (les mêmes données que Dataroma, WhaleWisdom ou TIKR) :
  • data.sec.gov/submissions/CIK##########.json  → liste des dépôts 13F-HR d'un gérant ;
  • www.sec.gov/Archives/edgar/data/<cik>/<n° de dépôt>/index.json → fichier « information table » (XML) ;
  • www.sec.gov/files/company_tickers.json        → correspondance émetteur → ticker → n° CIK ;
  • data.sec.gov/submissions/CIK<société>.json     → code SIC de la société → secteur ;
  • api.openfigi.com (facultatif)                  → CUSIP → ticker pour les émetteurs non reconnus.
La SEC demande un « User-Agent » avec une adresse de contact : secret `[sec] user_agent = "Nom adresse@mail"`
(à défaut : variable d'environnement SEC_USER_AGENT, puis l'adresse e-mail de la plateforme).

LIMITES (rappelées dans chaque écran et chaque rapport) : un 13F ne montre que les actions américaines
détenues à l'achat (pas de ventes à découvert, d'obligations, de liquidités ni d'actifs hors États-Unis),
publié jusqu'à 45 jours après la fin du trimestre, sans prix d'achat ni raison de l'investissement.

Module sans interface : utilisé par l'onglet « Tracking Best AM », le sous-onglet de « Conseil portefeuille »,
les rapports (PDF) et les tests (hors réseau, via parse_infotable / build_from_holdings / parse_import).
"""
from __future__ import annotations

import gzip
import io
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

SM_VERSION = "1.0"
CACHE_DIR = Path(__file__).parent.parent / "data" / "smart_money"
SNAPSHOT_FILE = CACHE_DIR / "snapshot.json"
CUSIP_FILE = CACHE_DIR / "cusip_map.json"
SIC_FILE = CACHE_DIR / "sic_cache.json"

LIMITS_TEXT = (
    "Les formulaires 13F ne montrent que les actions cotées aux États-Unis détenues à l'achat par les gérants "
    "de plus de 100 M$ : pas de ventes à découvert, d'obligations, de liquidités, d'actifs non américains ni de "
    "prix d'achat. Ils sont publiés jusqu'à 45 jours après la fin du trimestre : une position a pu être vendue "
    "depuis. Ce sont des pistes de recherche à vérifier (valorisation, thèse), jamais des ordres à copier.")

# ══════════════════════════════════════════════════════════════════════════════
#  GÉRANTS SUIVIS (n° CIK SEC ; le nom est revérifié à chaque chargement)
# ══════════════════════════════════════════════════════════════════════════════
STYLES = {
    "value": "Value & long terme",
    "macro": "Macro & activistes",
    "growth": "Croissance & tech",
    "quant": "Quantitatifs & multi-gérants",
    "mega": "Grandes sociétés de gestion",
}
MANAGERS = [
    # Value & long terme
    dict(code="BRK", cik=1067983, manager="Warren Buffett", fund="Berkshire Hathaway", style="value", key="BERKSHIRE"),
    dict(code="PSC", cik=1336528, manager="Bill Ackman", fund="Pershing Square", style="value", key="PERSHING"),
    dict(code="BAUPOST", cik=1061768, manager="Seth Klarman", fund="Baupost Group", style="value", key="BAUPOST"),
    dict(code="HIMALAYA", cik=1709323, manager="Li Lu", fund="Himalaya Capital", style="value", key="HIMALAYA"),
    dict(code="AKRE", cik=1112520, manager="Chuck Akre", fund="Akre Capital", style="value", key="AKRE"),
    dict(code="FUNDSMITH", cik=1569205, manager="Terry Smith", fund="Fundsmith", style="value", key="FUNDSMITH"),
    dict(code="DODGE", cik=200217, manager="Équipe Dodge & Cox", fund="Dodge & Cox", style="value", key="DODGE"),
    dict(code="OAKMARK", cik=813917, manager="Bill Nygren", fund="Harris Associates (Oakmark)", style="value", key="HARRIS"),
    dict(code="OAKTREE", cik=949509, manager="Howard Marks", fund="Oaktree Capital", style="value", key="OAKTREE"),
    dict(code="FIRSTEAGLE", cik=1325447, manager="First Eagle", fund="First Eagle Investment", style="value", key="FIRST EAGLE"),
    dict(code="TCI", cik=1647251, manager="Chris Hohn", fund="TCI Fund Management", style="value", key="TCI"),
    dict(code="GREENLIGHT", cik=1079114, manager="David Einhorn", fund="Greenlight / DME Capital", style="value", key="CAPITAL"),
    # Macro & activistes
    dict(code="DUQUESNE", cik=1536411, manager="Stanley Druckenmiller", fund="Duquesne Family Office", style="macro", key="DUQUESNE"),
    dict(code="APPALOOSA", cik=1656456, manager="David Tepper", fund="Appaloosa", style="macro", key="APPALOOSA"),
    dict(code="THIRDPOINT", cik=1040273, manager="Daniel Loeb", fund="Third Point", style="macro", key="THIRD POINT"),
    dict(code="SCION", cik=1649339, manager="Michael Burry", fund="Scion Asset Management", style="macro", key="SCION"),
    dict(code="BRIDGEWATER", cik=1350694, manager="Ray Dalio", fund="Bridgewater Associates", style="macro", key="BRIDGEWATER"),
    dict(code="SOROS", cik=1029160, manager="George Soros", fund="Soros Fund Management", style="macro", key="SOROS"),
    dict(code="TUDOR", cik=923093, manager="Paul Tudor Jones", fund="Tudor Investment", style="macro", key="TUDOR"),
    dict(code="ICAHN", cik=921669, manager="Carl Icahn", fund="Icahn Capital", style="macro", key="ICAHN"),
    dict(code="ELLIOTT", cik=1791786, manager="Paul Singer", fund="Elliott Investment Management", style="macro", key="ELLIOTT"),
    # Croissance & tech
    dict(code="VIKING", cik=1103804, manager="Andreas Halvorsen", fund="Viking Global", style="growth", key="VIKING"),
    dict(code="LONEPINE", cik=1061165, manager="Stephen Mandel", fund="Lone Pine Capital", style="growth", key="LONE PINE"),
    dict(code="COATUE", cik=1135730, manager="Philippe Laffont", fund="Coatue Management", style="growth", key="COATUE"),
    dict(code="TIGER", cik=1167483, manager="Chase Coleman", fund="Tiger Global", style="growth", key="TIGER"),
    dict(code="D1", cik=1747057, manager="Daniel Sundheim", fund="D1 Capital Partners", style="growth", key="D1 CAPITAL"),
    dict(code="ARK", cik=1697748, manager="Cathie Wood", fund="ARK Investment Management", style="growth", key="ARK"),
    dict(code="BAILLIE", cik=1088875, manager="Baillie Gifford", fund="Baillie Gifford & Co", style="growth", key="BAILLIE"),
    # Quantitatifs & multi-gérants
    dict(code="RENTECH", cik=1037389, manager="Renaissance (Jim Simons)", fund="Renaissance Technologies", style="quant", key="RENAISSANCE"),
    dict(code="TWOSIGMA", cik=1179392, manager="Two Sigma", fund="Two Sigma Investments", style="quant", key="TWO SIGMA"),
    dict(code="DESHAW", cik=1009207, manager="D. E. Shaw", fund="D. E. Shaw & Co", style="quant", key="SHAW"),
    dict(code="AQR", cik=1167557, manager="Cliff Asness", fund="AQR Capital", style="quant", key="AQR"),
    dict(code="CITADEL", cik=1423053, manager="Ken Griffin", fund="Citadel Advisors", style="quant", key="CITADEL"),
    dict(code="POINT72", cik=1603466, manager="Steve Cohen", fund="Point72", style="quant", key="POINT72"),
    dict(code="MILLENNIUM", cik=1273087, manager="Israel Englander", fund="Millennium Management", style="quant", key="MILLENNIUM"),
    # Grandes sociétés de gestion (fichiers très volumineux : chargement lent)
    dict(code="NORGES", cik=1374170, manager="Fonds souverain norvégien", fund="Norges Bank", style="mega", key="NORGES"),
    dict(code="CAPWORLD", cik=1422848, manager="Capital Group", fund="Capital Research Global Investors", style="mega", key="CAPITAL RESEARCH"),
    dict(code="TROWE", cik=80255, manager="T. Rowe Price", fund="T. Rowe Price Associates", style="mega", key="ROWE"),
    dict(code="AMUNDI", cik=1330387, manager="Amundi", fund="Amundi", style="mega", key="AMUNDI"),
    dict(code="BNPAM", cik=1520354, manager="BNP Paribas AM", fund="BNP Paribas Asset Management", style="mega", key="BNP"),
    dict(code="FIDELITY", cik=315066, manager="Fidelity", fund="FMR LLC", style="mega", key="FMR"),
]
MANAGER = {m["code"]: m for m in MANAGERS}
DEFAULT_CODES = ["BRK", "PSC", "BAUPOST", "HIMALAYA", "AKRE", "FUNDSMITH", "DODGE", "TCI", "DUQUESNE", "APPALOOSA",
                 "THIRDPOINT", "SCION", "VIKING", "LONEPINE", "COATUE", "TIGER"]
PRESETS = {
    "⭐ Sélection MIP (16 gérants de référence)": DEFAULT_CODES,
    "🏛️ Value & long terme": [m["code"] for m in MANAGERS if m["style"] == "value"],
    "🌍 Macro & activistes": [m["code"] for m in MANAGERS if m["style"] == "macro"],
    "🚀 Croissance & tech": [m["code"] for m in MANAGERS if m["style"] == "growth"],
    "🧮 Quantitatifs & multi-gérants": [m["code"] for m in MANAGERS if m["style"] == "quant"],
    "🏦 Grandes sociétés de gestion (lent)": [m["code"] for m in MANAGERS if m["style"] == "mega"],
}

# ══════════════════════════════════════════════════════════════════════════════
#  PLATEFORMES À SUIVRE
# ══════════════════════════════════════════════════════════════════════════════
PLATFORMS = [
    dict(nom="Dataroma", url="https://www.dataroma.com/m/home.php", gratuit=True,
         quoi="Portefeuilles d'environ 80 « superinvestisseurs » value (Buffett, Klarman, Li Lu…).",
         regarder="« Grand Portfolio » (positions les plus partagées), « Top buys » du trimestre, activité de chaque "
                  "gérant (ajouts, réductions), et les achats d'initiés."),
    dict(nom="WhaleWisdom", url="https://whalewisdom.com/", gratuit=True,
         quoi="Tous les dépôts 13F (plus de 5 000 gérants) avec historique, cartes de chaleur et « WhaleScore ».",
         regarder="Positions nouvelles et soldées, évolution sur plusieurs trimestres, gérants les plus performants "
                  "(WhaleScore), filtres par secteur."),
    dict(nom="TIKR", url="https://www.tikr.com/", gratuit=False,
         quoi="Suivi des « gurus » avec données financières et valorisations dans le même outil.",
         regarder="Positions ≥ 5 % du portefeuille, nouvelles entrées directement dans le top 10, achats groupés "
                  "de plusieurs gérants, puis vérification de la valorisation (méthode en 5 étapes)."),
    dict(nom="SEC EDGAR", url="https://www.sec.gov/edgar/search/", gratuit=True,
         quoi="Source officielle : formulaires 13F-HR originaux (utilisés par MIP).",
         regarder="Le fichier « information table » de chaque dépôt ; les 13D/13G (franchissements de 5 %) qui "
                  "arrivent plus vite que les 13F."),
    dict(nom="HedgeFollow", url="https://hedgefollow.com/", gratuit=True,
         quoi="Classements de hedge funds, positions et achats d'initiés.",
         regarder="Meilleurs gérants sur 3 ans, actions les plus achetées par les hedge funds."),
    dict(nom="13f.info", url="https://13f.info/", gratuit=True,
         quoi="Lecture rapide et comparaison des dépôts 13F trimestre par trimestre.",
         regarder="Comparaison entre deux trimestres d'un même gérant."),
    dict(nom="GuruFocus", url="https://www.gurufocus.com/guru/list", gratuit=False,
         quoi="Portefeuilles de gurus, valorisations, consensus des gérants.",
         regarder="« Guru Consensus », tendances sectorielles des gurus."),
    dict(nom="OpenInsider", url="http://openinsider.com/", gratuit=True,
         quoi="Achats et ventes des dirigeants (formulaires 4) : publiés en 2 jours ouvrés.",
         regarder="Achats groupés de plusieurs dirigeants d'une même société."),
    dict(nom="AMF — BDIF", url="https://bdif.amf-france.org/", gratuit=True,
         quoi="Pour la France : franchissements de seuils et déclarations des dirigeants.",
         regarder="Déclarations de franchissement de seuil (5 %, 10 %…) sur les sociétés françaises."),
]

# ══════════════════════════════════════════════════════════════════════════════
#  SECTEURS
# ══════════════════════════════════════════════════════════════════════════════
SECTORS = ["Technologie", "Communication & médias", "Consommation discrétionnaire", "Consommation de base",
           "Finance", "Santé", "Énergie", "Industrie", "Matériaux", "Services publics", "Immobilier",
           "ETF & fonds indiciels", "Non classé"]
CYCLICAL = {"Technologie", "Communication & médias", "Consommation discrétionnaire", "Finance", "Énergie",
            "Industrie", "Matériaux"}
DEFENSIVE = {"Consommation de base", "Santé", "Services publics", "Immobilier"}
SECTOR_ETF = {"Technologie": "XLK", "Communication & médias": "XLC", "Consommation discrétionnaire": "XLY",
              "Consommation de base": "XLP", "Finance": "XLF", "Santé": "XLV", "Énergie": "XLE",
              "Industrie": "XLI", "Matériaux": "XLB", "Services publics": "XLU", "Immobilier": "XLRE"}
SECTOR_COLORS = {"Technologie": "#00d4ff", "Communication & médias": "#7c3aed", "Consommation discrétionnaire": "#ff8c00",
                 "Consommation de base": "#a3e635", "Finance": "#ffd700", "Santé": "#00ff88", "Énergie": "#ff3b6b",
                 "Industrie": "#38bdf8", "Matériaux": "#c084fc", "Services publics": "#94a3b8",
                 "Immobilier": "#f472b6", "ETF & fonds indiciels": "#64748b", "Non classé": "#334155"}

# Lecture du régime officiel du comité (Jean-Michel TAUX-BAS) : secteurs favorisés / pénalisés
REGIME_SECTORS = {
    "Expansion désinflationniste": ({"Technologie", "Consommation discrétionnaire", "Communication & médias",
                                     "Industrie", "Finance"}, {"Services publics", "Consommation de base"}),
    "Surchauffe / reflation": ({"Énergie", "Matériaux", "Finance", "Industrie"},
                               {"Technologie", "Services publics", "Immobilier"}),
    "Ralentissement désinflationniste": ({"Santé", "Consommation de base", "Services publics", "Technologie"},
                                         {"Énergie", "Matériaux", "Finance"}),
    "Stagflation": ({"Énergie", "Matériaux", "Consommation de base", "Santé"},
                    {"Consommation discrétionnaire", "Technologie", "Immobilier"}),
    "Aversion au risque": ({"Consommation de base", "Santé", "Services publics"},
                           {"Consommation discrétionnaire", "Finance", "Technologie", "Matériaux"}),
}

# Classification GICS (simplifiée) des titres les plus détenus dans les 13F — évite des appels réseau
_HINTS: dict[str, str] = {}
for _sec, _tks in {
    "Technologie": "ADBE NOW INTU PANW CRWD FTNT SNOW PLTR ADSK WDAY TEAM DDOG NET ZS MDB SHOP TXN MU LRCX KLAC ADI "
                   "MRVL NXPI ON MCHP CDNS SNPS ANET CSCO DELL HPQ HPE SMCI APP ACN IT CTSH ARM ASML SAP CRM ORCL "
                   "IBM AAPL MSFT NVDA AMD INTC QCOM AVGO TSM AMAT",
    "Communication & médias": "GOOGL GOOG META NFLX DIS T VZ CMCSA CHTR TMUS SPOT TTWO EA LYV WBD FOXA NWSA OMC PINS "
                              "SNAP RDDT MTCH",
    "Consommation discrétionnaire": "AMZN TSLA MCD SBUX NKE HD LOW BKNG ABNB CMG HLT MAR QSR TJX ROST ORLY AZO MELI "
                                    "PDD BABA JD CPNG GM F RIVN LULU DECK YUM DPZ DRI RCL CCL NCLH EBAY ETSY DASH "
                                    "CVNA POOL SONY",
    "Consommation de base": "WMT COST PG KO PEP PM MO MDLZ CL KMB GIS KHC HSY STZ KDP MNST TGT DG DLTR KR SYY ADM "
                            "EL BUD DEO UL KVUE",
    "Finance": "BRK-B BRK-A JPM BAC GS MS C WFC AXP BLK V MA PYPL SQ XYZ HOOD COIN SCHW BK USB PNC COF ALLY CB AIG "
               "PGR TRV MKL MCO SPGI ICE CME NDAQ MSCI KKR BX APO ARES AON MMC AJG BRO NU SOFI JEF LPLA IBKR FI FIS "
               "GPN BN BAM",
    "Santé": "UNH JNJ PFE ABBV LLY MRK ELV CI HUM CVS TMO DHR ABT ISRG BSX MDT SYK BDX ZTS REGN VRTX GILD AMGN BMY "
             "MCK COR CAH HCA DVA IQV A BIIB MRNA NVO",
    "Énergie": "XOM CVX COP OXY SLB HAL EOG DVN FANG MPC PSX VLO KMI WMB OKE ET EPD CNQ SU CVE TPL LNG",
    "Industrie": "UBER UNP CSX NSC UPS FDX DE PH ITW EMR WM RSG GD NOC LHX HII TDG HEI GE GEV CARR OTIS URI PWR "
                 "CTAS ADP PAYX FERG JCI TT AME ROK CPRT ODFL DAL UAL LUV AAL FAST CAT MMM HON BA LMT RTX ETN VRT",
    "Matériaux": "LIN APD SHW ECL DD DOW NEM VMC MLM CRH ALB CF MOS IP BALL PPG FCX NUE",
    "Services publics": "NEE DUK SO D AEP EXC SRE PCG XEL ED PEG VST NRG AES CEG",
    "Immobilier": "EQIX O PSA CCI DLR WELL VICI CBRE CSGP AVB EQR INVH SPG AMT PLD HHH",
}.items():
    for _t in _tks.split():
        _HINTS[_t] = _sec


def canonical_sector(label: str) -> str:
    """Ramène un libellé de secteur MIP (utils.sectors) à l'un des SECTORS."""
    s = str(label or "")
    for p in ("ETF sectoriel — ", "ETF thématique — "):
        if s.startswith(p):
            s = s[len(p):]
    low = s.lower()
    rules = [("semi-conducteurs", "Technologie"), ("innovation", "Technologie"), ("technologie", "Technologie"),
             ("communication", "Communication & médias"), ("discrétionnaire", "Consommation discrétionnaire"),
             ("consommation de base", "Consommation de base"), ("finance", "Finance"), ("santé", "Santé"),
             ("énergies propres", "Services publics"), ("énergie", "Énergie"), ("aéronautique", "Industrie"),
             ("industrie", "Industrie"), ("matériaux", "Matériaux"), ("services publics", "Services publics"),
             ("immobilier", "Immobilier")]
    if label and str(label).startswith(("ETF —", "ETC —")) and "immobilier" not in low and "technologie" not in low:
        return "ETF & fonds indiciels"
    for k, v in rules:
        if k in low:
            return v
    return "Non classé"


def sic_sector(sic) -> str:
    """Code SIC (SEC) → secteur (approximation GICS)."""
    try:
        c = int(sic)
    except Exception:
        return "Non classé"
    R = [((100, 999), "Consommation de base"), ((1000, 1099), "Matériaux"), ((1200, 1399), "Énergie"),
         ((1400, 1499), "Matériaux"), ((1531, 1531), "Consommation discrétionnaire"), ((1500, 1799), "Industrie"),
         ((2000, 2199), "Consommation de base"), ((2200, 2399), "Consommation discrétionnaire"),
         ((2400, 2499), "Matériaux"), ((2500, 2599), "Consommation discrétionnaire"), ((2600, 2699), "Matériaux"),
         ((2700, 2799), "Communication & médias"), ((2830, 2836), "Santé"), ((2840, 2844), "Consommation de base"),
         ((2800, 2899), "Matériaux"), ((2900, 2999), "Énergie"), ((3011, 3011), "Consommation discrétionnaire"),
         ((3000, 3099), "Matériaux"), ((3100, 3199), "Consommation discrétionnaire"), ((3200, 3399), "Matériaux"),
         ((3400, 3499), "Industrie"), ((3570, 3579), "Technologie"), ((3500, 3599), "Industrie"),
         ((3630, 3639), "Consommation discrétionnaire"), ((3651, 3652), "Consommation discrétionnaire"),
         ((3600, 3629), "Industrie"), ((3640, 3689), "Technologie"), ((3690, 3699), "Industrie"),
         ((3711, 3716), "Consommation discrétionnaire"), ((3714, 3714), "Consommation discrétionnaire"),
         ((3751, 3751), "Consommation discrétionnaire"), ((3700, 3799), "Industrie"), ((3812, 3812), "Industrie"),
         ((3820, 3829), "Technologie"), ((3840, 3851), "Santé"), ((3800, 3899), "Industrie"),
         ((3900, 3999), "Consommation discrétionnaire"), ((4000, 4799), "Industrie"),
         ((4800, 4899), "Communication & médias"), ((4900, 4999), "Services publics"), ((5122, 5122), "Santé"),
         ((5140, 5149), "Consommation de base"), ((5000, 5199), "Industrie"), ((5331, 5331), "Consommation de base"),
         ((5399, 5399), "Consommation de base"), ((5400, 5499), "Consommation de base"),
         ((5912, 5912), "Consommation de base"), ((5200, 5999), "Consommation discrétionnaire"),
         ((6500, 6599), "Immobilier"), ((6798, 6798), "Immobilier"), ((6000, 6799), "Finance"),
         ((7000, 7099), "Consommation discrétionnaire"), ((7200, 7299), "Consommation discrétionnaire"),
         ((7370, 7379), "Technologie"), ((7300, 7399), "Industrie"), ((7990, 7999), "Consommation discrétionnaire"),
         ((7800, 7999), "Communication & médias"), ((8000, 8099), "Santé"), ((8731, 8731), "Santé"),
         ((8000, 8999), "Industrie"), ((9995, 9995), "Finance")]
    for (a, b), s in R:      # les plages précises sont listées avant les plages larges
        if a <= c <= b:
            return s
    return "Non classé"


def _is_etf_name(issuer: str, cls: str = "") -> bool:
    u = f"{issuer} {cls}".upper()
    return bool(re.search(r"\b(ETF|SPDR|ISHARES|VANGUARD (INDEX|WORLD|SCOTTSDALE|ADMIRAL|SPECIALIZED|INTL)|"
                          r"INVESCO QQQ|SELECT SECTOR|PROSHARES|DIREXION|INDEX FD|INDEX FUND)\b", u))


def sector_for_ticker(ticker: str) -> str:
    """Secteur d'un titre détenu par MIP ou par un gérant (sans réseau)."""
    t = str(ticker or "").upper().strip()
    if t in _HINTS:
        return _HINTS[t]
    try:
        from utils.sectors import sector_of
        return canonical_sector(sector_of(t))
    except Exception:
        return "Non classé"


# ══════════════════════════════════════════════════════════════════════════════
#  ACCÈS RÉSEAU (SEC EDGAR, OpenFIGI) — poli : ≤ 9 requêtes / seconde, cache disque
# ══════════════════════════════════════════════════════════════════════════════
_LAST_CALL = [0.0]


def user_agent() -> str:
    v = os.environ.get("SEC_USER_AGENT")
    if v:
        return v
    try:
        import streamlit as st
        if "sec" in st.secrets and st.secrets["sec"].get("user_agent"):
            return str(st.secrets["sec"]["user_agent"])
        if "email" in st.secrets:
            e = st.secrets["email"]
            for k in ("sender", "user", "username", "address", "from"):
                if e.get(k) and "@" in str(e.get(k)):
                    return f"McKenson Investment Platform (education) {e.get(k)}"
    except Exception:
        pass
    return "McKenson Investment Platform (education) mip.education.platform@gmail.com"


def _http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 25) -> bytes:
    import urllib.request
    if "sec.gov" in url:
        wait = 0.115 - (time.time() - _LAST_CALL[0])
        if wait > 0:
            time.sleep(wait)
        _LAST_CALL[0] = time.time()
    h = {"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        if r.headers.get("Content-Encoding", "") == "gzip" or raw[:2] == b"\x1f\x8b":
            raw = gzip.decompress(raw)
    return raw


def _json_get(url: str) -> dict:
    return json.loads(_http(url).decode("utf-8", "replace"))


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, obj) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, default=str), encoding="utf-8")
    except Exception:
        pass


def list_13f_filings(cik: int) -> tuple[str, list[dict]]:
    """(nom de l'entité, dépôts 13F-HR triés du plus récent au plus ancien, un par trimestre)."""
    d = _json_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    rec = d.get("filings", {}).get("recent", {})
    rows = []
    for i, form in enumerate(rec.get("form", [])):
        if form != "13F-HR":
            continue
        rows.append(dict(accession=rec["accessionNumber"][i], filed=rec["filingDate"][i],
                         period=(rec.get("reportDate") or [""] * (i + 1))[i] or rec["filingDate"][i]))
    rows.sort(key=lambda r: (r["period"], r["filed"]), reverse=True)
    seen, out = set(), []
    for r in rows:                     # un seul dépôt par trimestre (le plus récent)
        if r["period"] not in seen:
            seen.add(r["period"])
            out.append(r)
    return str(d.get("name", "")), out


def fetch_infotable(cik: int, accession: str) -> bytes:
    acc = accession.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}"
    idx = _json_get(f"{base}/index.json")
    items = idx.get("directory", {}).get("item", [])
    xmls = [it for it in items if str(it.get("name", "")).lower().endswith(".xml")
            and "primary_doc" not in str(it.get("name", "")).lower()]
    if not xmls:
        raise ValueError("fichier « information table » introuvable dans le dépôt")
    best = max(xmls, key=lambda it: int(str(it.get("size", "0") or "0").strip() or 0))
    return _http(f"{base}/{best['name']}", timeout=60)


# ══════════════════════════════════════════════════════════════════════════════
#  LECTURE DU 13F
# ══════════════════════════════════════════════════════════════════════════════
def parse_infotable(xml: bytes | str, filed: str = "2024-01-01") -> pd.DataFrame:
    """XML « information table » → lignes (cusip, émetteur, catégorie, valeur $, nombre, put/call)."""
    from xml.etree import ElementTree as ET
    root = ET.fromstring(xml if isinstance(xml, bytes) else xml.encode("utf-8"))
    rows = []
    for el in root.iter():
        if el.tag.split("}")[-1] != "infoTable":
            continue
        f = {}
        for ch in el.iter():
            f[ch.tag.split("}")[-1]] = (ch.text or "").strip()
        try:
            val = float(f.get("value", "0").replace(",", "") or 0)
            sh = float(f.get("sshPrnamt", "0").replace(",", "") or 0)
        except ValueError:
            continue
        rows.append(dict(cusip=f.get("cusip", "").upper(), issuer=f.get("nameOfIssuer", ""),
                         cls=f.get("titleOfClass", ""), value=val, shares=sh, sh_type=f.get("sshPrnamtType", "SH"),
                         put_call=f.get("putCall", "").capitalize()))
    df = pd.DataFrame(rows, columns=["cusip", "issuer", "cls", "value", "shares", "sh_type", "put_call"])
    if df.empty:
        return df
    # Avant 2023 la valeur était déclarée en milliers de dollars
    eq = df[(df["put_call"] == "") & (df["shares"] > 0)]
    implied = (eq["value"] / eq["shares"]).median() if len(eq) else np.nan
    if str(filed) < "2023-01-03" or (np.isfinite(implied) and implied < 0.5):
        df["value"] *= 1000.0
    return df


def aggregate(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(positions actions au comptant agrégées par CUSIP, positions d'options agrégées)."""
    if df is None or df.empty:
        e = pd.DataFrame(columns=["cusip", "issuer", "cls", "value", "shares"])
        return e, pd.DataFrame(columns=["cusip", "issuer", "put_call", "value", "shares"])
    stock = df[(df["put_call"] == "") & (df["sh_type"].str.upper() != "PRN")]
    eq = (stock.groupby("cusip", as_index=False)
          .agg(issuer=("issuer", "first"), cls=("cls", "first"), value=("value", "sum"), shares=("shares", "sum")))
    opt = df[df["put_call"] != ""]
    op = (opt.groupby(["cusip", "put_call"], as_index=False)
          .agg(issuer=("issuer", "first"), value=("value", "sum"), shares=("shares", "sum")))
    return eq.sort_values("value", ascending=False).reset_index(drop=True), op


def compare_quarters(cur: pd.DataFrame, prev: pd.DataFrame | None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Ajoute poids, rang et mouvements (Nouvelle / Renforcée / Allégée / Inchangée) ; renvoie aussi les soldées."""
    cur = cur.copy()
    tot = float(cur["value"].sum()) or 1.0
    cur["weight"] = cur["value"] / tot
    cur["rank"] = np.arange(1, len(cur) + 1)
    if prev is None or prev.empty:
        cur["prev_shares"], cur["prev_weight"], cur["d_weight"] = np.nan, np.nan, np.nan
        cur["chg_shares"], cur["status"] = np.nan, "—"
        return cur, pd.DataFrame(columns=["cusip", "issuer", "prev_weight", "prev_value"])
    p = prev.copy()
    p["prev_weight"] = p["value"] / (float(p["value"].sum()) or 1.0)
    p = p.rename(columns={"shares": "prev_shares", "value": "prev_value"})
    m = cur.merge(p[["cusip", "prev_shares", "prev_value", "prev_weight"]], on="cusip", how="left")
    m["d_weight"] = m["weight"] - m["prev_weight"].fillna(0.0)
    m["chg_shares"] = np.where(m["prev_shares"] > 0, m["shares"] / m["prev_shares"] - 1, np.nan)
    m["status"] = np.select(
        [m["prev_shares"].isna() | (m["prev_shares"] <= 0), m["chg_shares"] > 0.02, m["chg_shares"] < -0.02],
        ["Nouvelle", "Renforcée", "Allégée"], "Inchangée")
    sold = p[~p["cusip"].isin(cur["cusip"])][["cusip", "issuer", "prev_weight", "prev_value"]]
    return m, sold.sort_values("prev_weight", ascending=False).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  CUSIP → TICKER → SECTEUR
# ══════════════════════════════════════════════════════════════════════════════
_SUFFIX = r"\b(INC|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|HOLDINGS?|HLDGS?|GROUP|GRP|CL|CLASS|COM|NEW|DEL|THE|SA|NV|" \
          r"N V|AG|SE|LP|L P|LLC|INCORPORATED|CAP STK|COMMON|STOCK|SHS|ORD|ADR|SPONSORED|SPON|A|B|C|TR|TRUST)\b"


def norm_name(s: str) -> str:
    s = re.sub(r"/[A-Z]{2,3}/?", " ", str(s).upper())
    s = re.sub(r"[^A-Z0-9 ]", " ", s.replace("&", " AND "))
    s = re.sub(_SUFFIX, " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _class_hint(cls: str) -> str:
    u = str(cls).upper()
    m = re.search(r"\b(?:CL(?:ASS)?|SER(?:IES)?)\s*([ABC])\b", u)
    return m.group(1) if m else ""


def load_company_tickers() -> dict:
    """{nom normalisé: [(ticker, cik), …]} depuis la SEC (cache disque 7 jours)."""
    path = CACHE_DIR / "company_tickers.json"
    try:
        if path.exists() and time.time() - path.stat().st_mtime < 7 * 86400:
            raw = json.loads(path.read_text(encoding="utf-8"))
        else:
            raw = _json_get("https://www.sec.gov/files/company_tickers.json")
            _save_json(path, raw)
    except Exception:
        raw = _load_json(path, {})
    out: dict[str, list] = {}
    for v in (raw.values() if isinstance(raw, dict) else raw):
        try:
            out.setdefault(norm_name(v["title"]), []).append((str(v["ticker"]).upper(), int(v["cik_str"])))
        except Exception:
            continue
    return out


def match_ticker(issuer: str, cls: str, names: dict) -> tuple[str, int | None]:
    n = norm_name(issuer)
    cands = names.get(n)
    if not cands:
        toks = n.split()
        if len(toks) >= 2:
            pref = " ".join(toks[:2])
            hits = [k for k in names if k.startswith(pref)]
            if len(hits) == 1:
                cands = names[hits[0]]
    if not cands:
        return "", None
    hint = _class_hint(cls)
    tick = [c for c in cands if "-" not in c[0] and "." not in c[0]] or cands
    if hint:
        for t, cik in cands:
            if t.endswith(f"-{hint}") or t.endswith(f".{hint}"):
                return t, cik
        if hint == "C":
            for t, cik in tick:
                if t == "GOOG":
                    return t, cik
    return tick[0][0], tick[0][1]


def openfigi_map(cusips: list[str]) -> dict[str, str]:
    """CUSIP → ticker via OpenFIGI (gratuit, 10 identifiants par requête ; clé facultative [openfigi] api_key)."""
    out: dict[str, str] = {}
    key = os.environ.get("OPENFIGI_KEY")
    try:
        import streamlit as st
        key = key or (st.secrets["openfigi"].get("api_key") if "openfigi" in st.secrets else None)
    except Exception:
        pass
    size = 100 if key else 10
    for i in range(0, len(cusips), size):
        chunk = cusips[i:i + size]
        body = json.dumps([{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in chunk]).encode()
        h = {"Content-Type": "application/json"}
        if key:
            h["X-OPENFIGI-APIKEY"] = key
        try:
            res = json.loads(_http("https://api.openfigi.com/v3/mapping", data=body, headers=h, timeout=20))
        except Exception:
            break
        for c, r in zip(chunk, res):
            d = (r or {}).get("data") or []
            if d and d[0].get("ticker"):
                out[c] = str(d[0]["ticker"]).upper().replace("/", "-").replace(" ", "-")
        time.sleep(0.25 if key else 2.5)
    return out


def resolve(snapshot: dict, use_network: bool = True, progress=None, max_sic: int = 400) -> None:
    """Complète ticker et secteur de chaque ligne (cache disque des correspondances)."""
    cmap = _load_json(CUSIP_FILE, {})
    sic = _load_json(SIC_FILE, {})
    rows = [h for m in snapshot["managers"].values() for h in m.get("holdings", []) + m.get("sold", [])]
    todo = {h["cusip"]: h for h in rows if h.get("cusip") and h["cusip"] not in cmap}
    names = load_company_tickers() if (todo and use_network) else {}
    weight = {}
    for h in rows:
        weight[h.get("cusip")] = max(weight.get(h.get("cusip"), 0), h.get("weight") or h.get("prev_weight") or 0)
    unmatched = []
    for c, h in todo.items():
        t, cik = match_ticker(h.get("issuer", ""), h.get("cls", ""), names) if names else ("", None)
        if t:
            cmap[c] = dict(ticker=t, cik=cik)
        elif weight.get(c, 0) >= 0.003:
            unmatched.append(c)
    if unmatched and use_network:
        unmatched = sorted(unmatched, key=lambda c: -weight.get(c, 0))[:120]
        for c, t in openfigi_map(unmatched).items():
            cmap[c] = dict(ticker=t, cik=None)
    _save_json(CUSIP_FILE, cmap)
    # Secteurs : indications internes → code SIC de la société (SEC) → nom d'ETF → « Non classé »
    need = []
    for h in rows:
        info = cmap.get(h.get("cusip"), {})
        h["ticker"] = h.get("ticker") or info.get("ticker", "")
        if h.get("sector") and h["sector"] != "Non classé":
            continue
        if h["ticker"] and h["ticker"] in _HINTS:
            h["sector"] = _HINTS[h["ticker"]]
        elif _is_etf_name(h.get("issuer", ""), h.get("cls", "")):
            known = canonical_sector(_sector_of(h["ticker"])) if h["ticker"] else "Non classé"
            h["sector"] = known if known not in ("Non classé",) else "ETF & fonds indiciels"
        elif info.get("cik") and str(info["cik"]) in sic:
            h["sector"] = sic_sector(sic[str(info["cik"])])
        else:
            h["sector"] = sector_for_ticker(h["ticker"]) if h["ticker"] else "Non classé"
            if h["sector"] == "Non classé" and info.get("cik"):
                need.append((weight.get(h["cusip"], 0), info["cik"], h))
    if need and use_network:
        need.sort(key=lambda x: -x[0])
        done = 0
        for _, cik, h in need:
            if str(cik) not in sic:
                if done >= max_sic:
                    continue
                try:
                    sic[str(cik)] = _json_get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json").get("sic", "")
                except Exception:
                    sic[str(cik)] = ""
                done += 1
                if progress and done % 10 == 0:
                    progress(f"Secteurs : {done} sociétés identifiées…")
            h["sector"] = sic_sector(sic.get(str(cik)))
        _save_json(SIC_FILE, sic)


def _sector_of(t: str) -> str:
    try:
        from utils.sectors import sector_of
        return sector_of(t)
    except Exception:
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  CONSTRUCTION DU « SNAPSHOT » (tous les gérants)
# ══════════════════════════════════════════════════════════════════════════════
def _records(df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty:
        return []
    return json.loads(df.replace({np.nan: None}).to_json(orient="records"))


def manager_entry(meta: dict, cur: pd.DataFrame, prev: pd.DataFrame | None, options: pd.DataFrame | None,
                  period: str, prev_period: str | None, filed: str, entity: str = "") -> dict:
    hold, sold = compare_quarters(cur, prev)
    opt = options if options is not None else pd.DataFrame()
    eq_val = float(cur["value"].sum()) if len(cur) else 0.0
    return dict(**{k: meta.get(k) for k in ("code", "cik", "manager", "fund", "style")}, entity=entity,
                period=period, prev_period=prev_period, filed=filed, total_value=eq_val, n_positions=int(len(cur)),
                options_value=float(opt["value"].sum()) if len(opt) else 0.0,
                options=_records(opt.head(30)) if len(opt) else [], holdings=_records(hold), sold=_records(sold.head(40)))


def build_snapshot(codes: list[str], custom: list[dict] | None = None, progress=None, align: bool = True,
                   history_quarters: int = 4) -> dict:
    """Télécharge les deux derniers 13F de chaque gérant (trimestre aligné sur la majorité) puis les enrichit."""
    metas = [MANAGER[c] for c in codes if c in MANAGER] + list(custom or [])
    say = progress or (lambda *_: None)
    filings, errors = {}, {}
    for i, m in enumerate(metas):
        say(f"Dépôts 13F : {m['fund']} ({i + 1}/{len(metas)})")
        try:
            entity, fl = list_13f_filings(m["cik"])
            key = str(m.get("key") or "").upper()
            if key and key not in entity.upper():
                errors[m["code"]] = f"le n° CIK {m['cik']} correspond à « {entity} » : à vérifier"
                continue
            if not fl:
                errors[m["code"]] = "aucun 13F-HR trouvé"
                continue
            filings[m["code"]] = (m, entity, fl)
        except Exception as e:
            errors[m["code"]] = f"SEC injoignable ({type(e).__name__})"
    target = None
    if align and len(filings) >= 3:
        latest = pd.Series([fl[0]["period"] for _, _, fl in filings.values()]).value_counts().sort_index(ascending=False)
        cum = latest.cumsum() / len(filings)
        target = next((p for p, v in cum.items() if v >= 0.6), latest.index[0])
    managers = {}
    for i, (code, (m, entity, fl)) in enumerate(filings.items()):
        say(f"Positions : {m['fund']} ({i + 1}/{len(filings)})")
        try:
            k = 0
            if target:
                k = next((j for j, f in enumerate(fl) if f["period"] <= target), 0)
            f0 = fl[k]
            cur_raw = parse_infotable(fetch_infotable(m["cik"], f0["accession"]), f0["filed"])
            cur, opt = aggregate(cur_raw)
            prev, f1 = None, (fl[k + 1] if len(fl) > k + 1 else None)
            past = []                              # trimestres précédents : « depuis quand » et « en quelle proportion »
            for j, fj in enumerate(fl[k + 1:k + max(2, int(history_quarters))]):
                try:
                    say(f"Historique : {m['fund']} — {quarter_label(fj['period'])}")
                    agg_j, _ = aggregate(parse_infotable(fetch_infotable(m["cik"], fj["accession"]), fj["filed"]))
                    past.append((fj["period"], agg_j))
                except Exception:
                    break
            if past and f1 and past[0][0] == f1["period"]:
                prev = past[0][1]
            managers[code] = manager_entry(m, cur, prev, opt, f0["period"], f1["period"] if f1 else None,
                                           f0["filed"], entity)
            managers[code]["history"] = compact_history([(f0["period"], cur)] + past)
            if k > 0:
                managers[code]["newer"] = fl[0]["period"]
        except Exception as e:
            errors[code] = f"lecture du 13F impossible ({type(e).__name__})"
    snap = dict(version=SM_VERSION, source="SEC EDGAR (13F-HR)", built_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                target_period=target, managers=managers, errors=errors)
    if managers:
        say("Identification des tickers et des secteurs…")
        try:
            resolve(snap, True, say)
        except Exception as e:
            snap["errors"]["_secteurs"] = f"identification partielle ({type(e).__name__})"
        try:     # v5.11 : les actifs des gérants alimentent l'univers MIP (data/assets_best_am.csv)
            snap["assets_sync"] = sync_assets(snap)
        except Exception as e:
            snap["errors"]["_univers"] = f"univers MIP non mis à jour ({type(e).__name__})"
    return snap


def build_from_holdings(rows: list[dict], source: str = "import") -> dict:
    """Snapshot à partir de lignes {code, manager, fund, style, ticker, issuer, sector, value|weight, status,
    period} — import CSV (export Dataroma / WhaleWisdom) et tests."""
    df = pd.DataFrame(rows)
    managers = {}
    for code, g in df.groupby("code", sort=False):
        g = g.copy()
        if "value" not in g or g["value"].isna().all():
            g["value"] = g["weight"].astype(float) * 1e6
        g["value"] = g["value"].astype(float)
        g["cusip"] = g.get("cusip", pd.Series([None] * len(g), index=g.index)).fillna(g["ticker"])
        g["issuer"] = g.get("issuer", g["ticker"]).fillna(g["ticker"]) if "issuer" in g else g["ticker"]
        g["cls"], g["shares"] = "", g["value"]
        g = g.sort_values("value", ascending=False).reset_index(drop=True)
        tot = float(g["value"].sum()) or 1.0
        g["weight"] = g["value"] / tot
        g["rank"] = np.arange(1, len(g) + 1)
        if "status" not in g:
            g["status"] = "—"
        g["status"] = g["status"].fillna("—").map(_status_fr)
        if "d_weight" not in g:
            g["d_weight"] = np.nan          # pas de trimestre précédent dans un import : pas de flux calculé
        g["prev_weight"] = g["weight"] - g["d_weight"]
        if "sector" not in g:
            g["sector"] = None
        g["sector"] = [s if isinstance(s, str) and s.strip() else sector_for_ticker(t) for s, t in zip(g["sector"], g["ticker"])]
        g["sector"] = [canonical_or(s) for s in g["sector"]]
        first = g.iloc[0]
        meta = MANAGER.get(code, {})
        managers[code] = dict(code=code, cik=meta.get("cik"), manager=str(first.get("manager") or meta.get("manager", code)),
                              fund=str(first.get("fund") or meta.get("fund", code)),
                              style=str(first.get("style") or meta.get("style", "value")), entity="",
                              period=str(first.get("period") or ""), prev_period=None, filed="",
                              total_value=tot, n_positions=int(len(g)), options_value=0.0, options=[],
                              holdings=_records(g[["cusip", "issuer", "cls", "ticker", "sector", "value", "shares",
                                                   "weight", "rank", "prev_weight", "d_weight", "status"]]),
                              sold=[])
    return dict(version=SM_VERSION, source=source, built_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
                target_period=None, managers=managers, errors={})


def canonical_or(s: str) -> str:
    return s if s in SECTORS else canonical_sector(s)


def _status_fr(s) -> str:
    u = str(s or "").strip().lower()
    if u in ("new", "nouvelle", "nouveau", "buy", "achat"):
        return "Nouvelle"
    if u.startswith(("add", "renf", "increase", "hausse")):
        return "Renforcée"
    if u.startswith(("reduce", "all", "trim", "decrease", "baisse")):
        return "Allégée"
    if u.startswith(("inch", "unch", "hold")):
        return "Inchangée"
    return "—"


# ── Import d'un fichier (repli si la SEC est injoignable) ───────────────────────
IMPORT_COLUMNS = [
    ("gerant", "obligatoire", "Nom du gérant ou du fonds", "Berkshire Hathaway"),
    ("ticker", "obligatoire", "Ticker de l'action", "AAPL"),
    ("poids", "obligatoire*", "Poids dans le portefeuille du gérant (% ou fraction)", "22.5"),
    ("valeur", "facultatif*", "Montant déclaré en $ (si pas de poids)", "60000000000"),
    ("secteur", "facultatif", "Secteur (sinon déduit du ticker)", "Technologie"),
    ("mouvement", "facultatif", "Nouvelle / Renforcée / Allégée / Inchangée (ou new / add / reduce)", "Allégée"),
    ("periode", "facultatif", "Fin du trimestre déclaré", "2026-06-30"),
]


def import_template() -> bytes:
    df = pd.DataFrame([
        dict(gerant="Berkshire Hathaway", ticker="AAPL", poids=22.5, secteur="", mouvement="Allégée", periode="2026-06-30"),
        dict(gerant="Berkshire Hathaway", ticker="AXP", poids=15.0, secteur="", mouvement="Inchangée", periode="2026-06-30"),
        dict(gerant="Pershing Square", ticker="UBER", poids=15.7, secteur="", mouvement="Renforcée", periode="2026-06-30"),
    ])
    return df.to_csv(index=False).encode("utf-8-sig")


def parse_import(data: bytes, name: str) -> tuple[dict | None, list[str]]:
    errs = []
    try:
        if name.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(data))
        else:
            txt = data.decode("utf-8-sig", "replace")
            df = pd.read_csv(io.StringIO(txt), sep=None, engine="python")
    except Exception as e:
        return None, [f"Fichier illisible ({type(e).__name__})."]
    df.columns = [re.sub(r"[^a-z]", "", str(c).lower().replace("é", "e").replace("è", "e")) for c in df.columns]
    alias = {"manager": "gerant", "fund": "gerant", "fonds": "gerant", "weight": "poids", "pct": "poids",
             "portfolio": "poids", "value": "valeur", "sector": "secteur", "activity": "mouvement",
             "status": "mouvement", "statut": "mouvement", "period": "periode", "symbol": "ticker", "stock": "ticker"}
    df = df.rename(columns={c: alias.get(c, c) for c in df.columns})
    if "gerant" not in df or "ticker" not in df:
        return None, ["Colonnes « gerant » et « ticker » obligatoires."]
    if "poids" not in df and "valeur" not in df:
        return None, ["Indiquez une colonne « poids » ou « valeur »."]
    rows = []
    for _, r in df.iterrows():
        t = str(r.get("ticker", "")).strip().upper().replace(".", "-") if str(r.get("ticker", "")).strip() else ""
        if not t or t == "NAN":
            continue
        g = str(r["gerant"]).strip()
        w = pd.to_numeric(str(r.get("poids", "")).replace("%", "").replace(",", "."), errors="coerce") if "poids" in df else np.nan
        v = pd.to_numeric(r.get("valeur"), errors="coerce") if "valeur" in df else np.nan
        rows.append(dict(code=re.sub(r"[^A-Z0-9]", "", g.upper())[:14] or "GERANT", manager=g, fund=g, ticker=t,
                         issuer=t, sector=str(r.get("secteur") or "").strip() if "secteur" in df and pd.notna(r.get("secteur")) else "",
                         value=float(v) if pd.notna(v) else (float(w) if pd.notna(w) else np.nan),
                         status=r.get("mouvement") if "mouvement" in df else None,
                         period=str(r.get("periode")) if "periode" in df and pd.notna(r.get("periode")) else ""))
    rows = [r for r in rows if pd.notna(r["value"])]
    if not rows:
        return None, ["Aucune ligne exploitable."]
    return build_from_holdings(rows, "import de fichier"), errs


# ── Cache disque ────────────────────────────────────────────────────────────────
def save_snapshot(snap: dict) -> None:
    _save_json(SNAPSHOT_FILE, snap)


def load_cached_snapshot(max_age_days: float = 45) -> dict | None:
    snap = _load_json(SNAPSHOT_FILE, None)
    if not snap or not snap.get("managers"):
        return None
    try:
        age = (datetime.now() - datetime.strptime(snap["built_at"], "%Y-%m-%d %H:%M")).days
        snap["age_days"] = age
        if age > max_age_days:
            return None
    except Exception:
        pass
    return snap


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYSES
# ══════════════════════════════════════════════════════════════════════════════
def holdings_frame(snap: dict, codes: list[str] | None = None) -> pd.DataFrame:
    rows = []
    for code, m in snap.get("managers", {}).items():
        if codes and code not in codes:
            continue
        for h in m.get("holdings", []):
            rows.append({**h, "code": code, "fund": m["fund"], "manager": m["manager"], "style": m.get("style")})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    for c, d in (("ticker", ""), ("sector", "Non classé"), ("status", "—"), ("issuer", ""), ("d_weight", np.nan),
                 ("prev_weight", np.nan), ("rank", 0)):
        if c not in df:
            df[c] = d
    df["ticker"] = df["ticker"].fillna("")
    df["key"] = [t if isinstance(t, str) and t else str(c) for t, c in zip(df.get("ticker"), df["cusip"])]
    df["label"] = [t if isinstance(t, str) and t else i for t, i in zip(df.get("ticker"), df["issuer"])]
    df["sector"] = df["sector"].fillna("Non classé").replace("", "Non classé")
    for c in ("weight", "d_weight", "prev_weight", "value"):
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    return df


def sold_frame(snap: dict, codes: list[str] | None = None) -> pd.DataFrame:
    rows = []
    for code, m in snap.get("managers", {}).items():
        if codes and code not in codes:
            continue
        for h in m.get("sold", []):
            rows.append({**h, "code": code, "fund": m["fund"]})
    df = pd.DataFrame(rows)
    if not df.empty:
        df["key"] = [t if isinstance(t, str) and t else str(c) for t, c in zip(df.get("ticker", [""] * len(df)), df["cusip"])]
    return df


def manager_stats(snap: dict, codes: list[str] | None = None) -> pd.DataFrame:
    out = []
    for code, m in snap.get("managers", {}).items():
        if codes and code not in codes:
            continue
        h = pd.DataFrame(m.get("holdings", []))
        if h.empty:
            continue
        if "sector" not in h:
            h["sector"] = "Non classé"
        if "ticker" not in h:
            h["ticker"] = ""
        w = pd.to_numeric(h["weight"], errors="coerce").fillna(0)
        dw = pd.to_numeric(h.get("d_weight"), errors="coerce")
        sec = h.assign(w=w).groupby(h["sector"].fillna("Non classé"))["w"].sum().sort_values(ascending=False)
        sold = m.get("sold", [])
        turnover = (float(dw.abs().sum()) + sum(float(s.get("prev_weight") or 0) for s in sold)) / 2 if dw.notna().any() else np.nan
        out.append({"Code": code, "Gérant": m["manager"], "Fonds": m["fund"], "Style": STYLES.get(m.get("style"), "—"),
                    "Trimestre": m.get("period"), "Déposé le": m.get("filed"), "Valeur 13F ($)": m.get("total_value"),
                    "Lignes": m.get("n_positions"), "Top 10": float(w.head(10).sum()),
                    "1re ligne": str(h.iloc[0].get("ticker") or h.iloc[0].get("issuer")),
                    "Poids 1re ligne": float(w.iloc[0]), "Secteur dominant": sec.index[0] if len(sec) else "—",
                    "Nouvelles": int((h.get("status") == "Nouvelle").sum()), "Soldées": len(sold),
                    "Rotation": turnover, "Options ($)": m.get("options_value", 0.0)})
    return pd.DataFrame(out)


def sector_matrix(snap: dict, codes: list[str] | None = None, prev: bool = False) -> pd.DataFrame:
    """Gérants × secteurs (poids dans la poche 13F de chaque gérant)."""
    df = holdings_frame(snap, codes)
    if df.empty:
        return pd.DataFrame()
    col = "prev_weight" if prev else "weight"
    if prev:
        sold = sold_frame(snap, codes)
        if not sold.empty:
            sold["sector"] = sold.get("sector", pd.Series(["Non classé"] * len(sold))).fillna("Non classé")
            df = pd.concat([df, sold.assign(weight=0.0)], ignore_index=True)
    piv = df.pivot_table(index="fund", columns="sector", values=col, aggfunc="sum", fill_value=0.0)
    if prev:
        piv = piv.div(piv.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)
    cols = [s for s in SECTORS if s in piv.columns]
    return piv[cols]


def sector_allocation(snap: dict, codes: list[str] | None = None) -> pd.DataFrame:
    """Allocation sectorielle moyenne des gérants (équipondérée), pondérée par les montants, et flux du trimestre."""
    mat = sector_matrix(snap, codes)
    if mat.empty:
        return pd.DataFrame()
    df = holdings_frame(snap, codes)
    vw = df.groupby("sector")["value"].sum()
    vw = vw / vw.sum()
    out = pd.DataFrame({"Moyenne des gérants": mat.mean(), "Pondérée par les montants": vw.reindex(mat.columns).fillna(0),
                        "Gérants investis": (mat > 0.005).sum()})
    has_prev = df["d_weight"].notna().any()
    if has_prev:
        pm = sector_matrix(snap, codes, prev=True).reindex(columns=mat.columns, fill_value=0.0)
        common = mat.index.intersection(pm.index)
        out["Flux du trimestre (pts)"] = (mat.loc[common] - pm.loc[common]).mean()
    out = out.sort_values("Moyenne des gérants", ascending=False)
    return out


def consensus(snap: dict, codes: list[str] | None = None) -> pd.DataFrame:
    """Une ligne par action : nombre de gérants, poids moyen, achats / ventes du trimestre, score de conviction."""
    df = holdings_frame(snap, codes)
    if df.empty:
        return pd.DataFrame()
    n_mgr = df["code"].nunique()
    g = df.groupby("key")
    out = pd.DataFrame({
        "Titre": g["label"].first(), "Émetteur": g["issuer"].first(), "Secteur": g["sector"].first(),
        "Gérants": g["code"].nunique(), "Détenu par": g["fund"].apply(lambda s: ", ".join(sorted(set(s)))),
        "Poids moyen (détenteurs)": g["weight"].mean(), "Poids max": g["weight"].max(),
        "Poids dans la moyenne des gérants": g["weight"].sum() / n_mgr, "Valeur totale ($)": g["value"].sum(),
        "Nouvelles": g["status"].apply(lambda s: int((s == "Nouvelle").sum())),
        "Renforcées": g["status"].apply(lambda s: int((s == "Renforcée").sum())),
        "Allégées": g["status"].apply(lambda s: int((s == "Allégée").sum())),
        "Δ poids moyen (pts)": g["d_weight"].sum() / n_mgr,
    })
    sold = sold_frame(snap, codes)
    out["Soldées"] = sold.groupby("key")["code"].nunique().reindex(out.index).fillna(0).astype(int) if not sold.empty else 0
    breadth = out["Gérants"] / max(n_mgr, 1)
    conv = out["Poids dans la moyenne des gérants"] / (out["Poids dans la moyenne des gérants"].max() or 1)
    net = (out["Nouvelles"] + out["Renforcées"] - out["Allégées"] - out["Soldées"]) / max(n_mgr, 1)
    out["Score"] = (100 * (0.45 * breadth + 0.40 * conv + 0.15 * net.clip(-1, 1))).round(1)
    return out.sort_values(["Poids dans la moyenne des gérants", "Gérants"], ascending=False)


def top5(snap: dict, codes: list[str] | None = None, n: int = 5) -> dict:
    """Top secteurs, top actifs, top achats / ventes — utilisé par les rapports."""
    sa = sector_allocation(snap, codes)
    cs = consensus(snap, codes)
    if sa.empty or cs.empty:
        return dict(ok=False)
    sa_eq = sa.drop(index=[s for s in ("ETF & fonds indiciels", "Non classé") if s in sa.index], errors="ignore")
    buys = cs.assign(_b=cs["Nouvelles"] + cs["Renforcées"]).sort_values(["_b", "Δ poids moyen (pts)"], ascending=False)
    buys = buys[buys["_b"] > 0]
    sells = cs.assign(_s=cs["Allégées"] + cs["Soldées"]).sort_values(["_s", "Δ poids moyen (pts)"], ascending=[False, True])
    sells = sells[sells["_s"] > 0]
    periods = sorted({m.get("period") for m in snap["managers"].values() if (not codes or m["code"] in codes) and m.get("period")})
    return dict(ok=True, n_managers=len(codes or snap["managers"]), periods=periods,
                sectors=[(s, float(r["Moyenne des gérants"]), float(r.get("Flux du trimestre (pts)", np.nan)), int(r["Gérants investis"]))
                         for s, r in sa_eq.head(n).iterrows()],
                assets=[(r["Titre"], r["Secteur"], int(r["Gérants"]), float(r["Poids dans la moyenne des gérants"]),
                         float(r["Δ poids moyen (pts)"])) for _, r in cs.head(n).iterrows()],
                buys=[(r["Titre"], int(r["Nouvelles"]), int(r["Renforcées"]), r["Détenu par"]) for _, r in buys.head(n).iterrows()],
                sells=[(r["Titre"], int(r["Allégées"]), int(r["Soldées"])) for _, r in sells.head(n).iterrows()])


def signals(snap: dict, codes: list[str] | None = None) -> dict:
    """Les 4 filtres de la méthode « 13F » : convictions ≥ 5 %, nouvelles entrées dans le top 10,
    achats groupés (≥ 2 gérants), fortes hausses de poids (≥ 2 pts)."""
    df = holdings_frame(snap, codes)
    if df.empty:
        return {}
    cols = ["fund", "label", "sector", "weight", "d_weight", "status", "rank"]
    conv = df[df["weight"] >= 0.05].sort_values("weight", ascending=False)[cols]
    new10 = df[(df["status"] == "Nouvelle") & (df["rank"] <= 10)].sort_values("weight", ascending=False)[cols]
    big = df[df["d_weight"] >= 0.02].sort_values("d_weight", ascending=False)[cols]
    b = df[df["status"].isin(["Nouvelle", "Renforcée"])].groupby("key").agg(
        Titre=("label", "first"), Secteur=("sector", "first"), Acheteurs=("code", "nunique"),
        Qui=("fund", lambda s: ", ".join(sorted(set(s)))), Poids_moyen=("weight", "mean"))
    cluster = b[b["Acheteurs"] >= 2].sort_values(["Acheteurs", "Poids_moyen"], ascending=False)
    return dict(conviction=conv, new_top10=new10, big_increase=big, cluster=cluster)


# ══════════════════════════════════════════════════════════════════════════════
#  COMPARAISON AVEC UN PORTEFEUILLE MIP
# ══════════════════════════════════════════════════════════════════════════════
def portfolio_exposure(values: dict, cash: float = 0.0, lookthrough: dict | None = None) -> dict:
    """Poids par classe d'actifs, puis, dans la poche actions : poids par titre et par secteur.
    `lookthrough` : {ticker ETF: {secteur: poids}} (composition des ETF diversifiés, si connue)."""
    try:
        from utils.market_intel import asset_class
    except Exception:
        asset_class = lambda t: "Actions"  # noqa: E731
    vals = {str(t).upper(): float(v) for t, v in (values or {}).items() if v and float(v) > 0 and str(t).upper() != "CASH"}
    nav = sum(vals.values()) + max(float(cash or 0), 0.0)
    classes: dict[str, float] = {}
    eq = {}
    for t, v in vals.items():
        c = asset_class(t)
        if c == "Actions":
            eq[t] = v
        else:
            classes[c] = classes.get(c, 0.0) + v
    eq_tot = sum(eq.values())
    classes["Actions"] = eq_tot
    if cash:
        classes["Liquidités"] = classes.get("Liquidités", 0.0) + float(cash)
    cls_w = {k: v / nav for k, v in classes.items() if nav > 0 and v > 0}
    tw = {t: v / eq_tot for t, v in eq.items()} if eq_tot > 0 else {}
    sec: dict[str, float] = {}
    via = {}
    for t, w in tw.items():
        lt = (lookthrough or {}).get(t)
        if lt:
            tot = sum(lt.values()) or 1.0
            for s, x in lt.items():
                sec[s] = sec.get(s, 0.0) + w * x / tot
            via[t] = "composition de l'ETF"
        else:
            s = sector_for_ticker(t)
            sec[s] = sec.get(s, 0.0) + w
    non_us = sum(w for t, w in tw.items() if "." in t and not t.endswith(("-A", "-B")))
    return dict(nav=nav, classes=cls_w, equity_share=eq_tot / nav if nav else 0.0, tickers=tw, sectors=sec,
                lookthrough=via, non_us=non_us, n_lines=len(vals))


def benchmark(snap: dict, codes: list[str] | None = None, mode: str = "Moyenne des gérants") -> dict:
    """Allocation de référence des gérants : par secteur et par titre (somme = 1)."""
    df = holdings_frame(snap, codes)
    if df.empty:
        return dict(sectors={}, tickers={}, label=mode)
    if mode == "Pondérée par les montants":
        tot = df["value"].sum()
        sec = (df.groupby("sector")["value"].sum() / tot).to_dict()
        tk = (df.groupby("key")["value"].sum() / tot).to_dict()
    else:
        n = df["code"].nunique()
        sec = (df.groupby("sector")["weight"].sum() / n).to_dict()
        tk = (df.groupby("key")["weight"].sum() / n).to_dict()
    return dict(sectors=sec, tickers=tk, label=mode, top10=float(df.groupby("code")["weight"].apply(lambda s: s.nlargest(10).sum()).median()),
                n_lines=float(df.groupby("code").size().median()))


def compare(expo: dict, bench: dict, snap: dict | None = None, codes: list[str] | None = None) -> dict:
    """Écarts sectoriels, recouvrement, part active, titres en commun / absents."""
    secs = [s for s in SECTORS if s in set(expo["sectors"]) | set(bench["sectors"])]
    flows = {}
    if snap is not None:
        sa = sector_allocation(snap, codes)
        if "Flux du trimestre (pts)" in sa:
            flows = sa["Flux du trimestre (pts)"].to_dict()
    sec = pd.DataFrame({"Mon portefeuille": [expo["sectors"].get(s, 0.0) for s in secs],
                        "Meilleurs gérants": [bench["sectors"].get(s, 0.0) for s in secs]}, index=secs)
    sec["Écart (pts)"] = sec["Mon portefeuille"] - sec["Meilleurs gérants"]
    sec["Flux des gérants (pts)"] = [flows.get(s, np.nan) for s in secs]
    pw, bw = expo["tickers"], bench["tickers"]
    keys = set(pw) | set(bw)
    overlap = sum(min(pw.get(k, 0), bw.get(k, 0)) for k in keys)
    active = 0.5 * sum(abs(pw.get(k, 0) - bw.get(k, 0)) for k in keys)
    common = sorted([k for k in pw if k in bw], key=lambda k: -pw[k])
    cs = consensus(snap, codes) if snap is not None else pd.DataFrame()
    missing = cs[~cs.index.isin(list(pw))].head(10) if not cs.empty else pd.DataFrame()
    selling = []
    if not cs.empty:
        for k in pw:
            if k in cs.index and (cs.loc[k, "Allégées"] + cs.loc[k, "Soldées"]) >= 2:
                selling.append((k, int(cs.loc[k, "Allégées"]), int(cs.loc[k, "Soldées"])))
    mine_only = [k for k in sorted(pw, key=lambda k: -pw[k]) if k not in bw]
    top10 = sum(sorted(pw.values(), reverse=True)[:10]) if pw else 0.0
    return dict(sectors=sec.sort_values("Meilleurs gérants", ascending=False), overlap=overlap, active_share=active,
                common=common, missing=missing, selling=selling, mine_only=mine_only, top10=top10)


def explain_differences(expo: dict, comp: dict, bench: dict, snap: dict, codes: list[str] | None, regime: str | None,
                        profile: str = "Équilibré", sector_perf: dict | None = None) -> list[dict]:
    """Pourquoi mon portefeuille diffère-t-il des meilleurs gérants ? (raisons en mots simples)."""
    out = []
    periods = sorted({m.get("period") for c, m in snap["managers"].items() if (not codes or c in codes) and m.get("period")})
    per = periods[-1] if periods else "—"
    non_eq = 1 - expo["equity_share"]
    detail = ", ".join(f"{k.lower()} {v:.0%}" for k, v in sorted(expo["classes"].items(), key=lambda x: -x[1]) if k != "Actions")
    out.append(dict(titre="Ce que les 13F ne montrent pas", type="structure",
                    texte=(f"Les gérants ne déclarent que leurs actions américaines détenues à l'achat, au {per}. "
                           f"Votre portefeuille compte {non_eq:.0%} hors actions" + (f" ({detail})" if detail else "") +
                           " : cette part n'a pas d'équivalent dans les 13F. La comparaison porte donc sur votre seule poche "
                           f"actions ({expo['equity_share']:.0%} du portefeuille). Les gérants ont eux aussi des liquidités, "
                           "des obligations ou des ventes à découvert qui n'apparaissent pas.")))
    if expo.get("non_us", 0) > 0.05:
        out.append(dict(titre="Actions hors des États-Unis", type="structure",
                        texte=f"{expo['non_us']:.0%} de votre poche actions est cotée hors des États-Unis (Europe, Asie…) : "
                              "les 13F ne les montrent pas. Ce n'est pas une erreur, c'est une diversification que la "
                              "référence ne peut pas refléter."))
    if expo.get("lookthrough") or any(sector_for_ticker(t) == "ETF & fonds indiciels" for t in expo["tickers"]):
        out.append(dict(titre="ETF contre actions en direct", type="structure",
                        texte="Vous détenez des ETF : ils contiennent souvent les mêmes géants (Microsoft, Apple, Nvidia…) que "
                              "les gérants, mais pas sous le même nom de ligne. Le recouvrement « titre par titre » est donc "
                              "sous-estimé ; la comparaison par secteur est plus juste."))
    fav, pen = REGIME_SECTORS.get(regime or "", (set(), set()))
    sec = comp["sectors"].drop(index=[s for s in ("ETF & fonds indiciels", "Non classé") if s in comp["sectors"].index],
                               errors="ignore")
    gaps = sec.reindex(sec["Écart (pts)"].abs().sort_values(ascending=False).index).head(4)
    for s, r in gaps.iterrows():
        g = r["Écart (pts)"]
        if abs(g) < 0.03:
            continue
        over = g > 0
        mine = [t for t in sorted(expo["tickers"], key=lambda t: -expo["tickers"][t]) if sector_for_ticker(t) == s][:3]
        flow = r.get("Flux des gérants (pts)")
        txt = (f"Vous avez {r['Mon portefeuille']:.0%} de votre poche actions en {s.lower()} contre "
               f"{r['Meilleurs gérants']:.0%} pour les gérants ({g * 100:+.0f} pts)")
        txt += (f", surtout via {', '.join(mine)}. " if mine and over else ". ")
        if flow == flow and flow is not None and abs(flow) >= 0.005:
            txt += (f"Au dernier trimestre, les gérants ont {'renforcé' if flow > 0 else 'allégé'} ce secteur de "
                    f"{abs(flow) * 100:.1f} pt. ")
        if s in fav:
            txt += (f"Le régime officiel du comité (« {regime} ») est plutôt favorable à ce secteur : "
                    + ("votre surpondération va dans le sens du contexte actuel." if over else
                       "votre sous-pondération est à contre-courant du contexte."))
        elif s in pen:
            txt += (f"Le régime officiel du comité (« {regime} ») pénalise plutôt ce secteur : "
                    + ("votre surpondération est un pari contre le contexte actuel." if over else
                       "votre prudence est cohérente avec le contexte."))
        else:
            txt += "Le contexte de marché est neutre pour ce secteur : l'écart vient surtout des choix de titres."
        if sector_perf and s in sector_perf and sector_perf[s] == sector_perf[s]:
            txt += f" Performance du secteur sur 3 mois : {sector_perf[s]:+.1%}."
        out.append(dict(titre=f"{'Surpondération' if over else 'Sous-pondération'} — {s}", type="secteur", texte=txt,
                        ecart=float(g), secteur=s))
    try:
        from utils.compliance import HARD_LIMITS
        cap = HARD_LIMITS.get(profile, HARD_LIMITS["Équilibré"])["line"]
    except Exception:
        cap = 0.20
    bt = bench.get("top10", np.nan)
    base = (f"Les dix premières lignes pèsent {bt:.0%} du portefeuille d'un gérant (médiane, environ "
            f"{bench.get('n_lines', 0):.0f} lignes) contre {comp['top10']:.0%} dans votre poche actions "
            f"({len(expo['tickers'])} ligne(s)). ")
    if comp["top10"] > bt + 0.05:
        n_etf = sum(1 for t in expo["tickers"] if sector_for_ticker(t) == "ETF & fonds indiciels" or t in expo.get("lookthrough", {}))
        txt = base + ("Votre poche actions compte moins de lignes que les gérants" +
                      (", mais vos ETF indiciels contiennent chacun des centaines de sociétés : votre diversification réelle "
                       "est plus large que ce chiffre." if n_etf else
                       f" : chaque ligne pèse lourd. Votre profil {profile} plafonne une ligne à {cap:.0%} ; ajouter "
                       "quelques titres d'autres secteurs ou un ETF diversifié réduirait ce risque."))
    else:
        txt = base + (f"Les grands investisseurs concentrent leurs convictions ; votre profil {profile} plafonne chaque "
                      f"ligne à {cap:.0%} : cette différence est voulue et protège votre capital si une conviction se "
                      "révèle fausse.")
    out.append(dict(titre="Concentration : conviction contre diversification", type="style", texte=txt))
    out.append(dict(titre="Recouvrement avec les gérants", type="synthese",
                    texte=(f"{comp['overlap']:.0%} de votre poche actions est investie comme la moyenne des gérants "
                           f"(part active {comp['active_share']:.0%}). {len(comp['common'])} titre(s) en commun"
                           + (f" : {', '.join(comp['common'][:6])}" if comp["common"] else "") + ".")))
    if comp["selling"]:
        out.append(dict(titre="Titres que plusieurs gérants vendent", type="alerte",
                        texte="; ".join(f"{k} : {a} gérant(s) allègent, {s} soldent" for k, a, s in comp["selling"][:5]) +
                              ". Ce n'est pas une raison de vendre, mais une raison de revoir votre thèse."))
    return out


def suggestions(comp: dict, regime: str | None, snap: dict, codes: list[str] | None) -> list[dict]:
    """Pistes d'ajustement proposées par le comité — à valider par l'utilisateur, jamais exécutées."""
    fav, pen = REGIME_SECTORS.get(regime or "", (set(), set()))
    cs = consensus(snap, codes)
    out = []
    sec = comp["sectors"]
    for s, r in sec.iterrows():
        if s in ("ETF & fonds indiciels", "Non classé"):
            continue
        flow = r.get("Flux des gérants (pts)")
        flow = 0.0 if flow != flow or flow is None else flow
        names = list(cs[cs["Secteur"] == s].head(3)["Titre"]) if not cs.empty else []
        if r["Écart (pts)"] <= -0.05 and (flow > 0 or s in fav):
            step = min(abs(r["Écart (pts)"]) / 2, 0.05)
            out.append(dict(sens="Renforcer", secteur=s, ampleur=step, qui="Thierry BALANCEMENT",
                            texte=f"Étudier un renforcement progressif de {s.lower()} (+{step * 100:.0f} pts de la poche "
                                  f"actions au plus), via l'ETF {SECTOR_ETF.get(s, '')} ou des titres du consensus "
                                  f"({', '.join(names) or '—'}), après vérification de leur valorisation."))
        elif r["Écart (pts)"] >= 0.05 and (flow < 0 or s in pen):
            step = min(r["Écart (pts)"] / 2, 0.05)
            out.append(dict(sens="Alléger", secteur=s, ampleur=step, qui="Aline DE MARGE",
                            texte=f"Envisager d'alléger {s.lower()} de {step * 100:.0f} pts : vous êtes au-dessus des "
                                  "gérants" + (", qui réduisent ce secteur" if flow < 0 else "") +
                                  (f", et le régime « {regime} » le pénalise" if s in pen else "") + "."))
    for k, a, so in comp.get("selling", [])[:3]:
        out.append(dict(sens="Revoir", secteur=sector_for_ticker(k), ampleur=0.0, qui="Mc Henson ALGO-RITHME",
                        texte=f"Revoir la thèse sur {k} : {a + so} gérants suivis réduisent ou vendent."))
    miss = comp.get("missing")
    if isinstance(miss, pd.DataFrame) and len(miss):
        out.append(dict(sens="Surveiller", secteur="—", ampleur=0.0, qui="Marc ETING-FINANCIER",
                        texte="Ajouter à votre liste de surveillance les titres les plus partagés que vous ne détenez pas : "
                              + ", ".join(miss.head(5)["Titre"].astype(str)) + "."))
    out.append(dict(sens="Méthode", secteur="—", ampleur=0.0, qui="Constance Probité",
                    texte="Ne jamais copier une position : vérifier la valorisation actuelle, comprendre la thèse du gérant "
                          "et respecter votre politique d'investissement (plafonds, exclusions) avant tout ordre."))
    return out


# ══════════════════════════════════════════════════════════════════════════════
#  ANALYSE ET INTERPRÉTATION PAR LE COMITÉ
# ══════════════════════════════════════════════════════════════════════════════
def interpret(snap: dict, codes: list[str] | None = None, regime: str | None = None,
              perf_since: dict | None = None) -> dict:
    """Lecture des investissements des gérants par chaque membre du comité + synthèse simple."""
    t5 = top5(snap, codes)
    if not t5.get("ok"):
        return dict(ok=False)
    sa = sector_allocation(snap, codes)
    cs = consensus(snap, codes)
    sg = signals(snap, codes)
    st_ = manager_stats(snap, codes)
    fav, pen = REGIME_SECTORS.get(regime or "", (set(), set()))
    flows = sa["Flux du trimestre (pts)"] if "Flux du trimestre (pts)" in sa else pd.Series(dtype=float)
    cyc = float(flows[flows.index.isin(CYCLICAL)].sum()) if len(flows) else np.nan
    dfn = float(flows[flows.index.isin(DEFENSIVE)].sum()) if len(flows) else np.nan
    top_s = [s for s, *_ in t5["sectors"]]
    avis = []
    # 🌦️ Économiste
    p = [f"Secteurs dominants chez les gérants : {', '.join(top_s[:3])}."]
    if cyc == cyc:
        if cyc - dfn > 0.01:
            p.append(f"Au dernier trimestre, l'argent est allé vers les secteurs cycliques ({cyc * 100:+.1f} pts) plus que "
                     f"vers les défensifs ({dfn * 100:+.1f} pts) : les gérants parient sur une croissance qui tient.")
        elif dfn - cyc > 0.01:
            p.append(f"Au dernier trimestre, les gérants se sont protégés : défensifs {dfn * 100:+.1f} pts contre "
                     f"cycliques {cyc * 100:+.1f} pts — signe de prudence sur le cycle.")
        else:
            p.append("Pas de rotation marquée entre secteurs cycliques et défensifs au dernier trimestre.")
    if regime:
        agree = [s for s in top_s if s in fav]
        against = [s for s in top_s if s in pen]
        p.append(f"Régime officiel du comité : « {regime} ». " +
                 (f"Concordant pour {', '.join(agree)}. " if agree else "") +
                 (f"À contre-courant pour {', '.join(against)} : les gérants regardent plus loin que le cycle actuel, "
                  "ou leurs positions datent d'avant le changement de contexte." if against else ""))
    avis.append(dict(id="eco", titre="Ce que les flux disent du cycle", points=p))
    # 🧮 Quant
    top10_share = float(cs.head(10)["Poids dans la moyenne des gérants"].sum())
    hhi = float((sa["Moyenne des gérants"] ** 2).sum())
    p = [f"Les 10 titres les plus partagés représentent {top10_share:.0%} de l'allocation moyenne des gérants "
         f"(concentration sectorielle HHI {hhi:.2f}).",
         f"Achats groupés (au moins 2 gérants le même trimestre) : {len(sg.get('cluster', []))} titre(s)."]
    if perf_since:
        vals = [v for v in perf_since.values() if v == v]
        if vals:
            p.append(f"Depuis la fin du trimestre déclaré, les 10 premières positions du consensus ont évolué de "
                     f"{np.mean(vals):+.1%} en moyenne (de {min(vals):+.1%} à {max(vals):+.1%}) : le prix d'entrée "
                     "des gérants n'est plus celui d'aujourd'hui.")
    p.append("Un consensus très partagé est une preuve de qualité, pas un signal de rendement futur : les études "
             "montrent que l'avantage du « suivi des gérants » se concentre dans les convictions fortes et les "
             "achats groupés, et s'érode avec le délai de publication.")
    avis.append(dict(id="quant", titre="Ce que disent les chiffres", points=p))
    # 🏛️ Gérant
    conv = sg.get("conviction", pd.DataFrame())
    new10 = sg.get("new_top10", pd.DataFrame())
    clus = sg.get("cluster", pd.DataFrame())
    p = []
    if len(new10):
        p.append("Nouvelles positions entrées directement dans le top 10 (forte conviction) : " +
                 "; ".join(f"{r['label']} chez {r['fund']} ({r['weight']:.0%})" for _, r in new10.head(5).iterrows()) + ".")
    if len(clus):
        p.append("Achats groupés à étudier : " + "; ".join(f"{r['Titre']} ({r['Acheteurs']} gérants)" for _, r in clus.head(5).iterrows()) + ".")
    if len(conv):
        p.append(f"{len(conv)} position(s) dépassent 5 % du portefeuille d'un gérant : ce sont leurs vraies convictions.")
    p.append("Méthode : partir de ces pistes, vérifier la valorisation actuelle (multiples, marges, croissance du "
             "bénéfice), reconstituer la thèse du gérant ; si on ne sait pas l'expliquer, on passe.")
    avis.append(dict(id="cio", titre="Les idées à étudier (pas à copier)", points=p))
    # 🛡️ Risque
    med_top10 = float(st_["Top 10"].median()) if len(st_) else np.nan
    puts = [m["fund"] for c, m in snap["managers"].items() if (not codes or c in codes)
            and any(str(o.get("put_call")).lower() == "put" for o in m.get("options", []))]
    p = [f"Les portefeuilles suivis sont concentrés (top 10 = {med_top10:.0%} en médiane) : une erreur coûte cher.",
         "Risque de foule : quand beaucoup de gérants détiennent le même titre, les sorties sont simultanées "
         "(liquidité qui disparaît, baisse amplifiée).",
         "Données décalées (jusqu'à 45 jours), limitées aux actions américaines achetées : les couvertures, les ventes "
         "à découvert et les liquidités sont invisibles."]
    if puts:
        p.append(f"Options de vente (puts) déclarées par : {', '.join(puts[:5])} — couverture ou pari à la baisse ; "
                 "le 13F ne dit pas lequel.")
    avis.append(dict(id="cro", titre="Les angles morts", points=p))
    # ⚖️ Conformité
    avis.append(dict(id="cmp", titre="Cadre et règles", points=[
        "Les 13F sont exigés par la section 13(f) du Securities Exchange Act pour les gérants de plus de 100 M$ "
        "d'actions américaines : données publiques et officielles.",
        "Suivre un gérant n'est pas un conseil personnalisé : chaque idée passe par votre profil, votre politique "
        "d'investissement (plafonds, exclusions ESG) et les contrôles de conformité MIP avant tout ordre.",
        "Les titres hors de votre enveloppe (PEA, UCITS) restent inaccessibles même s'ils sont plébiscités."]))
    # 🎙️ CPM
    p = [f"En clair : les meilleurs gérants suivis investissent surtout en {', '.join(top_s[:3]).lower()}, et leurs "
         f"titres préférés sont {', '.join(a[0] for a in t5['assets'][:5])}."]
    if t5["buys"]:
        p.append(f"Ce trimestre, ils ont surtout acheté {', '.join(b[0] for b in t5['buys'][:3])}"
                 + (f" et vendu {', '.join(s[0] for s in t5['sells'][:3])}." if t5["sells"] else "."))
    p.append("Biais à éviter : biais d'autorité (« Buffett l'a acheté, donc c'est bon »), effet moutonnier, biais du "
             "survivant (on ne suit que les gérants qui ont réussi).")
    avis.append(dict(id="cpm", titre="Ce qu'il faut retenir", points=p))
    try:
        from utils.committee import MEMBER
        for a in avis:
            m = MEMBER.get(a["id"], {})
            a.update(nom=m.get("nom", a["id"]), emoji=m.get("emoji", ""), couleur=m.get("couleur", "#94a3b8"),
                     role=m.get("role", ""))
    except Exception:
        pass
    synth = (f"{t5['n_managers']} gérants suivis ({', '.join(t5['periods'][-1:]) or '—'}) : "
             f"top 3 des secteurs {', '.join(top_s[:3]).lower()} ; titres les plus partagés "
             f"{', '.join(a[0] for a in t5['assets'][:3])}. Ce sont des pistes de recherche à confronter à votre "
             "profil et au régime de marché, jamais des ordres à copier.")
    return dict(ok=True, avis=avis, synthese=synth, top5=t5)


# ══════════════════════════════════════════════════════════════════════════════
#  RAPPORTS (PDF / Excel / blocs pour les autres rapports)
# ══════════════════════════════════════════════════════════════════════════════
def report_blocks(snap: dict | None, codes: list[str] | None = None, short: bool = True) -> list[tuple]:
    """Petite section « Où investissent les meilleurs gérants » + plateformes à regarder (rapports MIP)."""
    b: list[tuple] = [("h", "Où investissent actuellement les meilleurs gérants")]
    t5 = top5(snap, codes) if snap else dict(ok=False)
    if t5.get("ok"):
        b.append(("p", f"D'après les derniers formulaires 13F de {t5['n_managers']} gérants suivis (trimestre "
                       f"{', '.join(t5['periods'][-1:]) or '—'}), voici leurs 5 premiers secteurs et leurs 5 titres préférés."))
        rows = [["#", "Top 5 secteurs", "Poids moyen", "Flux du trimestre", "#", "Top 5 actifs", "Gérants", "Poids moyen"]]
        for i in range(5):
            s = t5["sectors"][i] if i < len(t5["sectors"]) else ("", np.nan, np.nan, 0)
            a = t5["assets"][i] if i < len(t5["assets"]) else ("", "", 0, np.nan, np.nan)
            rows.append([str(i + 1), s[0], f"{s[1]:.1%}" if s[1] == s[1] else "", f"{s[2] * 100:+.1f} pt" if s[2] == s[2] else "—",
                         str(i + 1), f"{a[0]} ({a[1]})" if a[0] else "", str(a[2]) if a[0] else "", f"{a[3]:.1%}" if a[3] == a[3] else ""])
        b.append(("table", rows, [0.6, 3.8, 1.8, 2.0, 0.6, 4.6, 1.4, 1.8]))
        if t5["buys"] and not short:
            b.append(("p", "Achats les plus partagés du trimestre : " + "; ".join(
                f"{x[0]} ({x[1]} nouvelle(s), {x[2]} renforcement(s))" for x in t5["buys"])))
        try:
            mh, ms = most_held(snap, codes, 5), most_sold(snap, codes, 5)
            if len(mh):
                b.append(("table", [["Les plus détenus", "Gérants", "Poids moyen", "Détenu depuis", "Plus ancien détenteur"]] +
                          [[str(r["Titre"]), str(r["Gérants"]), f"{r['Poids moyen chez les gérants']:.1%}", r["Détenu depuis"],
                            str(r["Le plus ancien détenteur"])] for _, r in mh.iterrows()], [3.0, 1.6, 2.2, 3.4, 6.4]))
            if len(ms):
                b.append(("table", [["Les plus vendus", "Vendeurs", "Part vendue", "Ventes depuis", "Soldé par / allégé par"]] +
                          [[str(r["Titre"]), str(r["Vendeurs"]), f"{r['Part vendue (moyenne)']:.0%}", r["Ventes depuis"],
                            (r["Soldé par"] if r["Soldé par"] != "—" else r["Allégé par"])[:80]] for _, r in ms.iterrows()],
                          [3.0, 1.6, 2.0, 2.4, 7.6]))
        except Exception:
            pass
    else:
        b.append(("p", "Données des gérants non chargées : ouvrez l'onglet « Tracking Best AM » pour les télécharger."))
    b.append(("p", "**Plateformes à regarder** : " + " · ".join(f"{p['nom']} ({p['url'].split('//')[1].split('/')[0]})"
                                                               for p in PLATFORMS[:6]) + "."))
    b.append(("note", LIMITS_TEXT))
    return b


def current_snapshot() -> dict | None:
    """Relevé chargé dans la session (onglet Tracking Best AM), sinon le dernier relevé enregistré sur disque."""
    try:
        import streamlit as st
        s = st.session_state.get("sm_snap")
        if s and s.get("managers"):
            return s
    except Exception:
        pass
    return load_cached_snapshot()


def report_html(snap: dict | None, codes: list[str] | None = None, dark: bool = False) -> str:
    """Même section, en HTML pour les e-mails."""
    import html as _h
    t5 = top5(snap, codes) if snap else dict(ok=False)
    if not t5.get("ok"):
        return ""
    fg, mu = ("#cbd5e1", "#64748b") if dark else ("#1e293b", "#64748b")
    s = "".join(f"<li>{_h.escape(x[0])} — {x[1]:.0%}</li>" for x in t5["sectors"])
    a = "".join(f"<li>{_h.escape(x[0])} ({_h.escape(x[1])}) — {x[2]} gérants</li>" for x in t5["assets"])
    p = " · ".join(f'<a href="{x["url"]}">{_h.escape(x["nom"])}</a>' for x in PLATFORMS[:5])
    return (f'<div style="color:{"#00d4ff" if dark else "#0077b6"};font-weight:700;margin:14px 0 4px">🐋 Où investissent '
            f'les meilleurs gérants (13F, {_h.escape(", ".join(t5["periods"][-1:]))})</div>'
            f'<table style="width:100%;color:{fg};font-size:13px"><tr><td valign="top"><b>Top 5 secteurs</b><ol>{s}</ol></td>'
            f'<td valign="top"><b>Top 5 actifs</b><ol>{a}</ol></td></tr></table>'
            f'<p style="font-size:12px;color:{fg}">Plateformes à regarder : {p}</p>'
            f'<p style="font-size:11px;color:{mu}">{_h.escape(LIMITS_TEXT)}</p>')


def _charts(snap: dict, codes: list[str] | None, comp: dict | None = None) -> dict[str, bytes]:
    import matplotlib
    matplotlib.use("Agg")
    from utils import reporting as R
    out = {}
    sa = sector_allocation(snap, codes)
    if not sa.empty:
        fig, ax, t = R._fig("light", 9, 4.4)
        s = sa["Moyenne des gérants"].iloc[::-1]
        ax.barh(s.index, s.values * 100, color=[SECTOR_COLORS.get(i, "#64748b") for i in s.index])
        for y, v in enumerate(s.values):
            ax.text(v * 100 + 0.3, y, f"{v:.1%}", va="center", fontsize=7, color=t["fg"])
        R._title(ax, t, "Allocation sectorielle moyenne des gérants suivis", "poids moyen dans les portefeuilles 13F (%)")
        out["01_secteurs"] = R._png(fig)
        if "Flux du trimestre (pts)" in sa and sa["Flux du trimestre (pts)"].notna().any():
            f2, ax2, t2 = R._fig("light", 9, 4.0)
            fl = sa["Flux du trimestre (pts)"].dropna().sort_values()
            ax2.barh(fl.index, fl.values * 100, color=["#16a34a" if v > 0 else "#dc2626" for v in fl.values])
            ax2.axvline(0, color=t2["muted"], lw=0.8)
            R._title(ax2, t2, "Flux sectoriels du dernier trimestre", "variation du poids moyen (points)")
            out["02_flux"] = R._png(f2)
    mat = sector_matrix(snap, codes)
    if not mat.empty:
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 0.42 * len(mat) + 2), dpi=150)
        im = ax.imshow(mat.values * 100, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(mat.columns)))
        ax.set_xticklabels(mat.columns, rotation=40, ha="right", fontsize=7)
        ax.set_yticks(range(len(mat.index)))
        ax.set_yticklabels(mat.index, fontsize=7)
        for i in range(mat.shape[0]):
            for j in range(mat.shape[1]):
                v = mat.values[i, j]
                if v >= 0.05:
                    ax.text(j, i, f"{v:.0%}", ha="center", va="center", fontsize=6,
                            color="white" if v > 0.35 else "#0b1424")
        fig.colorbar(im, ax=ax, fraction=0.025, label="%")
        ax.set_title("Carte de chaleur — secteurs par gérant", loc="left", fontsize=11, fontweight="bold")
        out["03_carte_chaleur"] = R._png(fig)
    cs = consensus(snap, codes)
    if not cs.empty:
        fig, ax, t = R._fig("light", 9, 4.6)
        top = cs.head(15).iloc[::-1]
        ax.barh(top["Titre"].astype(str), top["Poids dans la moyenne des gérants"] * 100,
                color=[SECTOR_COLORS.get(s, "#64748b") for s in top["Secteur"]])
        for y, (v, n) in enumerate(zip(top["Poids dans la moyenne des gérants"], top["Gérants"])):
            ax.text(v * 100 + 0.2, y, f"{n} gérant(s)", va="center", fontsize=7, color=t["muted"])
        R._title(ax, t, "Les 15 titres les plus présents chez les gérants", "poids dans l'allocation moyenne (%)")
        out["04_consensus"] = R._png(fig)
    if comp is not None:
        sec = comp["sectors"]
        fig, ax, t = R._fig("light", 9, 4.6)
        y = np.arange(len(sec))
        ax.barh(y - 0.2, sec["Mon portefeuille"] * 100, 0.4, label="Mon portefeuille", color="#0077b6")
        ax.barh(y + 0.2, sec["Meilleurs gérants"] * 100, 0.4, label="Meilleurs gérants", color="#94a3b8")
        ax.set_yticks(y)
        ax.set_yticklabels(sec.index, fontsize=7)
        ax.invert_yaxis()
        ax.legend(fontsize=7, frameon=False)
        R._title(ax, t, "Poche actions : mon portefeuille contre les gérants", "poids par secteur (%)")
        out["05_comparaison"] = R._png(fig)
    return out


def build_pdf(snap: dict, codes: list[str] | None = None, regime: str | None = None, port_name: str | None = None,
              expo: dict | None = None, comp: dict | None = None, reasons: list[dict] | None = None,
              sugg: list[dict] | None = None, perf_since: dict | None = None) -> bytes:
    """Rapport d'analyse : secteurs et titres où investissent les meilleurs gérants (graphiques inclus)."""
    from utils import reporting as R
    from utils import legal as L
    imgs = _charts(snap, codes, comp)
    it = interpret(snap, codes, regime, perf_since)
    t5 = it.get("top5", {})
    b: list[tuple] = []
    b.append(("h", "En bref"))
    b.append(("p", it.get("synthese", "")))
    if t5.get("ok"):
        b.append(("kpis", [("Gérants analysés", str(t5["n_managers"])), ("Trimestre", ", ".join(t5["periods"][-1:]) or "—"),
                           ("1er secteur", t5["sectors"][0][0]), ("Titre le plus partagé", t5["assets"][0][0])]))
    b += report_blocks(snap, codes, short=False)[1:]
    b.append(("h", "1. Où investissent les gérants : secteurs"))
    for k in ("01_secteurs", "02_flux", "03_carte_chaleur"):
        if k in imgs:
            b.append(("img", imgs[k], 17))
    sa = sector_allocation(snap, codes)
    if not sa.empty:
        rows = [["Secteur", "Moyenne des gérants", "Pondérée par les montants", "Gérants investis", "Flux du trimestre"]]
        for s, r in sa.iterrows():
            f = r.get("Flux du trimestre (pts)", np.nan)
            rows.append([s, f"{r['Moyenne des gérants']:.1%}", f"{r['Pondérée par les montants']:.1%}",
                         str(int(r["Gérants investis"])), f"{f * 100:+.1f} pt" if f == f else "—"])
        b.append(("table", rows, [5.0, 3.2, 3.6, 2.6, 3.0]))
    b.append(("break",))
    b.append(("h", "2. Les titres préférés et les mouvements du trimestre"))
    if "04_consensus" in imgs:
        b.append(("img", imgs["04_consensus"], 17))
    cs = consensus(snap, codes)
    if not cs.empty:
        rows = [["Titre", "Secteur", "Gérants", "Poids moyen", "Nouv.", "Renf.", "All.", "Sold.", "Depuis fin trim."]]
        for k, r in cs.head(20).iterrows():
            ps = (perf_since or {}).get(r["Titre"], np.nan)
            rows.append([str(r["Titre"]), r["Secteur"], str(r["Gérants"]), f"{r['Poids dans la moyenne des gérants']:.1%}",
                         str(r["Nouvelles"]), str(r["Renforcées"]), str(r["Allégées"]), str(r["Soldées"]),
                         f"{ps:+.1%}" if ps == ps else "—"])
        b.append(("table", rows, [2.2, 4.2, 1.5, 2.0, 1.2, 1.2, 1.2, 1.2, 2.4]))
    sg = signals(snap, codes)
    if sg:
        if len(sg["new_top10"]):
            b.append(("p", "**Nouvelles positions entrées directement dans le top 10** : " + "; ".join(
                f"{r['label']} ({r['fund']}, {r['weight']:.1%})" for _, r in sg["new_top10"].head(8).iterrows())))
        if len(sg["cluster"]):
            b.append(("p", "**Achats groupés (≥ 2 gérants)** : " + "; ".join(
                f"{r['Titre']} ({r['Acheteurs']} : {r['Qui']})" for _, r in sg["cluster"].head(8).iterrows())))
    if it.get("ok"):
        b.append(("break",))
        b.append(("h", "3. Analyse et interprétation du comité"))
        for a in it["avis"]:
            b.append(("p", f"**{a.get('nom', '')} — {a['titre']}**"))
            b.append(("bullets", a["points"]))
    if comp is not None and expo is not None:
        b.append(("break",))
        b.append(("h", f"4. Comparaison avec le portefeuille « {port_name or ''} »"))
        b.append(("kpis", [("Poche actions", f"{expo['equity_share']:.0%}"), ("Recouvrement", f"{comp['overlap']:.0%}"),
                           ("Part active", f"{comp['active_share']:.0%}"), ("Titres en commun", str(len(comp["common"])))]))
        if "05_comparaison" in imgs:
            b.append(("img", imgs["05_comparaison"], 17))
        rows = [["Secteur", "Mon portefeuille", "Gérants", "Écart", "Flux des gérants"]]
        for s, r in comp["sectors"].iterrows():
            f = r["Flux des gérants (pts)"]
            rows.append([s, f"{r['Mon portefeuille']:.1%}", f"{r['Meilleurs gérants']:.1%}", f"{r['Écart (pts)'] * 100:+.1f} pt",
                         f"{f * 100:+.1f} pt" if f == f else "—"])
        b.append(("table", rows, [5.2, 3.0, 2.6, 2.6, 3.0]))
        if reasons:
            b.append(("p", "**Pourquoi ces différences ?**"))
            b.append(("bullets", [f"{r['titre']} : {r['texte']}" for r in reasons]))
        if sugg:
            b.append(("p", "**Pistes proposées par le comité (à valider par vous, aucun ordre n'est passé)**"))
            b.append(("table", [["Action", "Proposée par", "Détail"]] + [[s["sens"], s["qui"], s["texte"]] for s in sugg],
                      [2.2, 3.4, 11.8]))
    b.append(("h", "Méthode et limites"))
    b.append(("p", "Source : formulaires 13F-HR déposés auprès de la SEC (EDGAR). Poids = valeur déclarée de la ligne / "
                   "valeur totale des actions déclarées par le gérant. « Moyenne des gérants » : chaque gérant compte "
                   "autant (un petit fonds de conviction pèse autant que Berkshire). Secteurs : classification GICS "
                   "simplifiée (code SIC de la SEC à défaut). Mouvements : comparaison du nombre d'actions avec le "
                   "trimestre précédent (± 2 %)."))
    b.append(("note", LIMITS_TEXT))
    b.append(("note", L.DISCLAIMER))
    return R.make_pdf("Tracking Best AM — où investissent les meilleurs gérants",
                      f"McKenson Asset Management · rapport d'analyse 13F · {R.stamp()}", b)


def build_excel(snap: dict, codes: list[str] | None = None, comp: dict | None = None) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        manager_stats(snap, codes).to_excel(xw, sheet_name="Gérants", index=False)
        sector_allocation(snap, codes).to_excel(xw, sheet_name="Secteurs")
        sector_matrix(snap, codes).to_excel(xw, sheet_name="Secteurs par gérant")
        consensus(snap, codes).to_excel(xw, sheet_name="Consensus")
        hf = holdings_frame(snap, codes)
        if not hf.empty:
            hf[["fund", "label", "issuer", "sector", "weight", "d_weight", "status", "rank", "value"]].rename(columns={
                "fund": "Fonds", "label": "Titre", "issuer": "Émetteur", "sector": "Secteur", "weight": "Poids",
                "d_weight": "Δ poids", "status": "Mouvement", "rank": "Rang", "value": "Valeur ($)"}).to_excel(
                xw, sheet_name="Positions", index=False)
        if comp is not None:
            comp["sectors"].to_excel(xw, sheet_name="Comparaison secteurs")
        pd.DataFrame(PLATFORMS).to_excel(xw, sheet_name="Plateformes", index=False)
        pd.DataFrame({"Avertissement": [LIMITS_TEXT]}).to_excel(xw, sheet_name="Limites", index=False)
    return buf.getvalue()


METHOD_STEPS = [
    ("Choisir ses gérants", "Des gérants à la démarche claire et stable, peu de rotation, portefeuilles concentrés : leurs "
                            "mouvements ont un sens (le bruit des gérants très actifs ou quantitatifs en a peu)."),
    ("Se concentrer sur les convictions", "Ignorer les petites lignes (couvertures, ajustements) ; regarder les positions "
                                          "de 5 % ou plus et les fortes hausses de poids."),
    ("Repérer les achats groupés", "Plusieurs bons gérants qui achètent le même titre le même trimestre, de façon "
                                   "indépendante : un filtre de qualité."),
    ("Regarder les nouvelles positions", "Une nouvelle ligne qui entre directement dans le top 10 traduit une forte "
                                         "conviction (le gérant ne l'a pas construite progressivement)."),
    ("Vérifier avant d'agir", "Valorisation actuelle (le cours a pu bouger depuis la fin du trimestre), marges, dette, "
                              "croissance ; reconstituer la thèse du gérant. Si on ne sait pas l'expliquer, on passe."),
]


def sector_report(snap: dict, codes: list[str] | None, sector: str, regime: str | None = None) -> dict:
    """Analyse d'un secteur : qui y investit, quels titres, flux, lecture du comité."""
    df = holdings_frame(snap, codes)
    if df.empty:
        return dict(ok=False)
    d = df[df["sector"] == sector]
    sa = sector_allocation(snap, codes)
    mat = sector_matrix(snap, codes)
    by_mgr = (mat[sector].sort_values(ascending=False) if sector in mat else pd.Series(dtype=float))
    cs = consensus(snap, codes)
    names = cs[cs["Secteur"] == sector].head(15)
    fav, pen = REGIME_SECTORS.get(regime or "", (set(), set()))
    row = sa.loc[sector] if sector in sa.index else None
    flow = float(row.get("Flux du trimestre (pts)", np.nan)) if row is not None else np.nan
    txt = [f"Poids moyen chez les gérants : {row['Moyenne des gérants']:.1%} ; {int(row['Gérants investis'])} gérant(s) "
           f"sur {mat.shape[0]} investis." if row is not None else "Secteur absent des portefeuilles."]
    if flow == flow:
        txt.append(f"Flux du dernier trimestre : {flow * 100:+.2f} pt — les gérants {'renforcent' if flow > 0 else 'allègent'} ce secteur.")
    if regime:
        txt.append(f"Régime officiel du comité « {regime} » : secteur "
                   + ("plutôt favorisé." if sector in fav else "plutôt pénalisé." if sector in pen else "neutre."))
    if len(names):
        txt.append("Titres les plus partagés : " + ", ".join(f"{r['Titre']} ({r['Gérants']})" for _, r in names.head(6).iterrows()) + ".")
    buy = d[d["status"].isin(["Nouvelle", "Renforcée"])]
    if len(buy):
        txt.append("Achats du trimestre : " + "; ".join(f"{r['label']} par {r['fund']}" for _, r in
                                                       buy.sort_values("weight", ascending=False).head(6).iterrows()) + ".")
    return dict(ok=True, sector=sector, by_manager=by_mgr, names=names, holdings=d, text=txt, flow=flow, etf=SECTOR_ETF.get(sector))


def build_sector_pdf(snap: dict, codes: list[str] | None, sectors: list[str], regime: str | None = None) -> bytes:
    """Rapport d'analyse sur un ou plusieurs secteurs où investissent les gérants (graphiques inclus)."""
    import matplotlib
    matplotlib.use("Agg")
    from utils import reporting as R
    from utils import legal as L
    b: list[tuple] = [("p", f"Analyse de {len(sectors)} secteur(s) à partir des 13F de "
                            f"{len(codes or snap['managers'])} gérants. Régime officiel du comité : {regime or '—'}.")]
    for i, s in enumerate(sectors):
        rep = sector_report(snap, codes, s, regime)
        if not rep.get("ok"):
            continue
        if i:
            b.append(("break",))
        b.append(("h", f"{i + 1}. {s}" + (f" (ETF de référence {rep['etf']})" if rep.get("etf") else "")))
        b.append(("bullets", rep["text"]))
        bm = rep["by_manager"][rep["by_manager"] > 0]
        if len(bm):
            fig, ax, t = R._fig("light", 9, 0.3 * len(bm) + 1.6)
            ax.barh(bm.index[::-1], bm.values[::-1] * 100, color=SECTOR_COLORS.get(s, "#0077b6"))
            R._title(ax, t, f"Poids de {s.lower()} dans chaque portefeuille", "% de la poche 13F du gérant")
            b.append(("img", R._png(fig), 16))
        nm = rep["names"]
        if len(nm):
            fig, ax, t = R._fig("light", 9, 0.3 * len(nm) + 1.6)
            ax.barh(nm["Titre"].astype(str)[::-1], nm["Poids dans la moyenne des gérants"][::-1] * 100, color="#0077b6")
            R._title(ax, t, "Titres du secteur les plus présents", "poids dans l'allocation moyenne des gérants (%)")
            b.append(("img", R._png(fig), 16))
            b.append(("table", [["Titre", "Gérants", "Détenu par", "Poids moyen", "Nouv.", "Renf.", "All."]] +
                      [[str(r["Titre"]), str(r["Gérants"]), r["Détenu par"][:70], f"{r['Poids dans la moyenne des gérants']:.1%}",
                        str(r["Nouvelles"]), str(r["Renforcées"]), str(r["Allégées"])] for _, r in nm.iterrows()],
                      [2.0, 1.4, 8.0, 2.0, 1.2, 1.2, 1.2]))
    b.append(("note", LIMITS_TEXT))
    b.append(("note", L.DISCLAIMER))
    return R.make_pdf("Analyse sectorielle — où investissent les meilleurs gérants",
                      f"McKenson Asset Management · {', '.join(sectors)[:90]} · {R.stamp()}", b)



# ══════════════════════════════════════════════════════════════════════════════
#  HISTORIQUE : DEPUIS QUAND, EN QUELLE PROPORTION ; PLUS DÉTENUS / PLUS VENDUS
# ══════════════════════════════════════════════════════════════════════════════
def quarter_label(period: str | None) -> str:
    """« 2026-06-30 » → « T2 2026 »."""
    try:
        d = datetime.strptime(str(period)[:10], "%Y-%m-%d")
        return f"T{(d.month - 1) // 3 + 1} {d.year}"
    except Exception:
        return str(period or "—")


def compact_history(quarters: list[tuple[str, pd.DataFrame]], min_weight: float = 0.001) -> dict:
    """[(période, positions agrégées)] du plus récent au plus ancien → {periods, rows: {cusip: [[actions, poids]|None…]}}."""
    periods = [p for p, _ in quarters]
    tabs = []
    for _, df in quarters:
        if df is None or df.empty:
            tabs.append({})
            continue
        tot = float(df["value"].sum()) or 1.0
        tabs.append({c: (float(sh), float(v) / tot) for c, sh, v in zip(df["cusip"], df["shares"], df["value"])})
    keys = set()
    for t in tabs:
        keys |= {c for c, (_, w) in t.items() if w >= min_weight}
    rows = {c: [[round(t[c][0], 2), round(t[c][1], 6)] if c in t else None for t in tabs] for c in keys}
    return dict(periods=periods, rows=rows)


def _since(hist_row: list, periods: list[str]) -> tuple[str, int, bool]:
    """(trimestre de début de détention, nombre de trimestres consécutifs, détenu avant la fenêtre ?)."""
    n = 0
    for x in hist_row:
        if x and x[0] > 0:
            n += 1
        else:
            break
    if n == 0:
        return "—", 0, False
    return periods[n - 1], n, n == len(periods)


def _selling_since(hist_row: list, periods: list[str]) -> tuple[str | None, float]:
    """Début de la vente (trimestre de la première baisse consécutive) et part des actions vendues depuis le pic."""
    sh = [(x[0] if x else 0.0) for x in hist_row]
    i = 0
    while i + 1 < len(sh) and sh[i] < sh[i + 1] * 0.98:
        i += 1
    if i == 0 or sh[i] <= 0:
        return None, 0.0
    return periods[i - 1], 1 - sh[0] / sh[i]


def position_history(snap: dict, codes: list[str] | None = None) -> pd.DataFrame:
    """Une ligne par (gérant, titre détenu ou vendu) : depuis quand, poids au début / maintenant, ventes."""
    out = []
    for code, m in snap.get("managers", {}).items():
        if codes and code not in codes:
            continue
        hist = m.get("history") or {}
        periods, rows = hist.get("periods") or [m.get("period")], hist.get("rows") or {}
        for h in m.get("holdings", []):
            r = rows.get(h["cusip"])
            if r:
                since, n, before = _since(r, periods)
                first_w = next((x[1] for x in reversed(r[:n]) if x), np.nan)
                sell_from, sold_pct = _selling_since(r, periods)
                peak = max((x[1] for x in r if x), default=np.nan)
            else:
                since, n, before = (m.get("prev_period") if h.get("status") not in ("Nouvelle",) and m.get("prev_period")
                                    else m.get("period") or "—"), 0, False
                first_w, sell_from, sold_pct, peak = np.nan, None, 0.0, np.nan
                if h.get("status") == "Allégée" and h.get("chg_shares") == h.get("chg_shares") and h.get("chg_shares") is not None:
                    sell_from, sold_pct = m.get("period"), -float(h["chg_shares"])
            out.append(dict(code=code, fund=m["fund"], key=h.get("ticker") or h["cusip"], titre=h.get("ticker") or h.get("issuer"),
                            issuer=h.get("issuer"), sector=h.get("sector") or "Non classé", weight=h.get("weight"),
                            status=h.get("status"), since=since, quarters=n, before_window=before, first_weight=first_w,
                            peak_weight=peak, selling_since=sell_from, sold_pct=sold_pct, sold_out=False,
                            value=h.get("value"), prev_value=h.get("prev_value")))
        for s in m.get("sold", []):
            r = rows.get(s["cusip"])
            sell_from, since = m.get("period"), "—"
            if r:
                sh = [(x[0] if x else 0.0) for x in r]
                j = 1
                while j + 1 < len(sh) and sh[j] < sh[j + 1] * 0.98:
                    j += 1
                sell_from = periods[j - 1]
                k = 1
                while k < len(sh) and sh[k] > 0:
                    k += 1
                since = periods[k - 1]
            out.append(dict(code=code, fund=m["fund"], key=s.get("ticker") or s["cusip"], titre=s.get("ticker") or s.get("issuer"),
                            issuer=s.get("issuer"), sector=s.get("sector") or "Non classé", weight=0.0, status="Soldée",
                            since=since, quarters=0, before_window=False, first_weight=np.nan,
                            peak_weight=s.get("prev_weight"), selling_since=sell_from, sold_pct=1.0, sold_out=True,
                            value=0.0, prev_value=s.get("prev_value")))
    return pd.DataFrame(out)


def most_held(snap: dict, codes: list[str] | None = None, n: int = 25) -> pd.DataFrame:
    """Les actifs les plus détenus : par combien de gérants, quelle proportion, depuis quand."""
    cs = consensus(snap, codes)
    ph = position_history(snap, codes)
    if cs.empty:
        return cs
    held = ph[~ph["sold_out"]] if not ph.empty else ph
    tot_val = float(cs["Valeur totale ($)"].sum()) or 1.0
    rows = []
    for k, r in cs.head(n).iterrows():
        g = held[held["key"] == k] if not held.empty else pd.DataFrame()
        oldest = min((x for x in g["since"] if x and x != "—"), default=None) if len(g) else None
        before = bool(g["before_window"].any()) if len(g) else False
        longest = g.sort_values("quarters", ascending=False).iloc[0] if len(g) else None
        rows.append({"Titre": r["Titre"], "Émetteur": r["Émetteur"], "Secteur": r["Secteur"], "Gérants": r["Gérants"],
                     "Détenu par": r["Détenu par"], "Poids moyen chez les gérants": r["Poids dans la moyenne des gérants"],
                     "Poids max": r["Poids max"], "Part de la valeur suivie": r["Valeur totale ($)"] / tot_val,
                     "Valeur détenue ($)": r["Valeur totale ($)"],
                     "Détenu depuis": ("avant " if before else "") + quarter_label(oldest) if oldest else "—",
                     "Le plus ancien détenteur": longest["fund"] if longest is not None else "—",
                     "Durée moy. (trim.)": float(g["quarters"].mean()) if len(g) and g["quarters"].sum() else np.nan,
                     "Mouvements": f"{r['Nouvelles']} nouv. · {r['Renforcées']} renf. · {r['Allégées']} all."})
    return pd.DataFrame(rows)


def most_sold(snap: dict, codes: list[str] | None = None, n: int = 25) -> pd.DataFrame:
    """Les actifs les plus vendus : combien de gérants, quelle proportion de leurs actions, depuis quand, quel montant."""
    ph = position_history(snap, codes)
    if ph.empty:
        return ph
    s = ph[(ph["sold_out"]) | (ph["status"] == "Allégée") | (ph["sold_pct"] > 0.02)].copy()
    if s.empty:
        return pd.DataFrame()
    s["value_sold"] = [max(float(pv or 0) - float(v or 0), 0.0) if (pv == pv and pv is not None) else np.nan
                       for pv, v in zip(s["prev_value"], s["value"])]
    rows = []
    for k, g in s.groupby("key"):
        start = min((x for x in g["selling_since"] if x), default=None)
        rows.append({"Titre": g["titre"].iloc[0], "Secteur": g["sector"].iloc[0], "Vendeurs": g["code"].nunique(),
                     "Soldé par": ", ".join(sorted(g[g["sold_out"]]["fund"])) or "—",
                     "Allégé par": ", ".join(f"{f} (−{p:.0%})" for f, p in zip(g[~g["sold_out"]]["fund"], g[~g["sold_out"]]["sold_pct"])) or "—",
                     "Part vendue (moyenne)": float(g["sold_pct"].mean()),
                     "Montant vendu estimé ($)": float(np.nansum(g["value_sold"])) if g["value_sold"].notna().any() else np.nan,
                     "Poids avant (max)": float(np.nanmax(g["peak_weight"])) if g["peak_weight"].notna().any() else np.nan,
                     "Ventes depuis": quarter_label(start) if start else "—"})
    out = pd.DataFrame(rows)
    return out.sort_values(["Vendeurs", "Montant vendu estimé ($)"], ascending=False).head(n).reset_index(drop=True)


# ══════════════════════════════════════════════════════════════════════════════
#  ÉQUIVALENTS INVESTISSABLES ET ALIMENTATION DES CSV DE MIP
# ══════════════════════════════════════════════════════════════════════════════
ASSETS_FILE = Path(__file__).parent.parent / "data" / "assets_best_am.csv"
# ETF sectoriels : États-Unis (SPDR, déjà dans data/assets.csv), UCITS (iShares S&P 500 sectoriels, Londres),
# PEA (pas d'ETF sectoriel américain éligible : Nasdaq-100 PEA pour la tech, MSCI World PEA sinon)
SECTOR_UCITS = {"Technologie": "IUIT.L", "Finance": "IUFS.L", "Santé": "IUHC.L", "Énergie": "IUES.L",
                "Consommation discrétionnaire": "IUCD.L", "Consommation de base": "IUCS.L", "Industrie": "IUIS.L",
                "Matériaux": "IUMS.L", "Services publics": "IUUS.L"}
SECTOR_UCITS_NAMES = {"IUIT.L": "iShares S&P 500 Information Technology Sector UCITS ETF",
                      "IUFS.L": "iShares S&P 500 Financials Sector UCITS ETF",
                      "IUHC.L": "iShares S&P 500 Health Care Sector UCITS ETF",
                      "IUES.L": "iShares S&P 500 Energy Sector UCITS ETF",
                      "IUCD.L": "iShares S&P 500 Consumer Discretionary Sector UCITS ETF",
                      "IUCS.L": "iShares S&P 500 Consumer Staples Sector UCITS ETF",
                      "IUIS.L": "iShares S&P 500 Industrials Sector UCITS ETF",
                      "IUMS.L": "iShares S&P 500 Materials Sector UCITS ETF",
                      "IUUS.L": "iShares S&P 500 Utilities Sector UCITS ETF"}
SECTOR_PEA = {"Technologie": "PANX.PA", "Communication & médias": "PANX.PA"}


def equivalents(ticker: str, sector: str) -> dict:
    """Comment investir dans le même actif (ou son équivalent) depuis MIP."""
    t = str(ticker or "").upper()
    direct = bool(t) and re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", t) is not None
    return dict(direct=t if direct else "", etf_us=SECTOR_ETF.get(sector, "SPY"),
                etf_ucits=SECTOR_UCITS.get(sector, "CSPX.L"), etf_pea=SECTOR_PEA.get(sector, "EWLD.PA"),
                note=("Action américaine : achetable en direct sur un compte-titres (non éligible au PEA)." if direct else
                      "Ticker non identifié : passer par l'ETF du secteur."))


def assets_frame(snap: dict, codes: list[str] | None = None, min_holders: int = 1, top_per_manager: int = 15) -> pd.DataFrame:
    """Actifs des gérants au format des CSV de MIP (ticker,name,category,contract_mult,currency + colonnes Best AM)."""
    df = holdings_frame(snap, codes)
    if df.empty:
        return pd.DataFrame()
    keep = df[(df["rank"] <= top_per_manager) | (df["weight"] >= 0.03)]
    cs = consensus(snap, codes)
    sold = most_sold(snap, codes, 200)
    sold_keys = set(sold["Titre"]) if len(sold) else set()
    rows, seen = [], set()
    for k in list(keep["key"].unique()) + [k for k in cs.index if cs.loc[k, "Gérants"] >= max(2, min_holders)]:
        if k in seen or k not in cs.index:
            continue
        seen.add(k)
        r = cs.loc[k]
        t = str(r["Titre"])
        if not re.fullmatch(r"[A-Z]{1,5}(-[A-Z])?", t) or r["Gérants"] < min_holders:
            continue
        sec = r["Secteur"]
        eq = equivalents(t, sec)
        cat = "ETF" if sec == "ETF & fonds indiciels" else "Equity"
        rows.append(dict(ticker=t, name=str(r["Émetteur"]).title()[:60], category=cat, contract_mult=100, currency="USD",
                         source="Best AM (13F)", secteur=sec, gerants=int(r["Gérants"]), detenu_par=r["Détenu par"],
                         poids_moyen_gerants=round(float(r["Poids dans la moyenne des gérants"]), 5),
                         mouvement=f"{r['Nouvelles']} nouv., {r['Renforcées']} renf., {r['Allégées']} all., {r['Soldées']} sold.",
                         plus_vendu="Oui" if t in sold_keys else "Non",
                         equivalent_etf_us=eq["etf_us"], equivalent_etf_ucits=eq["etf_ucits"], equivalent_etf_pea=eq["etf_pea"],
                         periode=max((snap["managers"][c].get("period") or "" for c in (codes or snap["managers"])), default="")))
    return pd.DataFrame(rows).sort_values(["gerants", "poids_moyen_gerants"], ascending=False).reset_index(drop=True)


def sync_assets(snap: dict, codes: list[str] | None = None, path: Path | None = None) -> dict:
    """Écrit data/assets_best_am.csv (fusionné automatiquement par utils.data.load_assets dans tout MIP :
    Trading Desk → univers « 🐋 Best AM », Technique, Optimizer…) + les ETF équivalents UCITS manquants."""
    path = path or ASSETS_FILE
    df = assets_frame(snap, codes)
    if df.empty:
        return dict(ok=False, n=0)
    try:
        existing = set(pd.read_csv(path.parent / "assets.csv")["ticker"]) | set(pd.read_csv(path.parent / "assets_etf.csv")["ticker"])
    except Exception:
        existing = set()
    etf = [dict(ticker=t, name=SECTOR_UCITS_NAMES[t], category="ETF", contract_mult=100, currency="USD",
                source="Équivalent UCITS (Best AM)", secteur=s, gerants=0, detenu_par="", poids_moyen_gerants=0.0,
                mouvement="", plus_vendu="", equivalent_etf_us=SECTOR_ETF.get(s, ""), equivalent_etf_ucits=t,
                equivalent_etf_pea=SECTOR_PEA.get(s, "EWLD.PA"), periode="")
           for s, t in SECTOR_UCITS.items() if t not in existing]
    out = pd.concat([df, pd.DataFrame(etf)], ignore_index=True)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(path, index=False)
    except Exception:
        return dict(ok=False, n=len(df), csv=out.to_csv(index=False).encode("utf-8-sig"))
    return dict(ok=True, n=len(df), new=len([t for t in df["ticker"] if t not in existing]), path=str(path),
                at=datetime.now().strftime("%Y-%m-%d %H:%M"))


def assets_csv_bytes(snap: dict, codes: list[str] | None = None) -> bytes:
    df = assets_frame(snap, codes)
    return df.to_csv(index=False).encode("utf-8")


def best_am_tickers() -> list[str]:
    try:
        return list(pd.read_csv(ASSETS_FILE)["ticker"])
    except Exception:
        return []
