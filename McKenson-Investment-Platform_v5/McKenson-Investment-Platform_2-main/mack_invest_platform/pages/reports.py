# pages/reports.py  —  MAM v5 · Rapports PDF & images de performance
from __future__ import annotations

import pandas as pd
import streamlit as st

from components.ai_shared import all_portfolios, kpi, kpi_row, page_header
from components.ui import section_title


@st.cache_data(ttl=1800, show_spinner=False)
def _history(tickers: tuple):
    from utils.market_intel import fetch_prices
    return fetch_prices(tickers, "1y")


def _simple_box(simple: dict | None):
    """Encadré « En bref » : la performance et sa cause, en mots simples."""
    if not simple or not simple.get("phrases"):
        return
    import html as _h
    import re
    items = "".join("<li style='margin:3px 0'>" + re.sub(r"\*\*(.+?)\*\*", r"<b style='color:#e2e8f0'>\1</b>",
                                                          _h.escape(p)) + "</li>" for p in simple["phrases"])
    st.markdown('<div style="border-left:3px solid #00ff88;background:rgba(0,255,136,.05);border-radius:6px;'
                'padding:10px 16px;margin:8px 0;font-family:Share Tech Mono;font-size:.76rem;color:#cbd5e1;'
                'line-height:1.6"><div style="font-family:Rajdhani;font-size:.8rem;letter-spacing:.12em;color:#00ff88">'
                f'🗣️ EN BREF — VOTRE PORTEFEUILLE EN MOTS SIMPLES</div><ul style="margin:6px 0 0;padding-left:18px">'
                f'{items}</ul></div>', unsafe_allow_html=True)


def render():
    from utils import reporting as R
    from utils.data import get_multi_prices
    from utils.report_builders import portfolio_context, portfolio_images, portfolio_pdf

    page_header("📄 RAPPORTS", "Rapports PDF et images de performance de vos portefeuilles", "#ffd700")
    ports = all_portfolios()
    if not ports:
        st.info("Aucun portefeuille à analyser — créez-en un depuis le Dashboard.")
        return
    keys = list(ports)
    active = st.session_state.get("active_portfolio")
    c1, c2, c3 = st.columns([2, 1.2, 1])
    with c1:
        pid = st.selectbox("Portefeuille", keys, index=keys.index(active) if active in keys else 0,
                           format_func=lambda k: ports[k][0], key="rep_port")
    with c2:
        theme = st.radio("Thème des images", ["Clair", "Sombre"], horizontal=True, key="rep_theme")
    with c3:
        with_ml = st.checkbox("Inclure l'avis du modèle ML", value=True, key="rep_ml",
                              help="Utilise les signaux de la page IA Marchés (entraînement mis en cache)")
    port = ports[pid][1]
    holdings = tuple(sorted((port.get("holdings") or {}).keys()))

    _committee_report(pid, port)
    st.markdown("<br>", unsafe_allow_html=True)
    _investor_report(pid, port)
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("RAPPORT DE PERFORMANCE DÉTAILLÉ", "📊")

    if st.button("🧾 Générer le rapport", use_container_width=True, key="rep_go"):
        with st.spinner("Valorisation, historiques et graphiques…"):
            live = get_multi_prices(tuple(sorted(set(holdings) | {"SPY"}))) if holdings else {}
            hist, src = _history(tuple(sorted(set(holdings) | {"SPY"}))) if holdings else (pd.DataFrame(), "—")
            signals = None
            if with_ml and holdings:
                try:
                    from components.ai_shared import load_intel
                    intel = load_intel()
                    if intel["res"].get("ok"):
                        signals = intel["res"]["signals"]
                except Exception:
                    signals = None
            ctx = portfolio_context(port, live, hist, signals)
            th = "light" if theme == "Clair" else "dark"
            imgs = portfolio_images(ctx, th)
            ctx["images"] = imgs if th == "light" else portfolio_images(ctx, "light")
            pdf = portfolio_pdf(ctx)
        st.session_state["rep_out"] = {"pid": pid, "ctx": ctx, "imgs": imgs, "pdf": pdf, "src": src, "theme": th}

    out = st.session_state.get("rep_out")
    if not out or out["pid"] != pid:
        st.caption("Le rapport contient : positions et P&L, performance simulée des positions actuelles sur 1 an vs "
                   "S&P 500, drawdowns, rendements mensuels, stress tests, projection Monte Carlo, avis ML et "
                   "derniers ordres.")
        return
    ctx = out["ctx"]
    _simple_box(ctx.get("simple"))
    if out["src"] == "simulé":
        st.warning("⚠️ Historiques Yahoo Finance indisponibles : les courbes de performance utilisent des données simulées.")
    m = ctx.get("metrics", {})
    init = float(port.get("initial_cash", ctx["nav"]) or ctx["nav"])
    from utils.performance import since_inception
    _r0 = since_inception(port, ctx["nav"])[0]
    kpi_row([
        kpi("Valeur totale", f"{ctx['nav']:,.0f} $"),
        kpi("Depuis l'origine (TWR)", f"{_r0:+.2%}" if _r0 == _r0 else "—",
            color="#00ff88" if _r0 == _r0 and _r0 >= 0 else "#ff3b6b"),
        kpi("Positions", str(len(ctx["pos"]))),
        kpi("Volatilité 1 an (simulée)", f"{m['Volatilité']:.1%}" if m else "—"),
        kpi("Drawdown max 1 an", f"{m['Drawdown max']:.1%}" if m else "—", color="#ff3b6b"),
    ])
    c1, c2 = st.columns(2)
    with c1:
        st.download_button("⬇️ Télécharger le PDF", out["pdf"],
                           file_name=f"MAM_rapport_{port.get('name', 'portefeuille').replace(' ', '_')}_{pd.Timestamp.today():%Y%m%d}.pdf",
                           mime="application/pdf", use_container_width=True, key="rep_dl_pdf")
    with c2:
        if out["imgs"]:
            st.download_button("⬇️ Toutes les images (.zip)", R.zip_images(out["imgs"]),
                               file_name=f"MAM_images_{port.get('name', 'portefeuille').replace(' ', '_')}.zip",
                               mime="application/zip", use_container_width=True, key="rep_dl_zip")
    if ctx["pos"].empty:
        st.info("Portefeuille sans position : le PDF ne contient que le récapitulatif.")
        return
    section_title("APERÇU DES IMAGES", "🖼️")
    names = list(out["imgs"])
    cols = st.columns(2)
    for i, n in enumerate(names):
        with cols[i % 2]:
            st.image(out["imgs"][n], use_container_width=True)
            st.download_button(f"⬇️ {n}.png", out["imgs"][n], file_name=f"{n}.png", mime="image/png",
                               key=f"rep_img_{n}")


