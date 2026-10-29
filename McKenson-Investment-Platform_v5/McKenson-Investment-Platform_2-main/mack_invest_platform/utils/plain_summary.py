# utils/plain_summary.py  —  MAM v5.6 · Synthèse en langage simple pour l'investisseur
"""
Un rapport ne doit pas supposer que l'investisseur comprend tout. Ce module rédige,
en mots simples, la partie « En bref » placée en tête de chaque rapport :

* le portefeuille a-t-il fait MIEUX ou MOINS BIEN que son indice de référence, et de combien ;
* QUELLE LIGNE et QUELLE FAÇON D'INVESTIR (décisions manuelles, allocation du desk, plan
  du comité, modèles ETF, options…) expliquent ce résultat ;
* le poids des liquidités qui n'ont rien rapporté.

Unité utilisée partout : le « point », soit 1 % de la valeur du portefeuille au début de
la période. Les contributions de toutes les lignes s'additionnent exactement à la
performance du portefeuille.

Sans interface : utilisé par les rapports PDF / PNG, l'e-mail du lundi, le rapport
investisseur mensuel et l'analyse d'un portefeuille importé.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TOLERANCE = 0.005          # écart de moins de 0,5 point : « à peu près comme le marché »

STRATEGY_LABELS = [
    ("Comité MAM", "Plan du comité"),
    ("Hedge Fund Agent", "Allocation du desk (Hedge Fund Agent)"),
    ("auto-IA", "Auto-Portefeuille"),
    ("Auto-Portefeuille", "Auto-Portefeuille"),
    ("modèle ETF", "Portefeuilles modèles ETF"),
    ("Stratégie", "Stratégies d'options"),
    ("Trading Desk", "Décisions manuelles (Trading Desk)"),
]
OPTIONS_LABEL = "Options et couvertures"
MANUAL_LABEL = "Décisions manuelles (Trading Desk)"


# ══════════════════════════════════════════════════════════════════════════════
#  FORMATAGE
# ══════════════════════════════════════════════════════════════════════════════
def pct(x, sign: bool = False, digits: int = 1) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    s = f"{x * 100:+.{digits}f}" if sign else f"{x * 100:.{digits}f}"
    return s.replace(".", ",") + " %"


def pts(x) -> str:
    if x is None or not np.isfinite(x):
        return "—"
    v = x * 100
    return f"{v:+.1f}".replace(".", ",") + (" point" if abs(round(v, 1)) <= 1 else " points")


def _verb(x: float) -> str:
    return "a gagné" if x >= 0 else "a perdu"


def strategy_of_source(source: str | None) -> str:
    s = str(source or "").strip()
    if not s:
        return MANUAL_LABEL
    for key, lab in STRATEGY_LABELS:
        if s.startswith(key) or key in s:
            return lab
    return s


# ══════════════════════════════════════════════════════════════════════════════
#  CONTRIBUTIONS PAR LIGNE (portefeuille de la plateforme)
# ══════════════════════════════════════════════════════════════════════════════
def _line_strategy(port: dict) -> dict[str, str]:
    """Façon d'investir dominante par ligne : la source qui a acheté le plus gros montant."""
    amt: dict[str, dict[str, float]] = {}
    for t in port.get("trades", []) or []:
        if str(t.get("action", "")).upper() != "BUY":
            continue
        lab = strategy_of_source(t.get("source"))
        amt.setdefault(t.get("ticker"), {}).setdefault(lab, 0.0)
        amt[t.get("ticker")][lab] += float(t.get("total", 0) or 0)
    return {tk: max(d.items(), key=lambda kv: kv[1])[0] for tk, d in amt.items() if d}


