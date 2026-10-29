# utils/portfolio_census.py  —  MAM v5.7 · Recensement de TOUS les portefeuilles (vue administrateur)
"""
Rassemble tous les portefeuilles construits sur la plateforme (tous les utilisateurs si la
base Supabase est disponible, sinon ceux de l'état local) et calcule de quoi les comparer :
valeur, performance depuis l'origine, stratégie, profil, avis du comité, construction
(lignes, liquidités, classe dominante, thème), façon dont ils ont été construits
(décisions manuelles, desk, comité, modèles ETF…) et, à la demande, les indicateurs
historiques (volatilité, Sharpe, perte max, bêta, surperformance vs indice).

Sans interface : utilisé par l'onglet Administration → 📊 Tous les portefeuilles.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

VERDICT_TXT = {"ok": "Validé", "reserve": "Validé avec réserves", "veto": "Refusé", None: "À valider"}


def _j(v, default):
    if v is None:
        return default
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except Exception:
        return default


def from_db_rows(rows: list[dict]) -> list[dict]:
    """Lignes de mam_portfolios (load_all_portfolios) → [{port, proprietaire, equipe}]."""
    out = []
    for r in rows or []:
        port = {
            "id": r.get("id"), "name": r.get("name") or r.get("id"), "emoji": r.get("emoji") or "📁",
            "strategy": r.get("strategy") or "Libre", "asset_types": _j(r.get("asset_types"), []),
            "cash": float(r.get("cash") or 0.0), "initial_cash": float(r.get("initial_cash") or 0.0),
            "holdings": _j(r.get("holdings"), {}), "options": _j(r.get("options"), []),
            "trades": _j(r.get("trades"), []), "history": _j(r.get("history"), []),
            "ips": _j(r.get("ips"), None), "committee": _j(r.get("committee"), None),
            "created": str(r.get("created_at") or "")[:10],
            **(_j(r.get("extras"), {}) or {}),
        }
        team = r.get("team_name") or "Solo"
        out.append(dict(port=port, proprietaire=r.get("username") or "—",
                        equipe=f"{r.get('team_emoji') or ''} {team}".strip(),
                        user_id=r.get("user_id"), team_id=r.get("team_id"), source="db"))
    return out


def from_state(state: dict, owner: str = "—") -> list[dict]:
    out = []
    for tid, t in (state or {}).get("teams", {}).items():
        label = "Solo" if tid == "__solo__" else f"{t.get('emoji', '')} {t.get('name', tid)}".strip()
        for pid, p in (t.get("portfolios") or {}).items():
            if p.get("name"):
                p.setdefault("id", pid)
                out.append(dict(port=p, proprietaire=owner, equipe=label, team_id=tid, source="state"))
    return out


def collect_all(state: dict | None = None, owner: str = "—") -> tuple[list[dict], str]:
    """(portefeuilles, source). Base Supabase (tous les comptes) si disponible, sinon état local."""
    try:
        from utils.db import is_db_available, load_all_portfolios
        if is_db_available():
            rows = load_all_portfolios()
            if rows:
                return from_db_rows(rows), "base Supabase — tous les comptes"
    except Exception:
        pass
    if state is None:
        try:
            from utils.data import get_or_init_state
            state = get_or_init_state()
        except Exception:
            state = {}
    return from_state(state, owner), "état local de la session (base indisponible)"


def _strategy(port: dict) -> str:
    try:
        from utils.compliance import normalize_port_type
        return normalize_port_type(port)
    except Exception:
        return str(port.get("strategy") or "Libre")


def _profile(port: dict) -> str:
    if port.get("ips"):
        try:
            from utils.committee import constraints
            return constraints(port["ips"])["profil"]
        except Exception:
            pass
    return "non défini"


def construction_mix(port: dict) -> dict[str, float]:
    """Part des montants achetés par façon d'investir (décisions manuelles, desk, comité, modèles ETF…)."""
    from utils.plain_summary import strategy_of_source
    amt: dict[str, float] = {}
    for t in port.get("trades", []) or []:
        if str(t.get("action", "")).upper() != "BUY":
            continue
        lab = strategy_of_source(t.get("source"))
        amt[lab] = amt.get(lab, 0.0) + float(t.get("total", 0) or 0)
    tot = sum(amt.values())
    return {k: v / tot for k, v in sorted(amt.items(), key=lambda kv: -kv[1])} if tot > 0 else {}


