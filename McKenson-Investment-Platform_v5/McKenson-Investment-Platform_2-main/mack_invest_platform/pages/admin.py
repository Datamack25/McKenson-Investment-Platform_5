# pages/admin.py  —  MAM Admin Panel
"""
Password-protected admin panel.
Manage teams, portfolios, game state, reset cash, view audit logs,
export data and configure simulation parameters.
Default password: MAM2026
"""
from __future__ import annotations
import json
import csv
import io
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ui import section_title, metric_row
from utils.data import get_or_init_state, persist, load_assets, INITIAL_CASH

# ── À ajouter dans pages/admin.py, dans la fonction render() ─────────────────
# Bloc de persistance permanente — copier-coller dans Streamlit Secrets

def _render_persistence_block():
    """Affiche la clé d'état encodée pour copier dans les Streamlit Secrets."""
    import streamlit as st
    from utils.data import get_or_init_state, _encode_state

    state = get_or_init_state()
    b64   = _encode_state(state)
    n_teams = len(state.get("teams", {}))
    n_ports = sum(len(t.get("portfolios",{})) for t in state.get("teams",{}).values())
    n_trades= sum(
        len(p.get("trades",[]))
        for t in state.get("teams",{}).values()
        for p in t.get("portfolios",{}).values()
    )

    st.markdown("""
    <div style="background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.3);
    border-radius:10px;padding:16px 20px;margin-bottom:20px;">
    <div style="font-family:Rajdhani,sans-serif;font-size:1rem;font-weight:700;
    color:#ffd700;letter-spacing:.12em;margin-bottom:8px;">
    💾 SAUVEGARDE PERMANENTE — STREAMLIT SECRETS</div>
    <div style="font-family:Share Tech Mono,monospace;font-size:.72rem;color:#94a3b8;
    line-height:1.8;margin-bottom:12px;">
    Streamlit Cloud efface le filesystem à chaque redémarrage.<br>
    Copiez la clé ci-dessous dans vos <b style="color:#ffd700;">Streamlit Secrets</b>
    pour rendre les données permanentes.<br>
    <b style="color:#00d4ff;">share.streamlit.io → votre app → Settings → Secrets</b>
    </div>""", unsafe_allow_html=True)

    st.code(f'game_state_b64 = "{b64}"', language="toml")

    col1, col2, col3 = st.columns(3)
    col1.metric("Équipes", n_teams)
    col2.metric("Portefeuilles", n_ports)
    col3.metric("Trades", n_trades)

    st.markdown("""
    <div style="font-family:Share Tech Mono,monospace;font-size:.7rem;color:#475569;margin-top:8px;">
    ⚠️ Mettez à jour cette clé dans les Secrets après chaque session de trading importante.
    </div></div>""", unsafe_allow_html=True)


# Appeler dans render() :
# _render_persistence_block()

_ADMIN_PASSWORD = "MAM2026"
_P = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
          font=dict(color="#94a3b8", family="Share Tech Mono"),
          margin=dict(l=8, r=8, t=28, b=8))

STRATEGIES = [
    "Growth", "Value", "Momentum", "Hedging", "Balanced",
    "Income", "Arbitrage", "Quantitative", "ESG", "Macro Global",
]
EMOJIS_TEAM = ["🦅", "🐂", "🎯", "🌊", "🔥", "🦁", "🐉", "⚡", "🌙", "💎"]
EMOJIS_PORT = ["📈", "🛡️", "🚀", "💰", "🎲", "🌐", "💡", "🔮", "⚖️", "🏆"]


