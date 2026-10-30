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
    ("Portefeuille proposé (ajusté", "Portefeuille proposé puis ajusté par vous"),
    ("Portefeuille proposé", "Portefeuille proposé par le comité"),
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


FEES_LABEL = "Frais de transaction"
CASH_LABEL = "Liquidités (intérêts)"


def line_contributions(port: dict, start: str | pd.Timestamp | None = None, end: str | pd.Timestamp | None = None,
                       det: pd.DataFrame | None = None, prices: pd.DataFrame | None = None) -> dict:
    """Contribution de chaque ligne à la performance pondérée dans le temps (TWR, GIPS).

    Chaque jour : résultat de la ligne = variation de valeur − achats nets + dividendes reçus ;
    les frais de transaction et les intérêts des liquidités sont des lignes à part. Les contributions
    quotidiennes (résultat / valeur de la veille, apports et retraits inclus) sont chaînées par le
    lissage de Carino : leur somme est EXACTEMENT égale au TWR de la période, quels que soient les
    apports ou retraits de liquidités."""
    import math
    from utils import ledger as LG
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
    idx = det.index
    d0, d1 = idx[0], idx[-1]
    nav = det.sum(axis=1)
    nav0 = float(nav.iloc[0])
    if nav0 <= 0:
        return dict(ok=False, detail="valeur de départ nulle")
    ext = LG.daily_sum(port, LG.EXTERNAL, idx)
    r = LG.twr_returns(nav, ext)
    base = (nav.shift(1) + ext).iloc[1:]

    def _day(dates: pd.Series) -> np.ndarray:
        pos = idx.searchsorted(dates.dt.normalize())
        return pos

    # achats nets et frais par ligne et par jour
    buys = pd.DataFrame(0.0, index=idx, columns=[c for c in det.columns if c not in ("CASH", "OPTIONS")])
    fees = pd.Series(0.0, index=idx)
    tr = PF._spot_trades(port)
    if not tr.empty:
        pos = _day(tr["date"])
        for (_, t), p_ in zip(tr.iterrows(), pos):
            if 0 < p_ < len(idx) and t["ticker"] in buys.columns:
                buys.iloc[p_, buys.columns.get_loc(t["ticker"])] += (1 if t["action"] == "BUY" else -1) * t["qty"] * t["price"]
                fees.iloc[p_] += t.get("frais", 0.0)
    fees = fees - LG.daily_sum(port, ("frais",), idx)        # commissions d'options (montants négatifs)
    divs = LG.daily_sum(port, ("dividende",), idx, by_ticker=True)
    interest = LG.daily_sum(port, ("interet",), idx)
    prem = pd.Series(0.0, index=idx)
    for o in PF._option_positions(port):
        p_ = idx.searchsorted(o["date"].normalize())
        if 0 < p_ < len(idx):
            prem.iloc[p_] += o["sign"] * o["premium"] * o["units"]

    pnl = {}
    for c in buys.columns:
        dv = divs[c] if c in getattr(divs, "columns", []) else 0.0
        pnl[c] = (det[c].diff() - buys[c] + dv).iloc[1:]
    if "OPTIONS" in det:
        pnl["OPTIONS"] = (det["OPTIONS"].diff() - prem).iloc[1:]
    pnl[FEES_LABEL] = -fees.iloc[1:]
    pnl[CASH_LABEL] = interest.iloc[1:]

    R = float((1 + r).prod() - 1)
    lnR = math.log1p(R) / R if abs(R) > 1e-12 else 1.0
    k = pd.Series(np.where(r.abs() > 1e-12, np.log1p(r) / r.where(r.abs() > 1e-12, 1.0), 1.0), index=r.index) / lnR
    strat = _line_strategy(port)
    try:
        from utils.advisor import classify_ticker
    except Exception:
        classify_ticker = lambda t: None  # noqa: E731
    rows = []
    for c, s_ in pnl.items():
        res = float(s_.sum())
        contrib = float((s_ / base.where(base > 0)).fillna(0.0).mul(k).sum())
        if abs(res) < 1e-6 and abs(contrib) < 1e-9:
            continue
        if c == "OPTIONS":
            lab, cls, st_ = "Options", "Options", OPTIONS_LABEL
        elif c == FEES_LABEL:
            lab, cls, st_ = FEES_LABEL, "Frais", FEES_LABEL
        elif c == CASH_LABEL:
            lab, cls, st_ = CASH_LABEL, "Liquidités", "Liquidités rémunérées"
        else:
            lab, cls, st_ = c, (classify_ticker(c) or "Actions US"), strat.get(c, MANUAL_LABEL)
        rows.append(dict(ligne=lab, classe=cls, strategie=st_, resultat=res, contribution=contrib,
                         valeur_fin=float(det[c].iloc[-1]) if c in det else 0.0))
    df = pd.DataFrame(rows)
    cash_w = (det["CASH"] / nav).clip(lower=0) if "CASH" in det else pd.Series(0.0, index=idx)
    return dict(ok=True, lignes=df.sort_values("contribution") if not df.empty else df,
                debut=d0, fin=d1, nav0=nav0, nav1=float(nav.iloc[-1]), perf=R, cash_moyen=float(cash_w.mean()),
                nav=LG.twr_index(nav, ext), valeurs=nav, apports=float(ext.iloc[1:].sum()),
                interets=float(interest.iloc[1:].sum()), frais=float(fees.iloc[1:].sum()),
                dividendes=float(divs.values.sum()) if hasattr(divs, "values") and len(getattr(divs, "columns", []))
                else 0.0)


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
    cash_int = 0.0
    if lignes is not None and not lignes.empty and (lignes["ligne"] == CASH_LABEL).any():
        cash_int = float(lignes.loc[lignes["ligne"] == CASH_LABEL, "contribution"].sum())
    # effet des liquidités par rapport à un placement dans l'indice : intérêts reçus − ce qu'aurait
    # rapporté le marché sur la même part
    cash_drag = (cash_int - cash_moyen * perf_b) if (perf_b is not None and np.isfinite(perf_b)) else 0.0
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
        if hypothetical:
            phrases.append(f"En moyenne {pct(cash_moyen, digits=0)} du portefeuille est en liquidités (non rémunérées "
                           f"dans cette simulation) : {'cela a freiné' if cash_drag < 0 else 'cela a protégé'} le "
                           f"portefeuille d'environ {pts(abs(cash_drag)).lstrip('+')} par rapport au marché.")
        else:
            phrases.append(f"En moyenne {pct(cash_moyen, digits=0)} du portefeuille est resté en liquidités, rémunérées "
                           f"au taux monétaire ({pts(cash_int)} d'intérêts) : par rapport à un placement dans "
                           f"l'indice, {'cela a freiné' if cash_drag < 0 else 'cela a protégé'} le portefeuille "
                           f"d'environ {pts(abs(cash_drag)).lstrip('+')}.")
    phrases.append("Lecture : un « point » correspond à 1 % de la valeur du portefeuille ; les points de toutes les "
                   "lignes (frais et intérêts compris) s'additionnent pour donner la performance du portefeuille, "
                   "mesurée selon la norme GIPS (rendement pondéré dans le temps, net des frais de transaction, "
                   "dividendes et intérêts inclus, sans effet des apports ou retraits de liquidités).")
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
    out = _compose(lc["perf"], perf_b, bench_name, lc["lignes"], lc["cash_moyen"], lc["debut"], lc["fin"])
    extra = []
    if lc.get("dividendes", 0) > 0.5 or lc.get("interets", 0) > 0.5 or lc.get("frais", 0) > 0.5:
        extra.append(f"Revenus et coûts de la période : dividendes {_money(lc.get('dividendes', 0))}, intérêts sur "
                     f"liquidités {_money(lc.get('interets', 0))}, frais de transaction {_money(lc.get('frais', 0))}.")
    if abs(lc.get("apports", 0)) > 0.5:
        a_ = lc["apports"]
        extra.append(f"{'Apports' if a_ > 0 else 'Retraits'} de liquidités sur la période : {_money(abs(a_))}. Ils ne "
                     "comptent pas dans la performance (rendement pondéré dans le temps).")
    if extra:
        out["phrases"][-1:-1] = extra
    out.update(dividendes=lc.get("dividendes", 0.0), interets=lc.get("interets", 0.0), frais=lc.get("frais", 0.0),
               apports=lc.get("apports", 0.0))
    return out


def _money(x: float) -> str:
    return f"{x:,.0f} $".replace(",", " ")


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
    from utils.brand import add_to_figure
    H_ = fig.get_figheight()
    tx = 0.03 + (0.045 if add_to_figure(fig, 0.03, 1 - 0.68 / H_, 0.5 / H_) is not None else 0)
    fig.text(tx, 1 - 0.32 / H_, title, color=acc, fontsize=15, weight="bold", va="top")
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
