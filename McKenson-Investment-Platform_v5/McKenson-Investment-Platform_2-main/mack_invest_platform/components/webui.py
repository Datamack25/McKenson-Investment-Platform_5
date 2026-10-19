"""
components/webui.py — MAM : habillage « vraie page web » (Streamlit + HTML)

Streamlit garde la logique (widgets, état, navigation) ; le HTML/CSS fait le
rendu d'un site d'investissement : en-tête de marque, barre de navigation à
onglets, bandeau compte / KPI, cartes de portefeuilles, pied de page.
Même charte que l'existant : fond #080e1a, cyan #00d4ff, vert #00ff88,
violet #7c3aed, polices Rajdhani + Share Tech Mono.
"""
from __future__ import annotations

import html as _html
from datetime import datetime

import streamlit as st

# ══════════════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════════════

WEB_CSS = """
<style>
/* ── Chrome Streamlit masqué : on veut une page web, pas une app Streamlit ── */
#MainMenu, footer,
[data-testid="stToolbarActions"], [data-testid="stMainMenu"],
[data-testid="stAppDeployButton"], .stDeployButton, [data-testid="stDecoration"],
[data-testid="stSidebar"], [data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarNav"] {
    display: none !important;
}
[data-testid="stHeader"] {
    background: transparent !important; height: 0 !important; min-height: 0 !important;
}
.block-container {
    max-width: 1400px !important;
    padding: 0 2rem 1.5rem !important;
}
@media (max-width: 760px) { .block-container { padding: 0 .8rem 1rem !important; } }

/* ── Fond type site : halo discret ── */
[data-testid="stApp"] {
    background:
      radial-gradient(1100px 420px at 85% -10%, rgba(124,58,237,.10), transparent 60%),
      radial-gradient(900px 380px at 5% -5%,  rgba(0,212,255,.08),  transparent 60%),
      #080e1a !important;
}

/* ── Boutons toujours sombres, même si le navigateur est en thème clair ── */
.stButton button, [data-testid="stPopover"] button, [data-testid="stFormSubmitButton"] button {
    background-color: #0b1424 !important;
    background-image: linear-gradient(135deg, rgba(0,212,255,.12), rgba(124,58,237,.12)) !important;
    border: 1px solid rgba(0,212,255,.3) !important;
    color: #00d4ff !important;
}
[data-testid="stPopover"] button p, .stButton button p { color: inherit !important; }

/* ── Panneau 🔔 (popover) sombre ── */
[data-testid="stPopoverBody"], div[data-baseweb="popover"] > div {
    background: #0d1117 !important; border: 1px solid rgba(0,212,255,.25) !important;
}
[data-testid="stPopoverBody"] p, [data-testid="stPopoverBody"] label,
[data-testid="stPopoverBody"] [data-testid="stCaptionContainer"] { color: #cbd5e1 !important; }

/* ── Libellés de champs lisibles sur fond sombre ── */
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label { color: #94a3b8 !important; }

/* ── Barre de marque ── */
.mam-topbar {
    display: flex; align-items: center; justify-content: space-between; gap: 16px;
    flex-wrap: wrap;
    padding: 14px 20px; margin: 4px 0 8px;
    background: linear-gradient(135deg, rgba(0,212,255,.06), rgba(124,58,237,.06));
    border: 1px solid rgba(0,212,255,.14); border-radius: 10px;
}
.mam-brand { display: flex; align-items: center; gap: 12px; }
.mam-logo {
    width: 40px; height: 40px; border-radius: 9px; display: flex; align-items: center;
    justify-content: center; font-family: Rajdhani, sans-serif; font-weight: 700;
    font-size: 1.35rem; color: #080e1a;
    background: linear-gradient(135deg, #00ff88, #00d4ff);
    box-shadow: 0 0 22px rgba(0,255,136,.35);
}
.mam-brand-name {
    font-family: Rajdhani, sans-serif; font-weight: 700; font-size: 1.7rem; line-height: 1;
    letter-spacing: .22em; color: #00ff88; text-shadow: 0 0 24px rgba(0,255,136,.45);
}
.mam-brand-sub {
    font-family: Rajdhani, sans-serif; font-size: .6rem; letter-spacing: .26em;
    text-transform: uppercase; color: #475569; margin-top: 3px;
}
.mam-top-right { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.mkt-pill {
    display: inline-flex; align-items: center; gap: 6px; padding: 4px 10px;
    border-radius: 20px; font-family: Rajdhani, sans-serif; font-weight: 700;
    font-size: .68rem; letter-spacing: .1em; color: #64748b;
    border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.02);
}
.mkt-pill i { width: 7px; height: 7px; border-radius: 50%; background: #475569; display: inline-block; }
.mkt-pill.open { color: #00ff88; border-color: rgba(0,255,136,.35); background: rgba(0,255,136,.07); }
.mkt-pill.open i { background: #00ff88; box-shadow: 0 0 8px #00ff88; animation: mam-pulse 1.8s infinite; }
@keyframes mam-pulse { 50% { opacity: .35; } }
.mam-clock { font-family: 'Share Tech Mono', monospace; font-size: .72rem; color: #7a93b0; }
.mam-user {
    font-family: Rajdhani, sans-serif; font-weight: 700; font-size: .8rem; letter-spacing: .06em;
    color: #00d4ff; padding: 4px 12px; border-radius: 20px;
    border: 1px solid rgba(0,212,255,.3); background: rgba(0,212,255,.07);
}

/* ── Navigation à onglets (boutons Streamlit habillés) ── */
div[data-testid="stHorizontalBlock"]:has(.nav-marker) {
    gap: 2px !important; flex-wrap: nowrap !important; overflow-x: auto;
    border-bottom: 1px solid rgba(0,212,255,.14); margin-bottom: 14px;
    scrollbar-width: none;
}
div[data-testid="stHorizontalBlock"]:has(.nav-marker)::-webkit-scrollbar { display: none; }
div[data-testid="stHorizontalBlock"]:has(.nav-marker) > div[data-testid="stColumn"],
div[data-testid="stHorizontalBlock"]:has(.nav-marker) > div[data-testid="column"] {
    min-width: max-content !important; flex: 1 1 auto !important;
}
div[data-testid="stHorizontalBlock"]:has(.nav-marker) .stButton > button {
    background: transparent !important; border: none !important; border-radius: 0 !important;
    border-bottom: 2px solid transparent !important; box-shadow: none !important;
    color: #64748b !important; font-size: .86rem !important; padding: 10px 14px !important;
    letter-spacing: .1em !important; white-space: nowrap; transform: none !important;
}
div[data-testid="stHorizontalBlock"]:has(.nav-marker) .stButton > button:hover {
    color: #e2e8f0 !important; background: rgba(0,212,255,.05) !important;
}
div[data-testid="stHorizontalBlock"]:has(.nav-marker) .stButton > button[kind="primary"],
div[data-testid="stHorizontalBlock"]:has(.nav-marker) .stButton > button[data-testid="stBaseButton-primary"] {
    color: #00d4ff !important; border-bottom-color: #00d4ff !important;
    background: linear-gradient(180deg, transparent, rgba(0,212,255,.09)) !important;
    text-shadow: 0 0 14px rgba(0,212,255,.55);
}
.nav-marker { display: none; }

/* ── Bandeau compte : sélecteurs + KPI du portefeuille actif ── */
.acct-kpis { display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; }
.acct-kpi {
    min-width: 110px; padding: 6px 12px; border-radius: 8px;
    background: rgba(0,212,255,.04); border: 1px solid rgba(0,212,255,.12);
}
.acct-kpi .k { font-family: Rajdhani, sans-serif; font-size: .58rem; letter-spacing: .16em;
               text-transform: uppercase; color: #475569; }
.acct-kpi .v { font-family: 'Share Tech Mono', monospace; font-size: .95rem; color: #e2e8f0; }

/* ── Cartes de portefeuilles ── */
.port-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
             gap: 10px; margin: 6px 0 14px; }
.port-card {
    padding: 10px 14px; border-radius: 8px; background: rgba(13,17,23,.8);
    border: 1px solid rgba(0,212,255,.1); font-family: 'Share Tech Mono', monospace;
    font-size: .7rem; color: #7a93b0; line-height: 1.7; transition: all .2s;
}
.port-card:hover { border-color: rgba(0,212,255,.3); transform: translateY(-1px); }
.port-card.active { border-color: rgba(0,212,255,.45); box-shadow: 0 0 18px rgba(0,212,255,.1); }
.port-card .pn { font-family: Rajdhani, sans-serif; font-weight: 700; font-size: .9rem; color: #e2e8f0; }
.port-card .pt { font-family: Rajdhani, sans-serif; font-size: .6rem; color: #475569;
                 letter-spacing: .1em; margin-left: 6px; }

/* ── Pied de page ── */
.mam-footer {
    margin-top: 36px; padding: 22px 20px 12px; border-top: 1px solid rgba(0,212,255,.14);
    display: grid; grid-template-columns: 1.4fr 1fr 1fr; gap: 24px;
    font-family: 'Share Tech Mono', monospace; font-size: .68rem; color: #475569; line-height: 1.8;
}
@media (max-width: 760px) { .mam-footer { grid-template-columns: 1fr; } }
.mam-footer h4 { font-family: Rajdhani, sans-serif; font-size: .8rem; letter-spacing: .18em;
                 text-transform: uppercase; color: #00d4ff; margin: 0 0 6px; }
.mam-footer .fb { font-family: Rajdhani, sans-serif; font-weight: 700; font-size: 1.2rem;
                  letter-spacing: .22em; color: #00ff88; }
.mam-legal { grid-column: 1 / -1; border-top: 1px solid rgba(255,255,255,.05);
             padding-top: 10px; font-size: .62rem; color: #334155; }
</style>
"""


