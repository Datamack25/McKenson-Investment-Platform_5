# components/market_committee_ui.py  —  MAM v5.11 · IA Marchés → « 🧑‍⚖️ Analyse complète du comité »
"""Le comité dresse une analyse complète d'un marché (« le Nasdaq est négatif : pourquoi, quel impact,
comment s'adapter ? ») à partir des facteurs macro, des secteurs, de la technique, des actualités et des
réseaux sociaux, puis la relie au portefeuille choisi. Rapport PDF téléchargeable."""
from __future__ import annotations

import html as _h

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ai_shared import PLOT, all_portfolios, kpi, kpi_row, md_bold
from components.ui import section_title
from utils import market_drivers as MD


@st.cache_data(ttl=1800, show_spinner=False)
def _closes(tickers: tuple) -> pd.DataFrame:
    return MD.fetch_closes(tickers, "2y")


@st.cache_data(ttl=900, show_spinner=False)
def _gnews(market: str) -> list[dict]:
    m = MD.MARKETS[market]
    rows = MD.fetch_google_news(f"{market} stocks market why", 25)
    if m["region"] == "eu":
        rows += MD.fetch_google_news(f"{market} bourse", 15, "fr")
    return rows


@st.cache_data(ttl=900, show_spinner=False)
def _social(proxy: str) -> tuple:
    rd, s1 = MD.fetch_reddit()
    tw, s2 = MD.fetch_stocktwits(proxy)
    return rd, s1, tw, s2


def _bullets(items, color="#cbd5e1"):
    return "".join(f"<li style='margin:3px 0;color:{color}'>{md_bold(x)}</li>" for x in items)


def render(news: dict | None = None):
    section_title("LE COMITÉ ANALYSE LE MARCHÉ — POURQUOI, QUEL IMPACT, COMMENT S'ADAPTER", "🧑‍⚖️")
    st.caption("Exemple : « le Nasdaq est négatif cette semaine : pourquoi ? quel impact sur mon portefeuille ? que faire ? » "
               "Le comité décompose le mouvement par facteur (taux, dollar, peur, pétrole, crédit…), regarde les secteurs, "
               "les grandes capitalisations, la tendance, les actualités et les réseaux sociaux (Reddit, StockTwits).")
    c1, c2, c3, c4 = st.columns([1.2, 1, 1.6, 1])
    market = c1.selectbox("Marché", list(MD.MARKETS), key="mc_market")
    hz = c2.selectbox("Horizon", list(MD.HORIZONS), index=1, key="mc_hz")
    ports = all_portfolios()
    keys = ["—"] + list(ports)
    active = st.session_state.get("active_portfolio")
    pk = c3.selectbox("Impact sur le portefeuille", keys, index=keys.index(active) if active in keys else 0,
                      format_func=lambda k: "Aucun" if k == "—" else ports[k][0], key="mc_port")
    social_on = c4.checkbox("Réseaux sociaux", value=True, key="mc_social")
    key = (market, hz, pk, social_on)
    if st.button(f"🧑‍⚖️ Le comité analyse le {market}", key="mc_go", type="primary", use_container_width=True):
        st.session_state["mc_key"] = key
        st.session_state.pop("mc_llm_txt", None)
    if st.session_state.get("mc_key") != key:
        st.info("Choisissez un marché et un horizon, puis lancez l'analyse.")
        return
    with st.spinner("Le comité réunit les cours, les facteurs, les actualités et les réseaux sociaux…"):
        out = _run(market, MD.HORIZONS[hz], pk if pk != "—" else None, ports, social_on, news)
    if not out.get("ok"):
        st.error(f"Analyse impossible : {out.get('error', 'données indisponibles')}. Les cours Yahoo Finance sont peut-être "
                 "momentanément injoignables.")
        return
    _show(out)