def render():
    st.markdown(
        '<h1 style="font-family:Rajdhani,sans-serif;font-size:2rem;letter-spacing:.12em;'
        'color:#ff3b6b;margin:0 0 2px;text-shadow:0 0 30px rgba(255,59,107,.4);">'
        '⚙️ ADMIN PANEL — MAM</h1>', unsafe_allow_html=True)

    # ── Auth gate ──────────────────────────────────────────────────────────────
    if not st.session_state.get("admin_authenticated"):
        _login_form()
        return

    # ── Admin content ──────────────────────────────────────────────────────────
    _admin_header()

    tab_teams, tab_game, tab_assets, tab_logs, tab_export, tab_danger = st.tabs([
        "👥 ÉQUIPES & PORTEFEUILLES",
        "🎮 PARAMÈTRES JEU",
        "📋 ACTIFS",
        "📜 AUDIT LOGS",
        "💾 EXPORT / IMPORT",
        "☢️ ZONE DANGEREUSE",
    ])

    with tab_teams:
        _teams_tab()
    with tab_game:
        _game_settings_tab()
    with tab_assets:
        _assets_tab()
    with tab_logs:
        _logs_tab()
    with tab_export:
        _export_tab()
    with tab_danger:
        _danger_tab()


# ── Login ─────────────────────────────────────────────────────────────────────
def _login_form():
    st.markdown("<br>", unsafe_allow_html=True)
    col_c = st.columns([1, 2, 1])[1]
    with col_c:
        st.markdown(
            '<div style="background:rgba(255,59,107,.06);border:1px solid rgba(255,59,107,.3);'
            'border-radius:12px;padding:30px;text-align:center;">'
            '<div style="font-size:2.5rem;margin-bottom:10px;">🔐</div>'
            '<div style="font-family:Rajdhani;font-size:1.2rem;font-weight:700;'
            'color:#e2e8f0;letter-spacing:.1em;margin-bottom:20px;">ACCÈS ADMINISTRATEUR</div>'
            '</div>', unsafe_allow_html=True)
        pwd = st.text_input("Mot de passe", type="password", key="admin_pwd",
                            placeholder="Entrez le mot de passe admin…")
        if st.button("🔓 Connexion", key="admin_login", use_container_width=True):
            if pwd == _ADMIN_PASSWORD:
                st.session_state["admin_authenticated"] = True
                st.success("✅ Authentification réussie !")
                st.rerun()
            else:
                st.error("❌ Mot de passe incorrect.")
        st.markdown(
            '<div style="font-family:Share Tech Mono;font-size:.68rem;color:#475569;'
            'text-align:center;margin-top:12px;">Par défaut : MAM2026</div>',
            unsafe_allow_html=True)


def _admin_header():
    col1, col2 = st.columns([4, 1])
    with col1:
        st.markdown(
            '<div style="font-family:Share Tech Mono;font-size:.73rem;color:#ff3b6b;'
            'margin-bottom:16px;">🔴 MODE ADMINISTRATEUR ACTIVÉ — '
            f'Session: {datetime.now().strftime("%d/%m/%Y %H:%M")}</div>',
            unsafe_allow_html=True)
    with col2:
        if st.button("🔒 Déconnexion", key="admin_logout"):
            st.session_state["admin_authenticated"] = False
            st.rerun()

    state = get_or_init_state()
    teams = state.get("teams", {})
    total_ports  = sum(len(t["portfolios"]) for t in teams.values())
    total_trades = sum(
        len(p.get("trades", []))
        for t in teams.values()
        for p in t["portfolios"].values()
    )
    total_value  = sum(
        p.get("cash", 0) + sum(
            h.get("qty", 0) * h.get("avg_price", 0)
            for h in p.get("holdings", {}).values()
        )
        for t in teams.values()
        for p in t["portfolios"].values()
    )

    metric_row([
        {"label": "Équipes",       "value": str(len(teams)),       "color": ""},
        {"label": "Portefeuilles", "value": str(total_ports),      "color": ""},
        {"label": "Transactions",  "value": str(total_trades),     "color": ""},
        {"label": "AUM estimé",    "value": f"${total_value:,.0f}", "color": ""},
    ])
    st.markdown("---")


