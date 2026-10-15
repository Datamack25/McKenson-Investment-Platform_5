# pages/trading.py  —  MAM v5.0
"""
3 onglets :
  1. SPOT TRADING — avec validation de stratégie
  2. OPTIONS (Black-Scholes) — avec enregistrement correct
  3. MES POSITIONS — Holdings spot + Options ouvertes + Historique
     Performance globale = tous holdings selon stratégie
"""
from __future__ import annotations
import math
from datetime import datetime, date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ui import section_title, metric_row, pnl_cell
from utils.data import (
    get_or_init_state, persist, load_assets,
    get_price, get_price_change, get_history,
    get_multi_prices, value_portfolio, record_trade,
    get_contract_mult, get_currency,
)
from utils.options import bs_price, bs_greeks, implied_vol

_P = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94a3b8", family="Share Tech Mono"),
    margin=dict(l=8, r=8, t=28, b=8),
)

# ── Règles par stratégie ───────────────────────────────────────────────────────
PORTFOLIO_TYPES = {
    "Libre":         {"emoji":"🔓","color":"#94a3b8","allowed":None,          "forbidden":[],                                  "max_w":1.0,  "rules":"Aucune contrainte."},
    "Growth":        {"emoji":"🚀","color":"#00ff88","allowed":["Equities","ETF","Equity"], "forbidden":["Bonds","Commodities","Crypto"], "max_w":0.30, "rules":"Actions croissance. Interdit : bonds, commodities, crypto."},
    "Value":         {"emoji":"💎","color":"#ffd700","allowed":["Equities","ETF","Equity"], "forbidden":["Crypto","Commodities"],         "max_w":0.25, "rules":"Actions décotées. Interdit : crypto, spéculatif."},
    "Momentum":      {"emoji":"⚡","color":"#ff8c00","allowed":["Equities","ETF","Equity","Crypto"], "forbidden":["Bonds"],               "max_w":0.20, "rules":"Tendance positive. Interdit : obligations."},
    "Income":        {"emoji":"💰","color":"#00d4ff","allowed":["Equities","ETF","Bonds","Equity"],  "forbidden":["Crypto"],              "max_w":0.20, "rules":"Dividendes + obligations. Interdit : crypto."},
    "Global Macro":  {"emoji":"🌍","color":"#7c3aed","allowed":None,          "forbidden":[],                                  "max_w":0.25, "rules":"Multi-actifs. Max 25% par position."},
    "Hedging":       {"emoji":"🛡️","color":"#475569","allowed":["Bonds","ETF","Commodities","Equities","Equity"], "forbidden":["Crypto"], "max_w":0.20, "rules":"Défensif. Interdit : crypto."},
    "Balanced 60/40":{"emoji":"⚖️","color":"#00ff88","allowed":["Equities","Bonds","ETF","Equity"],  "forbidden":["Crypto","Commodities"],"max_w":0.20, "rules":"60% actions / 40% bonds."},
    "Commodity":     {"emoji":"🏭","color":"#ff8c00","allowed":["Commodities","ETF"],       "forbidden":["Crypto","Equities","Bonds","Equity"], "max_w":0.30, "rules":"Commodities uniquement."},
    "Crypto Alpha":  {"emoji":"₿", "color":"#ff3b6b","allowed":["Crypto"],    "forbidden":["Equities","Bonds","Commodities","Equity","ETF"], "max_w":0.40, "rules":"Crypto uniquement."},
    "Arbitrage":     {"emoji":"↔️","color":"#94a3b8","allowed":None,          "forbidden":[],                                  "max_w":0.15, "rules":"Delta-neutre. Max 15% par position."},
}

CATEGORY_MAP = {
    "Technology":"Equities","Financial Services":"Equities","Healthcare":"Equities",
    "Consumer Cyclical":"Equities","Consumer Defensive":"Equities","Industrials":"Equities",
    "Energy":"Equities","Utilities":"Equities","Real Estate":"Equities",
    "Communication Services":"Equities","Basic Materials":"Equities",
    "ETF":"ETF","Bond":"Bonds","Bonds":"Bonds","Crypto":"Crypto",
    "Cryptocurrency":"Crypto","Commodities":"Commodities","Commodity":"Commodities",
    "Equity":"Equities","Equities":"Equities",
}


def _validate(asset_row: pd.Series, port_type: str) -> tuple[bool, str]:
    rules = PORTFOLIO_TYPES.get(port_type, PORTFOLIO_TYPES["Libre"])
    if rules["allowed"] is None and not rules["forbidden"]:
        return True, f"✅ Autorisé ({port_type})"
    cat = CATEGORY_MAP.get(str(asset_row.get("category","Equities")), "Equities")
    if cat in rules["forbidden"]:
        return False, f"❌ '{cat}' interdit pour {port_type}"
    if rules["allowed"] and cat not in rules["allowed"]:
        return False, f"❌ '{cat}' non autorisé pour {port_type}"
    return True, f"✅ '{cat}' conforme à {port_type}"


