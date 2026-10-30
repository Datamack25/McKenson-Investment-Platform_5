# utils/reporting.py  —  MAM v5 · Images (PNG) et rapports PDF
"""
Graphiques matplotlib exportables en PNG (thème clair pour l'impression ou
sombre aux couleurs de la plateforme) et rapports PDF ReportLab :

* rapport « Auto-Portefeuille IA » (contexte de marché, allocation, backtest,
  risques, signaux ML, méthodologie) ;
* rapport de performance d'un portefeuille de la plateforme.
"""
from __future__ import annotations

import utils.legal as _LEGAL

import io
import re
import zipfile
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter, PercentFormatter

from utils.market_intel import CLASS_COLORS, asset_class, asset_name

_REG_COL = {"Crise / Risk-off": "#ff3b6b", "Ralentissement": "#ff8c00",
            "Reprise": "#ffd700", "Expansion / Risk-on": "#00c878"}

THEMES = {
    "light": {"bg": "#ffffff", "fg": "#1e293b", "muted": "#64748b", "grid": "#e2e8f0",
              "series": ["#0077b6", "#7c3aed", "#f59e0b", "#94a3b8", "#10b981"],
              "pos": "#059669", "neg": "#dc2626"},
    "dark": {"bg": "#080e1a", "fg": "#e2e8f0", "muted": "#7a93b0", "grid": "#1e293b",
             "series": ["#00d4ff", "#7c3aed", "#ffd700", "#94a3b8", "#00ff88"],
             "pos": "#00ff88", "neg": "#ff3b6b"},
}


def _fig(theme: str, w=9.0, h=4.2):
    t = THEMES[theme]
    fig, ax = plt.subplots(figsize=(w, h), dpi=150)
    fig.patch.set_facecolor(t["bg"])
    ax.set_facecolor(t["bg"])
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(colors=t["muted"], labelsize=8)
    ax.grid(True, color=t["grid"], lw=0.6)
    ax.set_axisbelow(True)
    return fig, ax, t


def _title(ax, t, title, sub=None):
    ax.set_title(title, loc="left", fontsize=11, fontweight="bold", color=t["fg"], pad=14 if sub else 8)
    if sub:
        ax.text(0, 1.015, sub, transform=ax.transAxes, fontsize=7.5, color=t["muted"])


def _png(fig) -> bytes:
    buf = io.BytesIO()
    fig.tight_layout()
    try:  # v5.10 : petit logo MAM en haut à droite de chaque image exportée
        from utils.brand import add_to_figure
        fw, fh = fig.get_size_inches()
        h = min(0.10, 0.42 / fh)
        lax = add_to_figure(fig, 1 - h * fh / fw - 0.006, 1 - h - 0.006, h)
        if lax is not None:
            lax.set_alpha(0.9)
    except Exception:
        pass
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return buf.getvalue()


_pct = FuncFormatter(lambda v, _: f"{v:.0%}")


# ══════════════════════════════════════════════════════════════════════════════
#  GRAPHIQUES
# ══════════════════════════════════════════════════════════════════════════════

