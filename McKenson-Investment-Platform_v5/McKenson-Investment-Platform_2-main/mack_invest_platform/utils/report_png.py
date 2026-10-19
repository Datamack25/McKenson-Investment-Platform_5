"""
utils/report_png.py — Rapport hebdomadaire au format PNG (une page, thème MAM)

Contenu : régime et synthèse, chiffres clés, évolution des facteurs (aujourd'hui vs
il y a un mois), allocation actuelle vs cible, alertes expliquées, recommandations,
stress tests avant / après ajustement, déclencheurs de révision.
"""
from __future__ import annotations

import io
import textwrap
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from utils import advisor as A  # noqa: E402

BG, PANEL, BORDER = "#080e1a", "#0d1626", "#1e3a52"
INK, INK2, MUTED = "#e2e8f0", "#94a3b8", "#64748b"
CYAN, GREEN, RED, AMBER, BLUE, VIOLET = "#00d4ff", "#00ff88", "#ff3b6b", "#f59e0b", "#38bdf8", "#a78bfa"
SEV_COL = {"critique": RED, "important": AMBER, "info": BLUE}


def _panel(fig, x, y, w, h, title=None):
    ax = fig.add_axes([x, y, w, h])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    ax.add_patch(FancyBboxPatch((0, 0), 1, 1, boxstyle="round,pad=0,rounding_size=0.015",
                                transform=ax.transAxes, facecolor=PANEL, edgecolor=BORDER, lw=1))
    if title:
        ax.text(0.02, 0.965, title.upper(), color=CYAN, fontsize=10.5, fontweight="bold",
                va="top", transform=ax.transAxes)
    return ax


def _style(ax):
    ax.set_facecolor(PANEL)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=INK2, labelsize=8.5, length=0)
    ax.grid(axis="x", color="#1e293b", lw=0.7)
    ax.set_axisbelow(True)


def _wrap(t, w):
    return "\n".join(textwrap.wrap(str(t), w))