def _pnl_col(v): return "#00ff88" if v > 0 else ("#ff3b6b" if v < 0 else "#94a3b8")
def _sgn(v):     return "+" if v > 0 else ""
def _arr(v):     return "▲" if v > 0 else ("▼" if v < 0 else "▬")
def _fmt(v):     return f"${v:,.0f}" if abs(v)>=1000 else f"${v:,.2f}" if abs(v)>=1 else f"${v:,.5f}"


# ══════════════════════════════════════════════════════════════════════════════
#  RENDER
# ══════════════════════════════════════════════════════════════════════════════

def render():
    state   = get_or_init_state()
    team_id = st.session_state.get("active_team")
    port_id = st.session_state.get("active_portfolio")
    teams   = state.get("teams", {})

    st.markdown(
        '<h1 style="font-family:Rajdhani,sans-serif;font-size:2rem;letter-spacing:.12em;'
        'color:#00ff88;margin:0 0 4px;text-shadow:0 0 30px rgba(0,255,136,.4);">'
        '💼 TRADING DESK — MAM</h1>', unsafe_allow_html=True)

    if not team_id or team_id not in teams:
        st.error("Sélectionnez une équipe dans la barre latérale."); return
    if not port_id:
        st.error("Sélectionnez un portefeuille dans la barre latérale."); return
    port = teams[team_id]["portfolios"].get(port_id)
    if not port:
        st.error(f"Portefeuille {port_id} introuvable."); return

    # ── Sélecteur de stratégie ────────────────────────────────────────────────
    current_type = port.get("portfolio_type", port.get("strategy", "Libre"))
    # Normalise ancien format
    _strat_map = {"growth":"Growth","value":"Value","momentum":"Momentum","income":"Income",
                  "macro":"Global Macro","hedging":"Hedging","balanced":"Balanced 60/40",
                  "commodity":"Commodity","crypto":"Crypto Alpha","arbitrage":"Arbitrage"}
    if current_type in _strat_map:
        current_type = _strat_map[current_type]

    type_list = list(PORTFOLIO_TYPES.keys())
    col_t, col_info = st.columns([1, 2])
    with col_t:
        new_type = st.selectbox("🎯 Stratégie", type_list,
                                index=type_list.index(current_type) if current_type in type_list else 0,
                                key="port_type_select")
        if new_type != current_type:
            port["portfolio_type"] = new_type; persist(); st.rerun()
    with col_info:
        r = PORTFOLIO_TYPES[new_type]
        st.markdown(
            f'<div style="background:rgba(0,0,0,.2);border-left:3px solid {r["color"]};'
            f'border-radius:4px;padding:8px 14px;font-family:Share Tech Mono;font-size:.72rem;'
            f'color:#7a93b0;margin-top:4px;">'
            f'<b style="color:{r["color"]}">{r["emoji"]} {new_type}</b> — {r["rules"]}'
            f'</div>', unsafe_allow_html=True)

    assets_df = load_assets()

    tab_spot, tab_opt, tab_pos = st.tabs([
        "📈 SPOT TRADING",
        "⚙️ OPTIONS",
        "📋 MES POSITIONS & PERFORMANCE",
    ])
    with tab_spot: _spot_desk(port, state, team_id, port_id, assets_df, new_type)
    with tab_opt:  _options_desk(port, state, team_id, port_id, assets_df)
    with tab_pos:  _positions_tab(port, assets_df)


# ══════════════════════════════════════════════════════════════════════════════
#  SPOT TRADING
# ══════════════════════════════════════════════════════════════════════════════

