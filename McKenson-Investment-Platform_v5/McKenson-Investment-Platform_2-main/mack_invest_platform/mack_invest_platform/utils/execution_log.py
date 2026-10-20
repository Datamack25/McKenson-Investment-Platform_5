# utils/execution_log.py  —  MAM v5.4 · Journal des écarts entre recommandation et exécution
"""
Chaque fois qu'un plan recommandé (Hedge Fund Agent, optimisation du comité,
Auto-Portefeuille) est exécuté, on enregistre dans le journal du desk :
* les ordres RECOMMANDÉS (quantité, montant) ;
* les ordres réellement EXÉCUTÉS (relus dans l'historique des transactions) ;
* l'écart ligne par ligne et sa cause (bloqué par la conformité, cash insuffisant,
  exécution partielle…) ;
* l'allocation CIBLE, pour mesurer ensuite la dérive du portefeuille.

Le suivi (follow_up) compare plus tard la cible à la composition actuelle :
la boucle décision → exécution → suivi est ainsi complète et traçable.
"""
from __future__ import annotations

import re
from datetime import datetime

import pandas as pd


def _norm_orders(orders: pd.DataFrame | None) -> pd.DataFrame:
    if orders is None or len(orders) == 0:
        return pd.DataFrame(columns=["ticker", "action", "qty", "price", "montant"])
    o = orders.copy()
    if "montant" not in o.columns:
        o["montant"] = o["qty"].astype(float) * o["price"].astype(float)
    return o[["ticker", "action", "qty", "price", "montant"]]


def compare(recommended: pd.DataFrame | None, executed_trades: list[dict], refusals: list[str]) -> pd.DataFrame:
    """Tableau recommandation / exécution, une ligne par (ticker, sens)."""
    rec = _norm_orders(recommended)
    ex = pd.DataFrame([dict(ticker=t["ticker"], action=str(t["action"]).upper(), qty=float(t.get("qty", 0)),
                            montant=float(t.get("total", float(t.get("qty", 0)) * float(t.get("price", 0)))))
                       for t in executed_trades if str(t.get("action", "")).upper() in ("BUY", "SELL")])
    if ex.empty:
        ex = pd.DataFrame(columns=["ticker", "action", "qty", "montant"])
    r = rec.groupby(["ticker", "action"], as_index=False)[["qty", "montant"]].sum()
    e = ex.groupby(["ticker", "action"], as_index=False)[["qty", "montant"]].sum()
    m = r.merge(e, on=["ticker", "action"], how="outer", suffixes=("_reco", "_exec")).fillna(0.0)
    reasons = {}
    for msg in refusals or []:
        tk = re.split(r"[ :]", str(msg).strip(), maxsplit=1)[0]
        reasons.setdefault(tk, str(msg))

    def status(row):
        if row["qty_reco"] <= 0 and row["qty_exec"] > 0:
            return "hors plan", ""
        why = reasons.get(row["ticker"], "")
        if row["qty_exec"] <= 1e-12:
            if "bloqué" in why:
                return "bloqué (conformité)", why
            if "cash" in why:
                return "non exécuté (cash)", why
            return "non exécuté", why
        ratio = row["qty_exec"] / row["qty_reco"] if row["qty_reco"] else 1.0
        if ratio < 0.99:
            return "partiel", why or "quantité disponible inférieure à la recommandation"
        return "exécuté", ""

    if m.empty:
        return m.assign(statut=pd.Series(dtype=str), raison=pd.Series(dtype=str), ecart_montant=pd.Series(dtype=float))
    st_ = m.apply(status, axis=1, result_type="expand")
    m["statut"], m["raison"] = st_[0], st_[1]
    m["ecart_montant"] = m["montant_exec"] - m["montant_reco"]
    return m.sort_values(["statut", "ticker"]).reset_index(drop=True)


def record_execution(port: dict, source: str, recommended: pd.DataFrame | None, trades_before: int,
                     refusals: list[str], target_weights: dict | pd.Series | None = None,
                     hedges_done: list | None = None, extra: dict | None = None) -> str | None:
    """Enregistre l'écart recommandation / exécution dans le journal du desk."""
    from utils import advisor as A
    executed = (port.get("trades") or [])[trades_before:]
    cmp_ = compare(recommended, executed, refusals)
    reco_amt = float(cmp_["montant_reco"].sum()) if len(cmp_) else 0.0
    exec_amt = float(cmp_.loc[cmp_["montant_reco"] > 0, "montant_exec"].clip(upper=cmp_["montant_reco"]).sum()) \
        if len(cmp_) else 0.0
    tw = target_weights.to_dict() if isinstance(target_weights, pd.Series) else (target_weights or {})
    entry = dict(
        type="execution", decision="exécution d'un plan", date=datetime.now().strftime("%Y-%m-%d %H:%M"),
        portefeuille=port.get("name"), portefeuille_id=port.get("id"), source=source,
        lignes=cmp_.round(6).to_dict("records"), cible={k: float(v) for k, v in tw.items() if float(v) > 1e-6},
        taux_execution=(exec_amt / reco_amt) if reco_amt else 1.0, montant_recommande=reco_amt,
        montant_execute=exec_amt, n_bloques=int((cmp_["statut"] == "bloqué (conformité)").sum()) if len(cmp_) else 0,
        couvertures=hedges_done or [], refus=list(refusals or []), **(extra or {}))
    return A.append_journal(entry)


def executions(journal: list) -> list[dict]:
    return [e for e in journal if e.get("type") == "execution"]


def follow_up(entry: dict, port: dict | None, live: dict) -> tuple[pd.DataFrame, float]:
    """Dérive depuis l'exécution : poids cible vs poids actuel. Renvoie (tableau, dérive totale)."""
    target = pd.Series(entry.get("cible") or {}, dtype=float)
    if port is None or target.empty:
        return pd.DataFrame(), float("nan")
    hold = port.get("holdings", {}) or {}
    vals = {t: float(h.get("qty", 0)) * float((live.get(t) or (h.get("avg_price", 0), 0))[0]) for t, h in hold.items()}
    nav = float(port.get("cash", 0.0)) + sum(vals.values())
    if nav <= 0:
        return pd.DataFrame(), float("nan")
    cur = pd.Series(vals, dtype=float) / nav
    idx = target.index.union(cur.index)
    df = pd.DataFrame({"Cible": target.reindex(idx).fillna(0.0), "Actuel": cur.reindex(idx).fillna(0.0)})
    df["Écart"] = df["Actuel"] - df["Cible"]
    df = df.reindex(df["Écart"].abs().sort_values(ascending=False).index)
    return df, float(df["Écart"].abs().sum() / 2)
