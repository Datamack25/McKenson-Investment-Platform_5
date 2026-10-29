# utils/report_builders.py  —  MAM v5 · Assemblage des rapports (images + PDF)
from __future__ import annotations

import numpy as np
import pandas as pd

from utils import reporting as R
from utils.auto_portfolio import (METHODS, PROFILES, fmt_metric, monte_carlo, perf_metrics,
                                  stress_test)
import utils.legal as _LEGAL
from utils.market_intel import asset_class, asset_name
from utils.ml_engine import FEATURE_FAMILY, FEATURE_LABELS

DISCLAIMER = ("Avertissement : ce document est produit par un outil de simulation pédagogique. Les "
              "prévisions issues de modèles statistiques et d'apprentissage automatique sont incertaines ; "
              "les performances passées et simulées (backtest) ne préjugent pas des performances futures. "
              "Ce document ne constitue ni un conseil en investissement personnalisé ni une recommandation "
              "d'achat ou de vente. " + _LEGAL.CREDIT + " " + _LEGAL.DISCLAIMER)


def _fmt_pct(v, sign=False):
    return "—" if v is None or v != v else (f"{v:+.1%}" if sign else f"{v:.1%}")


# ══════════════════════════════════════════════════════════════════════════════
#  AUTO-PORTEFEUILLE
# ══════════════════════════════════════════════════════════════════════════════

def auto_images(ctx: dict, theme: str = "light") -> dict[str, bytes]:
    imgs = {}
    alloc = ctx["alloc"]
    imgs["01_allocation"] = R.chart_allocation(alloc["weights"], theme)
    bt = ctx.get("bt") or {}
    if bt.get("ok"):
        series = {"Stratégie IA": bt["returns"]}
        for c in ctx["bench"].columns:
            series[c] = ctx["bench"][c]
        imgs["02_performance"] = R.chart_performance(series, None, theme,
                                                     "Backtest walk-forward vs indices de référence",
                                                     "Rendements journaliers composés, frais de transaction inclus pour la stratégie")
        imgs["03_drawdown"] = R.chart_drawdown({"Stratégie IA": bt["returns"],
                                                ctx["bench"].columns[0]: ctx["bench"].iloc[:, 0]}, theme)
        imgs["04_rendements_mensuels"] = R.chart_monthly(bt["returns"], theme)
        imgs["05_risque_glissant"] = R.chart_rolling(bt["returns"], theme)
    imgs["06_contribution_risque"] = R.chart_risk_contrib(alloc["weights"], alloc["risk_contrib"], theme)
    imgs["07_stress_tests"] = R.chart_stress(ctx["stress"], theme, ctx["capital"])
    if ctx.get("mc"):
        imgs["08_monte_carlo"] = R.chart_montecarlo(ctx["mc"], theme)
    imgs["09_signaux_ml"] = R.chart_signals(ctx["signals"], theme)
    imp = ctx.get("validation", {}).get("importance")
    if imp is not None and len(imp):
        imgs["10_variables_influentes"] = R.chart_importance(imp, FEATURE_LABELS, theme)
    reg = ctx.get("regimes") or {}
    if reg.get("ok") and ctx.get("spy") is not None:
        imgs["11_regimes"] = R.chart_regimes(ctx["spy"], reg["label"], theme)
    imgs["12_correlations"] = R.chart_corr(alloc["daily"][alloc["weights"][alloc["weights"] > 0].index], theme)
    return imgs