def summary_row(item: dict, prices: dict) -> dict:
    """Ligne de comparaison rapide (cours actuels, sans historique)."""
    from utils import advisor as A
    port = item["port"]
    hold = port.get("holdings") or {}
    vals = {}
    for t, h in hold.items():
        p = prices.get(t)
        p = float(p[0] if isinstance(p, (list, tuple)) else p) if p else float((h or {}).get("avg_price", 0) or 0)
        vals[t] = float((h or {}).get("qty", 0) or 0) * p
    vals = {t: v for t, v in vals.items() if v > 0}
    cash = float(port.get("cash", 0.0) or 0.0)
    nav = cash + sum(vals.values())
    init = float(port.get("initial_cash") or 0.0) or nav
    top = max(vals.items(), key=lambda kv: kv[1]) if vals else (None, 0.0)
    cls_w, _ = A.portfolio_to_classes({**vals, "CASH": cash}) if nav > 0 else (pd.Series(dtype=float), None)
    main_cls = cls_w.drop(labels=["Liquidités"], errors="ignore")
    main_cls = main_cls[main_cls > 0]
    theme = "—"
    try:
        from utils.themes import theme_exposure
        th = theme_exposure(vals, nav)
        if th and th[0]["poids"] >= 0.15:
            theme = f"{th[0]['theme']} ({th[0]['poids']:.0%})"
    except Exception:
        pass
    mix = construction_mix(port)
    trades = port.get("trades", []) or []
    from utils import ledger as LG
    mv = LG.movements(port, LG.EXTERNAL)
    net_ext = float(mv["montant"].sum()) if not mv.empty else 0.0
    # GIPS : sans flux externe, valeur / capital initial − 1 est exactement le TWR ;
    # avec des apports ou retraits, le TWR est calculé avec les indicateurs historiques
    perf_q = (nav / init - 1) if (init > 0 and mv.empty) else np.nan
    c = port.get("committee") or {}
    return {
        "id": port.get("id"), "Portefeuille": f"{port.get('emoji', '📁')} {port.get('name')}",
        "Propriétaire": item.get("proprietaire", "—"), "Équipe": item.get("equipe", "—"),
        "Stratégie": _strategy(port), "Profil": _profile(port),
        "Avis du comité": VERDICT_TXT.get(c.get("verdict"), "À valider"),
        "Valeur": nav, "Capital initial": init, "Apports nets": net_ext,
        "Performance": perf_q, "Résultat": nav - init - net_ext,
        "Liquidités": cash / nav if nav > 0 else np.nan, "Lignes": len(vals),
        "Première ligne": f"{top[0]} ({top[1] / nav:.0%})" if top[0] and nav > 0 else "—",
        "Classe dominante": (f"{main_cls.idxmax()} ({main_cls.max():.0%})" if len(main_cls) else "—"),
        "Thème dominant": theme,
        "Construit surtout par": (f"{next(iter(mix))} ({next(iter(mix.values())):.0%})" if mix else "—"),
        "Ordres": len(trades), "Dernier ordre": str(trades[-1].get("date", ""))[:10] if trades else "—",
        "Créé le": str(port.get("created") or "")[:10] or "—",
    }