# ── Teams tab ─────────────────────────────────────────────────────────────────
def _teams_tab():
    state = get_or_init_state()
    teams = state.get("teams", {})

    col_left, col_right = st.columns([1, 1])

    # ── Create team ────────────────────────────────────────────────────────────
    with col_left:
        section_title("CRÉER UNE ÉQUIPE", "➕")
        with st.form("form_create_team"):
            team_name  = st.text_input("Nom de l'équipe", placeholder="ex: Sigma Capital")
            team_emoji = st.selectbox("Emoji", EMOJIS_TEAM)
            team_cash  = st.number_input("Capital initial ($)", 100_000, 10_000_000,
                                          int(INITIAL_CASH), 100_000)
            n_ports    = st.slider("Nombre de portefeuilles à créer", 1, 10, 3)
            submitted  = st.form_submit_button("➕ Créer l'équipe", use_container_width=True)

        if submitted and team_name:
            tid = f"T{len(teams)+1:02d}_{team_name[:8].replace(' ','')}"
            if tid not in teams:
                portfolios = {}
                for i in range(n_ports):
                    pid  = f"P{i+1:02d}"
                    strat = STRATEGIES[i % len(STRATEGIES)]
                    portfolios[pid] = {
                        "name": f"Portfolio {i+1}", "emoji": EMOJIS_PORT[i % len(EMOJIS_PORT)],
                        "strategy": strat, "cash": float(team_cash),
                        "initial_cash": float(team_cash),
                        "holdings": {}, "trades": [], "history": [],
                        "created": datetime.now().isoformat(),
                    }
                state["teams"][tid] = {
                    "name": team_name, "emoji": team_emoji,
                    "portfolios": portfolios,
                    "created": datetime.now().isoformat(),
                }
                persist()
                st.success(f"✅ Équipe '{team_name}' créée avec {n_ports} portefeuilles !")
                st.rerun()
            else:
                st.error("⚠️ ID d'équipe déjà utilisé.")

    # ── Edit / manage existing teams ───────────────────────────────────────────
    with col_right:
        section_title("GÉRER LES ÉQUIPES", "⚙️")
        if not teams:
            st.info("Aucune équipe. Créez-en une à gauche.")
        else:
            for tid, team in list(teams.items()):
                with st.expander(f"{team['emoji']} {team['name']} ({tid})", expanded=False):
                    # Rename
                    new_name  = st.text_input("Nom", team["name"], key=f"nm_{tid}")
                    new_emoji = st.selectbox("Emoji", EMOJIS_TEAM,
                                             index=EMOJIS_TEAM.index(team["emoji"])
                                             if team["emoji"] in EMOJIS_TEAM else 0,
                                             key=f"em_{tid}")
                    col_a, col_b = st.columns(2)
                    with col_a:
                        if st.button("💾 Sauvegarder", key=f"save_{tid}", use_container_width=True):
                            state["teams"][tid]["name"]  = new_name
                            state["teams"][tid]["emoji"] = new_emoji
                            persist()
                            st.success("✅ Sauvegardé")
                            st.rerun()
                    with col_b:
                        if st.button("🗑️ Supprimer", key=f"del_{tid}", use_container_width=True):
                            del state["teams"][tid]
                            persist()
                            st.warning(f"Équipe {tid} supprimée.")
                            st.rerun()

                    # Portfolios
                    st.markdown('<div style="font-family:Rajdhani;font-size:.68rem;'
                                'color:#7a93b0;letter-spacing:.08em;margin:8px 0 4px;">'
                                'PORTEFEUILLES</div>', unsafe_allow_html=True)

                    for pid, port in team["portfolios"].items():
                        pc1, pc2, pc3 = st.columns([3, 2, 2])
                        with pc1:
                            st.markdown(
                                f'<span style="font-family:Share Tech Mono;font-size:.73rem;'
                                f'color:#e2e8f0;">{port["emoji"]} {port["name"]}</span>'
                                f'<span style="color:#7a93b0;font-size:.65rem;"> · {port["strategy"]}</span>',
                                unsafe_allow_html=True)
                        with pc2:
                            # Reset cash
                            reset_val = st.number_input(
                                "Reset cash ($)", 0, 10_000_000,
                                int(port.get("initial_cash", INITIAL_CASH)),
                                100_000, key=f"rc_{tid}_{pid}", label_visibility="collapsed")
                        with pc3:
                            if st.button("💵 Reset", key=f"rb_{tid}_{pid}", use_container_width=True):
                                state["teams"][tid]["portfolios"][pid]["cash"] = float(reset_val)
                                state["teams"][tid]["portfolios"][pid]["initial_cash"] = float(reset_val)
                                state["teams"][tid]["portfolios"][pid]["holdings"] = {}
                                state["teams"][tid]["portfolios"][pid]["trades"]   = []
                                state["teams"][tid]["portfolios"][pid]["history"]  = []
                                persist()
                                st.success(f"✅ {pid} reset à ${reset_val:,.0f}")
                                st.rerun()

                    # Add portfolio
                    st.markdown("---")
                    if len(team["portfolios"]) < 10:
                        with st.form(f"addport_{tid}"):
                            p_name  = st.text_input("Nom du nouveau portefeuille", key=f"pn_{tid}")
                            p_strat = st.selectbox("Stratégie", STRATEGIES, key=f"ps_{tid}")
                            p_cash  = st.number_input("Capital ($)", 100_000, 10_000_000,
                                                        int(INITIAL_CASH), key=f"pc_{tid}")
                            p_emoji = st.selectbox("Emoji", EMOJIS_PORT, key=f"pe_{tid}")
                            if st.form_submit_button("➕ Ajouter portefeuille"):
                                new_pid = f"P{len(team['portfolios'])+1:02d}"
                                state["teams"][tid]["portfolios"][new_pid] = {
                                    "name": p_name or f"Portfolio {new_pid}",
                                    "emoji": p_emoji, "strategy": p_strat,
                                    "cash": float(p_cash), "initial_cash": float(p_cash),
                                    "holdings": {}, "trades": [], "history": [],
                                    "created": datetime.now().isoformat(),
                                }
                                persist()
                                st.success("✅ Portefeuille ajouté !")
                                st.rerun()
                    else:
                        st.info("Maximum 10 portefeuilles par équipe atteint.")