def _spot_desk(port, state, team_id, port_id, assets_df, port_type="Libre"):
    section_title("ORDRE SPOT", "📈")
    col_l, col_r = st.columns([1, 1])

    with col_l:
        ticker_opts = {f'{r["ticker"]} — {r.get("name",r["ticker"])}': r["ticker"]
                       for _, r in assets_df.iterrows()}
        sel    = st.selectbox("Actif", list(ticker_opts.keys()), key="spot_asset")
        ticker = ticker_opts[sel]
        a_row  = assets_df[assets_df["ticker"]==ticker]
        a_s    = a_row.iloc[0] if not a_row.empty else pd.Series({"category":"Equities"})

        is_valid, valid_msg = _validate(a_s, port_type)
        vc = "#00ff88" if is_valid else "#ff3b6b"
        st.markdown(
            f'<div style="border-left:3px solid {vc};background:{vc}11;border-radius:4px;'
            f'padding:6px 12px;font-family:Share Tech Mono;font-size:.72rem;color:{vc};margin:6px 0;">'
            f'{valid_msg}</div>', unsafe_allow_html=True)

        action = st.radio("Direction", ["🟢 ACHETER","🔴 VENDRE"], horizontal=True, key="spot_dir")
        is_buy = "ACHETER" in action
        price, pct = get_price_change(ticker)
        pc = "#00ff88" if pct>=0 else "#ff3b6b"
        st.markdown(
            f'<div style="background:rgba(0,0,0,.3);border:1px solid rgba(0,212,255,.2);'
            f'border-radius:6px;padding:10px 14px;margin:8px 0;">'
            f'<div style="font-family:Rajdhani;font-size:.65rem;color:#7a93b0;">PRIX ACTUEL — {ticker}</div>'
            f'<div style="font-family:Share Tech Mono;font-size:1.6rem;color:#e2e8f0;">${price:,.4f}</div>'
            f'<div style="font-family:Share Tech Mono;font-size:.78rem;color:{pc};">'
            f'{"▲" if pct>=0 else "▼"} {"+" if pct>=0 else ""}{pct:.2f}% vs clôture préc.</div>'
            f'</div>', unsafe_allow_html=True)

        otype = st.radio("Type", ["Par quantité","Par montant ($)"], horizontal=True, key="spot_type")
        if otype == "Par quantité":
            qty = st.number_input("Quantité", min_value=0.0001, value=1.0, step=0.001,
                                  key="spot_qty", format="%.4f")
            total_order = qty * price
        else:
            amount = st.number_input("Montant ($)", min_value=1.0,
                                     value=min(10000.0, port.get("cash",0)),
                                     step=100.0, key="spot_amount")
            qty = amount / price if price > 0 else 0
            total_order = amount

        hist = get_history(ticker, "1mo")
        if not hist.empty and "Close" in hist.columns:
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            fig = go.Figure(go.Scatter(
                x=hist.index, y=hist["Close"], mode="lines",
                line=dict(color="#00d4ff" if pct>=0 else "#ff3b6b", width=2),
                fill="tozeroy",
                fillcolor="rgba(0,212,255,.06)" if pct>=0 else "rgba(255,59,107,.06)"))
            fig.update_layout(**_P, height=130,
                xaxis=dict(showgrid=False, showticklabels=False),
                yaxis=dict(showgrid=False, tickfont=dict(size=9)))
            st.plotly_chart(fig, use_container_width=True)

    with col_r:
        cash    = port.get("cash", 0.0)
        pos_qty = port.get("holdings",{}).get(ticker,{}).get("qty", 0)
        st.markdown(
            f'<div style="background:rgba(0,212,255,.05);border:1px solid rgba(0,212,255,.15);'
            f'border-radius:8px;padding:14px;margin-bottom:12px;">'
            f'<div style="font-family:Rajdhani;font-size:.7rem;color:#00d4ff;letter-spacing:.1em;'
            f'text-transform:uppercase;margin-bottom:8px;">{port.get("emoji","")} {port.get("name","")}</div>'
            f'<div style="font-family:Share Tech Mono;font-size:.8rem;color:#e2e8f0;line-height:1.9;">'
            f'Cash : <b style="color:#00d4ff;">${cash:,.2f}</b><br>'
            f'Position {ticker} : <b style="color:#00d4ff;">{pos_qty:,.4f}</b><br>'
            f'Valeur ordre : <b style="color:#ffd700;">${total_order:,.2f}</b>'
            f'</div></div>', unsafe_allow_html=True)

        errors = []
        if not is_valid and is_buy:
            errors.append(f"❌ Actif incompatible avec la stratégie {port_type}")
        if is_buy and total_order > cash + 0.01:
            errors.append(f"❌ Fonds insuffisants")
        if not is_buy and qty > pos_qty + 1e-6:
            errors.append(f"❌ Position insuffisante ({pos_qty:,.4f} dispo)")
        if qty <= 0:
            errors.append("❌ Quantité invalide")

        for e in errors:
            st.markdown(f'<div style="background:rgba(255,59,107,.1);border:1px solid rgba(255,59,107,.3);'
                        f'border-radius:4px;padding:8px 12px;font-family:Share Tech Mono;font-size:.75rem;'
                        f'color:#ff3b6b;margin:3px 0;">{e}</div>', unsafe_allow_html=True)

        btn_c = "#00ff88" if is_buy else "#ff3b6b"
        st.markdown(
            f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.07);'
            f'border-radius:6px;padding:10px 14px;margin-bottom:10px;font-family:Share Tech Mono;font-size:.76rem;">'
            f'<b style="color:{btn_c}">{"ACHAT" if is_buy else "VENTE"}</b> · '
            f'<b style="color:#00d4ff;">{ticker}</b> · '
            f'<b style="color:#ffd700;">{qty:,.4f} unités @ ${price:,.4f}</b>'
            f'</div>', unsafe_allow_html=True)

        if st.button(f'{"✅ ACHETER" if is_buy else "🔴 VENDRE"} {qty:,.4f} × {ticker}',
                     disabled=bool(errors), key="spot_exec", type="primary" if not errors else "secondary"):
            err = record_trade(port, ticker, "BUY" if is_buy else "SELL", qty, price)
            if err: st.error(err)
            else:
                st.success(f"✅ {'Achat' if is_buy else 'Vente'} : {qty:,.4f} × {ticker} @ ${price:,.4f}")
                st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  OPTIONS DESK
# ══════════════════════════════════════════════════════════════════════════════

