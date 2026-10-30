# pages/ai_markets.py  —  MAM v5 · IA Marchés
"""
Intelligence de marché par machine learning : régime, macro, géopolitique,
actualités, signaux par actif et conseils pour le portefeuille actif.
"""
from __future__ import annotations

import html as _h

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ai_shared import (PLOT, STRAT_TO_PROFILE, active_portfolio, get_intel, kpi, kpi_row,
                                  md_bold, page_header, refresh_button, source_banner)
from components.ui import section_title
from utils.market_intel import (ASSET_CLASSES, CLASS_COLORS, IMPACT, THEMES, UNIVERSE, asset_class,
                                asset_name)
from utils.ml_engine import FEATURE_FAMILY, FEATURE_LABELS, REGIME_COLORS, REGIME_NAMES, REGIME_TEXT

_SIG_COL = {"SURPONDÉRER": "#00ff88", "RENFORCER": "#7cf0b5", "NEUTRE": "#94a3b8",
            "ALLÉGER": "#ff8c00", "SOUS-PONDÉRER": "#ff3b6b"}


def render():
    c1, c2 = st.columns([6, 1])
    with c1:
        page_header("🧠 IA MARCHÉS", "Machine learning · macro-économie · géopolitique · actualités → aide à la "
                    "décision pour la construction de portefeuille")
    with c2:
        st.markdown("<div style='padding-top:10px'></div>", unsafe_allow_html=True)
        refresh_button("ai_refresh")

    intel, news = get_intel()
    res = intel["res"]
    if not res.get("ok"):
        st.error(f"Modèle indisponible : {res.get('error', 'erreur inconnue')}")
        return
    source_banner(intel, news)

    reg, val, sig = res["regimes"], res["validation"], res["signals"]
    cur = reg["current"] if reg.get("ok") else "—"
    ms, gpr, eco = intel["macro_score"], news["gpr"], news["econ_score"]
    kpi_row([
        kpi("Régime de marché", cur, f"probabilité {reg['current_proba'][cur]:.0%}" if reg.get("ok") else "",
            REGIME_COLORS.get(cur, "#e2e8f0")),
        kpi("Score macro", f"{ms:+.0f}/100", "favorable au risque" if ms > 20 else "défavorable" if ms < -20 else "neutre",
            "#00ff88" if ms > 20 else "#ff3b6b" if ms < -20 else "#ffd700"),
        kpi("Risque géopolitique", f"{gpr:.0f}/100", "indice actualités",
            "#ff3b6b" if gpr > 55 else "#ffd700" if gpr > 25 else "#00ff88"),
        kpi("Climat économique", f"{eco:+.0f}/100", f"{news['n']} titres analysés",
            "#00ff88" if eco > 20 else "#ff3b6b" if eco < -20 else "#ffd700"),
        kpi("Fiabilité du modèle", f"AUC {val['auc']:.2f}" if val.get("ok") else "—",
            f"précision {val['accuracy']:.0%} vs {val['baseline']:.0%} naïf" if val.get("ok") else ""),
    ])
    _regime_crosscheck(cur)

    tabs = st.tabs(["🧑‍⚖️ ANALYSE DU COMITÉ", "🌍 RÉGIME & MACRO", "🛰️ GÉOPOLITIQUE & ACTUALITÉS", "🤖 SIGNAUX ML",
                    "💡 CONSEILS PORTEFEUILLE", "🔬 MODÈLE & VALIDATION"])
    with tabs[0]:   # v5.11 : analyse complète du marché (facteurs, secteurs, actualités, réseaux sociaux)
        from components.market_committee_ui import render as _committee_market
        _committee_market(news)
    with tabs[1]:
        _tab_regime(intel, reg)
    with tabs[2]:
        _tab_news(news)
    with tabs[3]:
        _tab_signals(intel, sig)
    with tabs[4]:
        _tab_advice(intel, news, sig, reg)
    with tabs[5]:
        _tab_model(val)