# ── Game settings ─────────────────────────────────────────────────────────────
def _game_settings_tab():
    section_title("PARAMÈTRES DE LA SIMULATION", "🎮")
    state = get_or_init_state()
    cfg   = state.get("config", {})

    with st.form("game_config_form"):
        col1, col2 = st.columns(2)
        with col1:
            start_date  = st.text_input("Date de début simulation", cfg.get("start_date", "2026-01-01"))
            end_date    = st.text_input("Date de fin simulation",   cfg.get("end_date",   "2026-12-31"))
            rf_rate     = st.number_input("Taux sans risque (%)", 0.0, 20.0,
                                           float(cfg.get("rf_rate", 4.25)), 0.05)
            max_leverage = st.number_input("Levier max autorisé", 1.0, 10.0,
                                            float(cfg.get("max_leverage", 1.0)), 0.5)
        with col2:
            commission  = st.number_input("Commission par trade (bps)", 0.0, 100.0,
                                           float(cfg.get("commission_bps", 0.0)), 0.5)
            allow_short = st.checkbox("Autoriser la vente à découvert", cfg.get("allow_short", False))
            allow_crypto = st.checkbox("Activer Crypto", cfg.get("allow_crypto", True))
            allow_options = st.checkbox("Activer Options", cfg.get("allow_options", True))
            leaderboard_live = st.checkbox("Leaderboard temps réel", cfg.get("leaderboard_live", True))

        game_name = st.text_input("Nom de la simulation", cfg.get("game_name", "MAM Challenge 2026"))
        submitted = st.form_submit_button("💾 Sauvegarder la configuration", use_container_width=True)

    if submitted:
        state["config"] = {
            "start_date": start_date, "end_date": end_date,
            "rf_rate": rf_rate, "max_leverage": max_leverage,
            "commission_bps": commission, "allow_short": allow_short,
            "allow_crypto": allow_crypto, "allow_options": allow_options,
            "leaderboard_live": leaderboard_live,
            "game_name": game_name,
            "updated": datetime.now().isoformat(),
        }
        persist()
        st.success("✅ Configuration sauvegardée !")

    # Display current config
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("CONFIGURATION ACTUELLE", "📋")
    if state.get("config"):
        cfg_display = {k: v for k, v in state["config"].items() if k != "updated"}
        st.json(cfg_display)