def _options_desk(port, state, team_id, port_id, assets_df):
    section_title("OPTIONS EUROPÉENNES — BLACK-SCHOLES", "⚙️")

    if "category" in assets_df.columns:
        opt_assets = assets_df[assets_df["category"].isin(["Equities","ETF","Crypto","Equity"])]
    else:
        opt_assets = assets_df
    if opt_assets.empty: opt_assets = assets_df

    ticker_opts = {f'{r["ticker"]} — {r.get("name",r["ticker"])}': r["ticker"]
                   for _, r in opt_assets.head(80).iterrows()}

    col_l, col_r = st.columns([1, 1])
    with col_l:
        sel    = st.selectbox("Sous-jacent", list(ticker_opts.keys()), key="opt_asset")
        ticker = ticker_opts[sel]
        spot   = get_price(ticker)
        st.markdown(f'<div style="font-family:Share Tech Mono;font-size:.78rem;color:#7a93b0;margin-bottom:8px;">'
                    f'Spot : <b style="color:#00d4ff;">${spot:,.4f}</b></div>', unsafe_allow_html=True)
        opt_type    = st.radio("Type", ["call","put"], horizontal=True, key="opt_type")
        K           = st.number_input("Strike (K)", 0.01, 1e6, max(round(spot,2),0.01), key="opt_K")
        T_days      = st.slider("Maturité (jours)", 1, 730, 30, key="opt_T")
        T           = T_days / 365.0
        r_rate      = st.slider("Taux sans risque (%)", 0.0, 10.0, 4.25, 0.1, key="opt_r") / 100
        sigma       = st.slider("Volatilité impl. (%)", 1.0, 150.0, 20.0, 0.5, key="opt_sig") / 100
        mult        = get_contract_mult(ticker)
        n_contracts = st.number_input(f"Contrats (×{mult})", min_value=1, value=1, step=1, key="opt_n")

    with col_r:
        premium       = bs_price(spot, K, T, r_rate, sigma, opt_type)
        greeks        = bs_greeks(spot, K, T, r_rate, sigma, opt_type)
        total_premium = premium * n_contracts * mult

        ratio = spot/K if K>0 else 1.0
        if opt_type=="call":
            mon,mc = ("IN THE MONEY","#00ff88") if ratio>1.02 else (("OUT THE MONEY","#ff3b6b") if ratio<0.98 else ("AT THE MONEY","#ffd700"))
        else:
            mon,mc = ("IN THE MONEY","#00ff88") if ratio<0.98 else (("OUT THE MONEY","#ff3b6b") if ratio>1.02 else ("AT THE MONEY","#ffd700"))

        st.markdown(
            f'<div style="background:rgba(0,0,0,.3);border:1px solid rgba(0,212,255,.2);border-radius:8px;padding:14px;margin-bottom:10px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
            f'<span style="font-family:Rajdhani;font-size:1rem;font-weight:700;color:#00d4ff;">PRIME / UNITÉ</span>'
            f'<span style="font-family:Rajdhani;font-size:.7rem;font-weight:700;color:{mc};background:{mc}22;'
            f'border:1px solid {mc}44;padding:2px 8px;border-radius:3px;">{mon}</span></div>'
            f'<div style="font-family:Share Tech Mono;font-size:2rem;color:#7c3aed;font-weight:bold;">${premium:,.4f}</div>'
            f'<div style="font-family:Share Tech Mono;font-size:.78rem;color:#7a93b0;margin-top:4px;">'
            f'TOTAL {n_contracts} contrat(s) × {mult} : <b style="color:#e2e8f0;">${total_premium:,.2f}</b></div>'
            f'</div>', unsafe_allow_html=True)

        g_cols = st.columns(2)
        for i,(gname,gval,gcol) in enumerate([
            ("Δ DELTA",  f'{greeks["delta"]:+.4f}',    "#00d4ff"),
            ("Γ GAMMA",  f'{greeks["gamma"]:.6f}',     "#00ff88"),
            ("Θ THETA",  f'{greeks["theta"]:+.4f}$/j', "#ff3b6b"),
            ("ν VEGA",   f'{greeks["vega"]:+.4f}$/1%', "#ff8c00"),
            ("ρ RHO",    f'{greeks["rho"]:+.4f}$/1%',  "#7c3aed"),
        ]):
            try: vf = float(gval.replace("+","").replace("$","").replace("/j","").replace("/1%",""))
            except: vf = 0
            sc = "#00ff88" if vf>=0 else "#ff3b6b"
            with g_cols[i%2]:
                st.markdown(
                    f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.06);'
                    f'border-radius:6px;padding:7px 10px;margin:3px 0;">'
                    f'<div style="font-family:Rajdhani;font-size:.65rem;color:{gcol};font-weight:700;">{gname}</div>'
                    f'<div style="font-family:Share Tech Mono;font-size:.8rem;color:{sc};font-weight:bold;">{gval}</div>'
                    f'</div>', unsafe_allow_html=True)

    # Payoff chart
    st.markdown("<br>", unsafe_allow_html=True)
    col_iv, col_pay = st.columns(2)
    with col_iv:
        section_title("VOL IMPLICITE", "🔍")
        mkt_p = st.number_input("Prix marché observé ($)", 0.01, 1e6, max(round(premium,4),0.01), key="iv_mkt")
        iv = implied_vol(mkt_p, spot, K, T, r_rate, opt_type)
        if iv:
            ic = "#00ff88" if iv<sigma else "#ff3b6b"
            st.markdown(f'<div style="background:rgba(124,58,237,.08);border:1px solid rgba(124,58,237,.3);'
                        f'border-radius:6px;padding:12px;text-align:center;">'
                        f'<div style="font-family:Rajdhani;font-size:.68rem;color:#7a93b0;letter-spacing:.15em;">VOL IMPLICITE</div>'
                        f'<div style="font-family:Share Tech Mono;font-size:2rem;color:{ic};font-weight:bold;">{iv*100:.2f}%</div>'
                        f'<div style="font-family:Share Tech Mono;font-size:.7rem;color:#475569;">vs {sigma*100:.2f}% saisi</div>'
                        f'</div>', unsafe_allow_html=True)
        else:
            st.warning("Calcul impossible pour ce prix.")

    with col_pay:
        section_title("PAYOFF EXPIRATION", "📉")
        spots_ = np.linspace(max(spot*0.6,0.01), spot*1.4, 400)
        pnl_   = n_contracts*mult*(np.maximum(spots_-K,0)-premium) if opt_type=="call" else n_contracts*mult*(np.maximum(K-spots_,0)-premium)
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=spots_,y=np.where(pnl_>=0,pnl_,0),fill="tozeroy",fillcolor="rgba(0,255,136,.1)",line=dict(color="rgba(0,0,0,0)"),showlegend=False,hoverinfo="skip"))
        fig2.add_trace(go.Scatter(x=spots_,y=np.where(pnl_<0,pnl_,0),fill="tozeroy",fillcolor="rgba(255,59,107,.1)",line=dict(color="rgba(0,0,0,0)"),showlegend=False,hoverinfo="skip"))
        fig2.add_trace(go.Scatter(x=spots_,y=pnl_,mode="lines",line=dict(color="#7c3aed",width=2),hovertemplate="$%{x:.2f} → P&L $%{y:,.2f}<extra></extra>"))
        fig2.add_hline(y=0,line_color="rgba(255,255,255,.2)")
        fig2.add_vline(x=spot,line_dash="dot",line_color="#ffd700",annotation_text=f"S={spot:.0f}",annotation_font_color="#ffd700")
        fig2.add_vline(x=K,line_dash="dash",line_color="#94a3b8",annotation_text=f"K={K:.0f}",annotation_font_color="#94a3b8")
        fig2.update_layout(**_P,height=200,xaxis=dict(title="Prix",gridcolor="rgba(255,255,255,.04)"),yaxis=dict(title="P&L $",gridcolor="rgba(255,255,255,.04)"))
        st.plotly_chart(fig2, use_container_width=True)

    # ── Ordre option ───────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("PASSER UN ORDRE OPTION", "✅")

    opt_action = st.radio("Sens", ["🟢 ACHETER (Long)","🔴 VENDRE (Short)"], horizontal=True, key="opt_action")
    is_buy_opt = "ACHETER" in opt_action
    cash       = port.get("cash", 0.0)

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        if opt_type=="call" and is_buy_opt:    ml,mg,be = total_premium,"Illimité",K+premium
        elif opt_type=="put" and is_buy_opt:   ml,mg,be = total_premium,f"${(K-premium)*n_contracts*mult:,.0f}",K-premium
        elif opt_type=="call" and not is_buy_opt: ml,mg,be = "Illimité",total_premium,K+premium
        else:                                  ml,mg,be = f"${(K-premium)*n_contracts*mult:,.0f}",total_premium,K-premium
        st.markdown(
            f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.07);border-radius:6px;padding:12px;font-family:Share Tech Mono;font-size:.78rem;">'
            f'<div style="font-family:Rajdhani;font-size:.68rem;color:#7a93b0;letter-spacing:.1em;margin-bottom:8px;">RÉCAP OPTION</div>'
            f'{"LONG" if is_buy_opt else "SHORT"} · <b style="color:#7c3aed;">{opt_type.upper()}</b> · '
            f'<b style="color:#00d4ff;">{ticker}</b><br>'
            f'K=<b>${K:,.2f}</b> · T=<b>{T_days}j</b> · σ=<b>{sigma*100:.0f}%</b><br>'
            f'<b style="color:#ffd700;">{n_contracts} × {mult} = {n_contracts*mult} unités</b><br>'
            f'Prime/unité : <b style="color:#7c3aed;">${premium:,.4f}</b><br>'
            f'<b style="color:#ffd700;">{"Coût" if is_buy_opt else "Prime reçue"} : ${total_premium:,.2f}</b>'
            f'</div>', unsafe_allow_html=True)
    with col_s2:
        st.markdown(
            f'<div style="background:rgba(124,58,237,.06);border:1px solid rgba(124,58,237,.2);border-radius:6px;padding:12px;font-family:Share Tech Mono;font-size:.78rem;">'
            f'<div style="font-family:Rajdhani;font-size:.68rem;color:#7a93b0;letter-spacing:.1em;margin-bottom:8px;">RISQUE / RENDEMENT</div>'
            f'Gain max : <span style="color:#00ff88;font-weight:bold;">{mg if isinstance(mg,str) else f"${mg:,.2f}"}</span><br>'
            f'Perte max : <span style="color:#ff3b6b;font-weight:bold;">{ml if isinstance(ml,str) else f"${ml:,.2f}"}</span><br>'
            f'Seuil rentabilité : <span style="color:#ff8c00;">${be:,.2f}</span><br>'
            f'Cash dispo : <span style="color:#00d4ff;">${cash:,.2f}</span>'
            f'</div>', unsafe_allow_html=True)

    opt_errors = []
    if is_buy_opt and total_premium > cash + 0.01:
        opt_errors.append(f"❌ Fonds insuffisants (besoin ${total_premium:,.2f}, cash ${cash:,.2f})")

    for e in opt_errors:
        st.markdown(f'<div style="background:rgba(255,59,107,.1);border:1px solid rgba(255,59,107,.3);'
                    f'border-radius:4px;padding:8px 12px;font-family:Share Tech Mono;font-size:.75rem;'
                    f'color:#ff3b6b;margin:3px 0;">{e}</div>', unsafe_allow_html=True)

    if st.button(
        f'{"✅ ACHETER" if is_buy_opt else "🔴 VENDRE"} {n_contracts} × {opt_type.upper()} K=${K:.2f} — ${total_premium:,.2f}',
        disabled=bool(opt_errors), key="opt_submit", type="primary"
    ):
        port.setdefault("options", []).append({
            "date":          datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ticker":        ticker,
            "type":          opt_type,
            "action":        "BUY" if is_buy_opt else "SELL",
            "strike":        round(K, 4),
            "maturity_days": T_days,
            "sigma":         round(sigma*100, 2),
            "n_contracts":   n_contracts,
            "contract_mult": mult,
            "premium":       round(premium, 6),
            "total_premium": round(total_premium, 2),
            "spot_at_entry": round(spot, 4),
            "currency":      get_currency(ticker),
        })
        port["cash"] = port.get("cash",0) + (-total_premium if is_buy_opt else total_premium)
        port.setdefault("trades",[]).append({
            "date":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ticker": f"{ticker} {opt_type.upper()} K={K:.2f}",
            "action": "BUY OPTION" if is_buy_opt else "SELL OPTION",
            "qty":    n_contracts, "price": round(premium,6), "total": round(total_premium,2),
        })
        persist()
        st.success(f"✅ Option enregistrée : {n_contracts}× {opt_type.upper()} K=${K:.2f} sur {ticker}")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  MES POSITIONS & PERFORMANCE (onglet 3)
