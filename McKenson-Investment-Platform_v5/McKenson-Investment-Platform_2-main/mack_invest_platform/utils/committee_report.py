# utils/committee_report.py  —  MAM v5.3 · Rapport du comité (PNG hebdomadaire + PDF complet)
"""
Rapport destiné à l'investisseur, construit à partir d'une revue du comité
(utils.committee.review_portfolio) :

* PNG une page (e-mail du lundi) : verdict, graphique portefeuille vs indice,
  chiffres clés de risque, avis de CHAQUE professionnel virtuel, synthèse et
  recommandations de Marc ETING-FINANCIER, décisions à prendre.
* PDF complet : page 1 synthèse (CPM) → contexte (Économiste) → allocation et
  lignes (CIO) → risques, limites, couvertures (CRO, méthodes de John Hull) →
  conformité → signaux quantitatifs (Mc Henson ALGO-RITHME) → annexes (politique
  d'investissement, détail des lignes).

Sans dépendance à l'interface : utilisé par la page Rapports et par le job
hebdomadaire (GitHub Actions).
"""
from __future__ import annotations

import io
import re
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from utils import committee as C  # noqa: E402
from utils import legal as L  # noqa: E402
from utils.report_png import BG, PANEL, INK, INK2, MUTED, CYAN, GREEN, RED, AMBER, _panel, _wrap  # noqa: E402

VOTE_TXT = {"ok": "FAVORABLE", "reserve": "RÉSERVES", "veto": "VETO"}
SHORT = {"eco": "Taux-Bas", "quant": "Algo-Rithme", "cio": "Balancement", "cro": "De Marge", "cmp": "Probité",
         "cpm": "Eting-Financier"}
VOTE_COL = {"ok": GREEN, "reserve": AMBER, "veto": RED}
_EMO = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍]")


def _plain(t: str) -> str:
    """Texte sans markdown ni emoji (polices des PNG / PDF)."""
    return _EMO.sub("", re.sub(r"\*\*(.+?)\*\*", r"\1", str(t))).replace("  ", " ").strip()


def _pct(x, sign=False):
    if x is None or not isinstance(x, (int, float)) or not np.isfinite(x):
        return "—"
    return f"{x:+.1%}" if sign else f"{x:.1%}"


# ══════════════════════════════════════════════════════════════════════════════
#  GRAPHIQUE : portefeuille vs indice
# ══════════════════════════════════════════════════════════════════════════════
def _perf_axes(ax, nav: pd.Series | None, bench: pd.Series | None, bench_name: str, dark: bool, rev: dict):
    fg, mut, grid = (INK, INK2, "#1e293b") if dark else ("#0b1424", "#64748b", "#e2e8f0")
    ax.set_facecolor(PANEL if dark else "white")
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=mut, labelsize=8.5, length=0)
    ax.grid(True, color=grid, lw=.7)
    if nav is not None and len(nav.dropna()) >= 2:
        n = nav.dropna() / nav.dropna().iloc[0] * 100
        ax.plot(n.index, n.values, color=CYAN if dark else "#0077b6", lw=2.4, label=f"Portefeuille ({n.iloc[-1] - 100:+.1f} %)")
        if bench is not None and len(bench.dropna()) >= 2:
            b = bench.reindex(n.index).ffill().bfill()
            b = b / b.iloc[0] * 100
            ax.plot(b.index, b.values, color=(INK2 if dark else "#94a3b8"), lw=1.6, ls="--",
                    label=f"{bench_name} ({b.iloc[-1] - 100:+.1f} %)")
        ax.axhline(100, color=mut, lw=.6, alpha=.6)
        ax.legend(frameon=False, fontsize=8.5, labelcolor=fg, loc="upper left")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d/%m"))
        ax.set_ylabel("Base 100", color=mut, fontsize=8.5)
    else:  # pas d'historique : répartition par classe d'actifs
        cls = rev.get("classes")
        if cls is not None and len(cls):
            cls = cls[cls > 0.004].sort_values()
            ax.barh(range(len(cls)), cls.values * 100, color=CYAN if dark else "#0077b6", height=.6)
            ax.set_yticks(range(len(cls)), cls.index, fontsize=8.5, color=fg)
            for i, v in enumerate(cls.values):
                ax.text(v * 100 + .5, i, f"{v:.0%}", va="center", fontsize=8, color=fg)
            ax.set_xlabel("% du portefeuille (historique de performance insuffisant)", color=mut, fontsize=8)


