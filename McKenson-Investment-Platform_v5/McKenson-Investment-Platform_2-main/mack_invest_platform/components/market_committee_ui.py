# components/market_committee_ui.py  —  MAM v5.12 · Analyse Marché → « 🧑‍⚖️ Analyse complète du comité »
"""Le comité dresse une analyse complète d'un marché (« le Nasdaq est négatif : pourquoi, quel impact,
comment s'adapter ? ») à partir des facteurs macro, des secteurs, de la technique, des actualités et des
réseaux sociaux, puis la relie au portefeuille choisi. Rapport PDF téléchargeable.

v5.12 : cours sans recopie (fin des faux « +0,0 % »), contrôle des données, note de synthèse du comité avec
scénarios probabilisés, carte de chaleur sectorielle, évolution et sentiment sur 1 h / 6 h, plans de
remédiation et diagnostic des couvertures par options."""
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


@st.cache_data(ttl=300, show_spinner=False)
def _intraday(tickers: tuple) -> pd.DataFrame:
    from utils import prices as P
    return P.fetch_intraday(tickers, "5d", "5m")


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
        for c in out.get("checks") or []:
            st.warning(c)
        return
    _show(out)


def _run(market, horizon, pk, ports, social_on, news) -> dict:
    from utils.compliance import get_profile
    from utils import intraday as ID
    from utils import prices as P
    px = _closes(tuple(MD.needed_tickers(market)))
    if px is None or px.empty:
        return dict(ok=False, error="cours indisponibles (Yahoo Finance injoignable ou limite de requêtes atteinte)")
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
    # Intraday 1 h / 6 h (prix + sentiment horodaté)
    intra = None
    try:
        bars = _intraday(tuple(dict.fromkeys(ID.INTRADAY_TICKERS.get(market, ()))))
        intra = ID.analyse_intraday(market, bars, rows, rd, tw, MD.MARKETS[market]["kw"])
    except Exception:
        intra = None
    pimp, pctx = None, None
    if pk:
        port = ports[pk][1]
        try:
            from components.committee_ui import portfolio_values
            vals, cash, _ = portfolio_values(port)
            nav = sum(vals.values()) + cash
            pctx = dict(vals=vals, cash=cash, port=port, hist=None)
            if nav > 0 and vals:
                w = {t: v / nav for t, v in vals.items() if v > 0}
                from utils import performance as PF
                from datetime import datetime, timedelta
                unders = {str(o.get("ticker", "")).upper() for o in (port.get("options") or []) if o.get("ticker")}
                need = tuple(sorted(set(w) | unders | {"SOXX", "QQQ", "SPY"}))
                hist = PF.price_history(need, (datetime.now() - timedelta(days=760)).strftime("%Y-%m-%d"))
                if hist is not None and not hist.empty:
                    pctx["hist"] = hist
                    mret = P.true_closes(px[MD.MARKETS[market]["t"]]).pct_change()
                    att0 = MD.attribution(px, market, horizon)
                    if att0.get("ok"):
                        rets = pd.DataFrame({t: P.true_closes(hist[t]).pct_change() for t in w if t in hist})
                        pimp = MD.portfolio_impact(rets, w, mret, att0["move_pct"])
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
                    dict(news=f"{len(rows)} titres", reddit=s1, stocktwits=s2), intraday=intra, port_ctx=pctx)
    an["px"] = px
    return an


