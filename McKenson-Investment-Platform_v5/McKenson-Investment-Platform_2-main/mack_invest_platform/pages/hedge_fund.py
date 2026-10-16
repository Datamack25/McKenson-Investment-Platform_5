"""
pages/hedge_fund.py — 🦅 Hedge Fund Agent
Desk multi-rôles : veille → macro → stratège → risque (veto) → validation humaine → journal.
Conseils applicables à l'allocation du desk ET à n'importe quel portefeuille existant.
"""
from __future__ import annotations

import html
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from utils import advisor as A

try:
    import plotly.graph_objects as go
    _PLOTLY = True
except Exception:
    _PLOTLY = False

CYAN, GREEN, RED, VIOLET, GREY = "#00d4ff", "#00ff88", "#ff3b6b", "#7c3aed", "#94a3b8"
DISCLAIMER = ("Outil pédagogique d'aide à la décision sur une plateforme de simulation : "
              "ne constitue pas un conseil en investissement.")

_CSS = """
<style>
.hf-card{background:rgba(0,212,255,.04);border:1px solid rgba(0,212,255,.14);border-radius:8px;
         padding:14px 16px;margin:6px 0 12px}
.hf-title{font-family:'Rajdhani',sans-serif;font-weight:700;letter-spacing:.08em;color:#e2e8f0;
          font-size:1.05rem;margin-bottom:4px}
.hf-sub{color:#7a93b0;font-size:.74rem}
.hf-role{display:inline-block;padding:3px 9px;margin:2px 4px 2px 0;border-radius:12px;
         border:1px solid rgba(124,58,237,.35);color:#c4b5fd;font-size:.68rem;
         font-family:'Rajdhani',sans-serif;font-weight:700;letter-spacing:.06em}
.hf-badge{display:inline-block;padding:2px 8px;border-radius:4px;font-size:.68rem;font-weight:700}
.hf-ok{background:rgba(0,255,136,.1);color:#00ff88;border:1px solid rgba(0,255,136,.3)}
.hf-warn{background:rgba(255,59,107,.1);color:#ff3b6b;border:1px solid rgba(255,59,107,.3)}
.hf-adv{border-left:3px solid;padding:8px 12px;margin:6px 0;border-radius:4px;
        background:rgba(255,255,255,.02)}
.hf-adv b{font-family:'Rajdhani',sans-serif;letter-spacing:.04em;font-size:.92rem}
.hf-adv span{display:block;color:#94a3b8;font-size:.74rem;margin-top:2px}
.hf-news a{color:#cbd5e1;text-decoration:none;font-size:.74rem}
.hf-news a:hover{color:#00d4ff}
.hf-news small{color:#475569}
</style>
"""

ADV_STYLE = {
    "alerte": ("#ff3b6b", "⛔"), "risque": ("#f59e0b", "⚠️"), "action": ("#00d4ff", "🎯"),
    "info": ("#94a3b8", "ℹ️"), "atout": ("#00ff88", "✅"),
}


# ── Chargement partagé (cache) ────────────────────────────────────────────────
def _load_all():
    with st.spinner("Le desk collecte les marchés et l'actualité…"):
        px, missing = A.load_prices()
        news, news_sim = A.load_news()
        macro = A.compute_macro(px, news)
        cov = A.class_covariance(px)
    critical = {"SPY", "^VIX", "^TNX", "^IRX"}
    data_sim = len(missing) >= len(A.ALL_TICKERS) * 0.6 or bool(critical & set(missing))
    return px, missing, news, news_sim, macro, cov, data_sim