def inject_web_css():
    st.markdown(WEB_CSS, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# EN-TÊTE
# ══════════════════════════════════════════════════════════════════════════════

def _market_status() -> list[tuple[str, bool]]:
    """Ouverture des principales places (heure locale de chaque place)."""
    try:
        from zoneinfo import ZoneInfo
        out = []
        for label, tz, (oh, om), (ch, cm) in [
            ("NYSE", "America/New_York", (9, 30), (16, 0)),
            ("EURONEXT", "Europe/Paris", (9, 0), (17, 30)),
        ]:
            now = datetime.now(ZoneInfo(tz))
            minutes = now.hour * 60 + now.minute
            is_open = now.weekday() < 5 and oh * 60 + om <= minutes < ch * 60 + cm
            out.append((label, is_open))
        return out
    except Exception:
        return []


def render_topbar():
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Paris"))
    except Exception:
        now = datetime.now()

    pills = "".join(
        f'<span class="mkt-pill {"open" if o else ""}"><i></i>{n} {"OPEN" if o else "CLOSED"}</span>'
        for n, o in _market_status()
    )
    # Statut du flux de données (cours réels différés ou prix de secours)
    try:
        from utils.data import market_data_status
        live = market_data_status() == "live"
        pills += (f'<span class="mkt-pill {"open" if live else ""}" title="'
                  f'{"Cours Yahoo Finance différés" if live else "Yahoo Finance injoignable : ordres bloqués par la conformité"}">'
                  f'<i></i>DONNÉES {"LIVE (DIFF.)" if live else "DE REPLI"}</span>')
    except Exception:
        pass
    try:
        from utils.legal import APP_VERSION
        pills += f'<span class="mkt-pill" title="Version de la plateforme">v{APP_VERSION}</span>'
    except Exception:
        pass
    user = st.session_state.get("mam_user")
    uname = _html.escape(user["username"]) if user else "invité"
    st.markdown(
        f"""
<div class="mam-topbar">
  <div class="mam-brand">
    <div class="mam-logo">M</div>
    <div><div class="mam-brand-name">MAM</div>
         <div class="mam-brand-sub">McKenson Asset Management</div></div>
  </div>
  <div class="mam-top-right">
    {pills}
    <span class="mam-clock">{now.strftime("%d/%m/%Y · %H:%M")}</span>
    <span class="mam-user">👤 {uname}</span>
  </div>
</div>""",
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# NAVIGATION
# ══════════════════════════════════════════════════════════════════════════════

def render_nav(pages: dict[str, str]):
    """Onglets de navigation. `pages` = {libellé: clé}. Met à jour st.session_state['page']."""
    if "page" not in st.session_state:
        st.session_state["page"] = "dashboard"
    cols = st.columns(len(pages))
    for i, (col, (label, key)) in enumerate(zip(cols, pages.items())):
        with col:
            active = st.session_state["page"] == key
            clicked = st.button(label, key=f"nav_{key}", use_container_width=True,
                                type="primary" if active else "secondary")
            if i == len(pages) - 1:
                st.markdown('<span class="nav-marker"></span>', unsafe_allow_html=True)
            if clicked:
                st.session_state["page"] = key
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# BANDEAU COMPTE + CARTES PORTEFEUILLES
# ══════════════════════════════════════════════════════════════════════════════

def _port_stats(port: dict) -> dict:
    """Mêmes formules que l'ancien résumé de la sidebar."""
    from utils.data import get_multi_prices
    holdings = port.get("holdings", {}) or {}
    cash = port.get("cash", 0.0)
    mkt_val = pnl = 0.0
    if holdings:
        px = get_multi_prices(tuple(holdings.keys()))
        for tk, pos in holdings.items():
            qty, avg = pos.get("qty", 0), pos.get("avg_price", 0.0)
            curr, _ = px.get(tk, (avg, 0.0))
            mkt_val += qty * curr
            pnl += qty * (curr - avg)
    base = mkt_val - pnl
    return {
        "aum": cash + mkt_val, "cash": cash, "pnl": pnl,
        "pnl_pct": (pnl / base * 100) if base > 0 else 0.0,
        "n_pos": len(holdings),
    }


def render_account_bar(state: dict):
    """Sélecteurs équipe / portefeuille (mêmes clés qu'avant), KPI du portefeuille
    actif, panneau de notifications et déconnexion. Renvoie (sel_team, user_ports)."""
    teams = state.get("teams", {})
    team_names = {tid: t["name"] for tid, t in teams.items()}
    sel_team, user_ports = None, {}

    c_team, c_port, c_kpi, c_bell, c_out = st.columns([1.5, 1.7, 3.4, .45, .9])

    with c_team:
        if team_names:
            sel_team = st.selectbox("🏢 Équipe", list(team_names.keys()),
                                    format_func=lambda x: team_names[x], key="active_team")
        else:
            st.caption("Aucune équipe — créez-en une via Administration.")
            st.session_state["active_team"] = None

    with c_port:
        if sel_team:
            user_ports = {pid: p for pid, p in teams[sel_team].get("portfolios", {}).items()
                          if p.get("name")}
            if user_ports:
                labels = {pid: f'{p.get("emoji", "📁")} {p["name"]}' for pid, p in user_ports.items()}
                st.selectbox("📂 Portefeuille", list(labels.keys()),
                             format_func=lambda x: labels[x], key="active_portfolio")
            else:
                st.caption("Aucun portefeuille — créez-en un dans le Dashboard.")
                st.session_state["active_portfolio"] = None

    with c_kpi:
        pid = st.session_state.get("active_portfolio")
        if sel_team and pid in user_ports:
            try:
                s = _port_stats(user_ports[pid])
                col = "#00ff88" if s["pnl"] >= 0 else "#ff3b6b"
                sg = "+" if s["pnl"] >= 0 else "-"
                st.markdown(
                    f'<div class="acct-kpis">'
                    f'<div class="acct-kpi"><div class="k">AUM</div><div class="v">${s["aum"]:,.0f}</div></div>'
                    f'<div class="acct-kpi"><div class="k">Cash</div><div class="v">${s["cash"]:,.0f}</div></div>'
                    f'<div class="acct-kpi"><div class="k">P&amp;L latent</div>'
                    f'<div class="v" style="color:{col}">{sg}${abs(s["pnl"]):,.0f} '
                    f'<span style="font-size:.65rem">({sg}{abs(s["pnl_pct"]):.2f}%)</span></div></div>'
                    f'<div class="acct-kpi"><div class="k">Positions</div><div class="v">{s["n_pos"]}</div></div>'
                    f'</div>', unsafe_allow_html=True)
            except Exception:
                pass

    with c_bell:
        try:
            with st.popover("🔔", use_container_width=True):
                from utils.notifier import render_settings
                render_settings()
        except Exception:
            pass

    with c_out:
        if st.session_state.get("mam_user") or st.session_state.get("mam_guest"):
            if st.button("⎋ Quitter", key="btn_logout", use_container_width=True):
                for k in ("mam_user", "mam_user_id", "mam_guest", "mam_state",
                          "mam_db_loaded_for", "_mail_known", "active_team", "active_portfolio"):
                    st.session_state.pop(k, None)
                st.rerun()

    return sel_team, user_ports


def render_portfolio_cards(user_ports: dict, max_cards: int = 4):
    if not user_ports:
        return
    cards = ""
    active = st.session_state.get("active_portfolio")
    for pid, port in list(user_ports.items())[:max_cards]:
        try:
            s = _port_stats(port)
        except Exception:
            continue
        col = "#00ff88" if s["pnl"] >= 0 else "#ff3b6b"
        sg = "+" if s["pnl"] >= 0 else "-"
        cards += (
            f'<div class="port-card{" active" if pid == active else ""}">'
            f'<div class="pn">{_html.escape(str(port.get("emoji", "📁")))} '
            f'{_html.escape(str(port.get("name", "—")))}'
            f'<span class="pt">{_html.escape(str(port.get("portfolio_type", "Libre")))}</span></div>'
            f'AUM <b style="color:#e2e8f0">${s["aum"]:,.0f}</b> · {s["n_pos"]} pos.<br>'
            f'P&amp;L <b style="color:{col}">{sg}${abs(s["pnl"]):,.2f}</b> '
            f'<span style="color:{col};font-size:.62rem">({sg}{abs(s["pnl_pct"]):.2f}%)</span>'
            f'</div>'
        )
    if cards:
        st.markdown(f'<div class="port-grid">{cards}</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PIED DE PAGE
# ══════════════════════════════════════════════════════════════════════════════

def render_footer():
    from utils.legal import AUTHOR, AUTHOR_TITLE, APP_VERSION, APP_RELEASE, DISCLAIMER
    year = datetime.now().year
    st.markdown(
        f"""
<div class="mam-footer">
  <div><div class="fb">MAM</div>
       McKenson Asset Management<br>Plateforme éducative de simulation d'investissement.<br>
       Créée par <b style="color:#e2e8f0;">{AUTHOR}</b>, {AUTHOR_TITLE}.<br>
       Version <b style="color:#00d4ff;">{APP_VERSION}</b> · {APP_RELEASE}</div>
  <div><h4>Plateforme</h4>Trading Desk · ETF · Stratégies d'options<br>IA Marchés · Auto-Portefeuille IA<br>Optimiseur · Rapports PDF · Classement<br>Contrôles de conformité pré-négociation</div>
  <div><h4>Données</h4>Cours : Yahoo Finance (différé) · Actualités : Google News<br>ML : scikit-learn · Options : Black-Scholes<br>Sauvegarde : base PostgreSQL</div>
  <div class="mam-legal">© {year} {AUTHOR} — McKenson Asset Management — v{APP_VERSION}.<br>{DISCLAIMER}</div>
</div>""",
        unsafe_allow_html=True,
    )
