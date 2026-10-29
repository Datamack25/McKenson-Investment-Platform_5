# utils/ledger.py  —  MAM v5.8 · Journal des mouvements de liquidités et flux externes
"""
Tout ce qui fait bouger les liquidités d'un portefeuille, en dehors des achats et ventes au
comptant et des primes d'options, est inscrit dans port["mouvements"] :

  type        sens   nature
  ─────────── ────── ────────────────────────────────────────────────────────────────
  apport      +      flux EXTERNE : l'administrateur (ou l'investisseur) ajoute du cash
  retrait     −      flux EXTERNE : du cash est retiré du portefeuille
  dividende   +      revenu : dividende net de retenue à la source, versé à la date de détachement
  interet     +      revenu : intérêts monétaires quotidiens sur les liquidités
  frais       −      coût : commissions d'options, autres frais

Seuls les apports et retraits sont des flux EXTERNES : la performance pondérée dans le
temps (TWR, norme GIPS) les neutralise, ce qui fait qu'un apport ou un retrait décidé par
l'administrateur ne change pas la performance. Les revenus et les frais, eux, en font partie.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

EXTERNAL = ("apport", "retrait")
TYPES = ("apport", "retrait", "dividende", "interet", "frais")
LABEL = {"apport": "Apport de liquidités", "retrait": "Retrait de liquidités", "dividende": "Dividende",
         "interet": "Intérêts sur liquidités", "frais": "Frais"}


def add(port: dict, kind: str, amount: float, *, date: str | None = None, ticker: str | None = None,
        detail: str = "", author: str | None = None, apply_cash: bool = True) -> dict:
    """Inscrit un mouvement (montant positif ; le sens dépend du type) et met à jour les liquidités."""
    assert kind in TYPES, kind
    amt = abs(float(amount))
    signed = -amt if kind in ("retrait", "frais") else amt
    rec = dict(date=date or datetime.now().strftime("%Y-%m-%d %H:%M"), type=kind, montant=round(signed, 6))
    if ticker:
        rec["ticker"] = ticker
    if detail:
        rec["detail"] = detail
    if author:
        rec["auteur"] = author
    port.setdefault("mouvements", []).append(rec)
    if apply_cash:
        port["cash"] = float(port.get("cash", 0.0)) + signed
    return rec


def external_flow(port: dict, amount: float, author: str | None = None, note: str = "") -> tuple[bool, str]:
    """Apport (montant > 0) ou retrait (montant < 0) de liquidités par l'administrateur."""
    amount = float(amount)
    if amount == 0:
        return False, "Montant nul."
    if amount < 0 and -amount > float(port.get("cash", 0.0)) + 1e-6:
        return False, (f"Retrait impossible : {-amount:,.0f} $ demandés pour {port.get('cash', 0):,.0f} $ de "
                       "liquidités (vendre des titres d'abord).").replace(",", " ")
    add(port, "apport" if amount > 0 else "retrait", amount, author=author, detail=note)
    return True, (f"{'Apport' if amount > 0 else 'Retrait'} de {abs(amount):,.0f} $ enregistré. Il est traité comme "
                  "un flux externe : la performance (TWR) n'est pas modifiée.").replace(",", " ")


def movements(port: dict, kinds: tuple | None = None) -> pd.DataFrame:
    rows = [m for m in port.get("mouvements", []) or [] if not kinds or m.get("type") in kinds]
    if not rows:
        return pd.DataFrame(columns=["date", "type", "montant", "ticker"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "ticker" not in df:
        df["ticker"] = None
    return df.dropna(subset=["date"]).sort_values("date")


def net_external(port: dict) -> float:
    """Apports − retraits de liquidités depuis la création."""
    return float(sum(m.get("montant", 0) for m in port.get("mouvements", []) or [] if m.get("type") in EXTERNAL))


def has_external_flows(port: dict) -> bool:
    return any(m.get("type") in EXTERNAL for m in port.get("mouvements", []) or [])


def daily_sum(port: dict, kinds: tuple, index: pd.DatetimeIndex, by_ticker: bool = False):
    """Somme quotidienne des mouvements (alignée sur `index` : un mouvement tombant un jour non
    coté est rattaché au jour coté suivant)."""
    df = movements(port, kinds)
    if df.empty or len(index) == 0:
        return pd.DataFrame(index=index) if by_ticker else pd.Series(0.0, index=index)
    pos = index.searchsorted(df["date"].dt.normalize())
    df = df[pos < len(index)].copy()
    df["jour"] = index[pos[pos < len(index)]]
    if by_ticker:
        return df.pivot_table(index="jour", columns="ticker", values="montant", aggfunc="sum") \
            .reindex(index).fillna(0.0)
    return df.groupby("jour")["montant"].sum().reindex(index).fillna(0.0)


# ══════════════════════════════════════════════════════════════════════════════
#  PERFORMANCE PONDÉRÉE DANS LE TEMPS (GIPS)
# ══════════════════════════════════════════════════════════════════════════════
def twr_returns(nav: pd.Series, flows: pd.Series) -> pd.Series:
    """Rendements quotidiens pondérés dans le temps.
    Convention : le flux externe du jour t est disponible en début de journée,
        r_t = V_t / (V_{t−1} + F_t) − 1.
    Valorisation quotidienne = TWR « vrai » (pas d'approximation de Dietz)."""
    nav = nav.astype(float)
    f = flows.reindex(nav.index).fillna(0.0)
    base = nav.shift(1) + f
    r = nav / base - 1
    return r.iloc[1:].where(base.iloc[1:] > 0, 0.0).fillna(0.0)


def twr_index(nav: pd.Series, flows: pd.Series, start_value: float | None = None) -> pd.Series:
    """Indice de richesse : valeur qu'aurait un portefeuille sans apport ni retrait (chaînage
    géométrique des rendements quotidiens), démarrant à la première valeur (ou start_value)."""
    if nav is None or len(nav.dropna()) == 0:
        return pd.Series(dtype=float)
    r = twr_returns(nav, flows)
    v0 = float(start_value if start_value is not None else nav.iloc[0])
    idx = pd.concat([pd.Series([1.0], index=[nav.index[0]]), (1 + r).cumprod()]) * v0
    return idx.rename(nav.name)


def annualize(total: float, days: int) -> float | None:
    """GIPS : un rendement n'est annualisé que si la période couvre au moins un an."""
    if days is None or days < 365 or total is None:
        return None
    return (1 + total) ** (365.25 / days) - 1