def _auto_simple_blocks(ctx: dict) -> list[tuple]:
    """En bref (v5.6) : l'allocation proposée aurait-elle fait mieux ou moins bien que le marché sur le backtest ?"""
    from utils.plain_summary import pct, pts
    bt = ctx.get("bt") or {}
    alloc = ctx["alloc"]
    ph = []
    if bt.get("ok") and isinstance(ctx.get("bench"), pd.DataFrame) and len(ctx["bench"].columns):
        r = bt["returns"].dropna()
        b = ctx["bench"].iloc[:, 0].reindex(r.index).fillna(0)
        p_, pb = float((1 + r).prod() - 1), float((1 + b).prod() - 1)
        gap = p_ - pb
        word = "mieux" if gap > 0.005 else ("moins bien" if gap < -0.005 else "à peu près comme")
        ph.append(f"**En une phrase : sur le passé testé, cette allocation aurait fait {word} que le marché "
                  f"({ctx['bench'].columns[0]}).**")
        ph.append(f"Du {bt['start']:%m/%Y} au {bt['end']:%m/%Y}, elle aurait {'gagné' if p_ >= 0 else 'perdu'} "
                  f"{pct(abs(p_))}, contre {pct(abs(pb))} {'de gain' if pb >= 0 else 'de perte'} pour l'indice : "
                  f"un écart de {pts(gap)}.")
        dd = ctx.get("metrics", {}).get("Drawdown max")
        if dd is not None and np.isfinite(dd):
            ph.append(f"Sa plus forte baisse entre un sommet et un creux aurait été de {pct(abs(dd))} : c'est ce qu'il "
                      "faut être prêt à traverser.")
    else:
        ph.append("**En une phrase : allocation proposée selon votre profil et le contexte de marché, sans backtest "
                  "sur cette génération.**")
    top = alloc["weights"][alloc["weights"] > 0].sort_values(ascending=False).head(3)
    if len(top):
        ph.append("Ce qui pèse le plus : " + ", ".join(f"{t} ({w:.0%})" for t, w in top.items())
                  + f". Profil retenu : {alloc['profile']}.")
    ph.append("Un backtest décrit le passé : il ne garantit pas les résultats futurs.")
    return [("h", "En bref — en mots simples"), ("p", ph[0]), ("bullets", ph[1:])]