def chart_performance(series: dict[str, pd.Series], capital: float | None = None,
                      theme="light", title="Performance cumulée",
                      sub="Rendements journaliers composés") -> bytes:
    fig, ax, t = _fig(theme)
    for i, (name, r) in enumerate(series.items()):
        eq = (1 + r.fillna(0)).cumprod()
        y = eq * capital if capital else eq - 1
        ax.plot(y.index, y.values, lw=2.2 if i == 0 else 1.3, color=t["series"][i % 5],
                label=f"{name}  ({eq.iloc[-1] - 1:+.1%})", zorder=3 if i == 0 else 2)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f} $") if capital else _pct)
    ax.legend(frameon=False, fontsize=8, labelcolor=t["fg"], loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    _title(ax, t, title, sub)
    return _png(fig)


def chart_drawdown(series: dict[str, pd.Series], theme="light") -> bytes:
    fig, ax, t = _fig(theme, h=3.2)
    for i, (name, r) in enumerate(series.items()):
        eq = (1 + r.fillna(0)).cumprod()
        dd = eq / eq.cummax() - 1
        if i == 0:
            ax.fill_between(dd.index, dd.values, 0, color=t["neg"], alpha=.25, lw=0)
        ax.plot(dd.index, dd.values, lw=1.6 if i == 0 else 1, color=t["neg"] if i == 0 else t["series"][i % 5],
                label=f"{name}  (max {dd.min():.1%})")
    ax.yaxis.set_major_formatter(_pct)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    ax.legend(frameon=False, fontsize=8, labelcolor=t["fg"], loc="lower left")
    _title(ax, t, "Drawdowns (perte depuis le plus haut)")
    return _png(fig)


def chart_allocation(weights: pd.Series, theme="light", title="Allocation cible") -> bytes:
    t = THEMES[theme]
    w = weights[weights > 0.001].sort_values(ascending=False)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 4.4), dpi=150,
                                 gridspec_kw={"width_ratios": [1, 1.25]})
    fig.patch.set_facecolor(t["bg"])
    by_cls = w.groupby(lambda x: asset_class(x)).sum().sort_values(ascending=False)
    a1.set_facecolor(t["bg"])
    a1.pie(by_cls.values, colors=[CLASS_COLORS.get(c, "#888") for c in by_cls.index],
           startangle=90, counterclock=False, wedgeprops=dict(width=.38, edgecolor=t["bg"], lw=2))
    a1.text(0, 0, f"{len(w)}\nlignes", ha="center", va="center", fontsize=12, color=t["fg"], fontweight="bold")
    a1.legend([f"{c}  {v:.0%}" for c, v in by_cls.items()], loc="upper center",
              bbox_to_anchor=(.5, 0.02), ncol=2, frameon=False, fontsize=8, labelcolor=t["fg"])
    a1.set_title(title, loc="left", fontsize=11, fontweight="bold", color=t["fg"])
    a2.set_facecolor(t["bg"])
    y = np.arange(len(w))[::-1]
    a2.barh(y, w.values, color=[CLASS_COLORS.get(asset_class(x), "#888") for x in w.index], height=.65)
    a2.set_yticks(y, [f"{x}  ·  {asset_name(x)[:22]}" for x in w.index], fontsize=7.5, color=t["fg"])
    for yy, v in zip(y, w.values):
        a2.text(v + .003, yy, f"{v:.1%}", va="center", fontsize=7.5, color=t["fg"])
    a2.xaxis.set_major_formatter(_pct)
    a2.tick_params(colors=t["muted"], labelsize=7.5)
    for s in a2.spines.values():
        s.set_visible(False)
    a2.grid(True, axis="x", color=t["grid"], lw=.6)
    a2.set_axisbelow(True)
    a2.set_xlim(0, w.max() * 1.22)
    return _png(fig)