# ─────────────────────────────────────────────────────────────────────────────
def _tab_regime(intel, reg):
    if not reg.get("ok"):
        st.info("Historique insuffisant pour détecter les régimes.")
        return
    cur = reg["current"]
    c1, c2 = st.columns([1, 1.6])
    with c1:
        section_title("RÉGIME ACTUEL", "🧭")
        col = REGIME_COLORS.get(cur, "#00d4ff")
        st.markdown(
            f'<div style="border:1px solid {col}55;background:{col}12;border-radius:10px;padding:14px 16px;">'
            f'<div style="font-family:Rajdhani,sans-serif;font-size:1.4rem;font-weight:700;color:{col};">{cur}</div>'
            f'<div style="font-family:Share Tech Mono,monospace;font-size:.74rem;color:#cbd5e1;line-height:1.6;margin-top:6px;">'
            f'{_h.escape(REGIME_TEXT.get(cur, ""))}</div>'
            + ('<div style="margin-top:8px;font-family:Share Tech Mono,monospace;font-size:.72rem;color:#ff8c00;">'
               '🔥 Pression inflationniste détectée (taux longs + pétrole en hausse)</div>' if reg["inflation_flag"] else "")
            + '</div>', unsafe_allow_html=True)
        p = reg["current_proba"].reindex(REGIME_NAMES)
        fig = go.Figure(go.Bar(x=p.values, y=p.index, orientation="h",
                               marker_color=[REGIME_COLORS[n] for n in p.index],
                               text=[f"{v:.0%}" for v in p.values], textposition="auto"))
        fig.update_layout(**PLOT, height=220, title="Probabilités (mélange gaussien)")
        fig.update_xaxes(tickformat=".0%", range=[0, 1])
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        section_title("HISTORIQUE DES RÉGIMES", "📜")
        px = intel["prices"]["SPY"].dropna() if "SPY" in intel["prices"] else None
        if px is not None:
            lab = reg["label"].reindex(px.index).ffill()
            fig = go.Figure()
            for n in REGIME_NAMES:
                mask = lab == n
                fig.add_trace(go.Scatter(x=px.index, y=px.where(mask), mode="lines", name=n,
                                         line=dict(color=REGIME_COLORS[n], width=2), connectgaps=False))
            fig.update_layout(**PLOT, height=330, title="S&P 500 coloré par régime",
                              legend=dict(orientation="h", y=-0.15))
            st.plotly_chart(fig, use_container_width=True)
        prof = reg["profile"].copy()
        prof.columns = ["Perf. S&P 3 m", "Vol. S&P 3 m", "VIX (z)", "Crédit 3 m", "Pente courbe", "Tendance 200 j"]
        st.caption("Caractéristiques moyennes de chaque régime sur la période")
        st.dataframe(prof.style.format({"Perf. S&P 3 m": "{:+.1%}", "Vol. S&P 3 m": "{:.1%}", "VIX (z)": "{:+.2f}",
                                        "Crédit 3 m": "{:+.1%}", "Pente courbe": "{:+.2f}",
                                        "Tendance 200 j": "{:+.1%}"}, na_rep="—"),
                     use_container_width=True)

    section_title("TABLEAU DE BORD MACRO", "📊")
    rows = intel["macro_rows"]
    th = "".join(f'<th style="font-family:Rajdhani,sans-serif;font-size:.64rem;color:#00d4ff;letter-spacing:.1em;'
                 f'text-transform:uppercase;padding:8px 10px;background:rgba(0,212,255,.06);text-align:left;">{c}</th>'
                 for c in ["Indicateur", "Valeur", "Signal", "Lecture"])
    tb = ""
    for r in rows:
        v = r["valeur"]
        sc = {1: ("#00ff88", "▲ favorable"), 0: ("#ffd700", "● neutre"), -1: ("#ff3b6b", "▼ défavorable")}[r["signal"]]
        tb += (f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
               f'<td style="padding:7px 10px;color:#e2e8f0;font-family:Rajdhani,sans-serif;font-weight:700;">{r["indicateur"]}</td>'
               f'<td style="padding:7px 10px;font-family:Share Tech Mono,monospace;color:#e2e8f0;">'
               f'{r["format"].format(v) if v == v else "—"}</td>'
               f'<td style="padding:7px 10px;color:{sc[0]};font-family:Share Tech Mono,monospace;font-size:.74rem;">{sc[1]}</td>'
               f'<td style="padding:7px 10px;color:#94a3b8;font-size:.74rem;">{_h.escape(r["lecture"])}</td></tr>')
    st.markdown(f'<div class="mam-table-wrap"><table class="mam-table"><thead><tr>{th}</tr></thead>'
                f'<tbody>{tb}</tbody></table></div>', unsafe_allow_html=True)

    mac = intel["macro"].iloc[-504:]
    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure(go.Scatter(x=mac.index, y=mac["VIX"], line=dict(color="#ff3b6b", width=1.5), name="VIX"))
        fig.add_hline(y=20, line_dash="dot", line_color="rgba(255,255,255,.3)")
        fig.update_layout(**PLOT, height=230, title="VIX — indice de la peur")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = go.Figure(go.Scatter(x=mac.index, y=mac["US10Y"] - mac["US3M"], fill="tozeroy",
                                   line=dict(color="#7c3aed", width=1.5), name="10 ans – 3 mois"))
        fig.add_hline(y=0, line_color="rgba(255,255,255,.3)")
        fig.update_layout(**PLOT, height=230, title="Pente de la courbe des taux US (pts)")
        st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