def _run(market, horizon, pk, ports, social_on, news) -> dict:
    from utils.compliance import get_profile
    px = _closes(tuple(MD.needed_tickers(market)))
    if px is None or px.empty:
        return dict(ok=False, error="cours indisponibles")
    rows = list((news or {}).get("rows", [])) + _gnews(market)
    rd, s1, tw, s2 = ([], "désactivé", [], "désactivé")
    if social_on:
        rd, s1, tw, s2 = _social(MD.MARKETS[market]["proxy"])
    reg = None
    try:
        from components.committee_ui import get_context
        reg = get_context()["macro"].regime
    except Exception:
        pass
    profile = get_profile().get("risque", "Équilibré")
    pimp = None
    if pk:
        port = ports[pk][1]
        try:
            from components.committee_ui import portfolio_values
            vals, cash, _ = portfolio_values(port)
            nav = sum(vals.values()) + cash
            if nav > 0 and vals:
                w = {t: v / nav for t, v in vals.items() if v > 0}
                from utils import performance as PF
                from datetime import datetime, timedelta
                hist = PF.price_history(tuple(sorted(w)), (datetime.now() - timedelta(days=760)).strftime("%Y-%m-%d"))
                if hist is not None and not hist.empty:
                    mret = px[MD.MARKETS[market]["t"]].pct_change()
                    att0 = MD.attribution(px, market, horizon)
                    if att0.get("ok"):
                        pimp = MD.portfolio_impact(hist.pct_change(), w, mret, att0["move_pct"])
                        pimp["name"] = port.get("name")
        except Exception:
            pimp = None
    smart = None
    try:
        from utils import smart_money as SM
        snap = SM.current_snapshot()
        smart = SM.top5(snap) if snap else None
    except Exception:
        smart = None
    an = MD.analyse(market, horizon, px, rows, rd, tw, reg, profile, pimp, smart,
                    dict(news=f"{len(rows)} titres", reddit=s1, stocktwits=s2))
    an["px"] = px
    return an