def _simple_panel(fig, simple: dict | None, x: float, y: float, w: float, h: float):
    """Panneau « En bref » : la performance et sa cause, en langage simple."""
    p = _panel(fig, x, y, w, h, "En bref — votre portefeuille en mots simples")
    p.add_patch(plt.Rectangle((0, 0), .006, 1, color=GREEN, transform=p.transAxes))
    phrases = [s_ for s_ in ((simple or {}).get("phrases") or []) if not s_.startswith("Lecture :")]
    if not phrases:
        phrases = ["Synthèse indisponible."]
    first = _plain(phrases[0]) if phrases[0].startswith("**") else None
    rest = phrases[1:] if first else phrases
    yy = .80
    if first:
        p.text(.02, yy, _wrap(first, 120), color=INK, fontsize=10, fontweight="bold", va="top")
        yy -= .13 * (1 + first.count("\n") + len(first) // 120)
    body = "\n".join("• " + _wrap(_plain(t_), 128).replace("\n", "\n  ") for t_ in rest[:5])
    p.text(.02, yy, "\n".join(body.split("\n")[:8]), color=INK2, fontsize=8.3, va="top", linespacing=1.35)
    p.text(.98, .04, "1 point = 1 % de la valeur du portefeuille au début de la période", color=MUTED,
           fontsize=7, ha="right", va="bottom")


# ══════════════════════════════════════════════════════════════════════════════
#  PNG UNE PAGE — rapport hebdomadaire du comité
# ══════════════════════════════════════════════════════════════════════════════
def committee_png(rev: dict, name: str, nav: pd.Series | None = None, bench: pd.Series | None = None,
                  bench_name: str = "S&P 500", data_sim: bool = False) -> bytes:
    fig = plt.figure(figsize=(12, 19.5), dpi=130, facecolor=BG)
    cons, risk = rev["contraintes"], rev.get("risque") or {}
    v = rev["verdict"]
    vcol = VOTE_COL[v]

    # En-tête
    hd = fig.add_axes([0.03, 0.945, 0.94, 0.045])
    hd.axis("off")
    hd.text(0, .9, "McKENSON ASSET MANAGEMENT  ·  " + C.COMMITTEE_NAME, color=CYAN, fontsize=11,
            fontweight="bold", va="top")
    hd.text(0, .45, f"Rapport hebdomadaire — {_plain(name)}", color=INK, fontsize=19, fontweight="bold", va="top")
    hd.text(1, .9, datetime.now().strftime("%d/%m/%Y"), color=INK2, fontsize=11, ha="right", va="top")
    hd.text(1, .45, f"Profil {cons['profil']} · perte max {cons['perte_max']:.0%}", color=INK2, fontsize=11,
            ha="right", va="top")
    if data_sim:
        hd.text(1, .02, "DONNÉES PARTIELLEMENT SIMULÉES", color=RED, fontsize=9, ha="right", fontweight="bold")

    # Verdict
    ax = _panel(fig, .03, .895, .94, .043)
    ax.add_patch(plt.Rectangle((0, 0), .008, 1, color=vcol, transform=ax.transAxes))
    ax.text(.025, .68, _plain(rev["verdict_label"]), color=vcol, fontsize=15, fontweight="bold", va="center")
    ax.text(.025, .26, f"Régime officiel : {rev.get('regime', '—')}  ·  "
            + "  ·  ".join(f"{SHORT[a['id']]} : {VOTE_TXT[a['vote']]}" for a in rev["avis"][:5]),
            color=INK2, fontsize=8.8, va="center")

    # En bref — synthèse en langage simple (v5.6)
    _simple_panel(fig, rev.get("synthese_simple"), .03, .79, .94, .098)

    # Graphique + chiffres clés
    _panel(fig, .03, .575, .60, .207, "Portefeuille vs marché (base 100)" if nav is not None and len(nav) >= 2
           else "Répartition par classe d'actifs")
    axg = fig.add_axes([.075, .593, .53, .157])
    _perf_axes(axg, nav, bench, bench_name, True, rev)
    perf = None
    if nav is not None and len(nav.dropna()) >= 2:
        perf = float(nav.dropna().iloc[-1] / nav.dropna().iloc[0] - 1)
    tiles = [("Valeur", f"{rev['nav']:,.0f} $".replace(",", " "), ""),
             ("Performance", _pct(perf, True), "depuis le début"),
             ("Perte potentielle 1 an", _pct(risk.get("var95_1an")), f"VaR 95 % · limite {cons['perte_max']:.0%}"),
             ("Expected Shortfall", _pct(risk.get("es975_10j")), "97,5 % · 10 jours (Bâle)"),
             ("Pire stress test", _pct((risk.get("pire_scenario") or ("", None))[1], True),
              _plain((risk.get("pire_scenario") or ("", ""))[0])[:30])]
    for i, (lab, val, sub) in enumerate(tiles):
        t = _panel(fig, .645, .742 - i * .042, .325, .037)
        t.text(.04, .72, lab.upper(), color=MUTED, fontsize=7.8, fontweight="bold", va="center")
        t.text(.04, .3, val, color=INK, fontsize=13, fontweight="bold", va="center")
        t.text(.97, .3, sub, color=INK2, fontsize=7.6, va="center", ha="right")

    # Avis des 6 membres
    y0, h = .565, .125
    for i, a in enumerate(rev["avis"]):
        col, row = i % 2, i // 2
        x, y = .03 + col * .475, y0 - (row + 1) * (h + .008) + .008
        p = _panel(fig, x, y, .465, h)
        m = C.MEMBER[a["id"]]
        p.add_patch(plt.Rectangle((0, 0), .008, 1, color=m["couleur"], transform=p.transAxes))
        p.text(.03, .93, a["nom"], color=INK, fontsize=12, fontweight="bold", va="top")
        p.text(.03, .79, f"{a['role']}  ·  inspiration : {m['inspiration'].split(' (')[0]}", color=MUTED,
               fontsize=7.6, va="top")
        p.text(.97, .93, VOTE_TXT[a["vote"]], color=VOTE_COL[a["vote"]], fontsize=10, fontweight="bold",
               va="top", ha="right")
        p.text(.03, .66, _wrap(_plain(a["titre"]), 78), color=INK, fontsize=9, va="top", style="italic")
        body = [_plain(t) for t in a["points"][:3]]
        txt = "\n".join("• " + _wrap(t, 84).replace("\n", "\n  ") for t in body)
        lines = txt.split("\n")[:7]
        p.text(.03, .5, "\n".join(lines), color=INK2, fontsize=7.7, va="top", linespacing=1.32)

    # Synthèse et recommandations (CPM)
    yb = y0 - 3 * (h + .008) - .005
    p = _panel(fig, .03, yb - .118, .94, .118, "Synthèse et recommandations — Marc ETING-FINANCIER (relation client)")
    recos = rev.get("recommandations") or []
    rl = [f"{i + 1}. {_plain(r['action'])}  — {r['qui']}" for i, r in enumerate(recos[:5])] or \
         ["Aucune action nécessaire : le comité valide le portefeuille en l'état."]
    p.text(.02, .8, "\n".join(_wrap(x, 92) for x in rl), color=INK, fontsize=8.6, va="top", linespacing=1.4)
    dec = rev.get("decisions") or []
    if dec:
        p.text(.62, .8, "À VOUS DE DÉCIDER", color=CYAN, fontsize=8.5, fontweight="bold", va="top")
        p.text(.62, .68, "\n".join("☐ " + _wrap(_plain(d), 55).replace("\n", "\n   ") for d in dec[:4]),
               color=INK2, fontsize=7.8, va="top", linespacing=1.35)

    # Pied de page (mentions légales)
    fig.text(.5, .026, L.CREDIT, color=MUTED, fontsize=7.5, ha="center")
    fig.text(.5, .012, "Plateforme purement éducative : ne constitue pas un conseil en investissement. "
             f"{L.AUTHOR} n'est pas responsable des décisions prises ni engagé par les conseils de la plateforme. "
             "Membres du comité : personnages fictifs.", color=MUTED, fontsize=6.8, ha="center")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  PDF COMPLET
# ══════════════════════════════════════════════════════════════════════════════
def _perf_png_light(nav, bench, bench_name, rev) -> bytes:
    fig, ax = plt.subplots(figsize=(9, 3.6), dpi=150)
    fig.patch.set_facecolor("white")
    _perf_axes(ax, nav, bench, bench_name, False, rev)
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", facecolor="white", bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


def _member_block(a: dict) -> list[tuple]:
    m = C.MEMBER[a["id"]]
    q = m.get("citation")
    blocks = [("h", f"{a['nom']} — {a['role']}"),
              ("p", f"**Avis : {VOTE_TXT[a['vote']].capitalize()}** — {_plain(a['titre'])}"),
              ("bullets", [_plain(p) for p in a["points"]])]
    if a.get("actions"):
        blocks.append(("p", "**Recommandations :** " + " · ".join(_plain(x).rstrip(".") for x in a["actions"]) + "."))
    note = f"Style : {m['style']} Inspiration : {m['inspiration']}."
    if q:
        note += f" « {q[0]} » — {q[1]}{' (personnage fictif)' if q[1] == 'Mc Henson ALGO-RITHME' else ''}."
    blocks.append(("note", note))
    return blocks


def committee_pdf(rev: dict, name: str, nav: pd.Series | None = None, bench: pd.Series | None = None,
                  bench_name: str = "S&P 500", ips: dict | None = None, hedges: list | None = None,
                  data_sim: bool = False) -> bytes:
    from utils.reporting import make_pdf
    cons, risk = rev["contraintes"], rev.get("risque") or {}
    A_ = {a["id"]: a for a in rev["avis"]}
    perf = (float(nav.dropna().iloc[-1] / nav.dropna().iloc[0] - 1)
            if nav is not None and len(nav.dropna()) >= 2 else None)
    b: list[tuple] = []

    # ── En bref : la performance et sa cause en mots simples (v5.6) ──
    from utils.plain_summary import pdf_blocks
    b += pdf_blocks(rev.get("synthese_simple"))

    # ── Page 1 : synthèse (CPM) ──
    cpm = A_["cpm"]
    b += [("h", "Synthèse du comité — Marc ETING-FINANCIER, relation client"),
          ("p", f"**{_plain(rev['verdict_label'])}** — {_plain(cpm['titre'])}"),
          ("kpis", [("Valeur", f"{rev['nav']:,.0f} $".replace(",", " ")), ("Performance", _pct(perf, True)),
                    ("Perte potentielle 1 an (VaR 95 %)", _pct(risk.get("var95_1an"))),
                    ("Limite (perte max acceptable)", f"{cons['perte_max']:.0%}"),
                    ("Expected Shortfall 97,5 % 10 j", _pct(risk.get("es975_10j"))),
                    ("Régime officiel", str(rev.get("regime", "—"))),
                    ("Profil", cons["profil"]), ("Enveloppe", cons["enveloppe"])]),
          ("img", _perf_png_light(nav, bench, bench_name, rev), 17),
          ("bullets", [_plain(p) for p in cpm["points"]])]
    if rev.get("recommandations"):
        b += [("p", "**Recommandations du comité**"),
              ("table", [["#", "Action", "Proposée par", "Priorité"]] +
               [[str(i + 1), _plain(r["action"]), r["qui"], r["priorite"]] for i, r in enumerate(rev["recommandations"])],
               [0.8, 10.5, 3.6, 2.2])]
    if rev.get("decisions"):
        b += [("p", "**Ce que vous devez décider**"), ("bullets", [_plain(d) for d in rev["decisions"]])]
    b += [("table", [["Membre", "Rôle", "Avis", "En une phrase"]] +
           [[a["nom"], a["role"], VOTE_TXT[a["vote"]].capitalize(), _plain(a["titre"])] for a in rev["avis"]],
           [3.6, 3.6, 2.2, 8.0]), ("break",)]

    # ── Économiste ──
    b += _member_block(A_["eco"])
    # ── CIO ──
    b += _member_block(A_["cio"])
    cls, tgt = rev.get("classes"), rev.get("cible")
    if cls is not None and tgt is not None:
        rows = [["Classe d'actifs", "Portefeuille", "Cible du comité", "Écart"]]
        for c in C.A.CLASSES:
            pv, tv = float(cls.get(c, 0)), float(tgt.get(c, 0))
            if pv > 0.002 or tv > 0.002:
                rows.append([c, f"{pv:.1%}", f"{tv:.1%}", f"{pv - tv:+.1%}"])
        b.append(("table", rows, [6.5, 3.5, 3.5, 3.0]))
    b.append(("break",))
    # ── CRO ──
    b += _member_block(A_["cro"])
    if risk:
        b.append(("table", [["Mesure (méthodes de J. Hull)", "Valeur"],
                            ["Volatilité annuelle — historique / EWMA λ = 0,94 / retenue",
                             f"{_pct(risk.get('vol_hist_ann'))} / {_pct(risk.get('vol_ewma_ann'))} / {_pct(risk.get('vol_retenue_ann'))}"],
                            ["VaR 99 % — 1 jour / 10 jours (paramétrique)", f"{_pct(risk.get('var99_1j'))} / {_pct(risk.get('var99_10j'))}"],
                            ["VaR 99 % — 1 jour / 10 jours (historique)", f"{_pct(risk.get('var99_1j_hist'))} / {_pct(risk.get('var99_10j_hist'))}"],
                            ["Expected Shortfall 97,5 % — 1 jour / 10 jours", f"{_pct(risk.get('es975_1j'))} / {_pct(risk.get('es975_10j'))}"],
                            ["Perte potentielle à 1 an (VaR 95 %)", f"{_pct(risk.get('var95_1an'))} (limite {cons['perte_max']:.0%})"],
                            ["Backtesting de la VaR (Kupiec)",
                             (f"{risk['kupiec']['exceptions']} dépassements / {risk['kupiec']['attendues']:.1f} attendus — "
                              f"{risk['kupiec']['verdict']}") if risk.get("kupiec", {}).get("ok") else
                             str(risk.get("kupiec", {}).get("detail", "—"))],
                            ["Source", str(risk.get("source", "—"))]], [10.5, 6.5]))
        st_ = risk.get("stress")
        if st_ is not None and len(st_):
            b.append(("table", [["Scénario de crise", "Impact estimé"]] + [[k, f"{v:+.1%}"] for k, v in st_.items()],
                      [10.5, 6.5]))
        if risk.get("stress_inverse"):
            b.append(("p", "**Stress test inversé :** " + risk["stress_inverse"]["texte"]))
    if hedges:
        b.append(("table", [["Couverture proposée", "Stratégie", "Contrats", "Coût", "Perte si baisse : sans → avec"]] +
                  [[f"{h['panier']} ({h['sous_jacent']})", h["strategie"], str(h["contrats"]),
                    f"{h['cout']:,.0f} $".replace(",", " "),
                    f"{h['perte_sans']:,.0f} $ → {h['perte_avec']:,.0f} $".replace(",", " ")] for h in hedges],
                  [4.8, 2.8, 1.6, 2.4, 5.4]))
    # ── Conformité ──
    b += _member_block(A_["cmp"])
    b.append(("break",))
    # ── Quant (en fin de rapport : utile pour la rigueur, moins pour la décision) ──
    b += _member_block(A_["quant"])
    sig = rev.get("signaux")
    if isinstance(sig, pd.DataFrame) and not sig.empty:
        b.append(("table", [["Ligne", "Signal", "Avis", "Momentum 12-1", "Tendance / MM200", "Volatilité"]] +
                  [[t, f"{r['score']:+.2f}", r["avis"], _pct(r["mom_12_1"], True), _pct(r["tendance"], True), _pct(r["vol"])]
                   for t, r in sig.sort_values("score", ascending=False).iterrows()],
                  [2.6, 2.0, 2.4, 3.2, 3.6, 2.6]))
    # ── Annexes ──
    b += [("h", "Annexe — politique d'investissement")]
    if ips:
        b.append(("table", [["Critère", "Réponse"]] +
                  [[C.IPS_LABELS[k], (f"−{ips[k]:.0%}" if k == "perte_max" else
                                      ", ".join(ips[k]) if isinstance(ips[k], list) else str(ips[k]))]
                   for k in C.IPS_LABELS if k in ips and ips[k] not in (None, [])], [7.5, 9.5]))
    b.append(("p", f"Contraintes appliquées : profil {cons['profil']}, actions ≤ {cons['equity_max']:.0%}, "
                   f"crypto ≤ {cons['crypto_max']:.0%}, liquidités ≥ {cons['cash_min']:.0%}, volatilité cible ≤ "
                   f"{cons['vol_cible']:.0%} (perte maximale / 1,645)."))
    lines = risk.get("lignes") if risk else None
    if isinstance(lines, pd.DataFrame) and len(lines):
        b += [("h", "Annexe — lignes du portefeuille"),
              ("table", [["Ligne", "Classe", "Poids", "Part du risque (Euler)"]] +
               [[t, str(r["Classe"]), f"{r['Poids']:.1%}",
                 _pct(r.get("Part du risque")) if "Part du risque" in lines else "—"] for t, r in lines.iterrows()],
               [3.5, 6.0, 3.0, 4.5])]
    from utils.investor_report import METHOD_NOTE
    b.append(("note", METHOD_NOTE))
    b.append(("note", "Les membres du comité (Jean-Michel TAUX-BAS, Mc Henson ALGO-RITHME, Thierry BALANCEMENT, Aline DE MARGE, "
                      "Constance Probité, Marc ETING-FINANCIER) sont des personnages fictifs ; les citations de "
                      "vrais investisseurs illustrent le style dont chaque rôle s'inspire. "
                      + ("Données de marché partiellement simulées. " if data_sim else "") + L.DISCLAIMER))
    return make_pdf(f"Rapport du comité — {_plain(name)}",
                    f"McKenson Asset Management · {C.COMMITTEE_NAME.title()} · {datetime.now():%d/%m/%Y}", b)


# ══════════════════════════════════════════════════════════════════════════════
#  E-MAIL (corps HTML)
# ══════════════════════════════════════════════════════════════════════════════
def committee_email_html(rev: dict, name: str) -> str:
    import html
    vcol = VOTE_COL[rev["verdict"]]
    rows = "".join(
        f'<tr><td style="padding:6px 8px;color:#e2e8f0;font-weight:700">{html.escape(a["nom"])}</td>'
        f'<td style="padding:6px 8px;color:#94a3b8">{html.escape(a["role"])}</td>'
        f'<td style="padding:6px 8px;color:{VOTE_COL[a["vote"]]};font-weight:700">{VOTE_TXT[a["vote"]]}</td>'
        f'<td style="padding:6px 8px;color:#cbd5e1">{html.escape(_plain(a["titre"]))}</td></tr>' for a in rev["avis"])
    recos = "".join(f'<li style="margin:3px 0">{html.escape(_plain(r["action"]))} '
                    f'<span style="color:#64748b">— {html.escape(r["qui"])}</span></li>'
                    for r in rev.get("recommandations", [])) or "<li>Aucune action nécessaire.</li>"
    dec = "".join(f"<li>{html.escape(_plain(d))}</li>" for d in rev.get("decisions", []))
    from utils.plain_summary import html_block
    simple = html_block(rev.get("synthese_simple"))
    return f"""<html><body style="background:#080e1a;font-family:Arial,sans-serif;padding:18px">
<div style="max-width:760px;margin:auto">
 <div style="color:#00d4ff;font-size:13px;font-weight:700;letter-spacing:2px">McKENSON ASSET MANAGEMENT · {C.COMMITTEE_NAME}</div>
 <div style="color:#e2e8f0;font-size:20px;font-weight:700;margin:6px 0">Rapport hebdomadaire — {html.escape(name)}</div>
 <div style="border-left:4px solid {vcol};background:#0d1626;padding:10px 14px;margin:10px 0;color:{vcol};font-weight:700">
   {html.escape(_plain(rev['verdict_label']))} · régime : {html.escape(str(rev.get('regime', '—')))}</div>
 {simple}
 <table style="width:100%;border-collapse:collapse;background:#0d1626;font-size:13px">{rows}</table>
 <div style="color:#ff8c00;font-weight:700;margin:14px 0 4px">Synthèse et recommandations — Marc ETING-FINANCIER</div>
 <ul style="color:#cbd5e1;font-size:13px;margin:0">{recos}</ul>
 {f'<div style="color:#00d4ff;font-weight:700;margin:14px 0 4px">À vous de décider</div><ul style="color:#cbd5e1;font-size:13px;margin:0">{dec}</ul>' if dec else ''}
 <p style="color:#cbd5e1;font-size:13px">Le rapport complet est en pièces jointes (PNG une page + PDF détaillé).</p>
 {L.html_footer()}
 <p style="color:#475569;font-size:10px">Membres du comité : personnages fictifs.</p>
</div></body></html>"""


# ══════════════════════════════════════════════════════════════════════════════
#  ASSEMBLAGE (plateforme et job hebdomadaire)
# ══════════════════════════════════════════════════════════════════════════════
def build_for_portfolio(port: dict, ctx: dict, prices_live: dict | None = None, options_ok: bool = False,
                        bench_name: str = "S&P 500", default_profile: str = "Équilibré") -> dict:
    """Revue du comité + séries de performance + PNG + PDF pour un portefeuille MAM."""
    from utils import performance as PF
    from utils import hedging as H
    from utils.compliance import normalize_port_type
    hold = port.get("holdings", {}) or {}
    live = prices_live or {}
    vals = {}
    for t, h in hold.items():
        p = live.get(t)
        p = float(p[0] if isinstance(p, (list, tuple)) else p) if p else float(h.get("avg_price", 0))
        vals[t] = float(h.get("qty", 0)) * p
    cash = float(port.get("cash", 0.0))
    ips = port.get("ips") or C.default_ips(default_profile)
    nav_s, _ = PF.portfolio_series(port)
    bench = PF.benchmark_series(bench_name, nav_s.index.min()) if len(nav_s) >= 2 else pd.Series(dtype=float)
    perf = PF.metrics(nav_s, bench if len(bench) >= 2 else None) if len(nav_s) >= 2 else None
    nav = cash + sum(vals.values())
    hedges = []
    if C.constraints(ips)["couvertures"] != "Jamais d'options":
        try:
            hedges = [h for h in H.propose_hedges(H.exposures_from_values(vals), ctx["macro"].factors,
                                                  ctx.get("vix"), nav, prices=live) if h["contrats"] > 0]
        except Exception:
            hedges = []
    rev = C.review_portfolio(vals, cash, ips, ctx, options=port.get("options", []), options_ok=options_ok,
                             port_type=normalize_port_type(port), label=port.get("name", "Portefeuille"),
                             perf=perf, hedges=hedges, port=port)
    try:  # En bref : surperformance / sous-performance et sa cause, en mots simples (v5.6)
        from utils.plain_summary import plain_summary
        rev["synthese_simple"] = plain_summary(port, bench_name, bench=bench if len(bench) >= 2 else None)
    except Exception:
        rev["synthese_simple"] = None
    name = port.get("name", "Portefeuille")
    return dict(review=rev, nav=nav_s, bench=bench, hedges=hedges, ips=ips,
                png=committee_png(rev, name, nav_s, bench, bench_name, ctx.get("data_sim", False)),
                pdf=committee_pdf(rev, name, nav_s, bench, bench_name, ips, hedges, ctx.get("data_sim", False)),
                html=committee_email_html(rev, name))