# ══════════════════════════════════════════════════════════════════════════════
#  RAPPORT DU COMITÉ (PNG une page + PDF complet) — envoi et suivi hebdomadaire
# ══════════════════════════════════════════════════════════════════════════════
def _committee_report(pid: str, port: dict):
    from components.committee_ui import get_context, inject_css, render_review
    from utils import alerts as AL
    from utils import advisor as A
    from utils.committee_report import build_for_portfolio
    from utils.compliance import get_profile
    from utils.data import get_multi_prices, persist
    from utils.committee import summary_for_storage, constraints, default_ips
    from utils.performance import BENCHMARKS

    inject_css()
    section_title("RAPPORT DU COMITÉ D'INVESTISSEMENT", "🧑‍⚖️")
    st.caption("Le rapport que reçoit l'investisseur : graphique portefeuille vs marché, avis motivé de chacun des "
               "six professionnels virtuels, synthèse et recommandations de Marc ETING-FINANCIER, décisions à prendre. "
               "PNG d'une page (e-mail du lundi) + PDF détaillé (risques selon les méthodes de John Hull).")
    c1, c2 = st.columns([1, 1])
    bench = c1.selectbox("Indice de référence", list(BENCHMARKS), key="crep_bench")
    if c2.button("🧑‍⚖️ Générer le rapport du comité", key="crep_go", use_container_width=True, type="primary"):
        with st.spinner("Le comité se réunit et rédige le rapport…"):
            hold = tuple(sorted((port.get("holdings") or {}).keys()))
            live = get_multi_prices(hold) if hold else {}
            out = build_for_portfolio(port, get_context(), live, get_profile().get("options_ok", False), bench,
                                      get_profile().get("risque", "Équilibré"))
        port["committee"] = summary_for_storage(out["review"])
        persist()
        st.session_state["crep_out"] = dict(pid=pid, **out)
    out = st.session_state.get("crep_out")
    if not out or out["pid"] != pid:
        return
    fname = f"MAM_comite_{port.get('name', 'portefeuille').replace(' ', '_')}_{pd.Timestamp.today():%Y%m%d}"
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Rapport du comité (PDF)", out["pdf"], f"{fname}.pdf", "application/pdf",
                       use_container_width=True, key="crep_pdf")
    d2.download_button("⬇️ Rapport hebdomadaire (PNG)", out["png"], f"{fname}.png", "image/png",
                       use_container_width=True, key="crep_png")
    _simple_box(out["review"].get("synthese_simple"))
    render_review(out["review"])
    with st.expander("🖼️ Aperçu du rapport hebdomadaire (PNG)"):
        st.image(out["png"], use_container_width=True)

    st.markdown("##### 📬 Envoi et rapport automatique du lundi")
    user = A.current_user_key()
    from utils.notifier import recipients as _rcpts
    from utils.alerts import parse_recipients
    default_mail = ", ".join(_rcpts()) or (user if "@" in user else "")
    e1, e2 = st.columns([2, 1])
    to = e1.text_input("Adresse(s) de réception — plusieurs adresses séparées par des virgules",
                       value=default_mail, key="crep_to")
    if e2.button("📧 Envoyer maintenant", key="crep_send", use_container_width=True) and parse_recipients(to):
        err = AL.send_email(to, f"🧑‍⚖️ Rapport du comité MAM — {port.get('name')} — {pd.Timestamp.today():%d/%m/%Y}",
                            out["html"], [(f"{fname}.png", out["png"], "image/png"),
                                          (f"{fname}.pdf", out["pdf"], "application/pdf")])
        st.success("Rapport envoyé.") if not err else st.error(f"Envoi impossible : {err}")
    if A.journal_backend() != "Supabase":
        st.info("Le rapport automatique du lundi nécessite la base Supabase.")
        return
    subs = {s["portfolio_name"]: s for s in AL.subscriptions(user)}
    cur = subs.get(port.get("name"))
    if st.button(("🔁 Mettre à jour le suivi" if cur else "📬 Recevoir ce rapport chaque lundi"), key="crep_sub"):
        if not parse_recipients(to):
            st.error("Adresse e-mail invalide.")
        else:
            vals = {t: h.get("qty", 0) * h.get("avg_price", 0) for t, h in (port.get("holdings") or {}).items()}
            vals["CASH"] = port.get("cash", 0.0)
            prof = constraints(port.get("ips") or default_ips(get_profile().get("risque", "Équilibré")))["profil"]
            ok = AL.subscribe(user, ", ".join(parse_recipients(to)), port.get("name"), prof, vals, True, True,
                              "important")
            st.success(f"C'est noté : le comité examinera « {port.get('name')} » chaque lundi et vous enverra son "
                       "rapport (PNG + PDF).") if ok else st.error("Enregistrement impossible : base injoignable.")
    if cur:
        st.caption(f"Suivi actif vers {cur.get('email')} — rapport du lundi : {'oui' if cur.get('weekly') else 'non'}.")