# ── Graphiques ────────────────────────────────────────────────────────────────
def _bar_h(series: pd.Series, title: str, fmt: str = "+.2f", rng=None):
    s = series.sort_values()
    if _PLOTLY:
        fig = go.Figure(go.Bar(
            x=s.values, y=s.index, orientation="h",
            marker_color=[GREEN if v >= 0 else RED for v in s.values],
            text=[format(v, fmt) for v in s.values], textposition="outside"))
        fig.update_layout(title=title, height=40 + 34 * len(s), margin=dict(l=10, r=30, t=40, b=10),
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#cbd5e1", size=11), xaxis=dict(range=rng, gridcolor="#1e293b"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption(title)
        st.bar_chart(s)


def _alloc_compare(df: pd.DataFrame, cols: list[str], title: str):
    if _PLOTLY:
        fig = go.Figure()
        palette = [GREY, VIOLET, CYAN, GREEN]
        for i, c in enumerate(cols):
            fig.add_bar(name=c, x=df.index, y=df[c] * 100, marker_color=palette[i % 4])
        fig.update_layout(title=title, barmode="group", height=360, yaxis_title="%",
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#cbd5e1", size=11), legend=dict(orientation="h", y=-0.3),
                          margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(gridcolor="#1e293b"))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.bar_chart(df[cols])


def _pct_table(df: pd.DataFrame, pct_cols: list[str]):
    st.dataframe(df.style.format({c: "{:.1%}" for c in pct_cols} |
                                 {c: "{:+.2f}" for c in df.columns if c not in pct_cols
                                  and pd.api.types.is_numeric_dtype(df[c])}),
                 use_container_width=True)


# ── Portefeuilles de l'utilisateur (détection souple de la structure) ─────────
def _find_portfolios(obj, path="", out=None, depth=0):
    """Cherche des dicts du type {'positions'|'holdings': {ticker: qté ou {qty..}}}."""
    out = {} if out is None else out
    if depth > 5:
        return out
    if isinstance(obj, dict):
        for key in ("positions", "holdings", "portfolio"):
            pos = obj.get(key)
            if isinstance(pos, dict) and pos:
                q = {}
                for t, v in pos.items():
                    if isinstance(v, (int, float)):
                        q[t] = float(v)
                    elif isinstance(v, dict):
                        for qk in ("qty", "quantity", "shares", "qte", "quantite"):
                            if isinstance(v.get(qk), (int, float)):
                                q[t] = float(v[qk])
                                break
                if q:
                    name = obj.get("name") or obj.get("nom") or path or "Portefeuille"
                    cash = next((float(obj[c]) for c in ("cash", "liquidites", "balance")
                                 if isinstance(obj.get(c), (int, float))), 0.0)
                    out[str(name)] = dict(qty=q, cash=cash)
        for k, v in obj.items():
            if k not in ("positions", "holdings"):
                _find_portfolios(v, f"{path}/{k}" if path else str(k), out, depth + 1)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _find_portfolios(v, f"{path}[{i}]", out, depth + 1)
    return out


@st.cache_data(ttl=900, show_spinner=False)
def _last_prices(tickers: tuple) -> dict:
    try:
        import yfinance as yf
        d = yf.download(list(tickers), period="5d", auto_adjust=True, progress=False)["Close"]
        if isinstance(d, pd.Series):
            d = d.to_frame(tickers[0])
        return {t: float(d[t].dropna().iloc[-1]) for t in tickers if t in d and d[t].notna().any()}
    except Exception:
        return {}


def _user_portfolios() -> dict:
    try:
        from utils.data import get_or_init_state
        found = _find_portfolios(get_or_init_state())
    except Exception:
        found = {}
    res = {}
    for name, p in found.items():
        prices = _last_prices(tuple(sorted(p["qty"])))
        vals = {t: q * prices[t] for t, q in p["qty"].items() if t in prices and q > 0}
        if p["cash"] > 0:
            vals["CASH"] = p["cash"]
        if vals:
            res[name] = vals
    return res


# ══════════════════════════════════════════════════════════════════════════════
# Panneau de conseils réutilisable (aussi appelable depuis Auto-Portefeuille)
# ══════════════════════════════════════════════════════════════════════════════
def render_advice_panel(holdings: dict, profile: str = "Équilibré", key: str = "adv",
                        ctx=None):
    """holdings = {ticker: valeur en € ou $ (ou poids)}.
    Exemple depuis pages/auto_portfolio.py :
        from pages.hedge_fund import render_advice_panel
        render_advice_panel({t: w for t, w in weights.items()}, profile="Dynamique")
    """
    st.markdown(_CSS, unsafe_allow_html=True)
    px, missing, news, news_sim, macro, cov, data_sim = ctx or _load_all()
    target_raw = A.propose_allocation(macro.factors, profile)["Proposée (avant risque)"]
    target, _, _ = A.risk_engine(target_raw, profile, macro.factors, cov, data_sim)
    res = A.advise_portfolio(holdings, macro, profile, target, cov)

    c1, c2, c3 = st.columns(3)
    c1.metric("Volatilité estimée", f"{res['vol']:.1%}", help="Annualisée, via les proxies de classes")
    c2.metric("Pire scénario de stress", f"{res['stress'].iloc[0]:+.1%}", res["stress"].index[0],
              delta_color="off")
    c3.metric("Régime actuel", macro.regime)

    st.markdown("##### Conseils du desk")
    if not res["advice"]:
        st.success("Portefeuille cohérent avec le contexte et le profil choisi : aucun ajustement majeur.")
    for lvl, title, detail in res["advice"]:
        color, ico = ADV_STYLE[lvl]
        st.markdown(f'<div class="hf-adv" style="border-color:{color}"><b>{ico} {html.escape(title)}</b>'
                    f'<span>{html.escape(detail)}</span></div>', unsafe_allow_html=True)

    cmp = pd.DataFrame({"Actuel": res["class_weights"], "Cible du desk": target})
    cmp = cmp[(cmp > 0.004).any(axis=1)]
    _alloc_compare(cmp, ["Actuel", "Cible du desk"], "Répartition actuelle vs cible")

    col_a, col_b = st.columns(2)
    with col_a:
        _bar_h(res["stress"] * 100, "Stress tests (perte/gain estimés, %)", fmt="+.1f")
    with col_b:
        _bar_h(res["factor_exposure"].rename(lambda k: A.FACTORS[k][0]),
               "Sensibilité du portefeuille aux facteurs")
    st.caption("Stress tests : chocs approximatifs par classe d'actifs (hyp. = scénario hypothétique). "
               + DISCLAIMER)
    return res


# ══════════════════════════════════════════════════════════════════════════════
# Page
# ══════════════════════════════════════════════════════════════════════════════
def render():
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="hf-card"><div class="hf-title">🦅 HEDGE FUND AGENT</div>'
        '<div class="hf-sub">Un desk multi-rôles : chaque rôle fait un seul travail sur les mêmes données, '
        'un moteur de risque déterministe a le dernier mot, et rien n\'est exécuté sans votre validation.</div>'
        '<div style="margin-top:8px">'
        + "".join(f'<span class="hf-role">{r}</span>' for r in
                  ["1 · Données", "2 · Veille actualités", "3 · Macro & régime", "4 · Stratège",
                   "5 · Risque (veto)", "6 · Conseiller", "7 · Validation & journal"])
        + "</div></div>", unsafe_allow_html=True)

    top = st.columns([1, 1, 4])
    if top[0].button("🔄 Actualiser le desk", key="hf_refresh"):
        A.load_prices.clear() if hasattr(A.load_prices, "clear") else None
        A.load_news.clear() if hasattr(A.load_news, "clear") else None
        st.rerun()

    ctx = _load_all()
    px, missing, news, news_sim, macro, cov, data_sim = ctx
    badge = ('<span class="hf-badge hf-warn">DONNÉES DE MARCHÉ SIMULÉES</span>' if data_sim
             else '<span class="hf-badge hf-ok">DONNÉES DE MARCHÉ RÉELLES</span>')
    badge += (' <span class="hf-badge hf-warn">ACTUALITÉS SIMULÉES</span>' if news_sim
              else ' <span class="hf-badge hf-ok">ACTUALITÉS EN DIRECT</span>')
    top[2].markdown(badge + f' <span class="hf-sub">· {datetime.now():%d/%m/%Y %H:%M}</span>',
                    unsafe_allow_html=True)
    if missing and not data_sim:
        st.caption("Indicateurs indisponibles remplacés par du simulé : " + ", ".join(missing))

    t1, t2, t3, t4 = st.tabs(["🛰️ BRIEFING", "🎯 ALLOCATION DU DESK", "🩺 CONSEILS PORTEFEUILLE", "📒 JOURNAL"])

    # ── 1. Briefing ───────────────────────────────────────────────────────────
    with t1:
        st.markdown(f'<div class="hf-card"><div class="hf-title">Régime : {html.escape(macro.regime)}</div>'
                    f'<div class="hf-sub">{html.escape(macro.regime_text)}</div></div>',
                    unsafe_allow_html=True)
        c1, c2 = st.columns([1.1, 1])
        with c1:
            _bar_h(pd.Series({A.FACTORS[k][0]: v for k, v in macro.factors.items()}),
                   "Facteurs économiques, politiques et géopolitiques (−2 à +2)", rng=[-2.4, 2.4])
            for k, (label, meaning) in A.FACTORS.items():
                with st.expander(f"{label} : {macro.factors[k]:+.2f}  ·  {meaning}"):
                    for e in macro.evidence[k]:
                        st.markdown(f"- {e}")
        with c2:
            st.markdown("##### Briefing du desk")
            st.markdown(A.deterministic_briefing(macro, news))
            if A.llm_available():
                if st.button("✍️ Rédiger le briefing avec l'IA", key="hf_llm"):
                    try:
                        with st.spinner("Rédaction…"):
                            st.session_state["hf_llm_txt"] = A.llm_briefing(A.context_for_llm(macro, news))
                    except Exception as e:
                        st.warning(f"LLM indisponible : {e}")
                if st.session_state.get("hf_llm_txt"):
                    st.info(st.session_state["hf_llm_txt"])
            else:
                st.caption("💡 Briefing rédigé par IA disponible en ajoutant une clé gratuite Groq ou "
                           "Gemini dans les secrets Streamlit (section [llm]).")
            sc = A.class_scores(macro.factors)
            _bar_h(sc, "Classes d'actifs favorisées / pénalisées par le contexte")

        st.markdown("##### Veille actualités (7 derniers jours)")
        themes = sorted(news.items(), key=lambda kv: -kv[1]["intensity"])
        cols = st.columns(3)
        for i, (k, th) in enumerate(themes):
            with cols[i % 3]:
                lvl = th["intensity"]
                color = RED if lvl >= 60 else ("#f59e0b" if lvl >= 35 else GREEN)
                heads = "".join(
                    f'<div><a href="{html.escape(h["link"])}" target="_blank">{html.escape(h["title"][:110])}</a>'
                    f' <small>{h["date"]:%d/%m}</small></div>' for h in th["headlines"][:3])
                st.markdown(
                    f'<div class="hf-card hf-news"><div class="hf-title" style="font-size:.9rem">'
                    f'{html.escape(th["label"])} <span style="color:{color}">{lvl:.0f}/100</span></div>'
                    f'{heads or "<small>Aucun titre récent</small>"}</div>', unsafe_allow_html=True)

    # ── 2. Allocation du desk ─────────────────────────────────────────────────
    with t2:
        c1, c2, c3 = st.columns([1, 1, 1])
        profile = c1.selectbox("Profil", list(A.PROFILES), index=1, key="hf_profile")
        intensity = c2.slider("Intensité tactique", 0.0, 1.0, 0.5, 0.1, key="hf_int",
                              help="0 = allocation stratégique pure ; 1 = inclinaisons macro maximales")
        capital = c3.number_input("Capital (simulation)", 1_000, 100_000_000, 100_000, 1_000, key="hf_cap")

        prop = A.propose_allocation(macro.factors, profile, intensity)
        final, checks, allowed = A.risk_engine(prop["Proposée (avant risque)"], profile,
                                               macro.factors, cov, data_sim)
        prop["Finale (après risque)"] = final
        prop["Écart vs stratégique"] = final - prop["Stratégique"]
        prop["Montant"] = final * capital

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Volatilité stratégique", f"{A.port_vol(prop['Stratégique'], cov):.1%}")
        m2.metric("Volatilité finale", f"{A.port_vol(final, cov):.1%}",
                  f"limite {A.LIMITS[profile]['vol']:.0%}", delta_color="off")
        stress = A.stress_test(final)
        m3.metric("Pire stress test", f"{stress.iloc[0]:+.1%}", stress.index[0], delta_color="off")
        m4.metric("Exécution", "Autorisée" if allowed else "Bloquée")

        _alloc_compare(prop, ["Stratégique", "Proposée (avant risque)", "Finale (après risque)"],
                       "Stratégique → stratège → moteur de risque")

        show = prop[["Stratégique", "Finale (après risque)", "Écart vs stratégique", "Score macro"]].copy()
        show["Montant"] = prop["Montant"].map(lambda v: f"{v:,.0f}".replace(",", " "))
        show["Proxy"] = [A.CLASS_PROXY[c] for c in show.index]
        _pct_table(show, ["Stratégique", "Finale (après risque)", "Écart vs stratégique"])

        st.markdown("##### Pourquoi ces inclinaisons ?")
        movers = prop["Écart vs stratégique"].abs().sort_values(ascending=False)
        for c in movers.index[:5]:
            if movers[c] < 0.004:
                continue
            d = prop.loc[c, "Écart vs stratégique"]
            why = A.explain_class(c, macro.factors)
            st.markdown(f"**{'▲' if d > 0 else '▼'} {c} ({d:+.1%})** — " + " ; ".join(why))

        st.markdown("##### Moteur de risque")
        st.dataframe(pd.DataFrame(checks), use_container_width=True, hide_index=True)
        _bar_h(stress * 100, "Stress tests de l'allocation finale (%)", fmt="+.1f")

        st.markdown("##### Validation humaine")
        note = st.text_input("Commentaire (facultatif)", key="hf_note")
        b1, b2, b3 = st.columns([1, 1, 2])
        entry = dict(date=datetime.now().isoformat(timespec="seconds"), profil=profile,
                     regime=macro.regime, intensite=intensity, capital=capital,
                     facteurs={k: round(v, 2) for k, v in macro.factors.items()},
                     allocation={c: round(float(w), 4) for c, w in final.items() if w > 0.0005},
                     donnees_simulees=data_sim, commentaire=note)
        if b1.button("✅ Valider la proposition", key="hf_ok"):
            A.append_journal(entry | dict(decision="validée"))
            st.success("Proposition validée et inscrite au journal."
                       + ("" if allowed else " Exécution bloquée : données simulées."))
        if b2.button("❌ Rejeter", key="hf_ko"):
            A.append_journal(entry | dict(decision="rejetée"))
            st.info("Proposition rejetée et inscrite au journal.")
        orders = pd.DataFrame({"Classe": final.index, "Proxy": [A.CLASS_PROXY[c] for c in final.index],
                               "Poids": final.round(4).values, "Montant": (final * capital).round(2).values})
        b3.download_button("⬇️ Ordres (CSV)", orders.to_csv(index=False).encode("utf-8"),
                           f"ordres_desk_{datetime.now():%Y%m%d}.csv", "text/csv", key="hf_csv")
        st.caption("Pour exécuter dans un portefeuille MAM, utilisez ces poids dans 🤖 Auto-Portefeuille "
                   "ou le Trading Desk. " + DISCLAIMER)

    # ── 3. Conseils pour un portefeuille existant ─────────────────────────────
    with t3:
        st.markdown("Diagnostic de **n'importe quel portefeuille** au regard de la situation économique, "
                    "politique, géopolitique et financière actuelle.")
        found = _user_portfolios()
        options = list(found) + ["✏️ Saisie manuelle"]
        c1, c2 = st.columns([2, 1])
        src = c1.selectbox("Portefeuille à analyser", options, key="hf_src")
        prof2 = c2.selectbox("Profil de risque", list(A.PROFILES), index=1, key="hf_prof2")
        if src == "✏️ Saisie manuelle":
            if not found:
                st.caption("Aucun portefeuille MAM détecté automatiquement : saisissez vos lignes "
                           "(ticker Yahoo et montant).")
            base = pd.DataFrame({"Ticker": ["AAPL", "MSFT", "BNP.PA", "TLT", "GC=F", "BTC-USD", "CASH"],
                                 "Montant": [20000, 15000, 10000, 15000, 8000, 7000, 25000]})
            ed = st.data_editor(st.session_state.get("hf_manual", base), num_rows="dynamic",
                                use_container_width=True, key="hf_editor")
            holdings = {str(r.Ticker).strip(): float(r.Montant) for r in ed.itertuples()
                        if str(r.Ticker).strip() and pd.notna(r.Montant) and r.Montant > 0}
        else:
            holdings = found[src]
            st.dataframe(pd.DataFrame({"Valeur": holdings}).sort_values("Valeur", ascending=False)
                         .style.format("{:,.0f}"), use_container_width=True)
        if holdings:
            render_advice_panel(holdings, prof2, key="hf_t3", ctx=ctx)

    # ── 4. Journal ────────────────────────────────────────────────────────────
    with t4:
        j = A.load_journal()
        if not j:
            st.info("Le journal est vide. Chaque proposition validée ou rejetée y est enregistrée.")
        else:
            df = pd.DataFrame(j)[["date", "decision", "profil", "regime", "capital",
                                  "donnees_simulees", "commentaire"]].iloc[::-1]
            st.dataframe(df, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Exporter le journal (JSON)",
                               pd.Series(j).to_json(orient="values", force_ascii=False).encode("utf-8"),
                               "journal_hedge_fund.json", "application/json", key="hf_jdl")
        st.caption("Sur Streamlit Cloud, ce fichier est effacé au redémarrage : exportez-le, "
                   "ou je peux le brancher sur votre base Supabase.")
