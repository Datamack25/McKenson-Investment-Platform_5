# utils/costs.py  —  MAM v5.8 · Coûts de transaction réalistes
"""
Chaque ordre simulé supporte les coûts qu'il supporterait chez un courtier en ligne :

1. ÉCART ACHAT-VENTE (spread) : on achète au prix vendeur, on vend au prix acheteur.
   Le cours affiché est le cours médian ; l'exécution se fait à ± un demi-écart.
2. COURTAGE : pourcentage du montant, avec un minimum par ordre, selon le marché.
3. TAXES DE BOURSE à l'achat :
   * taxe française sur les transactions financières (TTF) : 0,4 % depuis le 1er avril 2025,
     sur les actions de sociétés françaises de plus d'un milliard d'euros de capitalisation ;
   * droit de timbre britannique (SDRT) : 0,5 % sur les actions de sociétés britanniques.
   Les ETF en sont exonérés.
4. OPTIONS : commission par contrat + demi-écart sur la prime.

Les barèmes sont modifiables ici (source unique). Les coûts sont enregistrés avec chaque
ordre (« frais ») et déduits des liquidités : la performance est donc nette de coûts de
transaction, comme l'exige GIPS.
"""
from __future__ import annotations

# demi-écart (fraction du cours), courtage (fraction), minimum par ordre (USD)
SCHEDULE = {
    "us_etf":      dict(half_spread=0.0001, commission=0.0005, minimum=1.0,
                        label="ETF coté aux États-Unis"),
    "us_equity":   dict(half_spread=0.0003, commission=0.0005, minimum=1.0,
                        label="Action cotée aux États-Unis"),
    "eu_etf":      dict(half_spread=0.0005, commission=0.0010, minimum=2.0, label="ETF coté en Europe"),
    "eu_equity":   dict(half_spread=0.0005, commission=0.0010, minimum=3.0,
                        label="Action cotée en Europe / Royaume-Uni / Suisse"),
    "asia_equity": dict(half_spread=0.0010, commission=0.0015, minimum=5.0, label="Action cotée en Asie"),
    "crypto":      dict(half_spread=0.0010, commission=0.0015, minimum=1.0, label="Crypto-actif"),
    "future":      dict(half_spread=0.0002, commission=0.0002, minimum=2.0, label="Contrat à terme / matière première"),
    "forex":       dict(half_spread=0.0001, commission=0.0, minimum=0.0, label="Devises"),
    "index":       dict(half_spread=0.0002, commission=0.0005, minimum=1.0, label="Indice"),
}
TTF_RATE = 0.004            # France, depuis le 1er avril 2025
UK_STAMP_RATE = 0.005       # Royaume-Uni (SDRT)
# Sociétés françaises soumises à la TTF (capitalisation > 1 Md€) présentes dans l'univers
TTF_TICKERS = {"TTE.PA", "BNP.PA", "MC.PA", "OR.PA", "SAN.PA", "CS.PA", "SU.PA", "HO.PA", "AI.PA", "BN.PA",
               "DG.PA", "EL.PA", "KER.PA", "RI.PA", "SGO.PA", "GLE.PA", "ACA.PA", "ORA.PA", "VIE.PA", "CAP.PA"}
UK_STAMP_TICKERS = {"HSBA.L", "BP.L", "SHEL.L", "RIO.L", "AZN.L", "ULVR.L", "GSK.L", "BARC.L", "LLOY.L", "VOD.L"}
OPTION_PER_CONTRACT = 0.65  # USD par contrat
OPTION_HALF_SPREAD = 0.015  # 1,5 % de la prime de part et d'autre du milieu de fourchette

_EU_SUFFIX = (".PA", ".DE", ".AS", ".MI", ".MC", ".BR", ".LS", ".IR", ".VI", ".HE", ".SW", ".L", ".ST", ".CO",
              ".OL")
_ASIA_SUFFIX = (".T", ".HK", ".KS", ".NS", ".SS", ".SZ", ".TW", ".SI", ".AX")
_ENABLED = True


def enable(flag: bool = True):
    """Tests : désactive les coûts pour vérifier un calcul brut."""
    global _ENABLED
    _ENABLED = bool(flag)


def _is_etf(ticker: str) -> bool:
    try:
        from utils.sectors import sector_of
        return sector_of(ticker).startswith(("ETF", "ETC"))
    except Exception:
        return False