# ══════════════════════════════════════════════════════════════════════════════

def _positions_tab(port, assets_df):
    holdings = port.get("holdings", {})
    options  = port.get("options",  [])
    trades   = port.get("trades",   [])
    cash     = port.get("cash", 0.0)
    init     = port.get("initial_cash", 1_000_000.0)
    strategy = port.get("portfolio_type", port.get("strategy","Libre"))

    # ── Fetch prix live ───────────────────────────────────────────────────────
    all_tk = set(holdings.keys()) | {o["ticker"] for o in options}
    live   = {}
    for tk in all_tk:
        p, pct = get_price_change(tk)
        if p and p==p and p>0:
            live[tk] = (float(p), float(pct))

    # ── KPIs globaux (spot + options) ─────────────────────────────────────────
    spot_mkt  = sum(holdings[tk].get("qty",0) * live.get(tk,(holdings[tk].get("avg_price",0),0))[0] for tk in holdings)
    spot_cost = sum(holdings[tk].get("qty",0) * holdings[tk].get("avg_price",0) for tk in holdings)
    spot_pnl  = spot_mkt - spot_cost

    # Options MTM P&L
    opt_pnl = 0.0
    for o in options:
        tk = o["ticker"]
        sp, _ = live.get(tk, (o["spot_at_entry"],0))
        T_rem = max(o.get("maturity_days",30)-1, 0.5)/365.0
        try:
            mtm = bs_price(sp, o["strike"], T_rem, 0.0425, o.get("sigma",20)/100, o["type"])
        except Exception:
            mtm = o["premium"]
        mult = o.get("contract_mult", get_contract_mult(tk))
        n    = o["n_contracts"]
        is_long = o.get("action","BUY") == "BUY"
        opt_pnl += (mtm - o["premium"])*n*mult if is_long else (o["premium"]-mtm)*n*mult

    total_val = cash + spot_mkt
    total_pnl = spot_pnl + opt_pnl
    pnl_pct   = total_pnl / init * 100 if init else 0
    pc        = _pnl_col(total_pnl)
    sg        = _sgn(total_pnl)

    # ── Bandeau performance ───────────────────────────────────────────────────
    ks = 'background:rgba(0,10,25,.7);border:1px solid rgba(0,212,255,.15);border-radius:8px;padding:12px 16px;'
    cols = st.columns(5)
    for col, lbl, val, vc in [
        (cols[0], "Valeur totale",   f"${total_val:,.0f}",    "#e2e8f0"),
        (cols[1], "Cash",            f"${cash:,.0f}",         "#00d4ff"),
        (cols[2], "Positions spot",  f"${spot_mkt:,.0f}",     "#e2e8f0"),
        (cols[3], "P&L spot",        f"{sg}${abs(spot_pnl):,.2f}", pc),
        (cols[4], f"P&L total ({strategy[:8]})", f"{sg}${abs(total_pnl):,.2f} ({sg}{abs(pnl_pct):.2f}%)", pc),
    ]:
        col.markdown(f'<div style="{ks}"><div style="font-family:Rajdhani;font-size:.62rem;color:#475569;letter-spacing:.1em;text-transform:uppercase;">{lbl}</div>'
                     f'<div style="font-family:Share Tech Mono;font-size:1rem;color:{vc};font-weight:bold;margin-top:3px;">{val}</div></div>',
                     unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── TAB interne : Holdings / Options / Historique ─────────────────────────
    sub_hold, sub_opt, sub_hist = st.tabs([
        f"📊 HOLDINGS ({len(holdings)} position{'s' if len(holdings)!=1 else ''})",
        f"⚙️ OPTIONS ({len(options)} position{'s' if len(options)!=1 else ''})",
        f"🔄 HISTORIQUE ({len(trades)} trade{'s' if len(trades)!=1 else ''})",
    ])

    # ── HOLDINGS ──────────────────────────────────────────────────────────────
    with sub_hold:
        if not holdings:
            st.info("Aucune position spot ouverte. Tradez depuis l'onglet Spot Trading.")
        else:
            hdr = ["TICKER","QTÉ","PX ENTRÉE","PX ACTUEL","VAR 1J","VALEUR","P&L $","P&L %","POIDS"]
            th  = "".join(f'<th style="font-family:Rajdhani;font-size:.63rem;color:#00d4ff;letter-spacing:.08em;'
                          f'text-transform:uppercase;padding:7px 10px;background:rgba(0,212,255,.06);'
                          f'border-bottom:1px solid rgba(0,212,255,.15);">{c}</th>' for c in hdr)
            tbody = ""
            for tk, pos in sorted(holdings.items(), key=lambda x: x[1].get("qty",0)*live.get(x[0],(x[1].get("avg_price",0),0))[0], reverse=True):
                qty     = pos.get("qty",0)
                avg     = pos.get("avg_price",0.0)
                curr,pd_= live.get(tk,(avg,0.0))
                mkt     = qty*curr; cost = qty*avg; pnl = mkt-cost
                ppct    = pnl/cost*100 if cost else 0
                weight  = mkt/total_val*100 if total_val else 0
                pc_     = _pnl_col(pnl); dc_ = _pnl_col(pd_)
                tbody += (
                    f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
                    f'<td style="padding:7px 10px;color:#00d4ff;font-weight:bold;font-family:Rajdhani;font-size:.85rem;">{tk}</td>'
                    f'<td style="padding:7px 10px;">{qty:,.4f}</td>'
                    f'<td style="padding:7px 10px;color:#7a93b0;">{_fmt(avg)}</td>'
                    f'<td style="padding:7px 10px;color:#e2e8f0;">{_fmt(curr)}</td>'
                    f'<td style="padding:7px 10px;color:{dc_};">{_arr(pd_)} {_sgn(pd_)}{abs(pd_):.2f}%</td>'
                    f'<td style="padding:7px 10px;">{_fmt(mkt)}</td>'
                    f'<td style="padding:7px 10px;color:{pc_};font-weight:bold;">{_sgn(pnl)}${abs(pnl):,.2f}</td>'
                    f'<td style="padding:7px 10px;color:{pc_};">{_arr(pnl)} {_sgn(pnl)}{abs(ppct):.2f}%</td>'
                    f'<td style="padding:7px 10px;">'
                    f'<div style="background:rgba(0,212,255,.12);border-radius:2px;height:4px;overflow:hidden;margin-bottom:2px;">'
                    f'<div style="width:{min(weight,100):.0f}%;height:100%;background:#00d4ff;"></div></div>'
                    f'<span style="font-size:.63rem;color:#475569;">{weight:.1f}%</span></td>'
                    f'</tr>'
                )
            # Total
            tc_ = _pnl_col(spot_pnl)
            tbody += (f'<tr style="background:rgba(0,212,255,.05);border-top:1px solid rgba(0,212,255,.2);">'
                      f'<td colspan="5" style="padding:7px 10px;font-family:Rajdhani;font-size:.7rem;color:#475569;letter-spacing:.1em;">TOTAL SPOT — {len(holdings)} positions</td>'
                      f'<td style="padding:7px 10px;color:#e2e8f0;font-weight:bold;">{_fmt(spot_mkt)}</td>'
                      f'<td style="padding:7px 10px;color:{tc_};font-weight:bold;">{_sgn(spot_pnl)}${abs(spot_pnl):,.2f}</td>'
                      f'<td style="padding:7px 10px;color:{tc_};">{_sgn(spot_pnl)}{abs(spot_pnl/spot_cost*100 if spot_cost else 0):.2f}%</td>'
                      f'<td></td></tr>')
            st.markdown(f'<div style="overflow-x:auto;border:1px solid rgba(0,212,255,.12);border-radius:8px;">'
                        f'<table style="width:100%;border-collapse:collapse;font-family:Share Tech Mono;font-size:.76rem;color:#e2e8f0;">'
                        f'<thead><tr>{th}</tr></thead><tbody>{tbody}</tbody></table></div>',
                        unsafe_allow_html=True)

            # Mini pie
            if len(holdings) > 1:
                labels = list(holdings.keys()) + ["Cash"]
                values = [holdings[tk].get("qty",0)*live.get(tk,(holdings[tk].get("avg_price",0),0))[0] for tk in holdings] + [cash]
                import plotly.express as px
                fig_pie = go.Figure(go.Pie(labels=labels,values=values,hole=0.55,
                    textfont=dict(family="Share Tech Mono",size=10),
                    marker=dict(colors=px.colors.qualitative.Dark24)))
                fig_pie.update_layout(**_P,height=240,showlegend=True,
                    legend=dict(font=dict(size=9,family="Share Tech Mono"),bgcolor="rgba(0,0,0,0)"))
                st.plotly_chart(fig_pie, use_container_width=True)

    # ── OPTIONS OUVERTES ──────────────────────────────────────────────────────
    with sub_opt:
        if not options:
            st.info("Aucune position option ouverte. Tradez depuis l'onglet Options.")
        else:
            hdr_o = ["SOUS-JAC.","C/P","STRIKE","EXPIRATION","QTÉ","MULT","PRIME ENTRÉE","PRIME MTM","VALEUR MTM","P&L","DELTA Σ"]
            th_o  = "".join(f'<th style="font-family:Rajdhani;font-size:.60rem;color:#7c3aed;letter-spacing:.08em;'
                            f'text-transform:uppercase;padding:7px 10px;background:rgba(124,58,237,.06);'
                            f'border-bottom:1px solid rgba(124,58,237,.15);">{c}</th>' for c in hdr_o)
            tbody_o = ""; total_opt_val = 0.0
            for o in options:
                tk   = o["ticker"]
                sp,_ = live.get(tk,(o["spot_at_entry"],0))
                T_rem= max(o.get("maturity_days",30)-1,0.5)/365.0
                mult = o.get("contract_mult",get_contract_mult(tk))
                n    = o["n_contracts"]
                avg_p= o["premium"]
                try:
                    mtm_p = bs_price(sp,o["strike"],T_rem,0.0425,o.get("sigma",20)/100,o["type"])
                    g_    = bs_greeks(sp,o["strike"],T_rem,0.0425,o.get("sigma",20)/100,o["type"])
                    delta = g_["delta"]*n*mult
                except Exception:
                    mtm_p=avg_p; delta=0.0
                mtm_val   = mtm_p*n*mult
                is_long   = o.get("action","BUY")=="BUY"
                pnl_o     = (mtm_p-avg_p)*n*mult if is_long else (avg_p-mtm_p)*n*mult
                total_opt_val += mtm_val
                pc_o = _pnl_col(pnl_o)
                cp_c = "#00ff88" if o["type"]=="call" else "#ff3b6b"
                tbody_o += (
                    f'<tr style="border-bottom:1px solid rgba(255,255,255,.04);">'
                    f'<td style="padding:7px 10px;color:#7c3aed;font-weight:bold;">{tk}</td>'
                    f'<td style="padding:7px 10px;color:{cp_c};font-weight:bold;">{"C" if o["type"]=="call" else "P"}</td>'
                    f'<td style="padding:7px 10px;">{o["strike"]:,.4f}</td>'
                    f'<td style="padding:7px 10px;color:#7a93b0;">{o.get("date","—")[:10]}</td>'
                    f'<td style="padding:7px 10px;">{n}</td>'
                    f'<td style="padding:7px 10px;color:#475569;">{mult}</td>'
                    f'<td style="padding:7px 10px;color:#7a93b0;">{avg_p:,.4f}</td>'
                    f'<td style="padding:7px 10px;color:#e2e8f0;">{mtm_p:,.4f}</td>'
                    f'<td style="padding:7px 10px;">${mtm_val:,.2f}</td>'
                    f'<td style="padding:7px 10px;color:{pc_o};font-weight:bold;">{_sgn(pnl_o)}${abs(pnl_o):,.2f}</td>'
                    f'<td style="padding:7px 10px;color:#94a3b8;">{delta:,.4f}</td>'
                    f'</tr>'
                )
            # Total options
            tc_o = _pnl_col(opt_pnl)
            tbody_o += (f'<tr style="background:rgba(124,58,237,.05);border-top:1px solid rgba(124,58,237,.2);">'
                        f'<td colspan="8" style="padding:7px 10px;font-family:Rajdhani;font-size:.7rem;color:#475569;letter-spacing:.1em;">TOTAL OPTIONS — {len(options)} positions</td>'
                        f'<td style="padding:7px 10px;color:#e2e8f0;font-weight:bold;">${total_opt_val:,.2f}</td>'
                        f'<td style="padding:7px 10px;color:{tc_o};font-weight:bold;">{_sgn(opt_pnl)}${abs(opt_pnl):,.2f}</td>'
                        f'<td></td></tr>')
            st.markdown(f'<div style="overflow-x:auto;border:1px solid rgba(124,58,237,.15);border-radius:8px;">'
                        f'<table style="width:100%;border-collapse:collapse;font-family:Share Tech Mono;font-size:.75rem;color:#e2e8f0;">'
                        f'<thead><tr>{th_o}</tr></thead><tbody>{tbody_o}</tbody></table></div>',
                        unsafe_allow_html=True)

    # ── HISTORIQUE ─────────────────────────────────────────────────────────────
    with sub_hist:
        if not trades:
            st.info("Aucune transaction enregistrée.")
        else:
            df = pd.DataFrame(trades[::-1])
            st.dataframe(df, use_container_width=True, hide_index=True)