def auto_pdf(ctx: dict) -> bytes:
    alloc, sig, cap = ctx["alloc"], ctx["signals"], ctx["capital"]
    imgs = ctx.get("images") or auto_images(ctx, "light")
    prof = PROFILES[alloc["profile"]]
    st_ = alloc["stats"]
    blocks: list[tuple] = []
    blocks.append(("kpis", [
        ("Profil", f"{alloc['profile']}"), ("Capital", f"{cap:,.0f} $"),
        ("Régime de marché", alloc["regime"]), ("Lignes", str(int((alloc['weights'] > 0).sum()))),
        ("Rendement attendu", _fmt_pct(st_["return"], True)), ("Volatilité estimée", _fmt_pct(st_["volatility"])),
        ("Score macro", f"{ctx.get('macro_score', 0):+.0f}/100"),
        ("Risque géopolitique", f"{ctx.get('news', {}).get('gpr', 0):.0f}/100"),
    ]))
    blocks += _auto_simple_blocks(ctx)
    blocks.append(("h", "1. Synthèse et justification"))
    blocks.append(("bullets", ctx.get("explanation", [])))
    blocks.append(("note", f"Méthode : {METHODS.get(alloc['method'], alloc['method'])}. "
                           f"Source des données : {ctx.get('source', '—')}."))
    blocks.append(("h", "2. Allocation cible"))
    blocks.append(("img", imgs["01_allocation"], 17.5))
    rows = [["Ticker", "Actif", "Classe", "Poids", "Montant", "Vue ML (an)", "Signal"]]
    for t, w in alloc["weights"][alloc["weights"] > 0].items():
        s = sig.loc[t] if t in sig.index else None
        rows.append([t, asset_name(t), asset_class(t), f"{w:.1%}", f"{w * cap:,.0f} $",
                     _fmt_pct(alloc["views"].get(t), True), s["signal"] if s is not None else "—"])
    blocks.append(("table", rows, [1.8, 4.4, 2.9, 1.5, 2.4, 1.9, 3.1]))
    b = alloc["bounds"]
    blocks.append(("note", "Bornes par classe (profil ajusté au régime) : " +
                   " · ".join(f"{c} {lo:.0%}–{hi:.0%}" for c, (lo, hi) in b.items())))
    blocks.append(("break",))
    blocks.append(("h", "3. Contexte de marché"))
    if ctx.get("macro_rows"):
        rows = [["Indicateur", "Valeur", "Lecture"]]
        for r in ctx["macro_rows"]:
            v = r["valeur"]
            rows.append([r["indicateur"], r["format"].format(v) if v == v else "—", r["lecture"]])
        blocks.append(("table", rows, [5.2, 2.2, 10.4]))
    if "11_regimes" in imgs:
        blocks.append(("img", imgs["11_regimes"], 17))
    nv = ctx.get("news") or {}
    if nv:
        top = sorted(nv["intensity"].items(), key=lambda x: -x[1])[:6]
        from utils.market_intel import THEMES
        blocks.append(("p", f"Lecture des actualités ({nv['n']} titres analysés) : indice de risque "
                            f"géopolitique **{nv['gpr']:.0f}/100**, climat économique **{nv['econ_score']:+.0f}/100**, "
                            f"tonalité moyenne {nv['sentiment']:+.2f}. Thèmes dominants : " +
                       ", ".join(f"{THEMES[k]['label']} ({v:.0%})" for k, v in top if v > 0) + "."))
    bt = ctx.get("bt") or {}
    if bt.get("ok"):
        blocks.append(("break",))
        blocks.append(("h", "4. Backtest walk-forward"))
        blocks.append(("p", f"Période {bt['start']:%m/%Y} – {bt['end']:%m/%Y}, rééquilibrage mensuel, "
                            f"modèle ré-entraîné tous les 3 mois avec les seules données disponibles à chaque "
                            f"date, frais {bt['cost_bps']:.0f} pb par unité de rotation (rotation annuelle "
                            f"{bt['turnover']:.0%}). Les actualités ne sont pas incluses dans le backtest "
                            f"(pas d'historique fiable)."))
        blocks.append(("img", imgs["02_performance"], 17.5))
        names = ["Stratégie IA"] + list(ctx["bench"].columns)
        mets = [ctx["metrics"]] + [perf_metrics(ctx["bench"][c]) for c in ctx["bench"].columns]
        keys = ["Rendement annualisé", "Volatilité", "Sharpe", "Sortino", "Drawdown max", "Calmar",
                "VaR 95 % (1 j)", "Mois positifs"]
        rows = [["Mesure"] + names] + [[k] + [fmt_metric(k, m.get(k, np.nan)) for m in mets] for k in keys]
        blocks.append(("table", rows, None))
        blocks.append(("img", imgs["03_drawdown"], 17))
        blocks.append(("img", imgs["04_rendements_mensuels"], 15))
        blocks.append(("img", imgs["05_risque_glissant"], 17))
    blocks.append(("break",))
    blocks.append(("h", "5. Risques"))
    blocks.append(("img", imgs["06_contribution_risque"], 16))
    blocks.append(("img", imgs["07_stress_tests"], 17))
    rows = [["Scénario", "Impact", "Perte / gain ($)", "Pire contributeur"]]
    for _, r in ctx["stress"].iterrows():
        rows.append([r["Scénario"], f"{r['Impact']:+.1%}", f"{r['Impact'] * cap:+,.0f}",
                     f"{r['Pire contributeur']} ({r['Contribution']:+.1%})"])
    blocks.append(("table", rows, [6.5, 2.0, 3.5, 5.6]))
    if ctx.get("mc"):
        mc = ctx["mc"]
        blocks.append(("img", imgs["08_monte_carlo"], 17))
        blocks.append(("p", f"Sur 2 000 trajectoires simulées à 1 an : valeur médiane "
                            f"{np.median(mc['final']):,.0f} $, intervalle 5 %–95 % [{mc['p5']:,.0f} $ ; "
                            f"{mc['p95']:,.0f} $], probabilité de perte {mc['prob_loss']:.0%}, VaR 95 % "
                            f"{mc['var95']:,.0f} $."))
    blocks.append(("break",))
    blocks.append(("h", "6. Signaux du modèle d'apprentissage automatique"))
    v = ctx.get("validation") or {}
    if v.get("ok"):
        blocks.append(("kpis", [("Précision hors échantillon", f"{v['accuracy']:.1%}"),
                                ("Référence naïve", f"{v['baseline']:.1%}"), ("AUC", f"{v['auc']:.3f}"),
                                ("IC moyen (rang)", f"{v['ic']:+.3f}")]))
    blocks.append(("img", imgs["09_signaux_ml"], 15))
    rows = [["Ticker", "Classe", "P(hausse 1 m)", "Rdt attendu 1 m", "Signal", "Moteurs principaux"]]
    for t, s in sig.iterrows():
        rows.append([t, s["classe"], f"{s['p_up']:.0%}", f"{s['exp_ret_1m']:+.1%}", s["signal"],
                     ", ".join((s["drivers_up"] if s["p_up"] >= .5 else s["drivers_down"])[:2])])
    blocks.append(("table", rows, [1.8, 2.7, 2.0, 2.2, 3.1, 6.0]))
    if "10_variables_influentes" in imgs:
        blocks.append(("img", imgs["10_variables_influentes"], 14))
    blocks.append(("h", "7. Méthodologie"))
    blocks.append(("bullets", [
        "Données : cours ajustés quotidiens (Yahoo Finance) de l'univers multi-actifs et séries macro "
        "(VIX, taux 10 ans et 3 mois, dollar, pétrole, or, cuivre, crédit HY/Treasuries).",
        "Modèle : ensemble Gradient Boosting + régression logistique régularisée, entraîné sur un panel "
        "hebdomadaire (momentum, volatilité, techniques, bêta, facteurs macro). Cible : rendement à 21 jours.",
        "Validation : walk-forward chronologique en 5 plis avec purge de 21 jours (aucune donnée future).",
        "Régimes : mélange gaussien sur tendance, volatilité, VIX, crédit et pente de courbe.",
        "Actualités : thèmes géopolitiques et économiques détectés dans les titres, traduits en inclinaisons "
        "par classe d'actifs via une matrice d'impact explicite.",
        "Construction : bornes par classe selon le profil et le régime, rendements Black-Litterman "
        "(a priori d'équilibre + vues ML pondérées par la confiance hors échantillon), covariance "
        "Ledoit-Wolf, optimisation sous contraintes.",
    ]))
    blocks.append(("note", DISCLAIMER))
    return R.make_pdf(f"Auto-Portefeuille IA — profil {alloc['profile']}",
                      f"Généré le {R.stamp()} · {prof['desc']} · {METHODS.get(alloc['method'])}", blocks)