def _show(an: dict):
    from utils.prices import fmt_pct
    att, tech, so = an["attribution"], an["technique"], an["social"]
    for c in an.get("checks") or []:
        st.warning("⚠️ " + c)
    col = "#00ff88" if att["move_pct"] > 0 else "#ff3b6b"
    st.markdown(f'<div style="border:1px solid {col}66;background:{col}10;border-radius:10px;padding:12px 16px;margin:6px 0">'
                f'<div style="font-family:Rajdhani;font-size:1.35rem;font-weight:700;color:{col}">{_h.escape(an["headline"])}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:.7rem;color:#94a3b8">clôture du {att["start"]} → clôture du {att["end"]} · '
                f'régime officiel du comité : {_h.escape(str(an.get("regime") or "—"))} · profil {an["profile"]}</div></div>',
                unsafe_allow_html=True)
    kpi_row([kpi("Mouvement", fmt_pct(att['move_pct'], 2), f"z = {att['z']:+.1f}" if att["z"] == att["z"] else "z indisponible", col),
             kpi("Expliqué par la macro", fmt_pct(np.expm1(att['explained']), 2), f"R² {att['r2']:.0%} sur {att['n_obs']} séances"),
             kpi("Propre au marché", fmt_pct(np.expm1(att['residual']), 2), "résultats, actualités, flux"),
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

    _synthesis(an)
    _intraday_block(an)

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
            fig.update_layout(**PLOT, height=380, title=f"Rotation sectorielle (ETF SPDR, %) — au {rot['Date'].max()}")
            st.plotly_chart(fig, use_container_width=True, key="mc_rot")
        else:
            st.info("Rotation sectorielle : cours des ETF sectoriels indisponibles pour l'instant (aucun chiffre "
                    "n'est inventé). Réessayez dans quelques minutes.")
    with c2:
        ld = an["leaders"]
        if len(ld):
            fig = go.Figure(go.Bar(x=ld["Titre"], y=ld["Rendement"] * 100,
                                   marker_color=["#00ff88" if v > 0 else "#ff3b6b" for v in ld["Rendement"]],
                                   text=[f"{v:+.1%}" for v in ld["Rendement"]], textposition="outside"))
            fig.update_layout(**PLOT, height=380, title=f"Les grandes capitalisations sur l'horizon (%) — au {ld['Date'].max()}")
            st.plotly_chart(fig, use_container_width=True, key="mc_lead")
        else:
            st.info("Grandes capitalisations : cours indisponibles pour l'instant (aucun chiffre n'est inventé).")
    _heatmap(an)
    _hedge_block(an)

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

    sc = an.get("scen") or {}
    if sc.get("ok"):
        from utils import scenarios as SC
        st.download_button("📝 Télécharger la note de synthèse du comité (texte)", SC.note_markdown(an, sc),
                           f"MAM_note_comite_{an['market'].replace(' ', '_')}_{pd.Timestamp.today():%Y%m%d}.md",
                           "text/markdown", use_container_width=True, key="mc_note")
    try:
        pdf = MD.build_pdf(an, an["px"], st.session_state.get("mc_llm_txt"))
        st.download_button("📄 Télécharger l'analyse du comité (PDF)", pdf,
                           f"MAM_analyse_marche_{an['market'].replace(' ', '_')}_{pd.Timestamp.today():%Y%m%d}.pdf",
                           "application/pdf", use_container_width=True, key="mc_pdf")
    except Exception as e:
        st.caption(f"PDF indisponible ({type(e).__name__}).")


# ══════════════════════════════════════════════════════════════════════════════
#  v5.12 — NOTE DE SYNTHÈSE, SCÉNARIOS, INTRADAY, CARTE DE CHALEUR, COUVERTURES
# ══════════════════════════════════════════════════════════════════════════════
def _is_admin() -> bool:
    return bool(st.session_state.get("admin_authenticated")
                or (st.session_state.get("mam_user") or {}).get("role") == "admin")


def _synthesis(an: dict):
    sc = an.get("scen") or {}
    section_title("NOTE DE SYNTHÈSE DU COMITÉ — SCÉNARIOS ET PROBABILITÉS", "📝")
    if not sc.get("ok"):
        st.info(f"Scénarios indisponibles ({sc.get('error', 'données insuffisantes')}).")
        return
    st.markdown(f'<div style="border:1px solid #00d4ff44;border-left:4px solid #00d4ff;border-radius:8px;padding:10px 14px;'
                f'background:rgba(0,212,255,.04);font-size:.86rem;color:#e2e8f0;line-height:1.55">{_h.escape(sc["resume"])}'
                f'</div>', unsafe_allow_html=True)
    cols = st.columns(len(sc["scenarios"]))
    for c, s in zip(cols, sc["scenarios"]):
        p = sc["probs"][s["id"]]
        col = s.get("couleur", "#94a3b8")
        star = " ★" if s["id"] == sc["main"] else ""
        forced = " · probabilité fixée par l'administrateur" if s.get("prob_forcee") not in (None, "") else ""
        c.markdown(f'<div style="border:1px solid {col}55;border-top:3px solid {col};border-radius:8px;padding:10px 12px;'
                   f'background:rgba(0,0,0,.25);min-height:210px"><div style="font-family:Rajdhani;font-weight:700;'
                   f'color:{col};letter-spacing:.06em">{_h.escape(s["nom"])}{star}</div>'
                   f'<div style="font-family:Share Tech Mono;font-size:2rem;color:{col}">{p:.0%}</div>'
                   f'<div style="height:6px;background:rgba(255,255,255,.06);border-radius:3px"><div style="width:{p * 100:.0f}%;'
                   f'height:6px;background:{col};border-radius:3px"></div></div>'
                   f'<div style="font-size:.74rem;color:#cbd5e1;margin-top:8px;line-height:1.45">{_h.escape(s["description"])}</div>'
                   f'<div style="font-size:.6rem;color:#64748b;margin-top:6px">a priori {float(s["prior"]):.0%}{forced}</div></div>',
                   unsafe_allow_html=True)
    c1, c2 = st.columns([1.15, 1])
    with c1:
        ct = sc["contributions"]
        fig = go.Figure(go.Bar(x=[r["contribution"] for r in ct][::-1], y=[r["signal"] for r in ct][::-1], orientation="h",
                               marker_color=["#00ff88" if r["contribution"] > 0 else "#ff3b6b" for r in ct][::-1],
                               text=[sc["raw"].get(r["cle"], "") for r in ct][::-1], textposition="auto"))
        fig.update_layout(**PLOT, height=330, title=f"Ce qui pousse vers la hausse (+) ou la baisse (−) — score {sc['score']:+.2f}")
        st.plotly_chart(fig, use_container_width=True, key="mc_sc_contrib")
    with c2:
        st.markdown("**Ce qui pourrait faire basculer les probabilités**")
        rows = [{"Catalyseur / hypothèse": r["catalyseur"], "Probabilité estimée": r["proba"],
                 "Sens": "haussier" if r["sens"] > 0 else "baissier",
                 "Baissier s'il se réalise": r["si_realise"].get("baissier", 0) * 100,
                 "Baissier s'il est écarté": r["si_ecarte"].get("baissier", 0) * 100} for r in sc["sensitivity"]]
        if rows:
            st.dataframe(pd.DataFrame(rows).style.format({"Probabilité estimée": "{:.0%}",
                                                          "Baissier s'il se réalise": "{:+.0f} pts",
                                                          "Baissier s'il est écarté": "{:+.0f} pts"}),
                         hide_index=True, use_container_width=True, height=260)
        for w in sc["watch"]:
            st.caption("• " + w)
    _remediation_block(sc)
    _plan_block(sc)
    hist = []
    try:
        from utils import core_params as CP
        hist = CP.revisions(an["market"])
        if _is_admin():
            with st.expander("📌 Enregistrer cette estimation (historique des révisions de probabilités)"):
                note = st.text_input("Commentaire (facultatif)", key="mc_rev_note",
                                     placeholder="ex. résultats Nvidia meilleurs que prévu")
                if st.button("Enregistrer", key="mc_rev_save"):
                    user = (st.session_state.get("mam_user") or {}).get("username", "admin")
                    CP.add_revision(an["market"], sc["probs"], note, user)
                    st.success("Estimation enregistrée.")
                    hist = CP.revisions(an["market"])
    except Exception:
        pass
    if len(hist) >= 2:
        h = pd.DataFrame(hist)
        fig = go.Figure()
        for s in sc["scenarios"]:
            k = f"p_{s['id']}"
            if k in h:
                fig.add_scatter(x=h["date"], y=h[k] * 100, name=s["nom"].split(" — ")[0], mode="lines+markers",
                                line=dict(color=s.get("couleur")))
        fig.update_layout(**PLOT, height=260, title="Révisions des probabilités (%)", legend=dict(orientation="h", y=-0.25))
        st.plotly_chart(fig, use_container_width=True, key="mc_rev_hist")
    if sc.get("custom"):
        st.caption("🧮 " + sc["custom"])
    st.caption("Probabilités = probabilités a priori déformées par le score des signaux et des catalyseurs (paramétrables "
               "dans Admin → Paramètres financiers). Lecture éducative, pas une prévision.")


def _remediation_block(sc: dict):
    rem = sc["remediation"]
    st.markdown("**🩹 Plans de remédiation** — à valider par vous, aucun ordre n'est passé")
    if rem["perso"]:
        st.markdown('<div style="border:1px solid #ff8c0055;border-left:4px solid #ff8c00;border-radius:8px;padding:8px 12px;'
                    'background:rgba(255,140,0,.05)"><div style="font-family:Rajdhani;font-weight:700;color:#ff8c00">'
                    'Votre portefeuille</div><ul style="padding-left:18px;margin:4px 0;font-size:.78rem">'
                    + _bullets(rem["perso"]) + "</ul></div>", unsafe_allow_html=True)
    cols = st.columns(len(sc["scenarios"]))
    for c, s in zip(cols, sc["scenarios"]):
        with c:
            with st.expander(f"Si {s['nom'].split(' — ')[0].lower()} ({sc['probs'][s['id']]:.0%})",
                             expanded=s["id"] == sc["main"]):
                for x in rem["plans"].get(s["id"], []):
                    st.markdown(f"- {x}")


def _intraday_block(an: dict):
    it = an.get("intraday") or {}
    section_title("ÉVOLUTION ET SENTIMENT SUR 1 H ET 6 H", "⏱️")
    if not it.get("ok"):
        st.info("Données intraday indisponibles pour ce marché pour l'instant (Yahoo Finance). Le sentiment horodaté "
                "reste affiché ci-dessous s'il est disponible.")
    se = it.get("sentiment") or {}
    ks = []
    for lab, key in (("1 h", "w1"), ("6 h", "w6")):
        w = it.get(key) or {}
        if w.get("ok"):
            colr = "#00ff88" if w["ret"] > 0 else "#ff3b6b"
            ks.append(kpi(f"Prix — {lab}", f"{w['ret']:+.2%}",
                          f"vol. {w['vol_h']:.2%}/h · {w['trend']}" if w["vol_h"] == w["vol_h"] else w["trend"], colr))
        else:
            ks.append(kpi(f"Prix — {lab}", "indispo.", ""))
    for lab in ("1 h", "6 h", "24 h"):
        v = se.get(lab, {})
        sc = v.get("score", np.nan)
        ks.append(kpi(f"Sentiment — {lab}", f"{sc:+.2f}" if sc == sc else "—", f"{v.get('n', 0)} message(s)",
                      "#00ff88" if sc == sc and sc > 0.1 else "#ff3b6b" if sc == sc and sc < -0.1 else "#e2e8f0"))
    kpi_row(ks)
    for a_ in it.get("alerts") or []:
        st.warning("🔔 " + a_)
    s = it.get("series")
    if s is not None and len(s) > 5:
        fig = go.Figure()
        fig.add_scatter(x=s.index, y=s.values, name=it.get("ticker"), line=dict(color="#00d4ff", width=1.4))
        end = s.index[-1]
        fig.add_vrect(x0=end - pd.Timedelta(hours=6), x1=end, fillcolor="rgba(255,215,0,.05)", line_width=0)
        fig.add_vrect(x0=end - pd.Timedelta(hours=1), x1=end, fillcolor="rgba(0,255,136,.08)", line_width=0)
        fig.update_layout(**PLOT, height=280, title=f"{it.get('ticker')} — barres 5 min (heure UTC ; zones : 6 h et 1 h)")
        st.plotly_chart(fig, use_container_width=True, key="mc_intra")
    age = it.get("age_min")
    st.caption("Cours intraday Yahoo Finance ≈ 15 min de différé"
               + (f" ; dernière barre il y a {age:.0f} min" if age == age and age is not None else "")
               + ". Suffisant pour une lecture éducative, pas pour du trading en temps réel.")


def _heatmap(an: dict):
    heat = an.get("heat")
    sc = an.get("scen") or {}
    section_title("CARTE DE CHALEUR — PERFORMANCE DES SECTEURS ET IMPACT ATTENDU DES SCÉNARIOS", "🌡️")
    if heat is None or not len(heat):
        st.info("Performance sectorielle indisponible pour l'instant (aucun chiffre n'est inventé).")
    else:
        cols = [c for c in ("1 J", "1 S", "1 M", "3 M", "Depuis 1er janv.") if c in heat]
        z = heat[cols].astype(float).values * 100
        txt = [[("—" if v != v else f"{v:+.1f}%") for v in row] for row in z]
        lim = float(np.nanpercentile(np.abs(z), 95)) if np.isfinite(z).any() else 1.0
        fig = go.Figure(go.Heatmap(z=z, x=cols, y=heat["Secteur / actif"], text=txt, texttemplate="%{text}",
                                   colorscale=[[0, "#ff3b6b"], [0.5, "#1e293b"], [1, "#00ff88"]], zmid=0,
                                   zmin=-max(lim, 0.5), zmax=max(lim, 0.5), showscale=False, hoverongaps=False))
        fig.update_layout(**PLOT, height=max(360, 26 * len(heat) + 60), title="Performance réalisée (%)")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True, key="mc_heat")
    if sc.get("ok"):
        sx = sc["sectors"]
        ids = [s["id"] for s in sc["scenarios"]]
        names = [f"{s['nom'].split(' — ')[0]} ({sc['probs'][s['id']]:.0%})" for s in sc["scenarios"]] + ["Impact pondéré"]
        z = sx[ids + ["Impact pondéré"]].astype(float).values * 100
        fig = go.Figure(go.Heatmap(z=z, x=names, y=sx["Secteur / actif"], text=[[f"{v:+.1f}%" for v in r] for r in z],
                                   texttemplate="%{text}", colorscale=[[0, "#ff3b6b"], [0.5, "#1e293b"], [1, "#00ff88"]],
                                   zmid=0, showscale=False))
        fig.update_layout(**PLOT, height=max(360, 26 * len(sx) + 60),
                          title="Impact attendu par scénario (hypothèses du comité, modifiables en admin)")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True, key="mc_heat_sc")


