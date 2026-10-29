# utils/portfolio_proposal.py  —  MAM v5.7 · Portefeuille proposé à l'utilisateur, puis ajusté par lui
"""
Le comité construit un portefeuille cible à partir de :
  * la politique d'investissement (IPS) du portefeuille — ou le profil investisseur de l'utilisateur ;
  * les conditions de marché RÉELLES (régime officiel à 8 facteurs, signaux validés hors échantillon) ;
  * les contraintes de l'IPS (exclusions, enveloppe, perte maximale, plafonds).

L'utilisateur peut ensuite modifier les poids, retirer ou ajouter des lignes. La version
ajustée est de nouveau soumise au comité (veto possible) et chaque ordre passe par la
conformité. Module sans interface (testable sans Streamlit).
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from utils import committee as CM

A = CM.A
MIN_WEIGHT = 0.005          # en dessous de 0,5 %, une ligne est ignorée (frais > intérêt)


def _reason(t: str, w: float, cls: str, cons: dict, target_cls: pd.Series, sig: pd.DataFrame | None,
            regime: str, held: bool, cls_scores: pd.Series | None) -> str:
    """Pourquoi cette ligne, en mots simples."""
    parts = []
    tw = float(target_cls.get(cls, 0.0))
    view = ""
    if cls_scores is not None and cls in cls_scores.index:
        s = float(cls_scores[cls])
        view = (" et le contexte actuel la favorise" if s > 0.5 else
                " même si le contexte actuel la pénalise un peu (diversification)" if s < -0.5 else "")
    parts.append(f"La classe « {cls} » vise {tw:.0%} du portefeuille pour un profil {cons['profil']} "
                 f"en régime « {regime} »{view}.")
    try:
        from utils.sectors import sector_of
        sec = sector_of(t)
    except Exception:
        sec = ""
    if held:
        parts.append(f"{t} est déjà détenu : il est conservé et pondéré selon son signal de tendance.")
    elif sec.startswith(("ETF", "ETC")):
        parts.append(f"{t} est un ETF large et peu coûteux qui couvre cette classe d'un coup.")
    else:
        parts.append(f"{t} est l'actif de référence de cette classe.")
    if isinstance(sig, pd.DataFrame) and t in sig.index and np.isfinite(sig.loc[t, "score"]):
        sc = float(sig.loc[t, "score"])
        if sc > 0.6:
            parts.append(f"Tendance favorable ({sc:+.1f}).")
        elif sc < -0.6:
            parts.append(f"Tendance défavorable ({sc:+.1f}) : poids réduit.")
    return " ".join(parts)


SECTOR_TILT_MAX = 0.30        # part maximale de la poche actions US orientée vers les secteurs porteurs
US_EQ_PROXIES = ("SPY", "CSPX.L", "VOO", "IVV")


def sector_tilt(tw: pd.Series, board: pd.DataFrame | None, cons: dict, intensity: float,
                n: int = 2) -> tuple[pd.Series, dict[str, str]]:
    """Oriente une partie de la poche « Actions US » vers les secteurs que les conditions de marché
    favorisent (performance récente + lecture du régime). Hors PEA et enveloppes UCITS (ETF sectoriels US),
    exclusions respectées. Renvoie (poids, {ticker: raison})."""
    why: dict[str, str] = {}
    if board is None or board.empty or intensity <= 0 or any(k in cons["enveloppe"] for k in ("PEA", "UCITS")):
        return tw, why
    proxy = next((t for t in US_EQ_PROXIES if tw.get(t, 0) >= 0.10), None)
    if not proxy:
        return tw, why
    good = board[(board["Score"] >= 60) & (board["Lecture du contexte"] != "pénalisé")]
    good = good[[not CM.excluded_reason(e, cons["exclusions"]) for e in good["ETF"]]].head(n)
    if good.empty:
        return tw, why
    tw = tw.copy()
    budget = float(tw[proxy]) * SECTOR_TILT_MAX * min(1.0, intensity / 0.5) * 0.999
    each = budget / len(good)
    for sec, r in good.iterrows():
        e = r["ETF"]
        tw[e] = tw.get(e, 0.0) + each
        p3 = r.get("Perf. 3 mois")
        why[e] = (f"Secteur porteur dans les conditions actuelles : {sec.lower()} (score {r['Score']:.0f}/100"
                  + (f", {p3:+.0%} sur 3 mois" if p3 == p3 else "") + f", contexte {r['Lecture du contexte']}). "
                  f"Il remplace une partie de {proxy} pour orienter la poche actions vers ce qui porte le marché.")
    tw[proxy] -= budget
    return tw, why


def build_proposal(values: dict[str, float], cash: float, ips: dict, ctx: dict, live: dict,
                   intensity: float = 0.5, board: pd.DataFrame | None = None) -> dict:
    """Portefeuille cible proposé par le comité (poids par ligne + explication par ligne).
    board : classement des secteurs (utils.upload_advisor.sector_board), facultatif."""
    opt = CM.committee_optimize(values, cash, ips, ctx, live, intensity, band=0.0)
    cons = opt["contraintes"]
    tw = opt["cible_lignes"]
    tw, tilt_why = sector_tilt(tw, board, cons, intensity)
    tw = tw[tw > MIN_WEIGHT]
    try:
        cls_scores = A.class_scores(ctx["macro"].factors)
    except Exception:
        cls_scores = None
    names = _names()
    rows = []
    for t, w in tw.items():
        cls = A.classify_ticker(t) or "Actions US"
        rows.append(dict(ticker=t, nom=names.get(t, t), classe=cls, poids=float(w),
                         pourquoi=tilt_why.get(t) or _reason(t, float(w), cls, cons, opt["cible_classes"],
                                                             opt.get("signaux"), ctx["macro"].regime, t in values,
                                                             cls_scores)))
    lines = pd.DataFrame(rows, columns=["ticker", "nom", "classe", "poids", "pourquoi"])
    if not lines.empty:
        lines = lines.sort_values("poids", ascending=False).reset_index(drop=True)
    cash_w = max(0.0, 1.0 - float(lines["poids"].sum()) if not lines.empty else 1.0)
    return dict(lignes=lines, liquidites=cash_w, contraintes=cons, regime=ctx["macro"].regime,
                allowed=opt["allowed"], data_sim=bool(ctx.get("data_sim")), notes=opt["notes"],
                cible_classes=opt["cible_classes"], nav=opt["nav"], preuve=opt.get("preuve"))


def _names() -> dict:
    try:
        from utils.data import load_assets
        df = load_assets()
        return dict(zip(df["ticker"], df["name"]))
    except Exception:
        return {}


def known_tickers() -> set[str]:
    try:
        from utils.data import load_assets
        return set(load_assets()["ticker"])
    except Exception:
        return set()


def normalize_edit(edited: pd.DataFrame, known: set[str] | None = None) -> tuple[pd.Series, list[str]]:
    """Poids saisis par l'utilisateur (en %) → Series de poids (0–1). Le reste va en liquidités.
    Renvoie (poids, messages). Si la somme dépasse 100 %, les poids sont ramenés à 100 %."""
    msgs = []
    w: dict[str, float] = {}
    for _, r in edited.iterrows():
        t = str(r.get("Ligne") or "").strip().upper()
        if not t or t in ("NONE", "NAN"):
            continue
        try:
            p = float(r.get("Poids (%)") or 0.0) / 100.0
        except Exception:
            p = 0.0
        if not math.isfinite(p) or p <= 0:
            continue
        if known is not None and t not in known:
            # tolère la casse d'origine (ex. « Su.pa »)
            match = next((k for k in known if k.upper() == t), None)
            if not match:
                msgs.append(f"« {t} » n'est pas dans l'univers de la plateforme : ligne ignorée.")
                continue
            t = match
        w[t] = w.get(t, 0.0) + p
    s = pd.Series(w, dtype=float)
    tot = float(s.sum())
    if tot > 1.0 + 1e-9:
        msgs.append(f"La somme des poids ({tot:.0%}) dépasse 100 % : les poids ont été ramenés à 100 %, "
                    "sans liquidités.")
        s = s / tot
    return s[s >= MIN_WEIGHT], msgs


def compare_with_proposal(proposal: pd.DataFrame, weights: pd.Series) -> pd.DataFrame:
    """Écarts entre la proposition du comité et la version ajustée par l'utilisateur."""
    p = proposal.set_index("ticker")["poids"] if not proposal.empty else pd.Series(dtype=float)
    idx = p.index.union(weights.index)
    df = pd.DataFrame({"Proposé": p.reindex(idx).fillna(0.0), "Votre version": weights.reindex(idx).fillna(0.0)})
    df["Écart"] = df["Votre version"] - df["Proposé"]
    df.index.name = "Ligne"
    return df[(df["Écart"].abs() > 1e-6)].sort_values("Écart")


def is_edited(proposal: pd.DataFrame, weights: pd.Series, tol: float = 0.0005) -> bool:
    return not compare_with_proposal(proposal, weights)[lambda d: d["Écart"].abs() > tol].empty


def projected_values(weights: pd.Series, nav: float) -> tuple[dict, float]:
    vals = {t: float(w) * nav for t, w in weights.items() if w > 0}
    return vals, max(0.0, nav - sum(vals.values()))