def _show(an: dict):
    att, tech, so = an["attribution"], an["technique"], an["social"]
    col = "#00ff88" if att["move_pct"] > 0 else "#ff3b6b"
    st.markdown(f'<div style="border:1px solid {col}66;background:{col}10;border-radius:10px;padding:12px 16px;margin:6px 0">'
                f'<div style="font-family:Rajdhani;font-size:1.35rem;font-weight:700;color:{col}">{_h.escape(an["headline"])}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:.7rem;color:#94a3b8">du {att["start"]} au {att["end"]} · '
                f'régime officiel du comité : {_h.escape(str(an.get("regime") or "—"))} · profil {an["profile"]}</div></div>',
                unsafe_allow_html=True)
    kpi_row([kpi("Mouvement", f"{att['move_pct']:+.2%}", f"z = {att['z']:+.1f}" if att["z"] == att["z"] else "", col),
             kpi("Expliqué par la macro", f"{np.expm1(att['explained']):+.2%}", f"R² {att['r2']:.0%} sur {att['n_obs']} séances"),
             kpi("Propre au marché", f"{np.expm1(att['residual']):+.2%}", "résultats, actualités, flux"),
             kpi("Tendance", tech.get("trend", "—") if tech.get("ok") else "—",
                 f"RSI {tech['rsi']:.0f} · recul {tech['drawdown']:+.1%}" if tech.get("ok") else ""),
             kpi("Réseaux sociaux", so["label"], f"score {so['score']:+.2f}" if so["score"] == so["score"] else
                 an["sources"].get("reddit", ""))])
    c1, c2, c3 = st.columns(3)
    for c, title, items, color in [(c1, "❓ POURQUOI ?", an["why"], "#00d4ff"), (c2, "🎯 QUEL IMPACT ?", an["impact"], "#ffd700"),
                                   (c3, "🧭 COMMENT S'ADAPTER ?", [a["texte"] for a in an["adapt"]], "#00ff88")]:
        c.markdown(f'<div style="border:1px solid {color}44;border-top:3px solid {color};border-radius:8px;padding:10px 12px;'
                   f'background:rgba(0,0,0,.25);min-height:260px"><div style="font-family:Rajdhani;font-weight:700;color:{color};'
                   f'letter-spacing:.1em">{title}</div><ul style="padding-left:18px;margin:6px 0;font-size:.76rem;line-height:1.5">'
                   f'{_bullets(items or ["—"])}</ul></div>', unsafe_allow_html=True)
    st.caption("Les pistes d'adaptation sont à valider par vous : aucun ordre n'est passé, chaque ordre reste soumis à votre "
               "profil et aux contrôles de conformité.")

    c1, c2 = st.columns(2)
    with c1:
        labels = [f["label"] for f in att["factors"]] + ["Propre au marché"]
        vals = [np.expm1(f["contrib"]) * 100 for f in att["factors"]] + [np.expm1(att["residual"]) * 100]
        fig = go.Figure(go.Waterfall(orientation="v", x=labels + ["Total"], measure=["relative"] * len(vals) + ["total"],
                                     y=vals + [0], text=[f"{v:+.2f}" for v in vals] + [f"{att['move_pct'] * 100:+.2f}"],
                                     increasing=dict(marker_color="#00ff88"), decreasing=dict(marker_color="#ff3b6b"),
                                     totals=dict(marker_color="#00d4ff")))
        fig.update_layout(**PLOT, height=360, title="Décomposition du mouvement (points de %)")
        st.plotly_chart(fig, use_container_width=True, key="mc_wf")
        ft = pd.DataFrame([{"Facteur": f["label"], "Variation": f["move_txt"], "Sensibilité β": f["beta"],
                            "Contribution": np.expm1(f["contrib"])} for f in att["factors"]])
        st.dataframe(ft.style.format({"Sensibilité β": "{:+.3f}", "Contribution": "{:+.2%}"}), hide_index=True,
                     use_container_width=True)
    with c2:
        s = an["px"][MD.MARKETS[an["market"]]["t"]].dropna()
        s1 = s.iloc[-260:]
        fig = go.Figure()
        fig.add_scatter(x=s1.index, y=s1, name=an["market"], line=dict(color="#00d4ff", width=1.6))
        fig.add_scatter(x=s1.index, y=s.rolling(50).mean().reindex(s1.index), name="MM 50", line=dict(color="#ffd700", width=1))
        fig.add_scatter(x=s1.index, y=s.rolling(200).mean().reindex(s1.index), name="MM 200", line=dict(color="#7c3aed", width=1))
        fig.add_vrect(x0=att["start"], x1=att["end"], fillcolor="rgba(255,255,255,.07)", line_width=0)
        fig.update_layout(**PLOT, height=360, title=f"{an['market']} sur un an (zone = horizon analysé)",
                          legend=dict(orientation="h", y=-0.15))
        st.plotly_chart(fig, use_container_width=True, key="mc_px")
    c1, c2 = st.columns(2)
    with c1:
        rot = an["rotation"]
        if len(rot):
            r = rot.iloc[::-1]
            fig = go.Figure(go.Bar(x=r["Rendement"] * 100, y=r["Secteur"], orientation="h",
                                   marker_color=["#00ff88" if v > 0 else "#ff3b6b" for v in r["Rendement"]],
                                   text=[f"{v:+.1%}" for v in r["Rendement"]], textposition="auto"))
            fig.update_layout(**PLOT, height=380, title="Rotation sectorielle (ETF SPDR, %)")
            st.plotly_chart(fig, use_container_width=True, key="mc_rot")
    with c2:
        ld = an["leaders"]
        if len(ld):
            fig = go.Figure(go.Bar(x=ld["Titre"], y=ld["Rendement"] * 100,
                                   marker_color=["#00ff88" if v > 0 else "#ff3b6b" for v in ld["Rendement"]],
                                   text=[f"{v:+.1%}" for v in ld["Rendement"]], textposition="outside"))
            fig.update_layout(**PLOT, height=380, title="Les grandes capitalisations sur l'horizon (%)")
            st.plotly_chart(fig, use_container_width=True, key="mc_lead")

    section_title("AVIS DES MEMBRES DU COMITÉ", "🧑‍⚖️")
    from components.smart_money_ui import avis_cards
    avis_cards(an["voices"])
    try:
        from utils import advisor as A
        if A.llm_available() and st.button("✍️ Faire rédiger la synthèse par le modèle de langage", key="mc_llm"):
            with st.spinner("Rédaction…"):
                st.session_state["mc_llm_txt"] = MD.llm_commentary(an)
        if st.session_state.get("mc_llm_txt"):
            st.markdown(st.session_state["mc_llm_txt"])
    except Exception:
        pass

    t1, t2 = st.tabs(["📰 ACTUALITÉS", "💬 RÉSEAUX SOCIAUX"])
    with t1:
        nv = an["news"]
        st.caption(f"{nv['n']} titre(s) liés au {an['market']} · tonalité moyenne {nv['tone']:+.2f} · thèmes : "
                   + (", ".join(nv["drivers"]) or "—"))
        for r in nv["rows"][:25]:
            s = r["sentiment"]
            c = "#00ff88" if s > .1 else "#ff3b6b" if s < -.1 else "#94a3b8"
            title = _h.escape(r["title"])
            if r.get("link"):
                title = f'<a href="{_h.escape(r["link"])}" target="_blank" style="color:#e2e8f0;text-decoration:none">{title}</a>'
            st.markdown(f'<div style="padding:5px 10px;border-left:3px solid {c};margin:3px 0;background:rgba(255,255,255,.015);'
                        f'font-size:.8rem;color:#e2e8f0">{title}<span style="font-family:Share Tech Mono;font-size:.64rem;color:{c};'
                        f'margin-left:8px">{s:+.2f}</span><span style="font-size:.6rem;color:#475569;margin-left:6px">'
                        f'{_h.escape(r.get("source", ""))}</span></div>', unsafe_allow_html=True)
    with t2:
        stw = so["stocktwits"]
        a, b = st.columns([1, 1.6])
        with a:
            if stw["bull"] + stw["bear"]:
                fig = go.Figure(go.Pie(labels=["Haussiers", "Baissiers"], values=[stw["bull"], stw["bear"]], hole=.6,
                                       marker=dict(colors=["#00ff88", "#ff3b6b"])))
                fig.update_layout(**{k: v for k, v in PLOT.items() if k not in ("xaxis", "yaxis")}, height=260,
                                  title=f"StockTwits — {MD.MARKETS[an['market']]['proxy']}")
                st.plotly_chart(fig, use_container_width=True, key="mc_st")
            else:
                st.caption(f"StockTwits : {an['sources'].get('stocktwits')}")
            if so["mentions"]:
                st.markdown("**Titres les plus cités sur Reddit**")
                st.dataframe(pd.DataFrame(so["mentions"], columns=["Titre", "Mentions"]), hide_index=True,
                             use_container_width=True)
        with b:
            st.caption(f"Reddit : {an['sources'].get('reddit')} · {so['n_reddit']} publication(s) liée(s) · tonalité "
                       + (f"{so['reddit_score']:+.2f}" if so["reddit_score"] == so["reddit_score"] else "—"))
            for p in so["top_posts"]:
                st.markdown(f'<div style="padding:5px 10px;border-left:3px solid #ff8c00;margin:3px 0;font-size:.78rem;color:#e2e8f0">'
                            f'<a href="{_h.escape(p.get("link", ""))}" target="_blank" style="color:#e2e8f0;text-decoration:none">'
                            f'{_h.escape(p["title"])}</a><span style="font-size:.62rem;color:#64748b;margin-left:6px">r/{p["sub"]} · '
                            f'▲ {p["score"]} · 💬 {p["comments"]}</span></div>', unsafe_allow_html=True)
            if not so["top_posts"]:
                st.info("Réseaux sociaux injoignables depuis ce serveur pour l'instant (Reddit et StockTwits limitent "
                        "parfois les accès automatiques). L'analyse s'appuie alors sur les actualités.")
        st.caption("Les réseaux sociaux mesurent l'humeur des investisseurs particuliers : utile pour repérer la peur ou "
                   "l'euphorie, jamais suffisant pour décider.")

    try:
        pdf = MD.build_pdf(an, an["px"], st.session_state.get("mc_llm_txt"))
        st.download_button("📄 Télécharger l'analyse du comité (PDF)", pdf,
                           f"MAM_analyse_marche_{an['market'].replace(' ', '_')}_{pd.Timestamp.today():%Y%m%d}.pdf",
                           "application/pdf", use_container_width=True, key="mc_pdf")
    except Exception as e:
        st.caption(f"PDF indisponible ({type(e).__name__}).")