def chart_monthly(r: pd.Series, theme="light") -> bytes:
    m = (1 + r).resample("ME").prod() - 1
    tab = pd.DataFrame({"y": m.index.year, "m": m.index.month, "v": m.values}).pivot(index="y", columns="m", values="v")
    tab = tab.reindex(columns=range(1, 13))
    fig, ax, t = _fig(theme, h=0.5 + 0.42 * len(tab))
    ax.grid(False)
    lim = max(0.02, np.nanmax(np.abs(tab.values)))
    ax.imshow(tab.values, cmap="RdYlGn", vmin=-lim, vmax=lim, aspect="auto")
    ax.set_xticks(range(12), ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
    ax.set_yticks(range(len(tab)), tab.index)
    for i in range(tab.shape[0]):
        for j in range(12):
            v = tab.values[i, j]
            if v == v:
                ax.text(j, i, f"{v:+.1%}", ha="center", va="center", fontsize=6.5, color="#111")
    _title(ax, t, "Rendements mensuels")
    return _png(fig)


def chart_rolling(r: pd.Series, theme="light", window=126) -> bytes:
    fig, ax, t = _fig(theme, h=3.2)
    vol = r.rolling(window).std() * np.sqrt(252)
    shp = (r.rolling(window).mean() * 252) / vol
    ax.plot(vol.index, vol.values, color=t["series"][0], lw=1.5, label="Volatilité 6 mois")
    ax.yaxis.set_major_formatter(_pct)
    ax2 = ax.twinx()
    ax2.plot(shp.index, shp.values, color=t["series"][2], lw=1.2, label="Sharpe 6 mois (axe droit)")
    ax2.tick_params(colors=t["muted"], labelsize=8)
    for s in ax2.spines.values():
        s.set_visible(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, frameon=False, fontsize=8, labelcolor=t["fg"], loc="upper left")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    _title(ax, t, "Risque glissant")
    return _png(fig)


def chart_signals(signals: pd.DataFrame, theme="light") -> bytes:
    s = signals.sort_values("p_up")
    fig, ax, t = _fig(theme, h=0.6 + 0.24 * len(s))
    cols = [t["pos"] if p >= .53 else t["neg"] if p <= .47 else t["muted"] for p in s["p_up"]]
    ax.barh(s.index, s["p_up"] - .5, left=.5, color=cols, height=.65)
    ax.axvline(.5, color=t["fg"], lw=.8)
    ax.set_xlim(max(0, s["p_up"].min() - .05), min(1, s["p_up"].max() + .05))
    ax.xaxis.set_major_formatter(_pct)
    ax.tick_params(axis="y", labelsize=7.5, colors=t["fg"])
    for i, (tk, p) in enumerate(s["p_up"].items()):
        ax.text(p + (.004 if p >= .5 else -.004), i, f"{p:.0%}", va="center",
                ha="left" if p >= .5 else "right", fontsize=6.5, color=t["fg"])
    _title(ax, t, "Probabilité de hausse à 1 mois (modèle ML)", "Vert : renforcer · Rouge : alléger · Gris : neutre")
    return _png(fig)


def chart_importance(imp: pd.Series, labels: dict, theme="light", top=12) -> bytes:
    s = imp.head(top)[::-1]
    fig, ax, t = _fig(theme, h=0.8 + .26 * len(s))
    ax.barh([labels.get(k, k) for k in s.index], s.values, color=t["series"][1], height=.6)
    ax.xaxis.set_major_formatter(_pct)
    ax.tick_params(axis="y", labelsize=8, colors=t["fg"])
    _title(ax, t, "Variables les plus influentes", "Importance par permutation, hors échantillon")
    return _png(fig)


def chart_regimes(price: pd.Series, labels: pd.Series, theme="light") -> bytes:
    fig, ax, t = _fig(theme, h=3.4)
    lab = labels.reindex(price.index).ffill()
    ax.plot(price.index, price.values, color=t["fg"], lw=1.2)
    ymin, ymax = price.min(), price.max()
    prev, start = None, None
    for d, v in lab.items():
        if v != prev:
            if prev is not None and isinstance(prev, str):
                ax.axvspan(start, d, color=_REG_COL.get(prev, "#999"), alpha=.18, lw=0)
            prev, start = v, d
    if isinstance(prev, str):
        ax.axvspan(start, lab.index[-1], color=_REG_COL.get(prev, "#999"), alpha=.18, lw=0)
    from matplotlib.patches import Patch
    ax.legend(handles=[Patch(color=c, alpha=.5, label=n) for n, c in _REG_COL.items()],
              frameon=False, fontsize=7.5, ncol=4, labelcolor=t["fg"], loc="upper left")
    ax.set_ylim(ymin * .95, ymax * 1.12)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%y"))
    _title(ax, t, "Régimes de marché détectés (S&P 500)")
    return _png(fig)


def chart_stress(stress: pd.DataFrame, theme="light", capital: float | None = None) -> bytes:
    s = stress.sort_values("Impact", ascending=False)
    fig, ax, t = _fig(theme, h=3.2)
    cols = [t["pos"] if v >= 0 else t["neg"] for v in s["Impact"]]
    ax.barh(s["Scénario"], s["Impact"], color=cols, height=.6)
    ax.axvline(0, color=t["fg"], lw=.8)
    ax.xaxis.set_major_formatter(_pct)
    ax.tick_params(axis="y", labelsize=8, colors=t["fg"])
    for i, v in enumerate(s["Impact"]):
        lab = f"{v:+.1%}" + (f"  ({v * capital:+,.0f} $)" if capital else "")
        ax.text(v, i, "  " + lab if v >= 0 else lab + "  ", va="center",
                ha="left" if v >= 0 else "right", fontsize=7.5, color=t["fg"])
    lo, hi = s["Impact"].min(), s["Impact"].max()
    ax.set_xlim(min(lo * 1.8, -0.05), max(hi * 1.8, 0.05))
    _title(ax, t, "Stress tests (scénarios hypothétiques)")
    return _png(fig)


def chart_montecarlo(mc: dict, theme="light") -> bytes:
    fig, ax, t = _fig(theme, h=3.6)
    p = mc["percentiles"]
    x = np.arange(len(p))
    c = t["series"][0]
    ax.fill_between(x, p["p5"], p["p95"], color=c, alpha=.15, lw=0, label="Intervalle 5 %–95 %")
    ax.fill_between(x, p["p25"], p["p75"], color=c, alpha=.3, lw=0, label="Intervalle 25 %–75 %")
    ax.plot(x, p["p50"], color=c, lw=2, label="Médiane")
    ax.axhline(mc["capital"], color=t["muted"], lw=.8, ls="--")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v / 1e6:.2f} M$" if mc["capital"] >= 1e6 else f"{v:,.0f} $"))
    ax.set_xlabel("Jours de bourse", color=t["muted"], fontsize=8)
    ax.legend(frameon=False, fontsize=8, labelcolor=t["fg"], loc="upper left")
    _title(ax, t, "Projection Monte Carlo à 1 an",
           f"Probabilité de perte {mc['prob_loss']:.0%} · médiane {np.median(mc['final']):,.0f} $")
    return _png(fig)