def line_contributions(port: dict, start: str | pd.Timestamp | None = None, end: str | pd.Timestamp | None = None,
                       det: pd.DataFrame | None = None, prices: pd.DataFrame | None = None) -> dict:
    """Contribution de chaque ligne (et des options) à la performance sur la période.

    contribution = (valeur finale − valeur initiale − achats nets de la période) / valeur du portefeuille
    au début. La somme des contributions est égale à la performance du portefeuille."""
    from utils import performance as PF
    if det is None:
        det = PF.nav_detail(port, prices)
    if det is None or det.empty:
        return dict(ok=False, detail="aucune transaction")
    if start is not None:
        det = det[det.index >= pd.Timestamp(start).normalize()]
    if end is not None:
        det = det[det.index <= pd.Timestamp(end)]
    if len(det) < 2:
        return dict(ok=False, detail="période trop courte")
    d0, d1 = det.index[0], det.index[-1]
    nav0 = float(det.iloc[0].sum())
    if nav0 <= 0:
        return dict(ok=False, detail="valeur de départ nulle")
    flows: dict[str, float] = {}
    tr = PF._spot_trades(port)
    if not tr.empty:
        win = tr[(tr["date"].dt.normalize() > d0) & (tr["date"].dt.normalize() <= d1)]
        for _, r in win.iterrows():
            flows[r["ticker"]] = flows.get(r["ticker"], 0.0) + (1 if r["action"] == "BUY" else -1) * r["qty"] * r["price"]
    opt_flow = 0.0
    for o in PF._option_positions(port):
        if d0 < o["date"].normalize() <= d1:
            opt_flow += o["sign"] * o["premium"] * o["units"]
    strat = _line_strategy(port)
    try:
        from utils.advisor import classify_ticker
    except Exception:
        classify_ticker = lambda t: None  # noqa: E731
    rows = []
    for c in det.columns:
        if c == "CASH":
            continue
        v0, v1 = float(det[c].iloc[0]), float(det[c].iloc[-1])
        flow = opt_flow if c == "OPTIONS" else flows.get(c, 0.0)
        pnl = v1 - v0 - flow
        if abs(pnl) < 1e-6 and v0 == 0 and v1 == 0:
            continue
        rows.append(dict(ligne=c if c != "OPTIONS" else "Options",
                         classe=("Options" if c == "OPTIONS" else (classify_ticker(c) or "Actions US")),
                         strategie=(OPTIONS_LABEL if c == "OPTIONS" else strat.get(c, MANUAL_LABEL)),
                         resultat=pnl, contribution=pnl / nav0, valeur_fin=v1))
    df = pd.DataFrame(rows)
    nav = det.sum(axis=1)
    cash_w = (det["CASH"] / nav).clip(lower=0) if "CASH" in det else pd.Series(0.0, index=det.index)
    return dict(ok=True, lignes=df.sort_values("contribution") if not df.empty else df,
                debut=d0, fin=d1, nav0=nav0, nav1=float(nav.iloc[-1]),
                perf=float(nav.iloc[-1] / nav0 - 1), cash_moyen=float(cash_w.mean()), nav=nav)