# ══════════════════════════════════════════════════════════════════════════════
#  PORTEFEUILLE EXISTANT
# ══════════════════════════════════════════════════════════════════════════════

def portfolio_context(port: dict, live: dict, hist: pd.DataFrame, signals: pd.DataFrame | None = None) -> dict:
    """Valorisation, poids, performance simulée des positions actuelles (1 an), risques."""
    from utils.data import value_portfolio
    val = value_portfolio(port, {t: v[0] for t, v in live.items()})
    pos = pd.DataFrame(val["positions"])
    nav = val["total"]
    ctx = {"port": port, "val": val, "pos": pos, "nav": nav, "signals": signals}
    try:  # En bref : performance réelle vs indice et sa cause, en mots simples (v5.6)
        from utils.plain_summary import plain_summary
        ctx["simple"] = plain_summary(port, "S&P 500")
    except Exception:
        ctx["simple"] = None
    if pos.empty:
        return ctx
    w = pos.set_index("ticker")["market_value"] / nav
    ctx["weights"] = w
    cols = [t for t in w.index if t in hist.columns]
    if cols:
        r = hist[cols].pct_change(fill_method=None).fillna(0)
        wr = (w[cols] / w[cols].sum()) * (1 - val["cash"] / nav)
        ctx["sim_returns"] = (r @ wr.values)
        if "SPY" in hist:
            ctx["spy"] = hist["SPY"].pct_change(fill_method=None).fillna(0)
        ctx["metrics"] = perf_metrics(ctx["sim_returns"], ctx.get("spy"))
        ctx["mc"] = monte_carlo(ctx["sim_returns"], nav)
    ctx["stress"] = stress_test(w)
    h = port.get("history") or []
    if len(h) >= 2:
        hd = pd.DataFrame(h)
        if {"date", "value"} <= set(hd.columns):
            hd["date"] = pd.to_datetime(hd["date"], errors="coerce")
            ctx["nav_hist"] = hd.dropna(subset=["date"]).set_index("date")["value"].astype(float)
    return ctx


