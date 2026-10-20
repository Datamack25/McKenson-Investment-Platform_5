# pages/leaderboard.py  —  MAM  v3.2  FIXED
"""
Leaderboard: team rankings + active-team portfolio detail.

FIX v3.2:
  - AttributeError: .str accessor on non-string → use numeric columns directly
  - Shows ONLY active team's ACTIVE portfolios (those with trades/holdings)
  - Split into 2 tables: team ranking + active-portfolio performance
  - Added Sharpe, Sortino, Calmar, Max Drawdown, Ann. Vol per team
  - Options trade validation fix referenced in trading.py
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from components.ui import section_title, metric_row, pnl_cell, pct_cell
from utils.data import (
    get_or_init_state, value_portfolio,
    get_multi_prices, compute_risk_metrics,
)

_P = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94a3b8", family="Share Tech Mono"),
    margin=dict(l=8, r=8, t=28, b=8),
)

# Ensure _STRATEGY_HINTS has no set syntax error — rebuild properly
_SH: dict[str, tuple[str, str, str]] = {
    "growth":    ("High Risk",      "#ff8c00", "Volatilité élevée. Horizon 5+ ans recommandé."),
    "value":     ("Moderate Risk",  "#ffd700", "Patience requise. Décotes parfois longues."),
    "momentum":  ("High Risk",      "#ff8c00", "Attention aux retournements. Stop-loss conseillés."),
    "income":    ("Low-Mod Risk",   "#00d4ff", "Surveiller la pérennité des dividendes."),
    "macro":     ("Moderate Risk",  "#ffd700", "Diversification multi-actifs obligatoire."),
    "hedging":   ("Low Risk",       "#00ff88", "Coûts de couverture à surveiller (theta decay)."),
    "balanced":  ("Low-Mod Risk",   "#00d4ff", "Rééquilibrage périodique recommandé."),
    "commodity": ("High Risk",      "#ff8c00", "Forte cyclicalité — surveiller USD & géopolitique."),
    "crypto":    ("Very High Risk", "#ff3b6b", "Volatilité extrême. Max 5-10% du capital total."),
    "arbitrage": ("Low Risk",       "#00ff88", "Risque d'exécution et de liquidité à surveiller."),
}


def render():
    state      = get_or_init_state()
    teams      = state.get("teams", {})
    active_team_id = st.session_state.get("active_team")

    st.markdown(
        '<h1 style="font-family:Rajdhani,sans-serif;font-size:2rem;letter-spacing:.12em;'
        'color:#ffd700;margin:0 0 2px;text-shadow:0 0 30px rgba(255,215,0,.4);">'
        '🏆 LEADERBOARD — MAM</h1>',
        unsafe_allow_html=True,
    )

    # ── Pre-fetch all prices ───────────────────────────────────────────────────
    all_tickers: set[str] = set()
    for t in teams.values():
        for p in t.get("portfolios", {}).values():
            all_tickers.update(p.get("holdings", {}).keys())
    prices_raw = get_multi_prices(tuple(all_tickers)) if all_tickers else {}
    prices     = {t: prices_raw[t][0] for t in prices_raw}

    tab1, tab2 = st.tabs(["🏆 CLASSEMENT ÉQUIPES", "📊 MES PORTEFEUILLES"])

    with tab1:
        _team_ranking(teams, prices)

    with tab2:
        _my_portfolios(teams, active_team_id, prices)


# ══════════════════════════════════════════════════════════════════════════════
#  TABLE 1 — TEAM RANKING
# ══════════════════════════════════════════════════════════════════════════════

def _team_ranking(teams: dict, prices: dict):
    section_title("CLASSEMENT PAR ÉQUIPE", "🏆")

    rows = []
    for tid, team in teams.items():
        portfolios = team.get("portfolios", {})
        team_total = 0.0
        team_init  = 0.0
        all_rets   = []

        for port in portfolios.values():
            val = value_portfolio(port, prices)
            team_total += val["total"]
            team_init  += port.get("initial_cash", 1_000_000)
            hist = port.get("history", [])
            if len(hist) >= 5:
                hdf  = pd.DataFrame(hist)
                if "value" in hdf.columns:
                    rets = hdf["value"].pct_change().dropna().tolist()
                    all_rets.extend(rets)

        pnl   = team_total - team_init
        pct   = pnl / team_init * 100 if team_init else 0.0

        # Risk metrics — computed directly on numeric data, no .str accessor
        sharpe = sortino = calmar = ann_vol = max_dd = 0.0
        if len(all_rets) >= 5:
            r  = pd.Series(all_rets).dropna()
            m  = compute_risk_metrics(r)
            if m:
                ann_vol = m["ann_vol"] * 100       # already numeric float
                sharpe  = m["sharpe"]
                sortino = m["sortino"]
                calmar  = m["calmar"]
                max_dd  = m["max_drawdown"] * 100  # numeric float

        rows.append({
            "_tid":    tid,
            "Équipe":  f'{team["emoji"]} {team["name"]}',
            "Valeur":  team_total,
            "P&L ($)": pnl,
            "P&L (%)": pct,
            # Numeric columns — NO string formatting yet (avoids .str error)
            "_sharpe":   sharpe,
            "_sortino":  sortino,
            "_calmar":   calmar,
            "_ann_vol":  ann_vol,
            "_max_dd":   max_dd,
            "Portefeuilles": len(portfolios),
        })

    if not rows:
        st.info("Aucune équipe.")
        return

    rows.sort(key=lambda r: r["P&L (%)"], reverse=True)

    # ── Medal summary cards ────────────────────────────────────────────────────
    top3 = rows[:3]
    medals = ["🥇", "🥈", "🥉"]
    cols3  = st.columns(min(len(top3), 3))
    for i, (col, r) in enumerate(zip(cols3, top3)):
        pnl_col = "#00ff88" if r["P&L (%)"] >= 0 else "#ff3b6b"
        sign    = "+" if r["P&L (%)"] >= 0 else ""
        with col:
            st.markdown(
                f'<div style="background:rgba(0,212,255,.05);border:1px solid rgba(0,212,255,.15);'
                f'border-radius:8px;padding:14px;text-align:center;">'
                f'<div style="font-size:1.8rem;">{medals[i]}</div>'
                f'<div style="font-family:Rajdhani;font-size:.95rem;font-weight:700;'
                f'color:#e2e8f0;">{r["Équipe"]}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:1.1rem;'
                f'color:{pnl_col};font-weight:bold;">'
                f'{sign}{r["P&L (%)"]:.2f}%</div>'
                f'<div style="font-family:Share Tech Mono;font-size:.75rem;color:#7a93b0;">'
                f'${r["Valeur"]:,.0f}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Full ranking table ─────────────────────────────────────────────────────
    hdr = ["#", "Équipe", "Valeur totale", "P&L ($)", "P&L (%)",
           "Sharpe", "Sortino", "Calmar", "Ann. Vol", "Max DD", "Portf."]
    th  = "".join(
        f'<th style="font-family:Rajdhani;font-size:.67rem;color:#ffd700;'
        f'letter-spacing:.1em;text-transform:uppercase;padding:8px 10px;'
        f'background:rgba(255,215,0,.06);border-bottom:1px solid rgba(255,215,0,.18);">'
        f'{c}</th>' for c in hdr)

    tbody = ""
    for rank, r in enumerate(rows, 1):
        pnl_cls = "pnl-pos" if r["P&L (%)"] > 0 else ("pnl-neg" if r["P&L (%)"] < 0 else "pnl-zero")
        sign    = "+" if r["P&L (%)"] > 0 else ""
        arr     = "▲" if r["P&L (%)"] > 0 else ("▼" if r["P&L (%)"] < 0 else "▬")
        med     = medals[rank - 1] if rank <= 3 else str(rank)

        # Sharpe color
        sh     = r["_sharpe"]
        sh_col = "#00ff88" if sh >= 2 else ("#ffd700" if sh >= 1 else ("#ff3b6b" if sh < 0 else "#94a3b8"))

        tbody += (
            f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
            f'<td style="padding:7px 10px;font-size:1rem;">{med}</td>'
            f'<td style="padding:7px 10px;font-family:Rajdhani;font-size:.88rem;'
            f'font-weight:700;color:#e2e8f0;">{r["Équipe"]}</td>'
            f'<td style="padding:7px 10px;font-family:Share Tech Mono;color:#e2e8f0;">'
            f'${r["Valeur"]:,.0f}</td>'
            f'<td style="padding:7px 10px;" class="{pnl_cls}">'
            f'{sign}${abs(r["P&L ($)"]):,.0f}</td>'
            f'<td style="padding:7px 10px;" class="{pnl_cls}">'
            f'{arr} {sign}{abs(r["P&L (%)"]):,.2f}%</td>'
            # Sharpe
            f'<td style="padding:7px 10px;font-family:Share Tech Mono;'
            f'color:{sh_col};">{sh:.2f}</td>'
            # Sortino
            f'<td style="padding:7px 10px;font-family:Share Tech Mono;color:#94a3b8;">'
            f'{r["_sortino"]:.2f}</td>'
            # Calmar
            f'<td style="padding:7px 10px;font-family:Share Tech Mono;color:#94a3b8;">'
            f'{r["_calmar"]:.2f}</td>'
            # Ann Vol
            f'<td style="padding:7px 10px;font-family:Share Tech Mono;color:#7a93b0;">'
            f'{r["_ann_vol"]:.2f}%</td>'
            # Max DD
            f'<td style="padding:7px 10px;font-family:Share Tech Mono;'
            f'color:#ff3b6b;">{r["_max_dd"]:.2f}%</td>'
            f'<td style="padding:7px 10px;font-family:Share Tech Mono;color:#00d4ff;">'
            f'{r["Portefeuilles"]}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<div style="overflow-x:auto;border:1px solid rgba(255,215,0,.18);border-radius:8px;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{th}</tr></thead><tbody>{tbody}</tbody></table></div>',
        unsafe_allow_html=True,
    )

    # ── Metric legend ──────────────────────────────────────────────────────────
    st.markdown(
        '<div style="font-family:Share Tech Mono;font-size:.7rem;color:#475569;'
        'margin-top:8px;">Légende : <b style="color:#00ff88;">Sharpe</b> rendement/risque total · '
        '<b style="color:#94a3b8;">Sortino</b> rendement/risque baisse · '
        '<b style="color:#94a3b8;">Calmar</b> rendement/max drawdown · '
        '<b style="color:#7a93b0;">Ann.Vol</b> volatilité annualisée · '
        '<b style="color:#ff3b6b;">Max DD</b> drawdown maximum</div>',
        unsafe_allow_html=True,
    )

    # ── P&L bar chart ──────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        section_title("P&L PAR ÉQUIPE", "📈")
        fig = go.Figure(go.Bar(
            x=[r["Équipe"] for r in rows],
            y=[r["P&L (%)"] for r in rows],
            marker_color=["rgba(0,255,136,.7)" if r["P&L (%)"] >= 0
                          else "rgba(255,59,107,.7)" for r in rows],
            text=[f'{"+" if r["P&L (%)"]>=0 else ""}{r["P&L (%)"]:.2f}%' for r in rows],
            textposition="outside",
            textfont=dict(family="Share Tech Mono", size=11),
            hovertemplate="%{x}<br>P&L: %{y:+.2f}%<extra></extra>",
        ))
        fig.add_hline(y=0, line_color="rgba(255,255,255,.2)", line_width=1)
        fig.update_layout(**_P, height=260,
            yaxis=dict(title="P&L (%)", gridcolor="rgba(255,255,255,.04)"),
            xaxis=dict(showgrid=False))
        st.plotly_chart(fig, use_container_width=True)

    with col_chart2:
        section_title("CLASSEMENT", "🏆")
        for r in rows[:5]:
            pnl_col = "#00ff88" if r["P&L (%)"] >= 0 else "#ff3b6b"
            sign    = "+" if r["P&L (%)"] >= 0 else ""
            st.markdown(
                f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.06);'
                f'border-radius:6px;padding:8px 14px;margin:4px 0;display:flex;'
                f'justify-content:space-between;align-items:center;">'
                f'<span style="font-family:Rajdhani;font-size:.9rem;color:#e2e8f0;">'
                f'{r["Équipe"]}</span>'
                f'<span style="font-family:Share Tech Mono;font-size:.88rem;'
                f'color:{pnl_col};font-weight:bold;">'
                f'{sign}{r["P&L (%)"]:.2f}%</span>'
                f'</div>',
                unsafe_allow_html=True,
            )


# ══════════════════════════════════════════════════════════════════════════════
#  TABLE 2 — ACTIVE TEAM'S ACTIVE PORTFOLIOS ONLY
# ══════════════════════════════════════════════════════════════════════════════

def _my_portfolios(teams: dict, active_team_id: str | None, prices: dict):
    section_title("MES PORTEFEUILLES ACTIFS", "📊")

    if not active_team_id or active_team_id not in teams:
        st.info("Sélectionnez une équipe dans la barre latérale.")
        return

    team       = teams[active_team_id]
    portfolios = team.get("portfolios", {})

    # ── Only show portfolios with actual activity ──────────────────────────────
    active_ports = {
        k: v for k, v in portfolios.items()
        if v.get("trades") or v.get("holdings")
    }

    if not active_ports:
        st.markdown(
            f'<div style="background:rgba(0,212,255,.05);border:1px solid rgba(0,212,255,.15);'
            f'border-radius:8px;padding:20px;text-align:center;">'
            f'<div style="font-family:Rajdhani;font-size:1rem;color:#7a93b0;'
            f'letter-spacing:.12em;">Aucun portefeuille actif pour {team["emoji"]} {team["name"]}</div>'
            f'<div style="font-family:Share Tech Mono;font-size:.78rem;color:#475569;margin-top:8px;">'
            f'Rendez-vous sur le Trading Desk pour commencer à investir.<br>'
            f'Seuls les portefeuilles avec des transactions apparaissent ici.</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        f'<div style="font-family:Share Tech Mono;font-size:.75rem;color:#7a93b0;margin-bottom:10px;">'
        f'Affichage des {len(active_ports)} portefeuille(s) actif(s) de '
        f'<b style="color:#00d4ff;">{team["emoji"]} {team["name"]}</b> — '
        f'les portefeuilles sans activité ne sont pas affichés.</div>',
        unsafe_allow_html=True,
    )

    rows = []
    for pid, port in active_ports.items():
        val   = value_portfolio(port, prices)
        total = val["total"]
        init  = port.get("initial_cash", 1_000_000)
        pnl   = total - init
        pct   = pnl / init * 100 if init else 0.0
        strat = port.get("strategy", "")
        hint  = _SH.get(strat, ("—", "#94a3b8", ""))

        # Risk metrics — numeric only
        sharpe = sortino = calmar = ann_vol = max_dd = 0.0
        hist = port.get("history", [])
        if len(hist) >= 5:
            hdf = pd.DataFrame(hist)
            if "value" in hdf.columns:
                rets = hdf["value"].pct_change().dropna()
                m = compute_risk_metrics(rets)
                if m:
                    ann_vol = m["ann_vol"] * 100
                    sharpe  = m["sharpe"]
                    sortino = m["sortino"]
                    calmar  = m["calmar"]
                    max_dd  = m["max_drawdown"] * 100

        rows.append({
            "pid": pid, "port": port,
            "name": f'{port["emoji"]} {port["name"]}',
            "strategy_id": strat,
            "total": total, "cash": val["cash"],
            "invested": val["spot_value"],
            "pnl": pnl, "pct": pct,
            "n_pos": len(val["positions"]),
            "n_tr": len(port.get("trades", [])),
            "hint": hint,
            "sharpe": sharpe, "sortino": sortino,
            "calmar": calmar, "ann_vol": ann_vol, "max_dd": max_dd,
        })

    # ── Portfolio performance table ────────────────────────────────────────────
    hdr = ["Portefeuille", "Stratégie", "Valeur", "Cash",
           "Investi", "P&L ($)", "P&L (%)", "Sharpe", "Ann.Vol", "Max DD",
           "Positions", "Trades", "Indicateur risque"]
    th  = "".join(
        f'<th style="font-family:Rajdhani;font-size:.64rem;color:#00d4ff;'
        f'letter-spacing:.09em;text-transform:uppercase;padding:8px 9px;'
        f'background:rgba(0,212,255,.06);border-bottom:1px solid rgba(0,212,255,.18);">'
        f'{c}</th>' for c in hdr)

    tbody = ""
    for r in rows:
        pnl_cls = "pnl-pos" if r["pnl"] > 0 else ("pnl-neg" if r["pnl"] < 0 else "pnl-zero")
        sign    = "+" if r["pnl"] > 0 else ""
        arr     = "▲" if r["pnl"] > 0 else ("▼" if r["pnl"] < 0 else "▬")
        sh_col  = "#00ff88" if r["sharpe"] >= 2 else ("#ffd700" if r["sharpe"] >= 1 else "#ff3b6b")
        hint_lbl, hint_col, hint_tip = r["hint"]

        tbody += (
            f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
            f'<td style="padding:7px 9px;font-family:Rajdhani;font-size:.85rem;'
            f'font-weight:700;color:#e2e8f0;">{r["name"]}</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;font-size:.72rem;'
            f'color:#7a93b0;">{r["strategy_id"]}</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;color:#e2e8f0;">'
            f'${r["total"]:,.0f}</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;color:#7a93b0;">'
            f'${r["cash"]:,.0f}</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;color:#7a93b0;">'
            f'${r["invested"]:,.0f}</td>'
            f'<td style="padding:7px 9px;" class="{pnl_cls}">'
            f'{sign}${abs(r["pnl"]):,.0f}</td>'
            f'<td style="padding:7px 9px;" class="{pnl_cls}">'
            f'{arr} {sign}{abs(r["pct"]):.2f}%</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;color:{sh_col};">'
            f'{r["sharpe"]:.2f}</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;color:#7a93b0;">'
            f'{r["ann_vol"]:.2f}%</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;color:#ff3b6b;">'
            f'{r["max_dd"]:.2f}%</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;color:#00d4ff;">'
            f'{r["n_pos"]}</td>'
            f'<td style="padding:7px 9px;font-family:Share Tech Mono;color:#7a93b0;">'
            f'{r["n_tr"]}</td>'
            f'<td style="padding:7px 9px;">'
            f'<span style="font-family:Rajdhani;font-size:.68rem;font-weight:700;'
            f'color:{hint_col};background:{hint_col}22;border:1px solid {hint_col}44;'
            f'padding:2px 7px;border-radius:3px;" title="{hint_tip}">'
            f'{hint_lbl}</span></td>'
            f'</tr>'
        )

    st.markdown(
        f'<div style="overflow-x:auto;border:1px solid rgba(0,212,255,.15);border-radius:8px;">'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<thead><tr>{th}</tr></thead><tbody>{tbody}</tbody></table></div>',
        unsafe_allow_html=True,
    )

    # ── Positions detail per active portfolio ──────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("DÉTAIL DES POSITIONS PAR PORTEFEUILLE", "📋")

    for r in rows:
        port = r["port"]
        val  = value_portfolio(port, prices)
        if not val["positions"]:
            continue

        pnl_col = "#00ff88" if r["pnl"] >= 0 else "#ff3b6b"
        sign    = "+" if r["pnl"] >= 0 else ""

        with st.expander(
            f'{r["name"]}  —  P&L {sign}${abs(r["pnl"]):,.0f}  ({sign}{r["pct"]:.2f}%)',
            expanded=len(rows) == 1,
        ):
            # Risk hint callout
            hint_lbl, hint_col, hint_tip = r["hint"]
            if hint_tip:
                st.markdown(
                    f'<div style="background:{hint_col}11;border-left:3px solid {hint_col};'
                    f'border-radius:0 4px 4px 0;padding:8px 12px;margin-bottom:10px;'
                    f'font-family:Share Tech Mono;font-size:.74rem;color:{hint_col};">'
                    f'⚠️ <b>{hint_lbl}</b> — {hint_tip}</div>',
                    unsafe_allow_html=True,
                )

            hdr2 = ["Ticker", "Quantité", "Px moy.", "Px actuel",
                    "Valeur", "P&L ($)", "P&L (%)"]
            th2  = "".join(
                f'<th style="font-family:Rajdhani;font-size:.64rem;color:#00d4ff;'
                f'letter-spacing:.09em;text-transform:uppercase;padding:6px 9px;'
                f'background:rgba(0,212,255,.06);border-bottom:1px solid rgba(0,212,255,.15);">'
                f'{c}</th>' for c in hdr2)

            tbody2 = ""
            for pos in val["positions"]:
                pc   = "pnl-pos" if pos["unreal_pnl"] > 0 else ("pnl-neg" if pos["unreal_pnl"] < 0 else "pnl-zero")
                sg   = "+" if pos["unreal_pnl"] > 0 else ""
                ar   = "▲" if pos["unreal_pnl"] > 0 else ("▼" if pos["unreal_pnl"] < 0 else "▬")
                tbody2 += (
                    f'<tr style="border-bottom:1px solid rgba(255,255,255,.03);">'
                    f'<td style="padding:6px 9px;color:#00d4ff;font-weight:bold;">{pos["ticker"]}</td>'
                    f'<td style="padding:6px 9px;">{pos["qty"]:,.4f}</td>'
                    f'<td style="padding:6px 9px;color:#7a93b0;">${pos["avg_price"]:,.4f}</td>'
                    f'<td style="padding:6px 9px;">${pos["current_price"]:,.4f}</td>'
                    f'<td style="padding:6px 9px;">${pos["market_value"]:,.0f}</td>'
                    f'<td style="padding:6px 9px;" class="{pc}">{sg}${abs(pos["unreal_pnl"]):,.2f}</td>'
                    f'<td style="padding:6px 9px;" class="{pc}">{ar} {abs(pos["pnl_pct"]):.2f}%</td>'
                    f'</tr>'
                )

            st.markdown(
                f'<div style="overflow-x:auto;border:1px solid rgba(0,212,255,.1);border-radius:6px;">'
                f'<table style="width:100%;border-collapse:collapse;font-family:Share Tech Mono;'
                f'font-size:.78rem;">'
                f'<thead><tr>{th2}</tr></thead><tbody>{tbody2}</tbody></table></div>',
                unsafe_allow_html=True,
            )