def chart_risk_contrib(w: pd.Series, rc: pd.Series, theme="light") -> bytes:
    idx = w[w > 0.001].sort_values(ascending=False).index
    fig, ax, t = _fig(theme, h=3.4)
    x = np.arange(len(idx))
    ax.bar(x - .2, w[idx], .4, color=t["series"][0], label="Poids")
    ax.bar(x + .2, rc.reindex(idx).fillna(0), .4, color=t["series"][2], label="Contribution au risque")
    ax.set_xticks(x, idx, rotation=45, fontsize=7.5, color=t["fg"])
    ax.yaxis.set_major_formatter(_pct)
    ax.legend(frameon=False, fontsize=8, labelcolor=t["fg"])
    _title(ax, t, "Poids vs contribution au risque")
    return _png(fig)


def chart_corr(daily: pd.DataFrame, theme="light") -> bytes:
    c = daily.corr()
    n = len(c)
    fig, ax, t = _fig(theme, w=max(5, .38 * n + 2), h=max(4, .38 * n + 1))
    ax.grid(False)
    im = ax.imshow(c.values, cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(n), c.columns, rotation=90, fontsize=7, color=t["fg"])
    ax.set_yticks(range(n), c.index, fontsize=7, color=t["fg"])
    cb = fig.colorbar(im, ax=ax, fraction=.04)
    cb.ax.tick_params(labelsize=7, colors=t["muted"])
    _title(ax, t, "Corrélations (rendements journaliers)")
    return _png(fig)


