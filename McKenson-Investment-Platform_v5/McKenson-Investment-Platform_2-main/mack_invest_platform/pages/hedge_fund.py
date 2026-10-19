"""
pages/hedge_fund.py — 🦅 Hedge Fund Agent
Desk multi-rôles : veille → macro → stratège → risque (veto) → validation humaine → journal.
Conseils applicables à l'allocation du desk ET à n'importe quel portefeuille existant.
"""
from __future__ import annotations

import html
import json
from datetime import datetime

import numpy as np
import pandas as pd
import streamlit as st

from utils import advisor as A
from utils import portfolio_manager as PM
from utils import alerts as AL

try:
    import plotly.graph_objects as go
    _PLOTLY = True
except Exception:
    _PLOTLY = False

CYAN, GREEN, RED, VIOLET, GREY = "#00d4ff", "#00ff88", "#ff3b6b", "#7c3aed", "#94a3b8"
from utils.legal import DISCLAIMER_SHORT as DISCLAIMER  # auteur, version et non-responsabilité

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
.hf-alert{border-left:4px solid;padding:10px 14px;margin:8px 0;border-radius:5px;background:rgba(255,255,255,.025)}
.hf-alert .hd{font-size:.68rem;font-weight:700;letter-spacing:.08em}
.hf-alert .tt{font-family:'Rajdhani',sans-serif;font-weight:700;font-size:1rem;color:#e2e8f0;margin:2px 0 6px}
.hf-alert .bd{font-size:.76rem;color:#94a3b8;line-height:1.5}
.hf-alert .bd b{color:#cbd5e1}
</style>
"""

ADV_STYLE = {
    "alerte": ("#ff3b6b", "⛔"), "risque": ("#f59e0b", "⚠️"), "action": ("#00d4ff", "🎯"),
    "info": ("#94a3b8", "ℹ️"), "atout": ("#00ff88", "✅"),
}


# ── Clés uniques pour les graphiques (évite les doublons d'ID Streamlit) ─────
def _pkey() -> str:
    n = st.session_state.get("_hf_plot_n", 0) + 1
    st.session_state["_hf_plot_n"] = n
    return f"hf_plot_{n}"


def _reset_pkeys():
    st.session_state["_hf_plot_n"] = 0



SEV_COLOR = {"critique": "#ff3b6b", "important": "#f59e0b", "info": "#38bdf8"}


def _alert_card(a: dict):
    c = SEV_COLOR[a["gravite"]]
    arrow = {"hausse": "▲", "baisse": "▼"}.get(a.get("sens"), "•")
    st.markdown(
        f'<div class="hf-alert" style="border-color:{c}">'
        f'<div class="hd" style="color:{c}">{a["icone"]} {a["gravite_label"].upper()} · '
        f'{html.escape(a["categorie"])} · {arrow} {html.escape(str(a.get("sens", "")))}'
        f' <span style="color:#475569;font-weight:400">· {str(a.get("date", ""))[:16].replace("T", " ")}</span></div>'
        f'<div class="tt">{html.escape(a["titre"])}</div>'
        f'<div class="bd"><b>Pourquoi c\'est important :</b> {html.escape(a["pourquoi"])}<br>'
        f'<b>Impact probable :</b> {html.escape(a["impact"])}<br>'
        f'<b>À surveiller / faire :</b> {html.escape(a["a_surveiller"])}</div></div>',
        unsafe_allow_html=True)


def _live_alerts(ctx, user_reviews: list | None = None) -> list:
    px, missing, news, news_sim, macro, cov, data_sim = ctx
    hist = PM.factor_history(px, news)
    prev = st.session_state.get("_hf_prev_news")
    if prev is None:
        prev = AL.get_state("news_intensity") or {}
        st.session_state["_hf_prev_news"] = prev
    al = AL.compute_alerts(px, missing, news, news_sim, macro, hist, prev, user_reviews or [])
    if data_sim:
        al = [a for a in al if a["regle"] == "actualite"]
    return al


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
        st.plotly_chart(fig, use_container_width=True, key=_pkey())
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
        st.plotly_chart(fig, use_container_width=True, key=_pkey())
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
# Revue de gestion réutilisable (aussi appelable depuis Auto-Portefeuille)
# ══════════════════════════════════════════════════════════════════════════════
def _fmt_money(v):
    return f"{v:,.0f}".replace(",", " ")


def render_advice_panel(holdings: dict, profile: str = "Équilibré", key: str = "adv",
                        ctx=None, name: str = "Portefeuille"):
    """Revue complète d'un portefeuille, comme un gérant professionnel.
    holdings = {ticker: valeur}. Exemple depuis pages/auto_portfolio.py :
        from pages.hedge_fund import render_advice_panel
        render_advice_panel({t: w * capital for t, w in weights.items()},
                            profile="Dynamique", name="Auto-portefeuille")
    """
    st.markdown(_CSS, unsafe_allow_html=True)
    if ctx is None:          # appel autonome (ex. depuis Auto-Portefeuille)
        _reset_pkeys()
        ctx = _load_all()

    with st.expander("⚙️ Règles de gestion", expanded=False):
        c1, c2, c3 = st.columns(3)
        band = c1.slider("Bande de tolérance par classe", 0.01, 0.10, 0.03, 0.01, key=f"{key}_band",
                         help="Pas d'ordre tant que l'écart à la cible reste dans cette bande")
        mode = c2.radio("Rééquilibrage", ["Complet", "Moitié du chemin"], key=f"{key}_mode",
                        help="« Moitié du chemin » limite la rotation quand la conviction est incertaine")
        max_line = c3.slider("Poids maximum par ligne", 0.05, 0.30, 0.15, 0.01, key=f"{key}_maxl")

    journal, _ = A.load_journal()
    with st.spinner("Le gérant analyse le portefeuille…"):
        R = PM.full_review(name, holdings, profile, ctx, journal, band=band,
                           mode="Complet" if mode == "Complet" else "Moitié", max_line=max_line)
    lines, plan, views, macro = R["lines"], R["plan"], R["views"], R["macro"]

    m = st.columns(5)
    m[0].metric("Valeur", _fmt_money(plan["total"]))
    m[1].metric("Volatilité", f"{R['vol_now']:.1%}", f"{R['vol_after'] - R['vol_now']:+.1%} après ajustement",
                delta_color="inverse")
    m[2].metric("Pire stress", f"{R['stress'].iloc[0]:+.1%}",
                f"{R['stress_after'].iloc[0] - R['stress'].iloc[0]:+.1%} après ajustement")
    m[3].metric("Rotation proposée", f"{plan['turnover']:.0%}", f"coûts ≈ {_fmt_money(plan['cost'])}",
                delta_color="off")
    m[4].metric("Régime", macro.regime)

    if R["since"]:
        st.warning("**Depuis votre dernière revue** ("
                   + str(R["last_review"].get("date", ""))[:10] + ") : " + " ; ".join(R["since"]))
    if R["line_missing"]:
        st.caption("Cours indisponibles pour " + ", ".join(R["line_missing"])
                   + " : analysés via l'ETF représentatif de leur classe.")

    s1, s2, s3, s4, s5, s6 = st.tabs(["📝 Note de gestion", "🔁 Plan d'ajustement", "🔍 Analyse des lignes",
                                      "📈 Évolution du contexte", "⚠️ Risques & déclencheurs",
                                      "📬 Rapport & alertes"])

    with s1:
        note = st.session_state.get(f"{key}_llm_note") or R["note"]
        st.markdown(note)
        b1, b2, b3 = st.columns(3)
        if A.llm_available() and b1.button("✍️ Reformuler par l'IA", key=f"{key}_llm"):
            try:
                with st.spinner("Rédaction…"):
                    st.session_state[f"{key}_llm_note"] = PM.llm_rewrite_note(R["note"])
                st.rerun()
            except Exception as e:
                st.warning(f"LLM indisponible : {e}")
        b2.download_button("⬇️ Note (Markdown)", note.encode("utf-8"),
                           f"note_gestion_{datetime.now():%Y%m%d}.md", "text/markdown", key=f"{key}_dl")
        if b3.button("💾 Enregistrer la revue", key=f"{key}_save"):
            t = plan["trades"]
            msg = A.append_journal(dict(
                type="revue", decision="revue", portefeuille=name, profil=profile,
                date=datetime.now().isoformat(timespec="seconds"), regime=macro.regime,
                capital=round(plan["total"], 2), donnees_simulees=R["data_sim"],
                facteurs={k: round(v, 2) for k, v in macro.factors.items()},
                allocation={c: round(float(w), 4) for c, w in
                            lines.groupby("Classe")["Poids"].sum().items()},
                ordres=[] if t.empty else t[["Ordre", "Ligne", "Montant"]].round(2).to_dict("records"),
                commentaire=f"Rotation {plan['turnover']:.0%}"))
            st.success("Revue enregistrée : la prochaine revue signalera ce qui a changé depuis.")
            if msg:
                st.warning(msg)

    with s2:
        t = plan["trades"]
        if t.empty:
            st.success(plan["timing"])
        else:
            st.markdown(f"**Calendrier d'exécution** — {plan['timing']}")
            show = t[["Priorité", "Ordre", "Ligne", "Classe", "Montant", "% du portefeuille",
                      "Conviction", "Motif"]].copy()
            st.dataframe(show.style.format({"Montant": lambda v: f"{v:+,.0f}".replace(",", " "),
                                            "% du portefeuille": "{:+.1%}"}),
                         use_container_width=True, hide_index=True)
            st.download_button("⬇️ Ordres (CSV)", show.to_csv(index=False).encode("utf-8"),
                               f"ordres_{datetime.now():%Y%m%d}.csv", "text/csv", key=f"{key}_csv")
        cmp = pd.DataFrame({"Actuel": lines.groupby("Classe")["Poids"].sum().reindex(A.CLASSES).fillna(0),
                            "Après ajustement": plan["after"].clip(lower=0),
                            "Cible du gérant": R["target"]})
        cmp = cmp[(cmp > 0.004).any(axis=1)]
        _alloc_compare(cmp, ["Actuel", "Après ajustement", "Cible du gérant"], "Allocation par classe")
        st.markdown("##### Vues du gérant")
        v = views[["Vue", "Conviction", "Poids stratégique", "Poids cible", "Cohérence des signaux", "Arguments"]]
        st.dataframe(v.style.format({"Poids stratégique": "{:.0%}", "Poids cible": "{:.0%}",
                                     "Cohérence des signaux": "{:.0%}"}), use_container_width=True)

    with s3:
        cols = ["Classe", "Poids", "Valeur", "Avis", "Motif", "Contribution au risque", "Volatilité",
                "Bêta", "Perf. 1 mois", "Perf. 3 mois", "Perf. 12 mois", "Drawdown", "Tendance", "Source"]
        pct = ["Poids", "Contribution au risque", "Volatilité", "Perf. 1 mois", "Perf. 3 mois",
               "Perf. 12 mois", "Drawdown"]
        st.dataframe(lines[cols].style.format({c: "{:.1%}" for c in pct} |
                                              {"Valeur": lambda v: _fmt_money(v), "Bêta": "{:.2f}"},
                                              na_rep="n.d."),
                     use_container_width=True)
        rc = lines[lines["Contribution au risque"] > 0]
        if len(rc) and _PLOTLY:
            fig = go.Figure()
            fig.add_bar(name="Poids", x=rc.index, y=rc["Poids"] * 100, marker_color=GREY)
            fig.add_bar(name="Contribution au risque", x=rc.index, y=rc["Contribution au risque"] * 100,
                        marker_color=RED)
            fig.update_layout(title="Poids vs contribution au risque (%)", barmode="group", height=320,
                              paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                              font=dict(color="#cbd5e1", size=11), legend=dict(orientation="h", y=-0.3),
                              margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(gridcolor="#1e293b"))
            st.plotly_chart(fig, use_container_width=True, key=_pkey())
        st.caption("Une ligne dont la contribution au risque dépasse nettement son poids concentre le risque "
                   "du portefeuille : c'est la première candidate à un allègement.")

    with s4:
        _render_factor_history(R["hist"], R["moves"])

    with s5:
        c1, c2 = st.columns(2)
        with c1:
            stx = pd.DataFrame({"Actuel": R["stress"] * 100,
                                "Après ajustement": R["stress_after"].reindex(R["stress"].index) * 100})
            if _PLOTLY:
                fig = go.Figure()
                fig.add_bar(name="Actuel", y=stx.index, x=stx["Actuel"], orientation="h", marker_color=RED)
                fig.add_bar(name="Après ajustement", y=stx.index, x=stx["Après ajustement"],
                            orientation="h", marker_color=CYAN)
                fig.update_layout(title="Stress tests (%)", barmode="group", height=340,
                                  paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                                  font=dict(color="#cbd5e1", size=11), legend=dict(orientation="h", y=-0.2),
                                  margin=dict(l=10, r=10, t=40, b=10), xaxis=dict(gridcolor="#1e293b"))
                st.plotly_chart(fig, use_container_width=True, key=_pkey())
            else:
                st.bar_chart(stx)
        with c2:
            cls_now = lines.groupby("Classe")["Poids"].sum().reindex(A.CLASSES).fillna(0)
            _bar_h(A.SENSITIVITY.T.dot(cls_now).rename(lambda k: A.FACTORS[k][0]),
                   "Sensibilité du portefeuille aux facteurs")
        st.markdown("##### Déclencheurs de révision")
        for x in R["triggers"]:
            st.markdown(f"- {x}")

    with s6:
        _render_report_section(R, holdings, profile, name, key, ctx)
    st.caption("Stress tests : chocs approximatifs par classe (hyp. = hypothétique). " + DISCLAIMER)
    return R



def _render_report_section(R: dict, holdings: dict, profile: str, name: str, key: str, ctx):
    px, missing, news, news_sim, macro, cov, data_sim = ctx
    my_alerts = _live_alerts(ctx, [(name, R["lines"], R["target"])])
    my_alerts = [a for a in my_alerts if a["categorie"] != "Portefeuille" or a["titre"].startswith(name + " ·")]

    st.markdown("##### Rapport PNG")
    c1, c2 = st.columns([1, 1])
    if c1.button("🖼️ Générer le rapport", key=f"{key}_png"):
        from utils.report_png import build_weekly_png
        with st.spinner("Mise en page du rapport…"):
            st.session_state[f"{key}_png_bytes"] = build_weekly_png(
                macro, news, my_alerts, R, name=name, profile=profile, hist=R["hist"], data_sim=data_sim)
    png = st.session_state.get(f"{key}_png_bytes")
    if png:
        c2.download_button("⬇️ Télécharger le PNG", png, f"rapport_{datetime.now():%Y%m%d}.png",
                           "image/png", key=f"{key}_pngdl")
        st.image(png, use_container_width=True)
        default_mail = A.current_user_key() if "@" in A.current_user_key() else ""
        to = st.text_input("Envoyer maintenant à", value=default_mail, key=f"{key}_to")
        if st.button("📧 Envoyer par email", key=f"{key}_send") and to:
            err = AL.send_email(to, f"📈 Rapport MAM — {name} — {datetime.now():%d/%m/%Y}",
                                AL.alerts_email_html(my_alerts[:6], f"Rapport — {name} · régime : {macro.regime}"),
                                [(f"rapport_{datetime.now():%Y%m%d}.png", png, "image/png")])
            st.success("Rapport envoyé.") if not err else st.error(f"Envoi impossible : {err}")

    st.markdown("##### Rapport hebdomadaire automatique et alertes par email")
    if A.journal_backend() != "Supabase":
        st.info("L'abonnement nécessite la base Supabase (section [supabase] des secrets).")
        return
    user = A.current_user_key()
    subs = {s["portfolio_name"]: s for s in AL.subscriptions(user)}
    cur = subs.get(name)
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    email = c1.text_input("Adresse de réception", value=(cur or {}).get("email") or
                          (user if "@" in user else ""), key=f"{key}_subemail")
    weekly = c2.checkbox("Rapport du lundi", value=(cur or {}).get("weekly", True), key=f"{key}_w")
    alerts_on = c3.checkbox("Alertes", value=(cur or {}).get("alerts", True), key=f"{key}_a")
    sev = c4.selectbox("Gravité minimum", ["critique", "important", "info"],
                       index=["critique", "important", "info"].index((cur or {}).get("min_severity", "important")),
                       key=f"{key}_sev")
    b1, b2 = st.columns(2)
    if b1.button("📬 " + ("Mettre à jour le suivi" if cur else "Suivre ce portefeuille"), key=f"{key}_sub"):
        if not email or "@" not in email:
            st.error("Adresse email invalide.")
        elif AL.subscribe(user, email, name, profile, holdings, weekly, alerts_on, sev):
            st.success(f"C'est noté : {name} sera analysé automatiquement"
                       + (" et le rapport PNG vous sera envoyé chaque lundi" if weekly else "")
                       + (f" ; alertes « {sev} » et plus graves par email" if alerts_on else "") + ".")
        else:
            st.error("Enregistrement impossible : base injoignable.")
    if cur and b2.button("🛑 Arrêter le suivi", key=f"{key}_unsub"):
        AL.unsubscribe(user, name)
        st.info("Suivi arrêté.")
    st.caption("Le suivi enregistre une copie des lignes actuelles : cliquez à nouveau sur « Mettre à jour » "
               "après avoir modifié le portefeuille. L'envoi automatique est assuré par GitHub Actions (voir README).")


def _render_factor_history(hist: pd.DataFrame, moves: list):
    if hist.empty:
        st.info("Historique insuffisant pour mesurer l'évolution des facteurs.")
        return
    num = hist.drop(index="Régime").astype(float)
    num.index = [A.FACTORS[k][0] for k in num.index]
    if _PLOTLY:
        fig = go.Figure()
        pal = [CYAN, GREEN, RED, VIOLET, "#f59e0b", "#e879f9", "#38bdf8", "#a3e635"]
        for i, (f, row) in enumerate(num.iterrows()):
            fig.add_scatter(x=list(row.index), y=row.values, mode="lines+markers", name=f,
                            line=dict(color=pal[i % len(pal)], width=2))
        fig.update_layout(title="Évolution des facteurs (−2 à +2)", height=380,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#cbd5e1", size=11), legend=dict(orientation="h", y=-0.25),
                          margin=dict(l=10, r=10, t=40, b=10), yaxis=dict(range=[-2.2, 2.2], gridcolor="#1e293b"))
        st.plotly_chart(fig, use_container_width=True, key=_pkey())
    else:
        st.line_chart(num.T)
    reg = hist.loc["Régime"]
    st.markdown("**Régime** : " + " → ".join(f"{c} : *{r}*" for c, r in reg.items()))
    st.markdown("##### Ce qui a bougé sur le dernier mois")
    if not moves:
        st.markdown("Aucun facteur n'a varié significativement : contexte stable.")
    for mv in moves:
        st.markdown(f"- {PM.describe_move(mv)}")
    st.caption("L'évolution est calculée sur les données de marché ; les actualités ne sont disponibles "
               "qu'à date et sont tenues constantes dans l'historique.")


# ══════════════════════════════════════════════════════════════════════════════
# Page
# ══════════════════════════════════════════════════════════════════════════════
def render():
    _reset_pkeys()
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

    live_alerts = _live_alerts(ctx)
    n_hot = sum(a["rang"] >= 2 for a in live_alerts)
    crit = [a for a in live_alerts if a["gravite"] == "critique"]
    if crit:
        st.error(f"🔴 {len(crit)} alerte(s) critique(s) : " + " · ".join(a["titre"] for a in crit[:3])
                 + " — détails dans l'onglet Alertes.")

    t1, t5, t2, t3, t4 = st.tabs(["🛰️ BRIEFING", f"🔔 ALERTES ({n_hot})", "🎯 ALLOCATION DU DESK",
                                  "🩺 CONSEILS PORTEFEUILLE", "📒 JOURNAL"])

    # ── Alertes ───────────────────────────────────────────────────────────────
    with t5:
        st.markdown("Le desk surveille en continu les **marchés** (mouvements anormaux à la hausse ou à la "
                    "baisse, tendances), la **volatilité**, les **taux**, l'**économie** (facteurs, régime), la "
                    "**géopolitique** et l'**actualité financière**, et vos **portefeuilles suivis**. Chaque "
                    "alerte explique pourquoi elle compte et ce qu'il faut surveiller.")
        f1, f2 = st.columns(2)
        sev_f = f1.multiselect("Gravité", ["critique", "important", "info"],
                               default=["critique", "important", "info"], key="hf_al_sev")
        cats = sorted({a["categorie"] for a in live_alerts}) or ["Marchés"]
        cat_f = f2.multiselect("Catégorie", cats, default=cats, key="hf_al_cat")
        # alertes des portefeuilles suivis
        port_al = []
        if A.journal_backend() == "Supabase":
            for sub in AL.subscriptions(A.current_user_key()):
                try:
                    Rv = PM.full_review(sub["portfolio_name"], sub["holdings"], sub["profile"] or "Équilibré", ctx, [])
                    port_al += AL.portfolio_alerts(sub["portfolio_name"], Rv["lines"], Rv["target"])
                except Exception:
                    pass
        shown = [a for a in live_alerts + port_al if a["gravite"] in sev_f and
                 (a["categorie"] in cat_f or a["categorie"] == "Portefeuille")]
        shown.sort(key=lambda a: -a["rang"])
        if not shown:
            st.success("Aucune alerte pour ces filtres : pas d'évolution qui mérite votre attention aujourd'hui.")
        for a in shown:
            _alert_card(a)
        if data_sim:
            st.caption("Données de marché simulées : seules les alertes d'actualité sont affichées.")
        hist_al = AL.alert_history(30) if A.journal_backend() == "Supabase" else []
        if hist_al:
            with st.expander(f"📜 Historique des alertes (30 jours) — {len(hist_al)}"):
                st.dataframe(pd.DataFrame(hist_al)[["date", "gravite_label", "categorie", "sens", "titre"]],
                             use_container_width=True, hide_index=True)

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

        with st.expander("📈 Évolution des facteurs sur 3 mois", expanded=False):
            hist = PM.factor_history(px, news)
            _render_factor_history(hist, PM.factor_moves(hist))

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
            msg = A.append_journal(entry | dict(decision="validée"))
            st.success("Proposition validée et inscrite au journal."
                       + ("" if allowed else " Exécution bloquée : données simulées."))
            if msg:
                st.warning(msg)
        if b2.button("❌ Rejeter", key="hf_ko"):
            msg = A.append_journal(entry | dict(decision="rejetée"))
            st.info("Proposition rejetée et inscrite au journal.")
            if msg:
                st.warning(msg)
        orders = pd.DataFrame({"Classe": final.index, "Proxy": [A.CLASS_PROXY[c] for c in final.index],
                               "Poids": final.round(4).values, "Montant": (final * capital).round(2).values})
        b3.download_button("⬇️ Ordres (CSV)", orders.to_csv(index=False).encode("utf-8"),
                           f"ordres_desk_{datetime.now():%Y%m%d}.csv", "text/csv", key="hf_csv")
        st.caption("Pour exécuter dans un portefeuille MAM, utilisez ces poids dans 🤖 Auto-Portefeuille "
                   "ou le Trading Desk. " + DISCLAIMER)

    # ── 3. Conseils pour un portefeuille existant ─────────────────────────────
    with t3:
        st.markdown("Revue de **n'importe quel portefeuille**, menée comme par un gérant professionnel : "
                    "évolution du contexte économique, politique et géopolitique, vues par classe avec "
                    "niveau de conviction, analyse ligne par ligne, plan d'ajustement chiffré et "
                    "déclencheurs de révision.")
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
            render_advice_panel(holdings, prof2, key="hf_t3", ctx=ctx,
                                name=src if src != "✏️ Saisie manuelle" else "Portefeuille saisi")

    # ── 4. Journal ────────────────────────────────────────────────────────────
    with t4:
        j, err = A.load_journal()
        st.caption(f"Stockage : **{A.journal_backend()}** · compte : {A.current_user_key()}")
        if err:
            st.warning(err)
        if not j:
            st.info("Le journal est vide. Chaque proposition validée ou rejetée y est enregistrée.")
        else:
            df = pd.DataFrame(j)
            cols = [c for c in ["date", "decision", "portefeuille", "profil", "regime", "intensite", "capital",
                                "donnees_simulees", "commentaire"] if c in df.columns]
            st.dataframe(df[cols].iloc[::-1], use_container_width=True, hide_index=True)
            pick = st.selectbox("Détail d'une décision", range(len(j)), format_func=lambda i:
                                f"{j[i].get('date', '')} · {j[i].get('decision', '')} · {j[i].get('profil', '')}",
                                index=len(j) - 1, key="hf_jpick")
            alloc = pd.Series(j[pick].get("allocation", {}), dtype=float)
            if not alloc.empty:
                _pct_table(alloc.rename("Poids").to_frame(), ["Poids"])
            st.download_button("⬇️ Exporter le journal (JSON)",
                               json.dumps(j, ensure_ascii=False, indent=1, default=str).encode("utf-8"),
                               "journal_hedge_fund.json", "application/json", key="hf_jdl")
        if A.journal_backend() != "Supabase":
            st.caption("Supabase non configuré : le fichier local est effacé au redémarrage de "
                       "Streamlit Cloud. Ajoutez la section [supabase] aux secrets.")