# ── Assets tab ────────────────────────────────────────────────────────────────
def _assets_tab():
    section_title("GESTION DES ACTIFS", "📋")
    assets_df = load_assets()

    st.markdown(
        f'<div style="font-family:Share Tech Mono;font-size:.73rem;color:#7a93b0;'
        f'margin-bottom:12px;">{len(assets_df)} actifs chargés depuis data/assets*.csv</div>',
        unsafe_allow_html=True)

    # Stats by category
    if not assets_df.empty and "category" in assets_df.columns:
        by_cat = assets_df["category"].value_counts()
        fig = go.Figure(go.Bar(
            x=by_cat.index, y=by_cat.values,
            marker_color="rgba(0,212,255,.6)",
            text=by_cat.values, textposition="outside",
            hovertemplate="%{x}: %{y} actifs<extra></extra>"))
        fig.update_layout(**_P, height=200,
            xaxis=dict(showgrid=False, tickangle=-20),
            yaxis=dict(title="Nb actifs", gridcolor="rgba(255,255,255,.04)"))
        st.plotly_chart(fig, use_container_width=True)

    # Filterable table
    cat_filter = st.selectbox("Filtrer par catégorie", ["Tous"] + sorted(assets_df["category"].unique().tolist()),
                               key="adm_cat")
    df_show = assets_df if cat_filter == "Tous" else assets_df[assets_df["category"] == cat_filter]
    st.dataframe(df_show, use_container_width=True, hide_index=True, height=350)

    # Add asset instructions
    section_title("AJOUTER DES ACTIFS", "➕")
    st.markdown("""
    <div style="background:rgba(0,212,255,.05);border:1px solid rgba(0,212,255,.2);
    border-radius:8px;padding:14px;font-family:Share Tech Mono;font-size:.74rem;
    color:#94a3b8;line-height:1.9;">
    📁 Pour ajouter des actifs, déposez un fichier <b style="color:#00d4ff;">assets_extra.csv</b>
    dans le dossier <b>data/</b>.<br>
    Colonnes requises : <b>ticker, name, category, subcategory, currency, exchange, description</b><br>
    Le fichier sera fusionné automatiquement au prochain démarrage.
    </div>""", unsafe_allow_html=True)

    # Inline add form
    st.markdown("<br>", unsafe_allow_html=True)
    with st.form("add_asset_form"):
        c1, c2 = st.columns(2)
        with c1:
            a_ticker = st.text_input("Ticker (ex: ASML)")
            a_name   = st.text_input("Nom (ex: ASML Holding NV)")
            a_cat    = st.selectbox("Catégorie", sorted(assets_df["category"].unique().tolist()) if not assets_df.empty else ["Equities"])
            a_subcat = st.text_input("Sous-catégorie (ex: Large Cap)")
        with c2:
            a_curr   = st.selectbox("Devise", ["USD", "EUR", "GBP", "JPY", "CHF"])
            a_exch   = st.text_input("Exchange (ex: AMS)")
            a_desc   = st.text_area("Description", height=80)
        if st.form_submit_button("➕ Ajouter l'actif", use_container_width=True):
            if a_ticker and a_name:
                extra_path = Path("data/assets_extra.csv")
                new_row    = f'{a_ticker},{a_name},{a_cat},{a_subcat},{a_curr},{a_exch},"{a_desc}"\n'
                if extra_path.exists():
                    with open(extra_path, "a", encoding="utf-8") as f:
                        f.write(new_row)
                else:
                    with open(extra_path, "w", encoding="utf-8") as f:
                        f.write("ticker,name,category,subcategory,currency,exchange,description\n")
                        f.write(new_row)
                st.success(f"✅ Actif {a_ticker} ajouté dans data/assets_extra.csv. Rechargez l'app pour voir l'effet.")
            else:
                st.error("Ticker et Nom sont requis.")


