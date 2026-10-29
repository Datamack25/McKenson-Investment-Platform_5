# components/admin_portfolios.py  —  MAM v5.7 · Administration → 📊 Tous les portefeuilles
"""
Comparaison de tous les portefeuilles construits sur la plateforme : performance,
stratégie, profil, avis du comité, construction, risque et façon dont ils ont été
construits. Logique dans utils/portfolio_census.py.
"""
from __future__ import annotations

import html as _h

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ui import section_title
from utils import portfolio_census as PC

_P = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
          font=dict(color="#94a3b8", family="Share Tech Mono"), margin=dict(l=8, r=8, t=30, b=8))
_COLORS = ["#00d4ff", "#00ff88", "#ffd700", "#7c3aed", "#ff8c00", "#ff3b6b", "#94a3b8", "#22d3ee", "#a3e635", "#f472b6"]
_PCT = ["Performance", "Performance annualisée", "Liquidités", "Volatilité (ann.)", "Perte max", "Perf. indice", "Surperformance",
        "Écart de suivi"]


def _fmt_table(df: pd.DataFrame):
    fmt = {}
    for c in df.columns:
        if c in _PCT or c.startswith(("Performance", "Liquidités", "Meilleure", "Moins bonne", "Surperformance",
                                      "Volatilité", "Perte max")):
            fmt[c] = lambda v: v if isinstance(v, str) else ("—" if pd.isna(v) else f"{v:+.1%}")
        elif c in ("Valeur", "Capital initial", "Résultat", "Valeur totale", "Apports nets"):
            fmt[c] = lambda v: "—" if pd.isna(v) else f"{v:,.0f} $".replace(",", " ")
        elif c in ("Sharpe", "Bêta", "Ratio d'information", "Sharpe moyen"):
            fmt[c] = lambda v: "—" if pd.isna(v) else f"{v:.2f}"
    return df.style.format(fmt, na_rep="—")