def _hedge_block(an: dict):
    sc = an.get("scen") or {}
    h = sc.get("hedge") if sc.get("ok") else None
    if not h or not h.get("ok"):
        return
    section_title("POURQUOI LES OPTIONS N'ONT PAS PROTÉGÉ À HAUTEUR DE L'EXPOSITION ?", "🛡️")
    cr, real = h["covered_ratio"], h["coverage_real"]
    kpi_row([kpi("Actions exposées", f"{h['equity']:,.0f} $".replace(",", " ")),
             kpi("Variation des actions", f"{h['equity_pnl']:+,.0f} $".replace(",", " "), f"sur {h['horizon']} séance(s)",
                 "#ff3b6b" if h["equity_pnl"] < 0 else "#00ff88"),
             kpi("Gain estimé des options", f"{h['hedge_gain']:+,.0f} $".replace(",", " "), f"{h['n_options']} ligne(s)"),
             kpi("Part protégée (delta)", f"{cr:.0%}" if cr == cr else "—", f"cible {h['target']:.0%}",
                 "#00ff88" if cr == cr and cr >= h["target"] else "#ff8c00"),
             kpi("Perte compensée", f"{max(real, 0):.0%}" if real == real else "—", "gain options / perte actions")])
    a, b = st.columns(2)
    with a:
        st.markdown("**Constats**")
        for x in h["causes"] or ["Couverture cohérente avec l'exposition."]:
            st.markdown(f"- {x}")
    with b:
        if h["fixes"]:
            st.markdown("**Corrections proposées** (à valider)")
            for x in h["fixes"]:
                st.markdown(f"- {x}")
    if len(h["lines"]):
        st.dataframe(h["lines"].style.format({"Delta": "{:+.2f}", "Notionnel delta $": "{:+,.0f}", "Gain estimé $": "{:+,.0f}"},
                                             na_rep="—"), hide_index=True, use_container_width=True)
    st.caption("Gain estimé = revalorisation Black-Scholes de chaque option entre le cours d'avant et le cours actuel du "
               "sous-jacent (volatilité de l'option conservée). Notionnel delta = contrats × multiplicateur × delta × cours.")