def summary_table(items: list[dict], prices: dict) -> pd.DataFrame:
    rows = [summary_row(it, prices) for it in items]
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def detailed_metrics(port: dict, bench_name: str = "S&P 500") -> dict:
    """Indicateurs historiques (NAV reconstituée à partir des transactions et des cours réels)."""
    from utils import performance as PF
    s, src = PF.portfolio_series(port)
    if len(s.dropna()) < 2:
        return {"Historique": "insuffisant"}
    b = PF.benchmark_series(bench_name, s.index.min())
    m = PF.metrics(s, b if len(b.dropna()) >= 2 else None)
    m["Historique"] = f"{m.get('Jours', 0)} jours"
    m["Performance (TWR)"] = m.get("Performance")
    m["Bat l'indice"] = (None if not np.isfinite(m.get("Surperformance", np.nan))
                         else bool(m["Surperformance"] > 0))
    return m


def aggregate(df: pd.DataFrame, by: str) -> pd.DataFrame:
    """Comparaison par stratégie, profil, propriétaire ou équipe."""
    if df.empty or by not in df:
        return pd.DataFrame()
    agg = {"Portefeuilles": ("Portefeuille", "count"), "Valeur totale": ("Valeur", "sum"),
           "Performance moyenne": ("Performance", "mean"), "Performance médiane": ("Performance", "median"),
           "Meilleure": ("Performance", "max"), "Moins bonne": ("Performance", "min"),
           "Liquidités moyennes": ("Liquidités", "mean")}
    for col, lab in (("Volatilité (ann.)", "Volatilité moyenne"), ("Sharpe", "Sharpe moyen"),
                     ("Perte max", "Perte max moyenne"), ("Surperformance", "Surperformance moyenne")):
        if col in df:
            agg[lab] = (col, "mean")
    out = df.groupby(by).agg(**agg)
    if "Bat l'indice" in df:
        out["Battent l'indice"] = df.groupby(by)["Bat l'indice"].apply(
            lambda s: f"{int((s == True).sum())}/{int(s.notna().sum())}" if s.notna().any() else "—")  # noqa: E712
    return out.sort_values("Performance moyenne", ascending=False)


def plain_ranking(df: pd.DataFrame, by: str = "Stratégie") -> list[str]:
    """Quelques phrases simples pour lire la comparaison."""
    out = []
    if df.empty:
        return out
    d = df.dropna(subset=["Performance"])
    if len(d):
        best, worst = d.loc[d["Performance"].idxmax()], d.loc[d["Performance"].idxmin()]
        out.append(f"Meilleur portefeuille : {best['Portefeuille']} ({best['Propriétaire']}, {best['Stratégie']}) "
                   f"avec {best['Performance']:+.1%} depuis sa création.")
        if len(d) > 1:
            out.append(f"Moins bon : {worst['Portefeuille']} ({worst['Propriétaire']}, {worst['Stratégie']}) "
                       f"avec {worst['Performance']:+.1%}.")
    ag = aggregate(df, by)
    if len(ag) >= 2:
        out.append(f"Par {by.lower()}, « {ag.index[0]} » obtient la meilleure performance moyenne "
                   f"({ag['Performance moyenne'].iloc[0]:+.1%}, {int(ag['Portefeuilles'].iloc[0])} portefeuille(s)), "
                   f"« {ag.index[-1]} » la moins bonne ({ag['Performance moyenne'].iloc[-1]:+.1%}).")
    if "Bat l'indice" in df and df["Bat l'indice"].notna().any():
        n, k = int(df["Bat l'indice"].notna().sum()), int((df["Bat l'indice"] == True).sum())  # noqa: E712
        out.append(f"{k} portefeuille(s) sur {n} font mieux que leur indice de référence sur leur propre période.")
    out.append("Attention : les portefeuilles n'ont pas tous le même âge ; une performance depuis l'origine sur "
               "quelques jours ne se compare pas à une performance sur plusieurs mois. Les indicateurs historiques "
               "(volatilité, Sharpe, surperformance) donnent une comparaison plus juste.")
    return out