# ══════════════════════════════════════════════════════════════════════════════
#  RÉDACTION
# ══════════════════════════════════════════════════════════════════════════════
def _compose(perf: float, perf_b: float | None, bench_name: str, lignes: pd.DataFrame, cash_moyen: float,
             debut, fin, hypothetical: bool = False, horizon_label: str | None = None) -> dict:
    per = (f"du {pd.Timestamp(debut):%d/%m/%Y} au {pd.Timestamp(fin):%d/%m/%Y}" if not horizon_label
           else horizon_label)
    sujet = "Votre portefeuille" if not hypothetical else "Avec sa composition actuelle, votre portefeuille"
    verbe = _verb(perf) if not hypothetical else ("aurait gagné" if perf >= 0 else "aurait perdu")
    phrases = []
    gap = None if perf_b is None or not np.isfinite(perf_b) else perf - perf_b
    if gap is None:
        verdict = "indisponible"
        phrases.append(f"{sujet} {verbe} {pct(abs(perf))} ({per}). L'indice de référence n'est pas disponible "
                       "pour la comparaison.")
    else:
        verdict = "mieux" if gap > TOLERANCE else ("moins bien" if gap < -TOLERANCE else "pareil")
        phrases.append(f"{sujet} {verbe} {pct(abs(perf))} ({per}) ; sur la même période, l'indice de référence "
                       f"({bench_name}) {_verb(perf_b)} "
                       f"{pct(abs(perf_b))}.")
        if verdict == "pareil":
            phrases.append(f"Le portefeuille a donc fait à peu près comme le marché (écart de {pts(gap)}).")
        else:
            phrases.append(f"Le portefeuille a donc fait **{verdict} que le marché**, de {pts(abs(gap)).lstrip('+')}.")

    # Causes : lignes et liquidités
    cause = None
    top_pos = lignes[lignes["contribution"] > 0].sort_values("contribution", ascending=False).head(3) \
        if lignes is not None and not lignes.empty else pd.DataFrame()
    top_neg = lignes[lignes["contribution"] < 0].sort_values("contribution").head(3) \
        if lignes is not None and not lignes.empty else pd.DataFrame()
    cash_drag = -cash_moyen * perf_b if (perf_b is not None and np.isfinite(perf_b)) else 0.0
    if verdict in ("moins bien", "mieux"):
        cands = []
        src = top_neg if verdict == "moins bien" else top_pos
        if not src.empty:
            r = src.iloc[0]
            cands.append((abs(r["contribution"]), f"{r['ligne']} ({pts(r['contribution'])})"))
        if verdict == "moins bien" and cash_drag < -TOLERANCE:
            cands.append((abs(cash_drag), f"la part gardée en liquidités ({pct(cash_moyen, digits=0)} en moyenne, environ "
                                           f"{pts(cash_drag)} par rapport au marché)"))
        if verdict == "mieux" and cash_drag > TOLERANCE:
            cands.append((abs(cash_drag), f"la part gardée en liquidités, qui a protégé pendant la baisse du marché "
                                          f"(environ {pts(cash_drag)})"))
        if cands:
            cause = max(cands)[1]
            phrases.insert(0, f"**En une phrase : le portefeuille a fait {verdict} que le marché, surtout grâce à "
                              f"{cause}.**" if verdict == "mieux" else
                              f"**En une phrase : le portefeuille a fait {verdict} que le marché, surtout à cause de "
                              f"{cause}.**")
    elif verdict == "pareil":
        phrases.insert(0, "**En une phrase : le portefeuille a suivi le marché.**")

    if not top_pos.empty:
        phrases.append("Ce qui a le plus aidé : " + ", ".join(f"{r['ligne']} ({pts(r['contribution'])})"
                                                               for _, r in top_pos.iterrows()) + ".")
    if not top_neg.empty:
        phrases.append("Ce qui a le plus pesé : " + ", ".join(f"{r['ligne']} ({pts(r['contribution'])})"
                                                               for _, r in top_neg.iterrows()) + ".")
    par_strat = pd.Series(dtype=float)
    par_classe = pd.Series(dtype=float)
    if lignes is not None and not lignes.empty:
        par_strat = lignes.groupby("strategie")["contribution"].sum().sort_values(ascending=False)
        par_classe = lignes.groupby("classe")["contribution"].sum().sort_values(ascending=False)
        if len(par_strat) >= 2 or (len(par_strat) == 1 and not hypothetical):
            phrases.append("Par façon d'investir : " + " ; ".join(
                f"{k} {'a rapporté' if v >= 0 else 'a coûté'} {pts(abs(v)).lstrip('+')}"
                for k, v in par_strat.items()) + ".")
        if len(par_classe) >= 2:
            phrases.append("Par type d'actif : " + " ; ".join(f"{k} {pts(v)}" for k, v in par_classe.items()) + ".")
    if cash_moyen > 0.10 and perf_b is not None and np.isfinite(perf_b) and abs(cash_drag) >= TOLERANCE:
        phrases.append(f"En moyenne {pct(cash_moyen, digits=0)} du portefeuille est resté en liquidités, qui ne rapportent rien "
                       f"dans la simulation : {'cela a freiné le portefeuille' if perf_b > 0 else 'cela l’a protégé'} "
                       f"d'environ {pts(abs(cash_drag)).lstrip('+')} par rapport au marché.")
    phrases.append("Lecture : un « point » correspond à 1 % de la valeur du portefeuille au début de la période ; "
                   "les points de toutes les lignes s'additionnent pour donner la performance du portefeuille.")
    return dict(ok=True, verdict=verdict, perf=perf, perf_indice=perf_b, ecart=gap, cause=cause,
                phrases=phrases, par_strategie=par_strat, par_classe=par_classe, lignes=lignes,
                debut=debut, fin=fin, indice=bench_name, hypothetique=hypothetical)