def chart_positions_pnl(pos: pd.DataFrame, theme="light") -> bytes:
    s = pos.set_index("ticker")["unreal_pnl"].sort_values()
    fig, ax, t = _fig(theme, h=0.8 + .3 * len(s))
    ax.barh(s.index, s.values, color=[t["pos"] if v >= 0 else t["neg"] for v in s.values], height=.6)
    ax.axvline(0, color=t["fg"], lw=.8)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f} $"))
    ax.tick_params(axis="y", labelsize=8, colors=t["fg"])
    _title(ax, t, "P&L latent par position")
    return _png(fig)


def zip_images(images: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in images.items():
            z.writestr(f"{name}.png", data)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════════════════════
#  PDF (ReportLab)
# ══════════════════════════════════════════════════════════════════════════════

def _fonts() -> tuple[str, str]:
    """Police Unicode (DejaVu, livrée avec matplotlib) pour les accents et symboles."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    try:
        if "DejaVu" not in pdfmetrics.getRegisteredFontNames():
            base = matplotlib.get_data_path() + "/fonts/ttf/"
            pdfmetrics.registerFont(TTFont("DejaVu", base + "DejaVuSans.ttf"))
            pdfmetrics.registerFont(TTFont("DejaVu-Bold", base + "DejaVuSans-Bold.ttf"))
        return "DejaVu", "DejaVu-Bold"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


_EMOJI = re.compile("[\U0001F000-\U0001FFFF☀-➿️]")


def _clean(text: str) -> str:
    text = _EMOJI.sub("", str(text))
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text).strip()


def make_pdf(title: str, subtitle: str, blocks: list[tuple]) -> bytes:
    """blocks : ('h', txt) · ('p', txt) · ('bullets', [txt]) · ('kpis', [(lab, val)])
    · ('table', rows, col_widths_cm|None) · ('img', png, width_cm) · ('break',) · ('note', txt)"""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate,
                                    Spacer, Table, TableStyle)

    reg, bold = _fonts()
    navy, cyan, muted = colors.HexColor("#0b1424"), colors.HexColor("#0077b6"), colors.HexColor("#64748b")
    S = {
        "title": ParagraphStyle("t", fontName=bold, fontSize=20, leading=24, textColor=navy),
        "sub": ParagraphStyle("s", fontName=reg, fontSize=9.5, leading=13, textColor=muted),
        "h": ParagraphStyle("h", fontName=bold, fontSize=13, leading=17, textColor=cyan,
                            spaceBefore=10, spaceAfter=5),
        "p": ParagraphStyle("p", fontName=reg, fontSize=9.2, leading=13.2, alignment=TA_LEFT,
                            textColor=colors.HexColor("#1e293b"), spaceAfter=4),
        "note": ParagraphStyle("n", fontName=reg, fontSize=7.6, leading=10, textColor=muted),
        "cell": ParagraphStyle("c", fontName=reg, fontSize=7.8, leading=9.6),
        "cellb": ParagraphStyle("cb", fontName=bold, fontSize=7.8, leading=9.6, textColor=colors.white),
        "kl": ParagraphStyle("kl", fontName=reg, fontSize=7, leading=9, textColor=muted),
        "kv": ParagraphStyle("kv", fontName=bold, fontSize=12, leading=15, textColor=navy),
    }
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1.6 * cm, rightMargin=1.6 * cm,
                            topMargin=1.5 * cm, bottomMargin=1.6 * cm, title=title,
                            author=_LEGAL.AUTHOR + " — MAM McKenson Asset Management")
    width = A4[0] - 3.2 * cm
    from reportlab.lib.utils import ImageReader
    from utils import brand as _brand
    _lb = _brand.png_bytes("mark")
    logo = ImageReader(io.BytesIO(_lb)) if _lb else None

    def on_page(c, d):
        c.saveState()
        c.setFillColor(navy)
        c.rect(0, A4[1] - .55 * cm, A4[0], .55 * cm, fill=1, stroke=0)
        x_txt = 1.6 * cm
        if logo is not None:   # v5.10 : logo MAM dans le bandeau de chaque page
            c.drawImage(logo, 1.6 * cm, A4[1] - .5 * cm, width=.45 * cm, height=.45 * cm, mask="auto")
            x_txt = 2.2 * cm
        c.setFillColor(colors.HexColor("#00d4ff"))
        c.setFont(bold, 7.5)
        c.drawString(x_txt, A4[1] - .37 * cm, f"MAM · McKenson Asset Management · v{_LEGAL.APP_VERSION}")
        c.setFillColor(muted)
        c.setFont(reg, 7)
        c.setFont(reg, 6.3)
        c.drawString(1.6 * cm, 1.1 * cm, _LEGAL.CREDIT)
        c.drawString(1.6 * cm, .8 * cm, "Plateforme purement éducative — ne constitue pas un conseil en investissement.")
        c.drawString(1.6 * cm, .5 * cm, f"{_LEGAL.AUTHOR} n'est pas responsable des décisions prises "
                     "ni engagé par les décisions ou conseils de la plateforme.")
        c.setFont(reg, 7)
        c.drawRightString(A4[0] - 1.6 * cm, 1.1 * cm, f"Page {d.page}")
        c.restoreState()

    head = [Paragraph(_clean(title), S["title"]), Spacer(1, 3), Paragraph(_clean(subtitle), S["sub"])]
    if logo is not None:       # page de titre : logo à gauche du titre
        lt = Table([[Image(io.BytesIO(_brand.png_bytes("mark")), width=1.5 * cm, height=1.5 * cm), head]],
                   colWidths=[1.9 * cm, width - 1.9 * cm])
        lt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        story = [lt, Spacer(1, 10)]
    else:
        story = head + [Spacer(1, 10)]
    for b in blocks:
        kind = b[0]
        if kind == "h":
            story.append(Paragraph(_clean(b[1]), S["h"]))
        elif kind == "p":
            story.append(Paragraph(_clean(b[1]), S["p"]))
        elif kind == "note":
            story.append(Paragraph(_clean(b[1]), S["note"]))
        elif kind == "bullets":
            for x in b[1]:
                story.append(Paragraph("• " + _clean(x), S["p"]))
        elif kind == "kpis":
            items = b[1]
            per_row = 4
            rows = []
            for i in range(0, len(items), per_row):
                chunk = items[i:i + per_row] + [("", "")] * (per_row - len(items[i:i + per_row]))
                rows.append([[Paragraph(_clean(l), S["kl"]), Paragraph(_clean(v), S["kv"])] for l, v in chunk])
            tb = Table(rows, colWidths=[width / per_row] * per_row)
            tb.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f5f9")),
                ("BOX", (0, 0), (-1, -1), .5, colors.HexColor("#cbd5e1")),
                ("INNERGRID", (0, 0), (-1, -1), .5, colors.white),
                ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story += [tb, Spacer(1, 8)]
        elif kind == "table":
            rows = b[1]
            cw = b[2] if len(b) > 2 and b[2] else None
            data = [[Paragraph(_clean(c), S["cellb"]) for c in rows[0]]] + \
                   [[Paragraph(_clean(c), S["cell"]) for c in r] for r in rows[1:]]
            tb = Table(data, colWidths=[x * cm for x in cw] if cw else None, repeatRows=1)
            tb.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), navy),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LINEBELOW", (0, 0), (-1, -1), .25, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
            story += [tb, Spacer(1, 8)]
        elif kind == "img":
            from reportlab.lib.utils import ImageReader
            ir = ImageReader(io.BytesIO(b[1]))
            iw, ih = ir.getSize()
            w = min(b[2] * cm if len(b) > 2 else width, width)
            story.append(KeepTogether([Image(io.BytesIO(b[1]), width=w, height=w * ih / iw), Spacer(1, 6)]))
        elif kind == "break":
            story.append(PageBreak())
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()


def stamp() -> str:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Paris")).strftime("%d/%m/%Y à %H:%M")
    except Exception:
        return datetime.now().strftime("%d/%m/%Y à %H:%M")