def market_of(ticker: str) -> str:
    t = str(ticker or "").upper()
    if t.endswith(("-USD", "-EUR")):
        return "crypto"
    if t.endswith("=F"):
        return "future"
    if t.endswith("=X"):
        return "forex"
    if t.startswith("^"):
        return "index"
    etf = _is_etf(t)
    if t.endswith(_ASIA_SUFFIX):
        return "asia_equity"
    if t.endswith(_EU_SUFFIX):
        return "eu_etf" if etf else "eu_equity"
    return "us_etf" if etf else "us_equity"


def spot_costs(ticker: str, side: str, qty: float, mid_price: float) -> dict:
    """Coûts d'un ordre au comptant. Renvoie le prix d'exécution (USD), les frais (courtage + taxe)
    et le détail lisible."""
    buy = str(side).upper().startswith("BUY")
    m = market_of(ticker)
    sch = SCHEDULE[m]
    if not _ENABLED or qty <= 0 or mid_price <= 0:
        return dict(prix=float(mid_price), frais=0.0, courtage=0.0, taxe=0.0, ecart=0.0, marche=sch["label"],
                    detail="sans frais")
    hs = sch["half_spread"]
    px = mid_price * (1 + hs) if buy else mid_price * (1 - hs)
    notional = qty * px
    courtage = max(sch["minimum"], notional * sch["commission"]) if sch["commission"] or sch["minimum"] else 0.0
    t = str(ticker).upper()
    taxe, taxe_lab = 0.0, ""
    if buy and t in TTF_TICKERS:
        taxe, taxe_lab = notional * TTF_RATE, f"TTF {TTF_RATE:.1%}"
    elif buy and t in UK_STAMP_TICKERS:
        taxe, taxe_lab = notional * UK_STAMP_RATE, f"droit de timbre britannique {UK_STAMP_RATE:.1%}"
    ecart = qty * abs(px - mid_price)
    detail = (f"{sch['label']} : écart {hs:.2%} ({ecart:,.2f} $), courtage {courtage:,.2f} $"
              + (f", {taxe_lab} {taxe:,.2f} $" if taxe else "")).replace(",", " ")
    return dict(prix=float(px), frais=round(courtage + taxe, 2), courtage=round(courtage, 2), taxe=round(taxe, 2),
                ecart=round(ecart, 2), marche=sch["label"], detail=detail)


def total_cost(ticker: str, side: str, qty: float, mid_price: float) -> float:
    """Débit (achat) ou crédit (vente) total en liquidités, frais compris."""
    c = spot_costs(ticker, side, qty, mid_price)
    gross = qty * c["prix"]
    return gross + c["frais"] if str(side).upper().startswith("BUY") else gross - c["frais"]


def affordable_qty(ticker: str, cash: float, mid_price: float, qty_wanted: float) -> float:
    """Plus grande quantité ≤ qty_wanted payable avec `cash`, frais compris."""
    if qty_wanted <= 0 or mid_price <= 0:
        return 0.0
    if total_cost(ticker, "BUY", qty_wanted, mid_price) <= cash + 1e-6:
        return qty_wanted
    lo, hi = 0.0, qty_wanted
    for _ in range(40):
        mid = (lo + hi) / 2
        if total_cost(ticker, "BUY", mid, mid_price) <= cash:
            lo = mid
        else:
            hi = mid
    return lo


def option_costs(side: str, n_contracts: int, mid_premium: float) -> dict:
    """Prime d'exécution (par unité) et commission d'un ordre d'options."""
    buy = str(side).upper().startswith("BUY")
    if not _ENABLED or n_contracts <= 0:
        return dict(prime=float(mid_premium), frais=0.0)
    prime = mid_premium * (1 + OPTION_HALF_SPREAD) if buy else mid_premium * (1 - OPTION_HALF_SPREAD)
    return dict(prime=float(max(prime, 0.0)), frais=round(OPTION_PER_CONTRACT * int(n_contracts), 2))


def describe() -> list[str]:
    out = [f"{v['label']} : écart {v['half_spread']:.2%} de part et d'autre, courtage {v['commission']:.2%} "
           f"(minimum {v['minimum']:.0f} $)" for v in SCHEDULE.values()]
    out.append(f"Taxe française sur les transactions financières : {TTF_RATE:.1%} à l'achat d'actions françaises "
               "de plus d'un milliard d'euros de capitalisation (ETF exonérés).")
    out.append(f"Droit de timbre britannique : {UK_STAMP_RATE:.1%} à l'achat d'actions britanniques (ETF exonérés).")
    out.append(f"Options : {OPTION_PER_CONTRACT:.2f} $ par contrat + écart de {OPTION_HALF_SPREAD:.1%} sur la prime.")
    return out