def _tab_news(news):
    c1, c2 = st.columns([1, 1.5])
    with c1:
        section_title("RISQUE GÉOPOLITIQUE", "🛰️")
        fig = go.Figure(go.Indicator(
            mode="gauge+number", value=news["gpr"], number=dict(suffix="/100", font=dict(color="#e2e8f0")),
            gauge=dict(axis=dict(range=[0, 100], tickcolor="#475569"),
                       bar=dict(color="#e2e8f0", thickness=.25),
                       steps=[dict(range=[0, 25], color="rgba(0,255,136,.25)"),
                              dict(range=[25, 55], color="rgba(255,215,0,.25)"),
                              dict(range=[55, 100], color="rgba(255,59,107,.3)")])))
        fig.update_layout(**{k: v for k, v in PLOT.items() if k not in ("xaxis", "yaxis")}, height=230)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Indice maison : part des titres évoquant conflits, sanctions ou guerre commerciale, "
                   "pondérée par leur tonalité et diminuée par les signaux de désescalade.")
    with c2:
        section_title("THÈMES DOMINANTS", "🗞️")
        it = pd.Series({THEMES[k]["label"]: v for k, v in news["intensity"].items()}).sort_values()
        fig = go.Figure(go.Bar(x=it.values, y=it.index, orientation="h", marker_color="#7c3aed",
                               text=[f"{v:.0%}" for v in it.values], textposition="auto"))
        fig.update_layout(**PLOT, height=380, title="Part des titres par thème")
        fig.update_xaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)

    section_title("IMPACT ATTENDU PAR ACTIF", "🎯")
    st.caption("Inclinaison issue des actualités (−1 défavorable … +1 favorable), intégrée comme vue "
               "Black-Litterman dans l'Auto-Portefeuille (poids volontairement limité).")
    tl = pd.Series({t: news["tilts"].get(UNIVERSE[t][2], 0) for t in UNIVERSE}).sort_values()
    fig = go.Figure(go.Bar(x=tl.index, y=tl.values,
                           marker_color=["#00ff88" if v > 0.05 else "#ff3b6b" if v < -0.05 else "#64748b" for v in tl.values],
                           hovertext=[asset_name(t) for t in tl.index]))
    fig.update_layout(**PLOT, height=260)
    fig.update_yaxes(range=[-1, 1])
    st.plotly_chart(fig, use_container_width=True)

    with st.expander("🔎 Matrice d'impact thèmes × actifs (hypothèses du modèle)"):
        subs = ["us_eq", "tech", "intl_eq", "em_eq", "energy_eq", "defense", "gov_long", "tips", "hy",
                "gold", "oil", "commo", "reit", "crypto", "cash"]
        M = pd.DataFrame({THEMES[t]["label"]: {s: IMPACT[t].get(s, 0) for s in subs} for t in THEMES}).T
        fig = go.Figure(go.Heatmap(z=M.values, x=M.columns, y=M.index, colorscale="RdYlGn", zmin=-1, zmax=1))
        fig.update_layout(**PLOT, height=420)
        st.plotly_chart(fig, use_container_width=True)

    section_title("TITRES ANALYSÉS", "📰")
    rows = news["rows"]
    cat = st.multiselect("Catégories", sorted({r["category"] for r in rows}), key="ai_news_cat")
    for r in rows:
        if cat and r["category"] not in cat:
            continue
        s = r["sentiment"]
        col = "#00ff88" if s > .1 else "#ff3b6b" if s < -.1 else "#94a3b8"
        tags = " ".join(f'<span style="font-size:.58rem;border:1px solid rgba(124,58,237,.5);color:#a78bfa;'
                        f'border-radius:3px;padding:0 4px;margin-left:4px;">{_h.escape(THEMES[t]["label"])}</span>'
                        for t in r["themes"])
        title = _h.escape(r["title"])
        if r.get("link"):
            title = f'<a href="{_h.escape(r["link"])}" target="_blank" style="color:#e2e8f0;text-decoration:none;">{title}</a>'
        st.markdown(
            f'<div style="padding:6px 10px;border-left:3px solid {col};margin:3px 0;background:rgba(255,255,255,.015);">'
            f'<span style="font-family:Rajdhani,sans-serif;font-size:.62rem;color:#7c3aed;letter-spacing:.1em;">'
            f'[{_h.escape(r["category"].upper())}]</span> '
            f'<span style="font-size:.82rem;color:#e2e8f0;">{title}</span>'
            f'<span style="font-family:Share Tech Mono,monospace;font-size:.64rem;color:{col};margin-left:8px;">{s:+.2f}</span>'
            f'{tags}<span style="font-size:.6rem;color:#475569;margin-left:6px;">{_h.escape(r.get("source", ""))}</span></div>',
            unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
def _tab_signals(intel, sig):
    section_title("SIGNAUX PAR ACTIF — HORIZON 1 MOIS", "🤖")
    classes = st.multiselect("Classes d'actifs", ASSET_CLASSES, default=[], key="ai_sig_cls",
                             placeholder="Toutes les classes")
    s = sig if not classes else sig[sig["classe"].isin(classes)]
    fig = go.Figure(go.Bar(x=s.index, y=s["p_up"] - .5, base=.5,
                           marker_color=[_SIG_COL.get(x, "#94a3b8") for x in s["signal"]],
                           text=[f"{p:.0%}" for p in s["p_up"]], textposition="outside",
                           hovertext=[asset_name(t) for t in s.index]))
    fig.add_hline(y=.5, line_color="rgba(255,255,255,.3)")
    fig.update_layout(**PLOT, height=300, title="Probabilité de hausse à 1 mois")
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

    th = "".join(f'<th style="font-family:Rajdhani,sans-serif;font-size:.62rem;color:#00d4ff;letter-spacing:.08em;'
                 f'text-transform:uppercase;padding:7px 8px;background:rgba(0,212,255,.06);text-align:left;">{c}</th>'
                 for c in ["Actif", "Classe", "P(hausse)", "Rdt attendu 1 m", "Vol.", "Mom. 3 m", "Signal",
                           "Pousse à la hausse", "Pousse à la baisse"])
    tb = ""
    for t, r in s.iterrows():
        col = _SIG_COL.get(r["signal"], "#94a3b8")
        tb += (f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
               f'<td style="padding:6px 8px;"><b style="color:#e2e8f0;font-family:Rajdhani,sans-serif;">{t}</b>'
               f'<div style="font-size:.62rem;color:#64748b;">{_h.escape(asset_name(t))}</div></td>'
               f'<td style="padding:6px 8px;color:{CLASS_COLORS.get(r["classe"], "#94a3b8")};font-size:.72rem;">{r["classe"]}</td>'
               f'<td style="padding:6px 8px;font-family:Share Tech Mono,monospace;color:#e2e8f0;">{r["p_up"]:.0%}</td>'
               f'<td style="padding:6px 8px;font-family:Share Tech Mono,monospace;color:{"#00ff88" if r["exp_ret_1m"] > 0 else "#ff3b6b"};">'
               f'{r["exp_ret_1m"]:+.2%}</td>'
               f'<td style="padding:6px 8px;font-family:Share Tech Mono,monospace;color:#94a3b8;">{r["vol"]:.0%}</td>'
               f'<td style="padding:6px 8px;font-family:Share Tech Mono,monospace;color:{"#00ff88" if r["mom_63"] > 0 else "#ff3b6b"};">'
               f'{r["mom_63"]:+.1%}</td>'
               f'<td style="padding:6px 8px;"><span style="color:{col};border:1px solid {col};border-radius:4px;'
               f'padding:1px 6px;font-family:Rajdhani,sans-serif;font-size:.7rem;font-weight:700;">{r["signal"]}</span></td>'
               f'<td style="padding:6px 8px;font-size:.68rem;color:#7cf0b5;">{_h.escape(", ".join(r["drivers_up"]))}</td>'
               f'<td style="padding:6px 8px;font-size:.68rem;color:#ff8c9f;">{_h.escape(", ".join(r["drivers_down"]))}</td></tr>')
    st.markdown(f'<div class="mam-table-wrap"><table class="mam-table"><thead><tr>{th}</tr></thead>'
                f'<tbody>{tb}</tbody></table></div>', unsafe_allow_html=True)
    st.caption("Les « moteurs » sont une approximation locale : écart de la variable à sa moyenne × "
               "sens de sa relation avec les rendements futurs × importance hors échantillon.")

    section_title("ZOOM SUR UN ACTIF", "🔍")
    t = st.selectbox("Actif", list(sig.index), format_func=lambda x: f"{x} — {asset_name(x)}", key="ai_zoom")
    px = intel["prices"][t].dropna().iloc[-504:]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=px.index, y=px, name=t, line=dict(color="#00d4ff", width=1.6)))
    fig.add_trace(go.Scatter(x=px.index, y=px.rolling(50).mean(), name="MM 50", line=dict(color="#ffd700", width=1)))
    fig.add_trace(go.Scatter(x=px.index, y=px.rolling(200).mean(), name="MM 200", line=dict(color="#7c3aed", width=1)))
    r = sig.loc[t]
    fig.update_layout(**PLOT, height=320, legend=dict(orientation="h", y=-0.15),
                      title=f"{t} · P(hausse 1 m) {r['p_up']:.0%} · {r['signal']}")
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
def _tab_advice(intel, news, sig, reg):
    from utils.auto_portfolio import PROFILES, build_allocation
    from utils.data import get_multi_prices

    pid, port = active_portfolio()
    if not port:
        st.info("Sélectionnez ou créez un portefeuille (bandeau du haut) pour obtenir des conseils personnalisés.")
        return
    section_title(f"CONSEILS POUR {port.get('emoji', '📁')} {port.get('name', '').upper()}", "💡")
    default = STRAT_TO_PROFILE.get(port.get("strategy", ""), "Équilibré")
    profile = st.radio("Profil de risque de référence", list(PROFILES), index=list(PROFILES).index(default),
                       horizontal=True, key="ai_adv_prof")
    regime = reg["current"] if reg.get("ok") else "Ralentissement"
    alloc = build_allocation(intel["prices"], sig, regime, reg.get("inflation_flag", False), profile, "ia_bl",
                             intel["conf"], news)
    target = alloc["weights"]

    holdings = port.get("holdings", {}) or {}
    live = get_multi_prices(tuple(sorted(set(holdings) | set(target.index)))) if holdings else {}
    vals = {t: h.get("qty", 0) * live.get(t, (h.get("avg_price", 0), 0))[0] for t, h in holdings.items()}
    nav = float(port.get("cash", 0)) + sum(vals.values())
    cur = pd.Series(vals) / nav if nav > 0 else pd.Series(dtype=float)
    cash_w = float(port.get("cash", 0)) / nav if nav > 0 else 1.0

    alerts = []
    if cash_w > 0.5:
        alerts.append(("🟡", f"{cash_w:.0%} du portefeuille est en liquidités : capital peu investi."))
    for t, w in cur.items():
        if w > 0.25:
            alerts.append(("🔴", f"Concentration : {t} pèse {w:.0%} du portefeuille (> 25 %)."))
    crypto = sum(w for t, w in cur.items() if asset_class(t) == "Crypto")
    lim = PROFILES[profile]["bounds"]["Crypto"][1]
    if crypto > lim + 0.01:
        alerts.append(("🔴", f"Crypto {crypto:.0%} > {lim:.0%} autorisé pour un profil {profile}."))
    eq = sum(w for t, w in cur.items() if asset_class(t) == "Actions")
    lo, hi = alloc["bounds"].get("Actions", (0, 1))
    if eq > hi + 0.05:
        alerts.append(("🟠", f"Actions {eq:.0%} au-dessus de la borne {hi:.0%} conseillée en régime « {regime} »."))
    elif eq < lo - 0.05 and cash_w < 0.5:
        alerts.append(("🟡", f"Actions {eq:.0%} sous la borne {lo:.0%} conseillée en régime « {regime} »."))
    for t in cur.index:
        if t in sig.index and sig.loc[t, "signal"] in ("SOUS-PONDÉRER",) and cur[t] > 0.05:
            alerts.append(("🟠", f"{t} ({cur[t]:.0%}) a un signal ML défavorable "
                                  f"(P(hausse) {sig.loc[t, 'p_up']:.0%})."))
    if alerts:
        for ic, txt in alerts:
            st.markdown(f'<div style="padding:6px 10px;margin:3px 0;border:1px solid rgba(255,255,255,.06);'
                        f'border-radius:6px;font-size:.8rem;color:#cbd5e1;">{ic} {_h.escape(txt)}</div>',
                        unsafe_allow_html=True)
    else:
        st.success("Aucune alerte de risque majeure sur ce portefeuille.")

    # comparaison actuel vs cible
    tick = sorted(set(cur.index) | set(target.index), key=lambda x: -max(cur.get(x, 0), target.get(x, 0)))
    rows = []
    for t in tick:
        a, b = float(cur.get(t, 0)), float(target.get(t, 0))
        d = b - a
        in_u = t in sig.index
        if not in_u:
            act = "Hors univers ML — à surveiller"
        elif abs(d) < 0.02:
            act = "Conserver"
        elif d > 0:
            act = f"Renforcer (+{d:.0%})"
        else:
            act = f"Alléger ({d:.0%})"
        rows.append({"Actif": t, "Nom": asset_name(t), "Poids actuel": a, "Poids conseillé": b if in_u else np.nan,
                     "Écart": d if in_u else np.nan,
                     "Signal ML": sig.loc[t, "signal"] if in_u else "—", "Action suggérée": act,
                     "_cv": a * nav})
    df = pd.DataFrame(rows)
    if not df.empty:
        fig = go.Figure()
        top = df.head(15)
        fig.add_trace(go.Bar(x=top["Actif"], y=top["Poids actuel"], name="Actuel", marker_color="#475569"))
        fig.add_trace(go.Bar(x=top["Actif"], y=top["Poids conseillé"], name="Conseillé (IA)", marker_color="#00d4ff"))
        fig.update_layout(**PLOT, height=300, barmode="group", legend=dict(orientation="h", y=1.12))
        fig.update_yaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df.drop(columns=["_cv"]).style.format(
            {"Poids actuel": "{:.1%}", "Poids conseillé": "{:.1%}", "Écart": "{:+.1%}"}, na_rep="—"),
            use_container_width=True, hide_index=True)
    st.caption(f"Allocation conseillée = méthode Black-Litterman IA, profil {profile}, régime {regime}. "
               "Pour l'appliquer automatiquement, utilisez l'onglet 🤖 Auto-Portefeuille → Appliquer.")
    if st.button("🤖 Ouvrir l'Auto-Portefeuille avec ce profil", key="ai_to_auto"):
        st.session_state["auto_profile"] = profile
        st.session_state["page"] = "auto_portfolio"
        st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