# ── Audit logs ────────────────────────────────────────────────────────────────
def _logs_tab():
    section_title("JOURNAL D'AUDIT DES TRANSACTIONS", "📜")
    state = get_or_init_state()
    teams = state.get("teams", {})

    all_trades = []
    for tid, team in teams.items():
        for pid, port in team["portfolios"].items():
            for tr in port.get("trades", []):
                all_trades.append({
                    "Date":        tr.get("date", ""),
                    "Équipe":      f'{team["emoji"]} {team["name"]}',
                    "Portefeuille": f'{port["emoji"]} {port["name"]}',
                    "Ticker":      tr.get("ticker", ""),
                    "Action":      tr.get("action", ""),
                    "Quantité":    tr.get("qty", 0),
                    "Prix":        tr.get("price", 0),
                    "Total ($)":   tr.get("total", 0),
                })

    if not all_trades:
        st.info("Aucune transaction enregistrée.")
        return

    df = pd.DataFrame(all_trades).sort_values("Date", ascending=False)
    metric_row([
        {"label": "Total transactions", "value": str(len(df)), "color": ""},
        {"label": "Volume total ($)",   "value": f'${df["Total ($)"].sum():,.0f}', "color": ""},
        {"label": "BUY",  "value": str(len(df[df["Action"]=="BUY"])),  "color": "positive"},
        {"label": "SELL", "value": str(len(df[df["Action"]=="SELL"])), "color": "negative"},
    ])

    st.markdown("<br>", unsafe_allow_html=True)

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        team_filter = st.selectbox("Équipe", ["Toutes"] + sorted(df["Équipe"].unique().tolist()),
                                    key="log_team")
    with col2:
        action_filter = st.selectbox("Action", ["Toutes", "BUY", "SELL"], key="log_action")
    with col3:
        ticker_filter = st.text_input("Ticker", "", key="log_ticker", placeholder="ex: AAPL")

    dff = df.copy()
    if team_filter   != "Toutes":
        dff = dff[dff["Équipe"] == team_filter]
    if action_filter != "Toutes":
        dff = dff[dff["Action"] == action_filter]
    if ticker_filter:
        dff = dff[dff["Ticker"].str.contains(ticker_filter, case=False, na=False)]

    st.dataframe(dff, use_container_width=True, hide_index=True, height=400)

    # Volume chart
    if len(df) > 1:
        st.markdown("<br>", unsafe_allow_html=True)
        section_title("VOLUME PAR ÉQUIPE", "📊")
        vol_by_team = df.groupby("Équipe")["Total ($)"].sum().sort_values(ascending=False)
        fig = go.Figure(go.Bar(
            x=vol_by_team.index, y=vol_by_team.values,
            marker_color="rgba(0,212,255,.6)",
            text=[f"${v:,.0f}" for v in vol_by_team.values],
            textposition="outside",
            hovertemplate="%{x}<br>Volume: $%{y:,.0f}<extra></extra>"))
        fig.update_layout(**_P, height=240,
            xaxis=dict(showgrid=False, tickangle=-20),
            yaxis=dict(title="Volume ($)", gridcolor="rgba(255,255,255,.04)"))
        st.plotly_chart(fig, use_container_width=True)