def all_portfolios_tab():
    from utils.data import get_multi_prices
    section_title("TOUS LES PORTEFEUILLES — COMPARAISON", "📊")
    owner = (st.session_state.get("mam_user") or {}).get("username", "—")
    items, source = PC.collect_all(owner=owner)
    st.caption(f"Source : {source}. Valorisation aux cours réels Yahoo Finance (différés ~15 min), convertis en "
               "USD. Performance selon la norme GIPS : rendement pondéré dans le temps (TWR), net des frais de "
               "transaction, dividendes et intérêts inclus ; les apports et retraits de liquidités ne la modifient "
               "pas ; pas d'annualisation sur moins d'un an. Pour un portefeuille ayant reçu un apport ou un retrait, "
               "la performance s'affiche après le calcul des indicateurs historiques. Simulation pédagogique.")
    if not items:
        st.info("Aucun portefeuille construit pour le moment.")
        return
    tick = tuple(sorted({t for it in items for t in (it["port"].get("holdings") or {})}))
    with st.spinner("Valorisation de tous les portefeuilles…"):
        prices = get_multi_prices(tick) if tick else {}
        df = PC.summary_table(items, prices)
    by_id = {it["port"].get("id"): it for it in items}

    # ── Filtres ──
    f = st.columns(5)
    sel = {}
    for i, col in enumerate(("Propriétaire", "Équipe", "Stratégie", "Profil", "Avis du comité")):
        opts = sorted(df[col].dropna().unique())
        sel[col] = f[i].multiselect(col, opts, default=[], key=f"apf_{col}", placeholder="Tous")
    only_invested = st.checkbox("Uniquement les portefeuilles investis (au moins un ordre)", value=False,
                                key="apf_inv")
    d = df.copy()
    for col, v in sel.items():
        if v:
            d = d[d[col].isin(v)]
    if only_invested:
        d = d[d["Ordres"] > 0]
    if d.empty:
        st.info("Aucun portefeuille ne correspond aux filtres.")
        return

    # ── Indicateurs historiques (à la demande : reconstitution de chaque NAV) ──
    c1, c2, c3 = st.columns([1.2, 1, 1.4])
    from utils.performance import BENCHMARKS
    bench = c1.selectbox("Indice de référence", list(BENCHMARKS), key="apf_bench")
    mkey = f"apf_metrics_{bench}"
    if c3.button(f"📈 Calculer les indicateurs historiques ({len(d)} portefeuille(s))", key="apf_go",
                 use_container_width=True, type="primary"):
        res = st.session_state.get(mkey, {})
        bar = st.progress(0.0, text="Reconstitution des historiques…")
        for k, pid in enumerate(d["id"]):
            try:
                res[pid] = PC.detailed_metrics(by_id[pid]["port"], bench)
            except Exception as e:  # noqa: BLE001
                res[pid] = {"Historique": f"erreur ({e})"}
            bar.progress((k + 1) / len(d), text=f"{k + 1}/{len(d)}")
        bar.empty()
        st.session_state[mkey] = res
    res = st.session_state.get(mkey, {})
    if res:
        cols = ["Historique", "Performance (TWR)", "Performance annualisée", "Volatilité (ann.)", "Sharpe",
                "Perte max", "Bêta", "Perf. indice", "Surperformance", "Ratio d'information", "Bat l'indice"]
        extra = pd.DataFrame([{**{c: res.get(pid, {}).get(c) for c in cols}, "id": pid} for pid in d["id"]])
        d = d.merge(extra, on="id", how="left")
        # GIPS : la performance de référence est le TWR reconstitué quand il est disponible
        d["Performance"] = pd.to_numeric(d["Performance (TWR)"], errors="coerce").combine_first(d["Performance"])
        d = d.drop(columns=["Performance (TWR)"])
        c2.caption(f"Indicateurs calculés pour {sum(1 for p in d['id'] if p in res)} portefeuille(s).")

    # ── Vue d'ensemble ──
    k = st.columns(5)
    k[0].metric("Portefeuilles", str(len(d)))
    k[1].metric("Utilisateurs", str(d["Propriétaire"].nunique()))
    k[2].metric("Valeur totale simulée", f"{d['Valeur'].sum():,.0f} $".replace(",", " "))
    k[3].metric("Performance médiane", f"{d['Performance'].median():+.1%}" if d["Performance"].notna().any() else "—")
    beat = d["Bat l'indice"] if "Bat l'indice" in d else None
    if beat is not None and beat.notna().any():
        k[4].metric(f"Battent {bench}", f"{int((beat == True).sum())}/{int(beat.notna().sum())}")  # noqa: E712
    else:
        k[4].metric("Validés par le comité", f"{int(d['Avis du comité'].str.startswith('Validé').sum())}/{len(d)}")
    lect = PC.plain_ranking(d, "Stratégie")
    if lect:
        st.markdown('<div style="border-left:3px solid #00ff88;background:rgba(0,255,136,.05);border-radius:6px;'
                    'padding:8px 14px;font-family:Share Tech Mono;font-size:.74rem;color:#cbd5e1;line-height:1.6">'
                    '<b style="color:#00ff88">EN BREF</b><ul style="margin:4px 0 0;padding-left:18px">'
                    + "".join(f"<li>{_h.escape(x)}</li>" for x in lect) + "</ul></div>", unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(["📋 Tableau comparatif", "📊 Par stratégie / profil", "📈 Courbes comparées",
                              "🔎 Détail d'un portefeuille"])
    with t1:
        order = st.selectbox("Trier par", [c for c in ("Performance", "Valeur", "Surperformance", "Sharpe",
                                                       "Perte max", "Volatilité (ann.)", "Ordres", "Créé le")
                                           if c in d], key="apf_sort")
        show = d.drop(columns=["id"]).sort_values(order, ascending=order in ("Volatilité (ann.)",), na_position="last")
        st.dataframe(_fmt_table(show), use_container_width=True, hide_index=True, height=min(600, 60 + 35 * len(show)))
        _bar(show)
        if "Volatilité (ann.)" in d and d["Volatilité (ann.)"].notna().any():
            _scatter(d)
        st.download_button("⬇️ Exporter la comparaison (CSV)", show.to_csv(index=False, sep=";", decimal=",")
                           .encode("utf-8-sig"), "MAM_tous_les_portefeuilles.csv", "text/csv", key="apf_csv")
    with t2:
        for by in ("Stratégie", "Profil", "Propriétaire", "Équipe", "Avis du comité"):
            ag = PC.aggregate(d, by)
            if len(ag):
                st.markdown(f"**Par {by.lower()}**")
                st.dataframe(_fmt_table(ag), use_container_width=True)
        st.caption("Moyennes simples des portefeuilles du groupe. Les indicateurs de risque n'apparaissent qu'après "
                   "le calcul des indicateurs historiques.")
    with t3:
        _curves(d, by_id, bench)
    with t4:
        _detail(d, by_id, prices, bench)


def _bar(d: pd.DataFrame):
    x = d.dropna(subset=["Performance"]).sort_values("Performance")
    if x.empty:
        return
    fig = go.Figure(go.Bar(x=x["Performance"] * 100, y=x["Portefeuille"] + " · " + x["Propriétaire"], orientation="h",
                           marker_color=["#00ff88" if v >= 0 else "#ff3b6b" for v in x["Performance"]],
                           customdata=x[["Stratégie", "Profil"]].values,
                           hovertemplate="%{y}<br>%{x:+.2f} %<br>%{customdata[0]} · %{customdata[1]}<extra></extra>"))
    fig.update_layout(**_P, height=max(260, 26 * len(x)), title="Performance depuis la création (%)",
                      xaxis=dict(gridcolor="rgba(255,255,255,.05)"))
    st.plotly_chart(fig, use_container_width=True, key="apf_bar")


def _scatter(d: pd.DataFrame):
    x = d.dropna(subset=["Volatilité (ann.)", "Performance"])
    if x.empty:
        return
    fig = go.Figure()
    for i, (s, g) in enumerate(x.groupby("Stratégie")):
        fig.add_trace(go.Scatter(x=g["Volatilité (ann.)"] * 100, y=g["Performance"] * 100, mode="markers+text",
                                 name=s, text=g["Portefeuille"], textposition="top center",
                                 marker=dict(size=12, color=_COLORS[i % len(_COLORS)]),
                                 hovertemplate="%{text}<br>volatilité %{x:.1f} % · performance %{y:+.1f} %<extra>"
                                               + s + "</extra>"))
    fig.update_layout(**_P, height=420, title="Risque / rendement par stratégie",
                      xaxis=dict(title="Volatilité annualisée (%)", gridcolor="rgba(255,255,255,.05)"),
                      yaxis=dict(title="Performance (%)", gridcolor="rgba(255,255,255,.05)"))
    st.plotly_chart(fig, use_container_width=True, key="apf_scatter")
    st.caption("En haut à gauche : beaucoup de performance pour peu de risque. En bas à droite : beaucoup de risque "
               "pour peu de performance.")


def _curves(d: pd.DataFrame, by_id: dict, bench: str):
    from utils import performance as PF
    cands = d[d["Ordres"] > 0]
    if cands.empty:
        st.info("Aucun portefeuille investi : pas de courbe à tracer.")
        return
    labels = {f"{r['Portefeuille']} · {r['Propriétaire']}": r["id"] for _, r in cands.iterrows()}
    default = list(cands.sort_values("Performance", ascending=False).head(5).apply(
        lambda r: f"{r['Portefeuille']} · {r['Propriétaire']}", axis=1))
    chosen = st.multiselect("Portefeuilles à comparer (8 au plus)", list(labels), default=default,
                            max_selections=8, key="apf_curves")
    if not chosen:
        return
    fig = go.Figure()
    start = None
    with st.spinner("Reconstitution des historiques…"):
        for i, lab in enumerate(chosen):
            s, _ = PF.portfolio_series(by_id[labels[lab]]["port"])
            if len(s.dropna()) < 2:
                continue
            start = s.index.min() if start is None else min(start, s.index.min())
            b = PF.base100(s)
            fig.add_trace(go.Scatter(x=b.index, y=b.values, mode="lines", name=lab,
                                     line=dict(width=2.3, color=_COLORS[i % len(_COLORS)])))
    if start is not None:
        bs = PF.benchmark_series(bench, start)
        if len(bs.dropna()) >= 2:
            bb = PF.base100(bs)
            fig.add_trace(go.Scatter(x=bb.index, y=bb.values, mode="lines", name=bench,
                                     line=dict(width=2, color="#e2e8f0", dash="dash")))
    fig.add_hline(y=100, line_color="rgba(255,255,255,.15)")
    fig.update_layout(**_P, height=420, hovermode="x unified", yaxis=dict(title="Base 100"),
                      legend=dict(orientation="h", y=1.12, bgcolor="rgba(0,0,0,0)"))
    st.plotly_chart(fig, use_container_width=True, key="apf_curves_fig")
    st.caption("Chaque courbe démarre à 100 le jour de son premier ordre : les portefeuilles récents ont une courbe "
               "plus courte.")


def _detail(d: pd.DataFrame, by_id: dict, prices: dict, bench: str):
    labels = {f"{r['Portefeuille']} · {r['Propriétaire']}": r["id"] for _, r in d.iterrows()}
    lab = st.selectbox("Portefeuille", list(labels), key="apf_detail")
    item = by_id[labels[lab]]
    port = item["port"]
    row = d[d["id"] == labels[lab]].iloc[0]
    k = st.columns(5)
    k[0].metric("Valeur", f"{row['Valeur']:,.0f} $".replace(",", " "))
    k[1].metric("Performance", "—" if pd.isna(row["Performance"]) else f"{row['Performance']:+.1%}")
    k[2].metric("Stratégie", row["Stratégie"])
    k[3].metric("Profil", row["Profil"])
    k[4].metric("Avis du comité", row["Avis du comité"])
    try:
        from utils.plain_summary import plain_summary
        from pages.reports import _simple_box
        _simple_box(plain_summary(port, bench))
    except Exception:
        pass
    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.markdown("**Positions**")
        hold = port.get("holdings") or {}
        rows = []
        nav = row["Valeur"] or 1.0
        for t, h in hold.items():
            p = prices.get(t)
            p = float(p[0] if isinstance(p, (list, tuple)) else p) if p else float(h.get("avg_price", 0) or 0)
            v = float(h.get("qty", 0) or 0) * p
            if v > 0:
                rows.append({"Ligne": t, "Valeur": v, "Poids": v / nav,
                             "Plus-value": (p / float(h.get("avg_price") or p) - 1) if h.get("avg_price") else None})
        if rows:
            st.dataframe(pd.DataFrame(rows).sort_values("Valeur", ascending=False).style.format(
                {"Valeur": "{:,.0f}", "Poids": "{:.1%}", "Plus-value": lambda v: "—" if v is None else f"{v:+.1%}"}),
                use_container_width=True, hide_index=True)
        else:
            st.caption("Aucune position.")
        st.caption(f"Liquidités : {port.get('cash', 0):,.0f} $".replace(",", " "))
    with c2:
        st.markdown("**Comment il a été construit**")
        mix = PC.construction_mix(port)
        if mix:
            st.dataframe(pd.DataFrame({"Façon d'investir": list(mix), "Part des achats": list(mix.values())})
                         .style.format({"Part des achats": "{:.0%}"}), use_container_width=True, hide_index=True)
        if port.get("ips"):
            from components.committee_ui import ips_summary
            st.caption("Politique d'investissement : " + ips_summary(port["ips"]).replace("**", ""))
        c = port.get("committee") or {}
        if c.get("recommandations"):
            st.markdown("**Dernières recommandations du comité**")
            for r in c["recommandations"][:5]:
                st.markdown(f"- {r}")
    _flows_block(item, labels[lab])
    tr = port.get("trades", []) or []
    if tr:
        st.markdown("**Derniers ordres**")
        st.dataframe(pd.DataFrame([{"Date": t.get("date"), "Ligne": t.get("ticker"), "Sens": t.get("action"),
                                    "Montant": float(t.get("total", 0) or 0), "Source": t.get("source") or "Trading Desk",
                                    "Pourquoi": (t.get("these") or {}).get("pourquoi", "—")} for t in reversed(tr[-25:])])
                     .style.format({"Montant": "{:,.0f}"}), use_container_width=True, hide_index=True)


def _flows_block(item: dict, pid: str):
    """Apport ou retrait de liquidités par l'administrateur — flux externe, sans effet sur la performance."""
    from utils import ledger as LG
    from utils.income import income_summary
    port = item["port"]
    st.markdown("**💵 Liquidités : apports, retraits et revenus**")
    inc = income_summary(port)
    k = st.columns(5)
    k[0].metric("Apports", f"{inc['apports']:,.0f} $".replace(",", " "))
    k[1].metric("Retraits", f"{inc['retraits']:,.0f} $".replace(",", " "))
    k[2].metric("Dividendes reçus", f"{inc['dividendes']:,.0f} $".replace(",", " "))
    k[3].metric("Intérêts reçus", f"{inc['interets']:,.0f} $".replace(",", " "),
                help=None if inc["taux"] is None else f"Taux monétaire actuel : {inc['taux']:.2%}")
    k[4].metric("Frais payés", f"{inc['frais']:,.0f} $".replace(",", " "))
    with st.form(f"apf_flow_{pid}"):
        c1, c2, c3 = st.columns([1, 1, 2])
        sens = c1.radio("Opération", ["Apport", "Retrait"], horizontal=True)
        amt = c2.number_input("Montant ($)", min_value=0.0, value=0.0, step=1000.0)
        note = c3.text_input("Motif (journal)")
        ok = st.form_submit_button("Enregistrer l'opération", use_container_width=True)
    st.caption("Un apport ou un retrait est un flux EXTERNE : il change la valeur du portefeuille mais pas sa "
               "performance (TWR, norme GIPS). Si l'utilisateur est connecté au même moment, demandez-lui de se "
               "reconnecter pour qu'il voie l'opération.")
    if ok and amt > 0:
        user = (st.session_state.get("mam_user") or {}).get("username")
        done, msg = LG.external_flow(port, amt if sens == "Apport" else -amt, author=user, note=note)
        if not done:
            st.error(msg)
            return
        try:
            if item.get("source") == "db":
                from utils.db import save_portfolio
                save_portfolio(pid, item.get("team_id"), item.get("user_id"), port)
            else:
                from utils.data import persist
                persist()
            st.success(msg)
        except Exception as e:  # noqa: BLE001
            st.error(f"Enregistrement impossible : {e}")