def portfolio_images(ctx: dict, theme="light") -> dict[str, bytes]:
    imgs = {}
    try:
        from utils.plain_summary import summary_png
        png = summary_png(ctx.get("simple"), theme=theme)
        if png:
            imgs["00_en_bref"] = png
    except Exception:
        pass
    if "weights" not in ctx:
        return imgs
    w = ctx["weights"]
    imgs["01_allocation"] = R.chart_allocation(w / w.sum(), theme, "Répartition des positions")
    imgs["02_pnl_positions"] = R.chart_positions_pnl(ctx["pos"], theme)
    if "sim_returns" in ctx:
        series = {"Positions actuelles": ctx["sim_returns"]}
        if "spy" in ctx:
            series["S&P 500 (SPY)"] = ctx["spy"]
        imgs["03_performance_1an"] = R.chart_performance(series, None, theme,
                                                         "Performance sur 1 an des positions actuelles")
        imgs["04_drawdown"] = R.chart_drawdown(series, theme)
        imgs["05_rendements_mensuels"] = R.chart_monthly(ctx["sim_returns"], theme)
    if "nav_hist" in ctx and len(ctx["nav_hist"]) >= 2:
        r = ctx["nav_hist"].pct_change().fillna(0)
        imgs["06_valeur_enregistree"] = R.chart_performance({"Valeur enregistrée": r},
                                                            float(ctx["nav_hist"].iloc[0]), theme,
                                                            "Historique de valeur enregistré")
    imgs["07_stress_tests"] = R.chart_stress(ctx["stress"], theme, ctx["nav"])
    if ctx.get("mc"):
        imgs["08_monte_carlo"] = R.chart_montecarlo(ctx["mc"], theme)
    return imgs


def _twr(port: dict, nav: float) -> float:
    from utils.performance import since_inception
    return since_inception(port, nav)[0]