# ══════════════════════════════════════════════════════════════════════════════
#  RAPPORT MENSUEL INVESTISSEUR (v5.6)
# ══════════════════════════════════════════════════════════════════════════════
def _investor_report(pid: str, port: dict):
    from components.committee_ui import get_context, portfolio_values
    from utils import alerts as AL
    from utils import committee as CM
    from utils import investor_report as IR
    from utils.compliance import get_profile, normalize_port_type
    from utils.performance import BENCHMARKS

    section_title("RAPPORT MENSUEL POUR L'INVESTISSEUR", "📬")
    st.caption("Le rapport à envoyer chaque mois à l'investisseur, écrit pour quelqu'un qui n'est pas spécialiste : "
               "en bref (mieux ou moins bien que le marché, et pourquoi), décisions du mois avec leur raison et leurs "
               "dangers, ce qui a marché ou non, respect des règles, avis du comité, prochaines étapes, lexique.")
    c1, c2, c3 = st.columns([1.2, 1, 1])
    period = c1.selectbox("Période", IR.month_choices(), key="irep_period",
                          format_func=lambda x: x if x == "Mois en cours" else IR.month_bounds(x)[2].capitalize())
    bench = c2.selectbox("Indice de référence", list(BENCHMARKS), key="irep_bench")
    if c3.button("📬 Rédiger le rapport mensuel", key="irep_go", use_container_width=True, type="primary"):
        with st.spinner("Rédaction du rapport mensuel…"):
            review = None
            try:
                ctx = get_context()
                vals, cash, _ = portfolio_values(port)
                ips = port.get("ips") or CM.default_ips(get_profile().get("risque", "Équilibré"))
                review = CM.review_portfolio(vals, cash, ips, ctx, options=port.get("options", []),
                                             options_ok=get_profile().get("options_ok", False),
                                             port_type=normalize_port_type(port), label=port.get("name", ""),
                                             port=port)
            except Exception:
                review = None
            earn = None
            try:
                from utils.earnings import earnings_window, next_earnings
                earn = earnings_window(next_earnings(list((port.get("holdings") or {}).keys())), 30)
            except Exception:
                earn = None
            out = IR.build(port, period, bench, review=review, earnings=earn)
        st.session_state["irep_out"] = dict(pid=pid, **out)
    out = st.session_state.get("irep_out")
    if not out or out["pid"] != pid:
        return
    _simple_box(out["simple"])
    fname = f"MAM_rapport_mensuel_{port.get('name', 'portefeuille').replace(' ', '_')}_{out['debut']:%Y%m}"
    d1, d2, d3 = st.columns([1, 1.4, 0.8])
    d1.download_button("⬇️ Rapport mensuel (PDF)", out["pdf"], f"{fname}.pdf", "application/pdf",
                       use_container_width=True, key="irep_pdf")
    from utils.notifier import recipients as _rcpts
    from utils.alerts import parse_recipients
    to = d2.text_input("Envoyer à", value=", ".join(_rcpts()), key="irep_to", label_visibility="collapsed",
                       placeholder="adresse1@gmail.com, adresse2@gmail.com")
    if d3.button("📧 Envoyer", key="irep_send", use_container_width=True) and parse_recipients(to):
        err = AL.send_email(to, f"Rapport mensuel MAM — {port.get('name')} — {out['periode']}", out["html"],
                            [(f"{fname}.pdf", out["pdf"], "application/pdf")])
        st.success("Rapport envoyé.") if not err else st.error(f"Envoi impossible : {err}")
    st.caption(f"{len(out['journal'])} décision(s) sur la période · {len(out['derogations'])} dérogation(s).")