def _plan_block(sc: dict):
    """v5.13 : stress des scénarios sur le portefeuille, plan par phases, processus, autocritique."""
    ps, plan, cr, pr = sc.get("portfolio") or {}, sc.get("plan") or {}, sc.get("critique") or {}, sc.get("process") or []
    if ps.get("ok"):
        st.markdown("**🧪 Stress des scénarios sur votre portefeuille**")
        cols = st.columns(len(sc["scenarios"]) + 1)
        for c, s in zip(cols, sc["scenarios"]):
            v = ps["scen"][s["id"]]
            c.markdown(kpi(s["nom"].split(" — ")[0], f"{v['pct']:+.1%}", f"{v['pnl']:+,.0f} $".replace(",", " "),
                           "#00ff88" if v["pct"] > 0 else "#ff3b6b"), unsafe_allow_html=True)
        cols[-1].markdown(kpi("Espérance pondérée", f"{ps['expected']:+.1%}",
                              f"limite IPS {-abs(ps['perte_max']):.0%}" if ps.get("perte_max") else "",
                              "#ff3b6b" if ps.get("breach") else "#e2e8f0"), unsafe_allow_html=True)
        if ps.get("breach"):
            st.error("Le pire scénario dépasse la perte maximale acceptée dans votre politique d'investissement.")
        if ps.get("unclassified"):
            st.caption(f"Lignes non classées par secteur (traitées comme le S&P 500) : {', '.join(ps['unclassified'][:8])}")
    if plan.get("ok") and plan["actions"]:
        st.markdown("**🗓️ Plan d'action par phases** — à valider, rien n'est exécuté automatiquement")
        if plan.get("frozen_note"):
            st.info("🧊 " + plan["frozen_note"])
        df = pd.DataFrame([{"Phase": a["phase"], "Action": a["action"],
                            "Montant": a["montant"] if a.get("montant") else None, "Lignes": a["lignes"],
                            "Pourquoi": a["pourquoi"], "Qui": a["qui"]} for a in plan["actions"]])
        st.dataframe(df.style.format({"Montant": lambda x: "—" if x is None or x != x else f"{x:,.0f} $".replace(",", " ")}),
                     hide_index=True, use_container_width=True)
    if pr:
        st.markdown("**🧭 Processus d'investissement — où en est-on ?**")
        st.markdown("".join(f'<div style="font-size:.78rem;margin:2px 0">{"✅" if r["ok"] else "⚠️"} <b>{_h.escape(r["etape"])}</b>'
                            f' — <span style="color:#94a3b8">{_h.escape(r["detail"])}</span></div>' for r in pr),
                    unsafe_allow_html=True)
    if cr:
        col = "#00ff88" if cr["note"] >= 8 else "#ffd700" if cr["note"] >= 6 else "#ff3b6b"
        st.markdown(f'<div style="border:1px solid {col}55;border-left:4px solid {col};border-radius:8px;padding:8px 12px;'
                    f'margin-top:8px;background:rgba(0,0,0,.2)"><div style="font-family:Rajdhani;font-weight:700;color:{col}">'
                    f'🔎 Autocritique du comité — {cr["note"]:g}/10 · {_h.escape(cr["verdict"])} '
                    f'<span style="color:#64748b;font-weight:400">({_h.escape(cr["qui"])})</span></div>'
                    '<ul style="padding-left:18px;margin:4px 0;font-size:.76rem">'
                    + _bullets(cr["faiblesses"] or ["Aucune faiblesse majeure relevée."])
                    + _bullets([f"À améliorer : {x}" for x in cr["ameliorations"]]) + "</ul></div>",
                    unsafe_allow_html=True)