def plain_summary(port: dict, bench_name: str = "S&P 500", start=None, end=None,
                  det: pd.DataFrame | None = None, bench: pd.Series | None = None,
                  prices: pd.DataFrame | None = None) -> dict:
    """Synthèse simple d'un portefeuille de la plateforme sur la période (depuis l'origine par défaut)."""
    from utils import performance as PF
    try:
        lc = line_contributions(port, start, end, det, prices)
    except Exception as e:  # noqa: BLE001
        lc = dict(ok=False, detail=str(e))
    if not lc.get("ok"):
        return dict(ok=False, verdict="indisponible", phrases=[
            "**En une phrase : le portefeuille est trop récent pour juger sa performance.**",
            "Il faut au moins deux jours d'historique après les premiers achats pour comparer le portefeuille à "
            "son indice de référence. Le comité juge donc pour l'instant la construction et les risques, pas le "
            "résultat."])
    perf_b = None
    try:
        b = bench if bench is not None and len(bench.dropna()) >= 2 else PF.benchmark_series(bench_name, lc["debut"])
        b = b.dropna()
        b = b[(b.index >= lc["debut"]) & (b.index <= lc["fin"] + pd.Timedelta(days=1))]
        if len(b) >= 2:
            perf_b = float(b.iloc[-1] / b.iloc[0] - 1)
    except Exception:
        perf_b = None
    return _compose(lc["perf"], perf_b, bench_name, lc["lignes"], lc["cash_moyen"], lc["debut"], lc["fin"])


def plain_summary_from_values(values: dict[str, float], cash: float, prices: pd.DataFrame,
                              bench: pd.Series | None, bench_name: str = "S&P 500", days: int = 63,
                              horizon_label: str = "sur les 3 derniers mois") -> dict:
    """Synthèse pour un portefeuille importé (sans historique de transactions) : ce qu'AURAIT fait la
    composition actuelle sur la période, à quantités constantes."""
    vals = {t: float(v) for t, v in values.items() if v and float(v) > 0}
    if not vals or prices is None or prices.empty:
        return dict(ok=False, verdict="indisponible", phrases=[
            "**En une phrase : historique de cours insuffisant pour mesurer la performance.**"])
    px = prices.dropna(how="all").iloc[-(days + 1):]
    nav1 = cash + sum(vals.values())
    rows, nav0 = [], cash
    for t, v in vals.items():
        if t in px.columns and px[t].dropna().size >= 2:
            s = px[t].dropna()
            r = float(s.iloc[-1] / s.iloc[0] - 1)
            v0 = v / (1 + r)
        else:
            r, v0 = 0.0, v
        nav0 += v0
        rows.append(dict(ligne=t, v0=v0, pnl=v - v0))
    if nav0 <= 0:
        return dict(ok=False, verdict="indisponible", phrases=["**Valeur de départ nulle.**"])
    try:
        from utils.advisor import classify_ticker
    except Exception:
        classify_ticker = lambda t: None  # noqa: E731
    lignes = pd.DataFrame([dict(ligne=r["ligne"], classe=classify_ticker(r["ligne"]) or "Actions US",
                                strategie="Composition actuelle", resultat=r["pnl"],
                                contribution=r["pnl"] / nav0) for r in rows])
    perf = nav1 / nav0 - 1
    perf_b = None
    if bench is not None and len(bench.dropna()) >= 2:
        b = bench.dropna().iloc[-(days + 1):]
        perf_b = float(b.iloc[-1] / b.iloc[0] - 1)
    out = _compose(perf, perf_b, bench_name, lignes, cash / nav1 if nav1 else 0.0, px.index[0], px.index[-1],
                   hypothetical=True, horizon_label=horizon_label)
    out["phrases"].insert(1 if out["phrases"][0].startswith("**En une phrase") else 0,
                          "Il s'agit d'une simulation : les quantités actuelles sont supposées détenues pendant toute "
                          "la période ; ce n'est pas la performance réellement obtenue.")
    return out


