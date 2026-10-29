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
DISCLAIMER = "Outil pédagogique d'aide à la décision sur une plateforme de simulation."

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


def _port_by_name(name: str) -> dict | None:
    """Portefeuille MAM portant ce nom (pour la synthèse en mots simples de la note de gestion)."""
    try:
        from utils.data import get_or_init_state
        for t in get_or_init_state().get("teams", {}).values():
            for p in (t.get("portfolios") or {}).values():
                if p.get("name") and p.get("name") == name:
                    return p
    except Exception:
        pass
    return None


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
        port_ = _port_by_name(name)
        if port_ is not None and not st.session_state.get(f"{key}_llm_note"):
            try:  # En bref : mieux ou moins bien que le marché, et pourquoi (v5.6)
                from utils.plain_summary import plain_summary
                simple = plain_summary(port_, "S&P 500")
                head, _, rest = note.partition("\n")
                note = (head + "\n\n## En bref — en mots simples\n\n"
                        + "\n".join(f"- {x}" for x in simple["phrases"]) + "\n" + rest)
            except Exception:
                pass
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
            _bar_h(A.sensitivity().T.dot(cls_now).rename(lambda k: A.FACTORS[k][0]),
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
# ══════════════════════════════════════════════════════════════════════════════
# Exécution de la proposition : nouveau portefeuille / portefeuille existant
# + couvertures par produits dérivés (au choix de l'investisseur)
# ══════════════════════════════════════════════════════════════════════════════
_EMOJIS = ["🦅", "🛡️", "📈", "🌍", "💼", "🎯", "⚖️", "🚀"]


def _desk_weights(final: pd.Series) -> pd.Series:
    """Allocation par classe → poids par ETF proxy (le monétaire BIL reste en liquidités)."""
    w = {}
    for cls, v in final.items():
        if v > 0.0005:
            t = A.CLASS_PROXY[cls]
            w[t] = w.get(t, 0.0) + float(v)
    return pd.Series(w, dtype=float)


def _hedge_cards(hedges: list[dict], options_ok: bool) -> list[str]:
    """Affiche les couvertures proposées ; renvoie les clés acceptées par l'investisseur."""
    accepted = []
    if not hedges:
        st.info("Aucune exposition couvrable significative (≥ 5 % de l'actif net) dans cette allocation.")
        return accepted
    for h in hedges:
        tag = ('<span class="hf-badge hf-warn">RECOMMANDÉE PAR LE DESK</span>' if h["recommandee"]
               else '<span class="hf-badge" style="border:1px solid #475569;color:#94a3b8">FACULTATIVE</span>')
        k1 = h["legs_unitaires"][0]["K"]
        legs_txt = (f"achat de puts strike {k1:,.2f}" if h["strategie"] == "Put de protection" else
                    f"achat put {k1:,.2f} / vente put {h['legs_unitaires'][1]['K']:,.2f}")
        st.markdown(
            f'<div class="hf-card"><div class="hf-title" style="font-size:.95rem">🛡️ {html.escape(h["panier"])} '
            f'· {_fmt_money(h["exposition"])} $ exposés {tag}</div>'
            f'<div class="hf-sub" style="font-size:.78rem;line-height:1.7">'
            f'<b>Protège contre :</b> {html.escape(h["protege_contre"])}.<br>'
            f'<b>Pourquoi :</b> {html.escape(" ; ".join(h["pourquoi"]))}.<br>'
            f'<b>Proposition :</b> {h["strategie"]} sur <b>{h["sous_jacent"]}</b> ({legs_txt}, échéance '
            f'{h["echeance"]} j) — <b>{h["contrats"]} contrat(s)</b>, soit {h["ratio_effectif"]:.0%} de '
            f'l\'exposition couverte (cible {h["ratio"]:.0%}).<br>'
            f'<b>Coût :</b> {_fmt_money(h["cout"])} $ ({h["cout_pct"]:.2%} de l\'actif net) · '
            f'<b>si {h["sous_jacent"]} baisse de {abs(h["choc"]):.0%} :</b> perte sans couverture '
            f'{_fmt_money(h["perte_sans"])} $ → avec couverture {_fmt_money(h["perte_avec"])} $'
            + ("" if h["contrats"] else
               f'<br><span style="color:#f59e0b">Exposition trop faible pour un contrat '
               f'(1 contrat ≈ {_fmt_money(h["valeur_contrat"])} $ de nominal).</span>')
            + '</div></div>', unsafe_allow_html=True)
        ok = st.checkbox(f"Inclure la couverture « {h['panier']} »", key=f"hf_hedge_{h['cle']}",
                         value=bool(h["recommandee"] and h["contrats"] > 0),
                         disabled=h["contrats"] <= 0)
        if ok and h["contrats"] > 0:
            accepted.append(h["cle"])
    chosen = [h for h in hedges if h["cle"] in accepted]
    if chosen:
        tot_cost = sum(h["cout"] for h in chosen)
        tbl = pd.DataFrame([{
            "Couverture": f'{h["panier"]} ({h["sous_jacent"]})', "Scénario": f'{h["sous_jacent"]} {h["choc"]:+.0%}',
            "Perte sans couverture": h["perte_sans"], "Gain des options": h["gain_couverture"],
            "Coût": -h["cout"], "Perte avec couverture": h["perte_avec"]} for h in chosen])
        st.markdown(f"**Effet des couvertures retenues** — coût total {_fmt_money(tot_cost)} $ "
                    f"(assurance payée d'avance, perdue si le marché ne baisse pas)")
        st.dataframe(tbl.style.format({c: "{:,.0f} $" for c in tbl.columns if c not in ("Couverture", "Scénario")}),
                     use_container_width=True, hide_index=True)
    else:
        st.caption("Aucune couverture retenue : le portefeuille restera entièrement exposé aux baisses de marché.")
    if not options_ok:
        st.warning("🔒 Votre profil investisseur n'autorise pas encore les options : les couvertures seront "
                   "bloquées par la conformité (règle O01). Passez le test dans Trading Desk → « Mon profil investisseur ».")
    return accepted


def _render_execution(final: pd.Series, allowed: bool, data_sim: bool, macro, profile: str,
                      intensity: float, capital: float):
    from utils.data import get_or_init_state, persist, get_multi_prices
    from utils.auto_portfolio import plan_orders, execute_orders
    from utils import hedging as H
    from utils.compliance import get_profile

    state = get_or_init_state()
    teams = state.setdefault("teams", {})
    weights = _desk_weights(final)
    vix = (macro.indicators or {}).get("vix")

    st.markdown("##### 🎯 Exécution de la proposition")
    dests = ["🆕 Créer un nouveau portefeuille", "✏️ Modifier un portefeuille existant",
             "📒 Journal uniquement (sans exécution)"]
    dest = st.radio("Que faire de cette proposition ?", dests, key="hf_dest", horizontal=True)

    port, port_label, mode, pct, new_cfg = None, "", "cash", 1.0, {}
    projected, nav = {}, float(capital)
    if dest == dests[0]:
        c1, c2, c3 = st.columns([2, 1, 1.5])
        name = c1.text_input("Nom du nouveau portefeuille",
                             value=f"Desk {profile} — {datetime.now():%d/%m/%Y}", key="hf_new_name")
        emoji = c2.selectbox("Icône", _EMOJIS, key="hf_new_emoji")
        team_opts = {tid: f'{t.get("emoji", "🏢")} {t.get("name", tid)}' for tid, t in teams.items()}
        team_opts.setdefault("__solo__", "👤 Solo")
        team_opts["__new__"] = "➕ Nouvelle équipe…"
        default_team = st.session_state.get("active_team")
        keys = list(team_opts)
        tid = c3.selectbox("Équipe", keys, format_func=lambda k: team_opts[k],
                           index=keys.index(default_team) if default_team in keys else 0, key="hf_new_team")
        new_team = None
        if tid == "__new__":
            t1, t2 = st.columns([3, 1])
            new_team = dict(name=t1.text_input("Nom de la nouvelle équipe", value="Équipe Desk",
                                               key="hf_new_team_name").strip() or "Équipe Desk",
                            emoji=t2.selectbox("Emblème", ["🦅", "🐂", "🐻", "🐋", "🦈", "🐺", "⚡", "🦁"],
                                               key="hf_new_team_emoji"))
            st.caption("Créer une autre équipe permet de comparer des portefeuilles construits avec des "
                       "approches différentes (Dashboard → Performance comparée, regroupement par équipe).")
        new_cfg = dict(name=name.strip() or f"Desk {profile}", emoji=emoji, tid=tid, new_team=new_team)
        port_label = f"{emoji} {new_cfg['name']}"
        projected = {t: w * capital for t, w in weights.items() if t != "BIL"}
        st.caption(f"Le portefeuille sera créé avec {_fmt_money(capital)} $ (champ « Capital » ci-dessus), "
                   "investi selon l'allocation finale du desk ; la poche monétaire reste en liquidités.")
    elif dest == dests[1]:
        ports = {(t_id, pid): (f'{p.get("emoji", "📁")} {p["name"]} · {teams[t_id].get("name", "Solo")}', p)
                 for t_id, team in teams.items() for pid, p in team.get("portfolios", {}).items() if p.get("name")}
        if not ports:
            st.info("Aucun portefeuille existant : choisissez « Créer un nouveau portefeuille ».")
            return
        keys = list(ports)
        active = (st.session_state.get("active_team"), st.session_state.get("active_portfolio"))
        sel = st.selectbox("Portefeuille à modifier", keys, format_func=lambda k: ports[k][0],
                           index=keys.index(active) if active in keys else 0, key="hf_mod_port")
        port_label, port = ports[sel]
        c1, c2 = st.columns([2, 1])
        m = c1.radio("Mode", ["Investir uniquement le cash disponible",
                              "Rééquilibrer tout le portefeuille vers l'allocation du desk"], key="hf_mod_mode")
        mode = "cash" if m.startswith("Investir") else "full"
        pct = c2.slider("Part à investir", 0.1, 1.0, 0.9, 0.05, key="hf_mod_pct")
        live = get_multi_prices(tuple(sorted(set(weights.index) | set(port.get("holdings", {})))))
        orders = plan_orders(port, weights, live, pct, mode)
        current = {t: h.get("qty", 0) * live.get(t, (h.get("avg_price", 0), 0))[0]
                   for t, h in port.get("holdings", {}).items()}
        nav = float(port.get("cash", 0)) + sum(current.values())
        projected = dict(current)
        for _, o in orders.iterrows():
            projected[o["ticker"]] = projected.get(o["ticker"], 0.0) + (o["montant"] if o["action"] == "BUY"
                                                                       else -o["montant"])
        if orders.empty:
            st.info("Aucun ordre spot nécessaire (cash insuffisant ou portefeuille déjà aligné) — "
                    "vous pouvez tout de même ajouter des couvertures.")
        else:
            st.dataframe(orders.style.format({"qty": "{:,.4f}", "price": "{:,.2f}", "montant": "{:,.0f}"}),
                         use_container_width=True, hide_index=True)
        if mode == "full":
            st.warning("Le rééquilibrage complet vend les lignes qui ne font pas partie de l'allocation du desk.")

    # ── Couvertures par dérivés ───────────────────────────────────────────────
    accepted, hedges = [], []
    if dest != dests[2]:
        st.markdown("##### 🛡️ Couvertures par produits dérivés")
        st.caption("Le desk ne s'arrête pas aux actifs : pour chaque exposition importante, il propose une option "
                   "qui compense une baisse du marché concerné (Nasdaq, S&P 500, Europe, émergents, énergie, "
                   "matières premières, taux). Ce sont des recommandations : c'est vous qui décidez, selon votre "
                   "tolérance au risque, de les garder ou de les retirer.")
        hedges = H.propose_hedges(H.exposures_from_values(projected), macro.factors, vix, nav)
        accepted = _hedge_cards(hedges, get_profile().get("options_ok", False))

    # ── Validation par le comité virtuel (bloquante) ──────────────────────────
    executing = dest != dests[2]
    committee_rev, ips = None, None
    if executing:
        from utils import committee as CM
        from components.committee_ui import render_ips_form, ips_summary, render_review, render_personas
        st.markdown("##### 🧑‍⚖️ Validation par le comité MAM")
        if dest == dests[0]:
            ips = st.session_state.get("hf_ips") or CM.default_ips(profile)
            if st.session_state.get("hf_ips_profile") != profile and not st.session_state.get("hf_ips_custom"):
                ips = CM.default_ips(profile)
            st.session_state["hf_ips"], st.session_state["hf_ips_profile"] = ips, profile
        else:
            ips = (port or {}).get("ips") or CM.default_ips(profile)
        st.markdown("**Politique d'investissement :** " + ips_summary(ips)
                    + ("" if dest == dests[0] or (port or {}).get("ips") else " _(par défaut : ce portefeuille n'a pas encore de politique)_"))
        with st.expander("✏️ Adapter la politique d'investissement (horizon, perte maximale, exclusions…)"):
            new_ips = render_ips_form("hf_ips_form", ips)
            if new_ips:
                if dest == dests[0]:
                    st.session_state["hf_ips"], st.session_state["hf_ips_custom"] = new_ips, True
                else:
                    port["ips"] = new_ips
                    from utils.data import persist
                    persist()
                st.rerun()
        cash_proj = nav - sum(v for v in projected.values() if v > 0)
        committee_rev = CM.review_portfolio(
            projected, max(cash_proj, 0.0), ips, dict(px=None, macro=macro, cov=A.class_covariance(A.load_prices()[0]),
                                                     data_sim=data_sim, vix=vix),
            options=(port or {}).get("options", []) if dest == dests[1] else [],
            options_ok=get_profile().get("options_ok", False), label=port_label,
            hedges=[h for h in (hedges or []) if h["cle"] in accepted])
        render_review(committee_rev)
        with st.expander("🏛️ Comité de gestion MIP — l'équipe du desk"):
            render_personas()
        if committee_rev["verdict"] == "veto":
            st.error("⛔ Le comité oppose son veto : exécution impossible. Baissez l'intensité tactique, changez de "
                     "profil, ajoutez des couvertures ou adaptez la politique d'investissement.")

    st.markdown("##### Validation humaine")
    note = st.text_input("Commentaire (facultatif)", key="hf_note")
    confirm = True
    if executing:
        confirm = st.checkbox(f"Je confirme l'exécution simulée dans « {port_label} »"
                              + (f" avec {len(accepted)} couverture(s)" if accepted else " sans couverture")
                              + " — chaque ordre est contrôlé par la conformité", key="hf_confirm")
    entry = dict(date=datetime.now().isoformat(timespec="seconds"), profil=profile,
                 regime=macro.regime, intensite=intensity, capital=capital,
                 facteurs={k: round(v, 2) for k, v in macro.factors.items()},
                 allocation={c: round(float(w), 4) for c, w in final.items() if w > 0.0005},
                 donnees_simulees=data_sim, commentaire=note,
                 destination=dest, portefeuille=port_label, couvertures=accepted)
    b1, b2, b3 = st.columns([1.3, 1, 1.2])
    label = "✅ Valider et exécuter" if executing else "✅ Valider la proposition"
    vetoed = bool(committee_rev and committee_rev["verdict"] == "veto")
    if b1.button(label, key="hf_ok", disabled=executing and (not confirm or vetoed)):
        if not executing:
            msg = A.append_journal(entry | dict(decision="validée"))
            st.success("Proposition validée et inscrite au journal.")
            if msg:
                st.warning(msg)
        elif not allowed:
            A.append_journal(entry | dict(decision="validée — exécution bloquée (données simulées)"))
            st.error("⛔ Exécution bloquée par le moteur de risque : données de marché simulées. "
                     "La proposition est inscrite au journal.")
        else:
            entry["comite"] = committee_rev["verdict"] if committee_rev else None
            _execute(dest == dests[0], new_cfg, port, weights, mode, pct, accepted, macro, vix, entry, teams,
                     ips=ips, committee_rev=committee_rev)
    if b2.button("❌ Rejeter", key="hf_ko"):
        msg = A.append_journal(entry | dict(decision="rejetée"))
        st.info("Proposition rejetée et inscrite au journal.")
        if msg:
            st.warning(msg)
    orders_csv = pd.DataFrame({"Classe": final.index, "Proxy": [A.CLASS_PROXY[c] for c in final.index],
                               "Poids": final.round(4).values, "Montant": (final * capital).round(2).values})
    b3.download_button("⬇️ Ordres (CSV)", orders_csv.to_csv(index=False).encode("utf-8"),
                       f"ordres_desk_{datetime.now():%Y%m%d}.csv", "text/csv", key="hf_csv")


def _execute(is_new: bool, new_cfg: dict, port: dict | None, weights: pd.Series, mode: str, pct: float,
             accepted: list[str], macro, vix, entry: dict, teams: dict, ips: dict | None = None,
             committee_rev: dict | None = None):
    import uuid
    from utils.data import persist, get_multi_prices
    from utils.auto_portfolio import plan_orders, execute_orders
    from utils import hedging as H

    if is_new:
        tid = new_cfg["tid"]
        if tid == "__new__":
            tid = "T" + uuid.uuid4().hex[:6].upper()
            nt = new_cfg.get("new_team") or {}
            teams[tid] = {"id": tid, "name": nt.get("name", "Équipe Desk"), "emoji": nt.get("emoji", "🦅"),
                          "portfolios": {}}
        if tid not in teams:
            teams[tid] = {"id": tid, "name": "Solo", "emoji": "👤", "portfolios": {}}
        pid = "P" + uuid.uuid4().hex[:6].upper()
        cap = float(entry["capital"])
        port = {"id": pid, "name": new_cfg["name"], "emoji": new_cfg["emoji"], "strategy": "Global Macro",
                "portfolio_type": "Libre", "asset_types": [], "cash": cap, "initial_cash": cap,
                "holdings": {}, "trades": [], "history": [], "options": [],
                "created": datetime.now().isoformat(timespec="seconds"), "source": "Hedge Fund Agent"}
        teams[tid]["portfolios"][pid] = port
        st.session_state["_select_portfolio"] = (tid, pid)
        mode, pct = "cash", 1.0
        from components.committee_followup import mark_pending
        mark_pending(port, "création (Hedge Fund Agent)")
    if ips:
        port["ips"] = ips
    if committee_rev:
        from utils.committee import summary_for_storage
        port["committee"] = summary_for_storage(committee_rev)
    live = get_multi_prices(tuple(sorted(set(weights.index) | set(port.get("holdings", {})))))
    orders = plan_orders(port, weights, live, pct, mode)
    n_before = len(port.get("trades", []) or [])
    errs = execute_orders(port, orders, tag="Hedge Fund Agent") if not orders.empty else []

    # Couvertures recalculées sur le portefeuille réellement obtenu
    hedge_errs, done = [], []
    if accepted:
        hold = port.get("holdings", {})
        live2 = get_multi_prices(tuple(sorted(hold)))
        vals = {t: h.get("qty", 0) * live2.get(t, (h.get("avg_price", 0), 0))[0] for t, h in hold.items()}
        nav = port.get("cash", 0.0) + sum(vals.values())
        for h in H.propose_hedges(H.exposures_from_values(vals), macro.factors, vix, nav):
            if h["cle"] in accepted:
                e = H.execute_hedge(port, h)
                (hedge_errs.append(e) if e else done.append(h.get("ajustement")
                                                             or f'{h["panier"]} ({h["contrats"]} × {h["sous_jacent"]})'))
    persist()
    msg = A.append_journal(entry | dict(decision="validée et exécutée", couvertures_executees=done,
                                        ordres=len(orders), refus=errs + hedge_errs))
    try:  # journal des écarts recommandation / exécution (v5.4)
        from utils.execution_log import record_execution
        record_execution(port, "Hedge Fund Agent", orders, n_before, errs + hedge_errs,
                         target_weights=weights, hedges_done=done)
    except Exception:
        pass
    st.success(f"✅ {'Portefeuille créé' if is_new else 'Portefeuille modifié'} : {entry['portefeuille']} — "
               f"{len(orders) - len(errs)} ordre(s) spot"
               + (f", couvertures : {', '.join(done)}" if done else ", aucune couverture") + ".")
    if errs or hedge_errs:
        st.warning("Certains ordres ont été bloqués par la conformité :\n\n- " + "\n- ".join(errs + hedge_errs))
    if msg:
        st.warning(msg)
    if is_new:
        st.info("Le nouveau portefeuille est sélectionné dans la barre du haut dès le prochain affichage "
                "(cliquez sur n'importe quel onglet) ; ses positions et couvertures sont visibles dans le "
                "Trading Desk et le Dashboard.")


def _gap_journal(j: list):
    """Écarts entre recommandation et exécution, puis dérive depuis l'exécution (v5.4)."""
    from utils import execution_log as EL
    ex = EL.executions(j)
    st.markdown("##### 🔍 Écarts entre recommandation et exécution")
    if not ex:
        st.caption("Aucune exécution de plan enregistrée pour l'instant : chaque plan exécuté depuis le Hedge Fund "
                   "Agent, l'optimisation du comité ou Auto-Portefeuille apparaîtra ici.")
        return
    summ = pd.DataFrame([dict(Date=e.get("date"), Portefeuille=e.get("portefeuille"), Source=e.get("source"),
                              Recommandé=e.get("montant_recommande", 0.0), Exécuté=e.get("montant_execute", 0.0),
                              **{"Taux d'exécution": e.get("taux_execution", 1.0), "Bloqués": e.get("n_bloques", 0)})
                         for e in ex]).iloc[::-1]
    st.dataframe(summ.style.format({"Recommandé": "${:,.0f}", "Exécuté": "${:,.0f}", "Taux d'exécution": "{:.0%}"}),
                 use_container_width=True, hide_index=True)
    pick = st.selectbox("Détail d'une exécution", range(len(ex)), index=len(ex) - 1, key="hf_gap_pick",
                        format_func=lambda i: f"{ex[i].get('date')} · {ex[i].get('portefeuille')} · {ex[i].get('source')}")
    e = ex[pick]
    lines = pd.DataFrame(e.get("lignes") or [])
    if not lines.empty:
        show = pd.DataFrame({"Ticker": lines["ticker"], "Sens": lines["action"].map({"BUY": "Achat", "SELL": "Vente"}),
                             "Qté recommandée": lines["qty_reco"], "Qté exécutée": lines["qty_exec"],
                             "Montant recommandé": lines["montant_reco"], "Montant exécuté": lines["montant_exec"],
                             "Écart": lines["ecart_montant"], "Statut": lines["statut"], "Raison": lines["raison"]})
        st.dataframe(show.style.format({"Qté recommandée": "{:,.4f}", "Qté exécutée": "{:,.4f}",
                                        "Montant recommandé": "${:,.0f}", "Montant exécuté": "${:,.0f}",
                                        "Écart": "${:+,.0f}"}), use_container_width=True, hide_index=True)
    if e.get("couvertures"):
        st.caption("Couvertures exécutées : " + ", ".join(map(str, e["couvertures"])))
    # Suivi : dérive de la composition depuis l'exécution
    from utils.data import get_or_init_state, get_multi_prices
    state = get_or_init_state()
    port = next((p for t in state.get("teams", {}).values() for pid, p in t.get("portfolios", {}).items()
                 if pid == e.get("portefeuille_id") or p.get("id") == e.get("portefeuille_id")), None)
    if port is None:
        st.caption("Portefeuille introuvable (supprimé ou appartenant à un autre compte) : suivi impossible.")
        return
    live = get_multi_prices(tuple(sorted(set(port.get("holdings", {})) | set(e.get("cible") or {}))))
    df, drift = EL.follow_up(e, port, live)
    if df.empty:
        return
    c1, c2 = st.columns([1, 3])
    c1.metric("Dérive depuis l'exécution", f"{drift:.1%}", help="Part du portefeuille à déplacer pour revenir à la "
              "composition visée lors de l'exécution (marchés, ordres manuels, ordres bloqués).")
    with c2:
        st.dataframe(df.head(12).style.format("{:+.1%}", subset=["Écart"]).format("{:.1%}", subset=["Cible", "Actuel"]),
                     use_container_width=True)


def render():
    _reset_pkeys()
    st.markdown(_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="hf-card"><div class="hf-title">🦅 HEDGE FUND AGENT</div>'
        '<div class="hf-sub">Un desk multi-rôles : chaque rôle fait un seul travail sur les mêmes données, '
        'un moteur de risque déterministe a le dernier mot, et rien n\'est exécuté sans votre validation.</div>'
        '<div style="margin-top:8px">'
        + "".join(f'<span class="hf-role">{r}</span>' for r in
                  ["🌦️ Taux-Bas · Macro & Régimes", "🧮 Algo-Rithme · Signaux & ML",
                   "🏛️ Balancement · Ordres & Stratégie", "🛡️ De Marge · Garde-fou & Limites (veto)",
                   "⚖️ Probité · Conformité (veto)", "🎙️ Eting-Financier · Reporting & Biais",
                   "✅ Vous · Décision finale"])
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

    t1, t5, t2, t3, t4, t6 = st.tabs(["🛰️ BRIEFING", f"🔔 ALERTES ({n_hot})", "🎯 ALLOCATION DU DESK",
                                      "🩺 CONSEILS PORTEFEUILLE", "📒 JOURNAL", "🧪 CALIBRATION & BACKTEST"])

    # ── Calibration des hypothèses sur l'historique (v5.4) ───────────────────
    with t6:
        from components import calibration_ui
        calibration_ui.render()

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
        try:
            from utils.calibration import sensitivity_source
            st.caption(f"Matrice de sensibilité utilisée : {sensitivity_source()} — détails dans l'onglet Calibration.")
        except Exception:
            pass
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
        st.caption("Intensité = place du sujet dans l'actualité · tonalité = bonne ou mauvaise nouvelle pour les "
                   "marchés (lexique financier français / anglais, de −1 à +1). ● vert : titre positif · "
                   "● rouge : négatif · ● gris : neutre.")
        themes = sorted(news.items(), key=lambda kv: -kv[1]["intensity"])
        cols = st.columns(3)

        def _dot(v):
            c_ = GREEN if v is not None and v > 0.05 else (RED if v is not None and v < -0.05 else "#64748b")
            return f'<span style="color:{c_}">●</span> '

        for i, (k, th) in enumerate(themes):
            with cols[i % 3]:
                lvl = th["intensity"]
                color = RED if lvl >= 60 else ("#f59e0b" if lvl >= 35 else GREEN)
                sen = th.get("sentiment") or {}
                tone = ""
                if sen.get("n"):
                    tc = GREEN if sen["score"] >= 0.15 else (RED if sen["score"] <= -0.15 else "#94a3b8")
                    tone = (f'<div class="hf-sub">Tonalité : <b style="color:{tc}">{html.escape(sen["libelle"])} '
                            f'({sen["score"]:+.2f})</b> · {sen["positifs"]} positif(s), {sen["negatifs"]} négatif(s) '
                            f'sur {sen["n"]} titres</div>')
                heads = "".join(
                    f'<div>{_dot(h.get("tonalite"))}<a href="{html.escape(h["link"])}" target="_blank">'
                    f'{html.escape(h["title"][:110])}</a> <small>{h["date"]:%d/%m}</small></div>'
                    for h in th["headlines"][:3])
                st.markdown(
                    f'<div class="hf-card hf-news"><div class="hf-title" style="font-size:.9rem">'
                    f'{html.escape(th["label"])} <span style="color:{color}">{lvl:.0f}/100</span></div>'
                    f'{tone}{heads or "<small>Aucun titre récent</small>"}</div>', unsafe_allow_html=True)
        try:
            from utils.sentiment import class_sentiment
            cs = class_sentiment(news)
        except Exception:
            cs = {}
        if cs:
            st.markdown("##### Tonalité de l'actualité par classe d'actifs")
            rows = [{"Classe d'actifs": c, "Tonalité": v["score"], "Lecture": v["libelle"], "Titres": v["n"],
                     "Exemple négatif": (v["exemples_neg"] or [""])[0][:90],
                     "Exemple positif": (v["exemples_pos"] or [""])[0][:90]}
                    for c, v in sorted(cs.items(), key=lambda kv: kv[1]["score"])]
            st.dataframe(pd.DataFrame(rows).style.format({"Tonalité": "{:+.2f}"}), use_container_width=True,
                         hide_index=True)
            st.caption("Chaque titre est rattaché aux classes qu'il mentionne (mots-clés) ; tonalité moyenne pondérée "
                       "par la fraîcheur. Indicateur d'ambiance, à croiser avec les facteurs : un lexique ne "
                       "comprend ni l'ironie ni le contexte long.")

    # ── 2. Allocation du desk ─────────────────────────────────────────────────
    with t2:
        c1, c2, c3 = st.columns([1, 1, 1])
        from components.committee_ui import active_profile
        _ips_prof, _ips_origin = active_profile()
        _pl = list(A.PROFILES)
        profile = c1.selectbox("Profil", _pl, index=_pl.index(_ips_prof) if _ips_prof in _pl else 1, key="hf_profile",
                               help=f"Par défaut : {_ips_prof} ({_ips_origin}).")
        intensity = c2.slider("Intensité tactique", 0.0, 1.0, 0.5, 0.1, key="hf_int",
                              help="0 = allocation stratégique pure ; 1 = inclinaisons macro maximales")
        capital = c3.number_input("Capital (simulation)", 1_000, 100_000_000, 1_000_000, 10_000, key="hf_cap",
                                  help="Capital d'un nouveau portefeuille créé par le desk. Les options sur ETF portent sur 100 titres : sous ~200 000 $, les couvertures risquent d'être trop petites pour un contrat.")

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

        _render_execution(final, allowed, data_sim, macro, profile, intensity, capital)

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
        from components.committee_ui import active_profile
        _p2, _o2 = active_profile()
        _pl2 = list(A.PROFILES)
        prof2 = c2.selectbox("Profil de risque", _pl2, index=_pl2.index(_p2) if _p2 in _pl2 else 1, key="hf_prof2",
                             help=f"Par défaut : {_p2} ({_o2}).")
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
            _gap_journal(j)
            st.download_button("⬇️ Exporter le journal (JSON)",
                               json.dumps(j, ensure_ascii=False, indent=1, default=str).encode("utf-8"),
                               "journal_hedge_fund.json", "application/json", key="hf_jdl")
        if A.journal_backend() != "Supabase":
            st.caption("Supabase non configuré : le fichier local est effacé au redémarrage de "
                       "Streamlit Cloud. Ajoutez la section [supabase] aux secrets.")