def portfolio_pdf(ctx: dict) -> bytes:
    port, val, nav = ctx["port"], ctx["val"], ctx["nav"]
    imgs = ctx.get("images") or portfolio_images(ctx)
    init = float(port.get("initial_cash", nav) or nav)
    from utils.plain_summary import pdf_blocks
    blocks = pdf_blocks(ctx.get("simple"))
    blocks += [("kpis", [
        ("Valeur totale", f"{nav:,.0f} $"), ("Performance depuis l'origine (TWR)", _fmt_pct(_twr(port, nav), True)),
        ("Liquidités", f"{val['cash']:,.0f} $"), ("Positions", str(len(ctx["pos"]))),
        ("Capital initial", f"{init:,.0f} $"), ("P&L latent", f"{ctx['pos']['unreal_pnl'].sum():+,.0f} $" if len(ctx['pos']) else "—"),
        ("Stratégie", str(port.get("strategy", "—"))), ("Ordres passés", str(len(port.get("trades", [])))),
    ])]
    if ctx["pos"].empty:
        blocks.append(("p", "Le portefeuille ne contient aucune position pour l'instant."))
    else:
        blocks.append(("h", "1. Positions"))
        blocks.append(("img", imgs["01_allocation"], 17.5))
        rows = [["Ticker", "Quantité", "PRU", "Cours", "Valeur", "Poids", "P&L latent", "P&L %"]]
        for _, p in ctx["pos"].sort_values("market_value", ascending=False).iterrows():
            rows.append([p["ticker"], f"{p['qty']:,.4f}", f"{p['avg_price']:,.2f}", f"{p['current_price']:,.2f}",
                         f"{p['market_value']:,.0f}", f"{p['market_value'] / nav:.1%}",
                         f"{p['unreal_pnl']:+,.0f}", f"{p['pnl_pct']:+.1f} %"])
        blocks.append(("table", rows, None))
        blocks.append(("img", imgs["02_pnl_positions"], 15))
        if "03_performance_1an" in imgs:
            blocks.append(("break",))
            blocks.append(("h", "2. Performance et risque (positions actuelles sur 1 an)"))
            blocks.append(("note", "Simulation : rendement qu'auraient eu les positions actuelles, à poids constants, "
                                   "sur les 12 derniers mois. Ce n'est pas la performance réalisée du portefeuille."))
            blocks.append(("img", imgs["03_performance_1an"], 17.5))
            m = ctx.get("metrics", {})
            rows = [["Mesure", "Valeur", "Mesure", "Valeur"]]
            ks = list(m.keys())
            for i in range(0, len(ks), 2):
                a = ks[i]
                b = ks[i + 1] if i + 1 < len(ks) else None
                rows.append([a, fmt_metric(a, m[a]), b or "", fmt_metric(b, m[b]) if b else ""])
            blocks.append(("table", rows, [4.8, 3.9, 4.8, 3.9]))
            blocks.append(("img", imgs["04_drawdown"], 17))
            blocks.append(("img", imgs["05_rendements_mensuels"], 15))
        if "06_valeur_enregistree" in imgs:
            blocks.append(("img", imgs["06_valeur_enregistree"], 17))
        blocks.append(("break",))
        blocks.append(("h", "3. Stress tests et projection"))
        blocks.append(("img", imgs["07_stress_tests"], 17))
        if "08_monte_carlo" in imgs:
            blocks.append(("img", imgs["08_monte_carlo"], 17))
        sig = ctx.get("signals")
        if sig is not None and len(sig):
            held = [t for t in ctx["weights"].index if t in sig.index]
            if held:
                blocks.append(("h", "4. Avis du modèle ML sur les positions"))
                rows = [["Ticker", "P(hausse 1 m)", "Signal", "Moteurs"]]
                for t in held:
                    s = sig.loc[t]
                    rows.append([t, f"{s['p_up']:.0%}", s["signal"],
                                 ", ".join((s["drivers_up"] if s["p_up"] >= .5 else s["drivers_down"])[:3])])
                blocks.append(("table", rows, [2.2, 2.8, 3.2, 9.6]))
    trades = port.get("trades", [])[-25:]
    if trades:
        blocks.append(("h", "Derniers ordres"))
        rows = [["Date", "Ticker", "Sens", "Quantité", "Prix", "Montant"]]
        for t in reversed(trades):
            rows.append([str(t.get("date", "")), t.get("ticker", ""), t.get("action", ""),
                         f"{float(t.get('qty', 0)):,.4f}", f"{float(t.get('price', 0)):,.2f}",
                         f"{float(t.get('total', 0)):,.0f}"])
        blocks.append(("table", rows, None))
    blocks.append(("note", DISCLAIMER))
    return R.make_pdf(f"Rapport de portefeuille — {port.get('name', '')}",
                      f"Généré le {R.stamp()}", blocks)