def strip_md(t: str) -> str:
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(t))


# ══════════════════════════════════════════════════════════════════════════════
#  RENDU (PDF, PNG, HTML, Excel)
# ══════════════════════════════════════════════════════════════════════════════
TITLE = "En bref — votre portefeuille en mots simples"


def pdf_blocks(summary: dict | None, title: str = TITLE) -> list[tuple]:
    """Blocs pour utils.reporting.make_pdf, à placer en tête du rapport."""
    if not summary or not summary.get("phrases"):
        return []
    ph = list(summary["phrases"])
    lecture = [p for p in ph if p.startswith("Lecture :")]
    body = [p for p in ph if not p.startswith("Lecture :")]
    out: list[tuple] = [("h", title)]
    if body and body[0].startswith("**En une phrase"):
        out.append(("p", body.pop(0)))
    out.append(("bullets", body))
    if lecture:
        out.append(("note", lecture[0]))
    return out


def html_block(summary: dict | None, color: str = "#cbd5e1") -> str:
    """Bloc HTML (e-mails)."""
    import html
    if not summary or not summary.get("phrases"):
        return ""
    items = "".join(f"<li style='margin:3px 0'>{_md_html(p)}</li>" for p in summary["phrases"])
    return (f'<div style="color:#00ff88;font-weight:700;margin:14px 0 4px">{html.escape(TITLE)}</div>'
            f'<ul style="color:{color};font-size:13px;margin:0">{items}</ul>')


def _md_html(t: str) -> str:
    import html
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", html.escape(str(t)))


def plain_lines(summary: dict | None) -> list[str]:
    return [strip_md(p) for p in (summary or {}).get("phrases", [])]


def summary_png(summary: dict | None, title: str = TITLE, theme: str = "light") -> bytes | None:
    """Image autonome de la synthèse (jointe aux exports d'images)."""
    if not summary or not summary.get("phrases"):
        return None
    import io
    import textwrap
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    dark = theme != "light"
    bg, ink, mut, acc = (("#0b1220", "#e2e8f0", "#94a3b8", "#00ff88") if dark else
                         ("white", "#0b1424", "#64748b", "#0077b6"))
    lines = []
    for p in summary["phrases"]:
        txt = strip_md(p)
        wrapped = textwrap.wrap(txt, 105)
        lines.append((wrapped, p.startswith("**"), txt.startswith("Lecture :")))
    n = sum(len(w) for w, _, _ in lines) + len(lines)
    fig = plt.figure(figsize=(12, max(2.6, 0.9 + 0.27 * n)), dpi=130, facecolor=bg)
    fig.text(0.03, 1 - 0.32 / fig.get_figheight(), title, color=acc, fontsize=15, weight="bold", va="top")
    y = 1 - 0.85 / fig.get_figheight()
    step = 0.27 / fig.get_figheight()
    for wrapped, bold, note in lines:
        for i, w in enumerate(wrapped):
            fig.text(0.03 if i == 0 else 0.045, y, ("• " if i == 0 and not bold else "") + w,
                     color=(mut if note else ink), fontsize=(9 if note else 11), weight=("bold" if bold else "normal"),
                     va="top")
            y -= step
        y -= step * 0.45
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=bg)
    plt.close(fig)
    return buf.getvalue()