def _tab_model(val):
    if not val.get("ok"):
        st.info("Validation indisponible (historique insuffisant).")
        return
    section_title("PERFORMANCE HORS ÉCHANTILLON (WALK-FORWARD)", "🔬")
    a, b = val["period"]
    kpi_row([
        kpi("Précision directionnelle", f"{val['accuracy']:.1%}", f"référence naïve {val['baseline']:.1%}",
            "#00ff88" if val["accuracy"] > val["baseline"] + .01 else "#ffd700"),
        kpi("AUC", f"{val['auc']:.3f}", "0.5 = hasard", "#00ff88" if val["auc"] > .53 else "#ffd700"),
        kpi("Information coefficient", f"{val['ic']:+.3f}", f"t-stat {val['ic_t']:.1f}"),
        kpi("Écart top/bottom 20 %", f"{val['ls_spread_month']:+.2%}", "par mois, moyenne"),
        kpi("Observations testées", f"{val['n_obs']:,}", f"{a:%m/%Y} → {b:%m/%Y}"),
    ])
    st.markdown(
        '<div style="font-size:.78rem;color:#94a3b8;line-height:1.6;">Le modèle est évalué uniquement sur des '
        'périodes qu\'il n\'a jamais vues : chaque pli est entraîné sur le passé, avec une purge de 21 jours pour '
        'éviter que la cible (rendement à 1 mois) ne déborde sur la période de test. Sur les marchés, une AUC de '
        '0,52–0,58 et un IC de 0,02–0,08 sont déjà considérés comme utiles ; des scores bien plus élevés '
        'signaleraient le plus souvent une fuite d\'information.</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    imp = val["importance"]
    with c1:
        s = imp.head(15)[::-1]
        fig = go.Figure(go.Bar(x=s.values, y=[FEATURE_LABELS.get(k, k) for k in s.index], orientation="h",
                               marker_color="#7c3aed"))
        fig.update_layout(**PLOT, height=420, title="Variables les plus influentes")
        fig.update_xaxes(tickformat=".0%")
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fam = imp.groupby(lambda k: FEATURE_FAMILY.get(k, "Autre")).sum().sort_values()
        fig = go.Figure(go.Pie(labels=fam.index, values=fam.values, hole=.55,
                               marker=dict(colors=["#00d4ff", "#7c3aed", "#ffd700", "#00ff88", "#ff8c00",
                                                   "#ff3b6b", "#94a3b8", "#38bdf8"])))
        fig.update_layout(**{k: v for k, v in PLOT.items() if k not in ("xaxis", "yaxis")}, height=420,
                          title="Poids par famille d'information")
        st.plotly_chart(fig, use_container_width=True)
    oos = val["oos"]
    bins = pd.cut(oos["p_up"], [0, .35, .45, .5, .55, .65, 1])
    cal = oos.groupby(bins, observed=True).agg(freq=("y_ret", lambda x: (x > 0).mean()), n=("y_ret", "size"),
                                               ret=("y_ret", "mean"))
    fig = go.Figure()
    fig.add_trace(go.Bar(x=[str(i) for i in cal.index], y=cal["freq"], name="Fréquence réelle de hausse",
                         marker_color="#00d4ff", text=[f"n={n}" for n in cal["n"]], textposition="outside"))
    fig.add_trace(go.Scatter(x=[str(i) for i in cal.index], y=cal["ret"] * 10 + .5, name="Rendement moyen 1 m (×10, décalé)",
                             mode="lines+markers", line=dict(color="#ffd700")))
    fig.add_hline(y=.5, line_dash="dot", line_color="rgba(255,255,255,.3)")
    fig.update_layout(**PLOT, height=300, title="Calibration : probabilité prédite vs réalisé",
                      legend=dict(orientation="h", y=-0.2))
    fig.update_yaxes(tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)


# ── Régime officiel du comité vs modèle statistique (contrôle croisé) ─────────
_FAMILY = {
    "Expansion désinflationniste": {"Expansion / Risk-on", "Reprise"},
    "Surchauffe / reflation": {"Expansion / Risk-on", "Reprise"},
    "Ralentissement désinflationniste": {"Ralentissement"},
    "Stagflation": {"Ralentissement", "Crise / Risk-off"},
    "Aversion au risque": {"Crise / Risk-off"},
}


def _regime_crosscheck(gmm_regime: str):
    """Le régime OFFICIEL est celui du comité (8 facteurs, Jean-Michel TAUX-BAS) : il pilote allocations,
    couvertures et stratégies d'options. Le mélange gaussien de cette page sert de contrôle croisé."""
    try:
        from components.committee_ui import get_context
        off = get_context()["macro"].regime
    except Exception:
        return
    agree = gmm_regime in _FAMILY.get(off, set())
    col = "#00ff88" if agree else "#ffd700"
    st.markdown(
        f'<div style="border-left:3px solid {col};background:rgba(0,0,0,.25);border-radius:4px;padding:7px 12px;'
        f'margin:6px 0 10px;font-family:Share Tech Mono;font-size:.72rem;color:#cbd5e1;">'
        f'🌦️ <b>Régime officiel du comité</b> (Jean-Michel TAUX-BAS, 8 facteurs macro) : <b>{off}</b> · '
        f'modèle statistique de cette page (mélange gaussien) : <b>{gmm_regime}</b> → '
        f'<b style="color:{col}">{"concordant" if agree else "divergent : prudence, les deux lectures ne racontent pas la même histoire"}</b>. '
        f'<span style="color:#64748b">Le régime officiel pilote les allocations, les couvertures et les stratégies d\'options.</span>'
        f'</div>', unsafe_allow_html=True)