def build_weekly_png(macro, news: dict, alerts: list, review: dict | None = None,
                     name: str = "Desk MAM", profile: str = "Équilibré",
                     hist: pd.DataFrame | None = None, data_sim: bool = False) -> bytes:
    fig = plt.figure(figsize=(12, 17), dpi=130, facecolor=BG)

    # ── En-tête ───────────────────────────────────────────────────────────────
    hd = fig.add_axes([0.03, 0.935, 0.94, 0.055])
    hd.axis("off")
    hd.text(0, 0.85, "McKENSON ASSET MANAGEMENT  ·  HEDGE FUND AGENT", color=CYAN, fontsize=11,
            fontweight="bold", va="top")
    hd.text(0, 0.45, f"Rapport hebdomadaire — {name}", color=INK, fontsize=19, fontweight="bold", va="top")
    hd.text(1, 0.85, datetime.now().strftime("%d/%m/%Y"), color=INK2, fontsize=11, ha="right", va="top")
    hd.text(1, 0.45, f"Profil {profile}", color=INK2, fontsize=11, ha="right", va="top")
    if data_sim:
        hd.text(1, 0.05, "DONNÉES PARTIELLEMENT SIMULÉES", color=RED, fontsize=9, ha="right",
                fontweight="bold", va="bottom")

    # ── Régime + synthèse ─────────────────────────────────────────────────────
    ax = _panel(fig, 0.03, 0.855, 0.94, 0.07)
    ax.text(0.02, 0.78, f"Régime : {macro.regime}", color=INK, fontsize=14, fontweight="bold", va="top")
    s = A.class_scores(macro.factors).sort_values()
    synth = (f"{macro.regime_text} Classes favorisées : {', '.join(s.index[-3:][::-1])}. "
             f"Classes pénalisées : {', '.join(s.index[:3])}.")
    ax.text(0.02, 0.45, _wrap(synth, 150), color=INK2, fontsize=9.5, va="top", linespacing=1.4)

    # ── Chiffres clés ─────────────────────────────────────────────────────────
    n_crit = sum(a["gravite"] == "critique" for a in alerts)
    n_imp = sum(a["gravite"] == "important" for a in alerts)
    if review:
        p = review["plan"]
        tiles = [("Valeur", f"{p['total']:,.0f}".replace(",", " "), None),
                 ("Volatilité", f"{review['vol_now']:.1%}", f"→ {review['vol_after']:.1%} après ajustement"),
                 ("Pire stress", f"{review['stress'].iloc[0]:+.0%}", review["stress"].index[0]),
                 ("Rotation proposée", f"{p['turnover']:.0%}", f"{len(p['trades'])} ordres"),
                 ("Alertes", f"{n_crit + n_imp}", f"{n_crit} critiques · {n_imp} importantes")]
    else:
        vix = macro.indicators.get("vix")
        tiles = [("VIX", f"{vix:.1f}" if vix and np.isfinite(vix) else "n.d.", "volatilité implicite"),
                 ("Stress de marché", f"{macro.factors['stress']:+.1f}", "échelle −2 / +2"),
                 ("Risque géopolitique", f"{macro.factors['geopolitique']:+.1f}", "échelle −2 / +2"),
                 ("Croissance", f"{macro.factors['croissance']:+.1f}", "échelle −2 / +2"),
                 ("Alertes", f"{n_crit + n_imp}", f"{n_crit} critiques · {n_imp} importantes")]
    w = 0.94 / len(tiles)
    for i, (lab, val, sub) in enumerate(tiles):
        t = _panel(fig, 0.03 + i * w + 0.004, 0.79, w - 0.008, 0.057)
        t.text(0.06, 0.82, lab.upper(), color=MUTED, fontsize=8, fontweight="bold", va="top")
        t.text(0.06, 0.52, val, color=INK, fontsize=17, fontweight="bold", va="top")
        if sub:
            t.text(0.06, 0.13, _wrap(sub, 30), color=INK2, fontsize=7.5, va="bottom")

    # ── Facteurs : aujourd'hui vs il y a 1 mois ───────────────────────────────
    _panel(fig, 0.03, 0.57, 0.46, 0.21, "Facteurs (aujourd'hui vs il y a 1 mois)")
    axf = fig.add_axes([0.20, 0.585, 0.27, 0.165])
    _style(axf)
    labels = [A.FACTORS[k][0] for k in A.F_KEYS]
    now = np.array([macro.factors[k] for k in A.F_KEYS])
    y = np.arange(len(labels))[::-1]
    axf.barh(y, now, color=[GREEN if v >= 0 else RED for v in now], height=0.55)
    if hist is not None and "Il y a 1 mois" in hist.columns:
        before = np.array([float(hist.loc[k, "Il y a 1 mois"]) for k in A.F_KEYS])
        axf.scatter(before, y, s=34, color=INK, zorder=3, label="il y a 1 mois",
                    edgecolor=PANEL, linewidth=1.5)
        axf.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), fontsize=7.5, frameon=False,
                   labelcolor=INK2, borderaxespad=0.2)
    axf.set_yticks(y)
    axf.set_yticklabels(labels, fontsize=8.5, color=INK)
    axf.set_xlim(-2.3, 2.3)
    axf.axvline(0, color=MUTED, lw=0.8)

    # ── Allocation : actuelle vs cible ────────────────────────────────────────
    _panel(fig, 0.51, 0.57, 0.46, 0.21, "Allocation actuelle vs cible" if review else "Allocation cible du desk")
    axa = fig.add_axes([0.665, 0.585, 0.29, 0.165])
    _style(axa)
    if review:
        cur = review["lines"].groupby("Classe")["Poids"].sum().reindex(A.CLASSES).fillna(0)
        tgt = review["target"].reindex(A.CLASSES).fillna(0)
    else:
        cov = None
        tgt_raw = A.propose_allocation(macro.factors, profile)["Proposée (avant risque)"]
        tgt = tgt_raw
        cur = pd.Series(A.PROFILES[profile], index=A.CLASSES)
    keep = [c for c in A.CLASSES if max(cur[c], tgt[c]) > 0.004]
    yy = np.arange(len(keep))[::-1]
    axa.barh(yy + 0.19, [cur[c] * 100 for c in keep], height=0.36, color=MUTED,
             label="Actuelle" if review else "Stratégique")
    axa.barh(yy - 0.19, [tgt[c] * 100 for c in keep], height=0.36, color=CYAN, label="Cible")
    axa.set_yticks(yy)
    axa.set_yticklabels(keep, fontsize=8.5, color=INK)
    axa.legend(loc="lower right", fontsize=7.5, frameon=False, labelcolor=INK2)
    axa.set_xlabel("%", color=INK2, fontsize=8)

    # ── Alertes ───────────────────────────────────────────────────────────────
    ax = _panel(fig, 0.03, 0.355, 0.94, 0.205, "Alertes de la semaine")
    top = alerts[:5]
    if not top:
        ax.text(0.02, 0.8, "Aucune alerte significative cette semaine : contexte sans rupture.",
                color=INK2, fontsize=10, va="top")
    yv = 0.87
    for a in top:
        col = SEV_COL[a["gravite"]]
        ax.add_patch(plt.Rectangle((0.015, yv - 0.15), 0.004, 0.15, color=col, transform=ax.transAxes))
        ax.text(0.03, yv, f"{a['gravite_label'].upper()} · {a['categorie']}", color=col, fontsize=8,
                fontweight="bold", va="top")
        ax.text(0.20, yv, _wrap(a["titre"], 110), color=INK, fontsize=9.5, fontweight="bold", va="top")
        ax.text(0.03, yv - 0.055, _wrap(a["pourquoi"], 175)[:330], color=INK2, fontsize=7.8, va="top",
                linespacing=1.3)
        yv -= 0.172

    # ── Recommandations ──────────────────────────────────────────────────────
    ax = _panel(fig, 0.03, 0.165, 0.555, 0.18,
                "Recommandations du gérant" if review else "Vues par classe d'actifs")
    if review and not review["plan"]["trades"].empty:
        tr = review["plan"]["trades"].head(7)
        heads = ["Prio.", "Ordre", "Ligne", "Montant", "% ptf", "Conviction"]
        xs = [0.02, 0.09, 0.30, 0.47, 0.64, 0.78]
        for x, h in zip(xs, heads):
            ax.text(x, 0.86, h.upper(), color=MUTED, fontsize=7.5, fontweight="bold", va="top")
        yv = 0.76
        for _, r in tr.iterrows():
            col = GREEN if r["Montant"] > 0 else RED
            vals = [f"P{r['Priorité']}", r["Ordre"], r["Ligne"], f"{r['Montant']:+,.0f}".replace(",", " "),
                    f"{r['% du portefeuille']:+.1%}", r["Conviction"]]
            for j, (x, v) in enumerate(zip(xs, vals)):
                ax.text(x, yv, str(v)[:22], color=col if j in (3, 4) else INK, fontsize=8.5, va="top")
            yv -= 0.082
        n_more = len(review["plan"]["trades"]) - len(tr)
        if n_more > 0:
            ax.text(0.02, yv, f"+ {n_more} autre(s) ordre(s) dans la plateforme", color=MUTED, fontsize=7.5, va="top")
        ax.text(0.02, 0.03, _wrap(review["plan"]["timing"], 120), color=INK2, fontsize=7, va="bottom")
    elif review:
        ax.text(0.02, 0.8, _wrap(review["plan"]["timing"], 95), color=INK2, fontsize=9.5, va="top")
    else:
        sc = A.class_scores(macro.factors).sort_values(ascending=False)
        yv = 0.84
        for c, v in sc.items():
            vue = "Surpondérer" if v > 0.6 else ("Sous-pondérer" if v < -0.6 else "Neutre")
            col = GREEN if v > 0.6 else (RED if v < -0.6 else INK2)
            ax.text(0.03, yv, c, color=INK, fontsize=8.8, va="top")
            ax.text(0.45, yv, vue, color=col, fontsize=8.8, fontweight="bold", va="top")
            ax.text(0.72, yv, f"score {v:+.2f}", color=INK2, fontsize=8.5, va="top")
            yv -= 0.073

    # ── Stress tests ─────────────────────────────────────────────────────────
    _panel(fig, 0.595, 0.165, 0.375, 0.18, "Stress tests")
    axs = fig.add_axes([0.765, 0.18, 0.19, 0.135])
    _style(axs)
    if review:
        st_now = review["stress"]
        st_after = review["stress_after"].reindex(st_now.index)
    else:
        st_now = A.stress_test(pd.Series(A.PROFILES[profile], index=A.CLASSES))
        st_after = None
    ys = np.arange(len(st_now))[::-1]
    axs.barh(ys + (0.19 if st_after is not None else 0), st_now.values * 100,
             height=0.36 if st_after is not None else 0.6, color=RED, label="Actuel")
    if st_after is not None:
        axs.barh(ys - 0.19, st_after.values * 100, height=0.36, color=CYAN, label="Après ajustement")
        axs.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, fontsize=7, frameon=False,
                   labelcolor=INK2, borderaxespad=0.2)
    axs.set_yticks(ys)
    axs.set_yticklabels([_wrap(i, 22) for i in st_now.index], fontsize=7.5, color=INK)
    axs.axvline(0, color=MUTED, lw=0.8)
    axs.set_xlabel("%", color=INK2, fontsize=8)

    # ── Déclencheurs + actualité ─────────────────────────────────────────────
    ax = _panel(fig, 0.03, 0.04, 0.94, 0.115, "Déclencheurs de révision et thèmes d'actualité")
    trig = (review["triggers"] if review else [])[:3]
    yv = 0.78
    for x in trig:
        ax.text(0.02, yv, "•  " + _wrap(x, 105), color=INK2, fontsize=8, va="top", linespacing=1.25)
        yv -= 0.25
    hot = sorted(news.values(), key=lambda t: -t["intensity"])[:5]
    xh = 0.70 if trig else 0.02
    yv = 0.78
    for t in hot:
        lvl = t["intensity"]
        col = RED if lvl >= 70 else (AMBER if lvl >= 40 else GREEN)
        ax.text(xh, yv, t["label"], color=INK, fontsize=8.3, va="top")
        ax.text(0.975, yv, f"{lvl:.0f}/100", color=col, fontsize=8.3, fontweight="bold", va="top", ha="right")
        yv -= 0.15

    from utils.legal import CREDIT, AUTHOR
    fig.text(0.5, 0.024, CREDIT, color=MUTED, fontsize=7.5, ha="center")
    fig.text(0.5, 0.008, "Plateforme purement éducative : ne constitue pas un conseil en investissement. "
             f"{AUTHOR} n'est pas responsable des décisions prises ni engagé par les conseils de la plateforme.",
             color=MUTED, fontsize=7, ha="center")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=BG)
    plt.close(fig)
    return buf.getvalue()