# ── Export ────────────────────────────────────────────────────────────────────
def _export_tab():
    section_title("EXPORT DES DONNÉES", "💾")
    state = get_or_init_state()

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div style="font-family:Rajdhani;font-size:.72rem;color:#7a93b0;'
                    'letter-spacing:.08em;margin-bottom:8px;">EXPORT JSON (game_state)</div>',
                    unsafe_allow_html=True)
        json_str = json.dumps(state, indent=2, default=str)
        st.download_button(
            "⬇️ Télécharger game_state.json",
            data=json_str, file_name="mam_game_state.json",
            mime="application/json", use_container_width=True)

    with col2:
        st.markdown('<div style="font-family:Rajdhani;font-size:.72rem;color:#7a93b0;'
                    'letter-spacing:.08em;margin-bottom:8px;">EXPORT CSV (transactions)</div>',
                    unsafe_allow_html=True)
        teams = state.get("teams", {})
        rows  = []
        for tid, team in teams.items():
            for pid, port in team["portfolios"].items():
                for tr in port.get("trades", []):
                    rows.append({
                        "team_id": tid, "team_name": team["name"],
                        "port_id": pid, "port_name": port["name"],
                        **tr
                    })
        if rows:
            csv_buf = io.StringIO()
            writer  = csv.DictWriter(csv_buf, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
            st.download_button(
                "⬇️ Télécharger transactions.csv",
                data=csv_buf.getvalue(), file_name="mam_transactions.csv",
                mime="text/csv", use_container_width=True)
        else:
            st.info("Aucune transaction à exporter.")

    # Import state
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("IMPORT D'UN ÉTAT DE JEU", "📤")
    uploaded = st.file_uploader("Importer un fichier game_state.json", type=["json"])
    if uploaded:
        try:
            new_state = json.load(uploaded)
            if st.button("⚠️ Confirmer l'import (remplace l'état actuel)", key="confirm_import"):
                state_path = Path("data/game_state.json")
                with open(state_path, "w") as f:
                    json.dump(new_state, f, indent=2, default=str)
                st.success("✅ État importé avec succès. Rechargez l'application.")
        except Exception as e:
            st.error(f"❌ Erreur lors de l'import : {e}")


# ── Danger zone ───────────────────────────────────────────────────────────────
def _danger_tab():
    st.markdown(
        '<div style="background:rgba(255,59,107,.08);border:2px solid rgba(255,59,107,.4);'
        'border-radius:10px;padding:16px;margin-bottom:20px;">'
        '<div style="font-family:Rajdhani;font-size:1.1rem;font-weight:700;color:#ff3b6b;'
        'letter-spacing:.1em;">☢️ ZONE DANGEREUSE</div>'
        '<div style="font-family:Share Tech Mono;font-size:.73rem;color:#94a3b8;margin-top:6px;">'
        'Les actions suivantes sont irréversibles. Procédez avec précaution.'
        '</div></div>', unsafe_allow_html=True)

    state = get_or_init_state()

    # Reset all portfolios
    st.markdown('<div style="font-family:Rajdhani;font-size:.8rem;color:#ff3b6b;'
                'letter-spacing:.08em;margin-bottom:6px;">🔄 RÉINITIALISER TOUS LES PORTEFEUILLES</div>',
                unsafe_allow_html=True)
    confirm_reset = st.checkbox("Je comprends que cela effacera toutes les positions et transactions",
                                 key="confirm_reset_all")
    if confirm_reset:
        if st.button("💥 Réinitialiser tous les portefeuilles", key="btn_reset_all",
                     use_container_width=True):
            for tid in state.get("teams", {}):
                for pid in state["teams"][tid]["portfolios"]:
                    port = state["teams"][tid]["portfolios"][pid]
                    init_cash = port.get("initial_cash", INITIAL_CASH)
                    state["teams"][tid]["portfolios"][pid].update({
                        "cash": float(init_cash), "holdings": {},
                        "trades": [], "history": [],
                    })
            persist()
            st.success("✅ Tous les portefeuilles ont été réinitialisés.")
            st.rerun()

    st.markdown("---")

    # Delete all teams
    st.markdown('<div style="font-family:Rajdhani;font-size:.8rem;color:#ff3b6b;'
                'letter-spacing:.08em;margin-bottom:6px;">🗑️ SUPPRIMER TOUTES LES ÉQUIPES</div>',
                unsafe_allow_html=True)
    confirm_del = st.checkbox("Je comprends que cela supprimera TOUTES les équipes et données",
                               key="confirm_del_all")
    if confirm_del:
        if st.button("☠️ SUPPRIMER TOUTES LES ÉQUIPES", key="btn_del_all",
                     use_container_width=True):
            state["teams"] = {}
            persist()
            st.error("Toutes les équipes ont été supprimées.")
            st.rerun()

    st.markdown("---")

    # Change admin password
    section_title("CHANGER LE MOT DE PASSE ADMIN", "🔑")
    st.warning("⚠️ Le changement de mot de passe n'est actif que pour la session en cours "
               "et ne persiste pas entre les redémarrages. Modifiez _ADMIN_PASSWORD dans admin.py "
               "pour une persistance permanente.")
    new_pwd = st.text_input("Nouveau mot de passe", type="password", key="new_admin_pwd")
    if st.button("🔑 Appliquer", key="btn_change_pwd") and new_pwd:
        # Store in session for current session only
        st.session_state["_admin_pwd_override"] = new_pwd
        st.success("✅ Mot de passe modifié pour cette session.")
