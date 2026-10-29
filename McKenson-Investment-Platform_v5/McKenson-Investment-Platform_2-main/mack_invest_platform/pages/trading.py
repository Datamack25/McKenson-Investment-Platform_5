# pages/trading.py  —  MAM v5.1
"""
3 onglets :
  1. SPOT TRADING — univers filtrable (dont ETF), fiches ETF, portefeuilles modèles
     ETF, contrôles de conformité expliqués avant chaque ordre
  2. OPTIONS (Black-Scholes) — option simple + stratégies multi-jambes selon le
     régime de marché, avec contrôles produits complexes
  3. MES POSITIONS — Holdings spot + Options + Historique + Exposition & conformité
"""
from __future__ import annotations
import math
import uuid
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
    get_contract_mult, get_currency, get_price_source,
)
from utils.options import bs_price, bs_greeks, implied_vol
from utils.compliance import (
    PORTFOLIO_TYPES, CATEGORY_MAP, validate_mandate, normalize_port_type,
    pre_trade_spot, pre_trade_options, log_decision, render_decision,
    render_profile_panel, render_rules_reference, get_profile, recent_log, HARD_LIMITS,
)
from utils.legal import render_risk_banner
from utils.sectors import sector_of, option_sector, short_sector
import html as _h

_P = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#94a3b8", family="Share Tech Mono"),
    margin=dict(l=8, r=8, t=28, b=8),
)

# Univers proposés dans le sélecteur d'actifs (catégories de data/assets*.csv)
UNIVERSES = {
    "Tous": None,
    "🧺 ETF": ["ETF"],
    "📈 Actions": ["Equity", "Equities"],
    "₿ Crypto": ["Crypto"],
    "🛢️ Matières premières": ["Commodity", "Commodities", "Futures"],
    "💱 Devises & indices": ["Forex", "Index"],
    "🔌 Thèmes": "THEMES",          # paniers thématiques / chaînes de valeur (utils/themes.py)
}


def _validate(asset_row: pd.Series, port_type: str) -> tuple[bool, str]:
    return validate_mandate(str(asset_row.get("category", "Equities")), port_type)


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

    # ── Profil investisseur (adéquation / caractère approprié) ────────────────
    render_profile_panel()

    # ── Comité virtuel : politique d'investissement et validation du portefeuille ─
    from components.committee_ui import committee_panel
    committee_panel(port, key=f"td_cm_{port_id}")
    from components.proposal_ui import proposal_panel
    proposal_panel(port, key=f"td_pp_{port_id}")

    # ── Sélecteur de stratégie ────────────────────────────────────────────────
    current_type = normalize_port_type(port)

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
    with tab_opt:
        render_risk_banner("options")
        sub_single, sub_strat = st.tabs(["⚙️ OPTION SIMPLE", "🎯 STRATÉGIES SELON LE MARCHÉ"])
        with sub_single: _options_desk(port, state, team_id, port_id, assets_df)
        with sub_strat:  _strategy_desk(port, assets_df)
    with tab_pos:  _positions_tab(port, assets_df)


# ══════════════════════════════════════════════════════════════════════════════
#  SPOT TRADING
# ══════════════════════════════════════════════════════════════════════════════

def _etf_card(ticker: str):
    """Fiche synthétique d'un ETF (frais, UCITS, PEA, zone)."""
    try:
        from utils.etf_universe import etf_meta, etf_class
    except Exception:
        return
    meta = etf_meta(ticker)
    cls = etf_class(ticker)
    if not meta and not cls:
        return
    if meta:
        body = (f'<b style="color:#e2e8f0;">{meta.get("name", ticker)}</b><br>'
                f'{meta.get("description", "")}<br>'
                f'Classe : <b>{cls}</b> · Zone : <b>{meta.get("zone", "—")}</b><br>'
                f'Frais courants (TER) : <b style="color:#ffd700;">{float(meta.get("ter_pct", 0)):.2f} %/an</b> · '
                f'UCITS : <b>{meta.get("ucits", "—")}</b> · PEA : <b>{meta.get("pea", "—")}</b> · '
                f'Diversifié : <b>{meta.get("diversifie", "—")}</b>')
    else:
        body = f'ETF · classe de risque : <b>{cls}</b>'
    st.markdown(
        f'<div style="border-left:3px solid #00d4ff;background:rgba(0,212,255,.05);border-radius:4px;'
        f'padding:8px 12px;font-family:Share Tech Mono;font-size:.7rem;color:#94a3b8;line-height:1.7;margin:6px 0;">'
        f'🧺 {body}<br><span style="color:#475569;font-size:.64rem;">Frais indicatifs : vérifiez le DIC (document '
        f'd\'informations clés) du fonds.</span></div>', unsafe_allow_html=True)


def _etf_models(port, port_type):
    """Portefeuilles modèles 100 % ETF pour petits investisseurs, avec contrôle de conformité."""
    from utils.etf_universe import ETF_MODELS, model_summary, model_ter
    from utils.auto_portfolio import plan_orders, execute_orders

    with st.expander("🧺 PORTEFEUILLES MODÈLES 100 % ETF — pour investir simplement et à moindre coût"):
        st.caption("Pour les investisseurs qui préfèrent ne pas choisir des actions une à une : quelques ETF "
                   "indiciels larges suffisent à diversifier sur des milliers d'entreprises, avec des frais "
                   "réduits. Chaque modèle respecte les limites du profil indiqué.")
        name = st.selectbox("Modèle", list(ETF_MODELS), key="etf_model_sel")
        model = ETF_MODELS[name]
        prof = get_profile()
        c1, c2, c3 = st.columns(3)
        c1.metric("Profil cible", model["profil"])
        c2.metric("Frais moyens (TER)", f"{model_ter(name):.2%}/an")
        c3.metric("Nombre de lignes", len(model["poids"]))
        st.markdown(f"_{model['idee']}_")
        df = model_summary(name)
        st.dataframe(df.style.format({"Poids": "{:.0%}", "Frais (TER)": "{:.2%}"}),
                     use_container_width=True, hide_index=True)
        if model["profil"] != prof["risque"]:
            st.warning(f"Ce modèle vise un profil **{model['profil']}** ; votre profil est **{prof['risque']}**. "
                       "Les contrôles de conformité peuvent bloquer une partie des ordres.")
        if port_type not in ("Libre", "ETF Core", "Global Macro"):
            st.info(f"Le mandat « {port_type} » peut interdire certaines classes (obligations, or…). "
                    "Choisissez la stratégie « 🧺 ETF Core » ou « Libre » pour appliquer un modèle complet.")
        pct = st.slider("Part du cash à investir", 0.1, 1.0, 0.9, 0.05, key="etf_model_pct")
        w = pd.Series(model["poids"], dtype=float)
        live = get_multi_prices(tuple(sorted(set(w.index) | set(port.get("holdings", {}).keys()))))
        orders = plan_orders(port, w, live, pct, "cash", cash_proxy="__none__")
        if orders.empty:
            st.info("Aucun ordre à passer (cash insuffisant).")
            return
        st.dataframe(orders.style.format({"qty": "{:,.4f}", "price": "{:,.2f}", "montant": "{:,.0f}"}),
                     use_container_width=True, hide_index=True)
        # ── Avis du comité sur le portefeuille obtenu (profil + politique d'investissement) ──
        vetoed, rev = False, None
        if st.checkbox("🧑‍⚖️ Soumettre le portefeuille obtenu au comité (obligatoire avant d'investir)",
                       key="etf_model_cm"):
            try:
                from utils import committee as CM
                from components.committee_ui import get_context, portfolio_values, render_review
                vals, cash0, _ = portfolio_values(port)
                proj = dict(vals)
                for _, o in orders.iterrows():
                    proj[o["ticker"]] = proj.get(o["ticker"], 0.0) + (o["montant"] if o["action"] == "BUY"
                                                                      else -o["montant"])
                proj = {t: v for t, v in proj.items() if v > 1}
                nav0 = cash0 + sum(vals.values())
                ips = port.get("ips") or CM.default_ips(prof["risque"])
                rev = CM.review_portfolio(proj, max(nav0 - sum(proj.values()), 0.0), ips, get_context(),
                                          options=port.get("options", []), options_ok=prof.get("options_ok", False),
                                          port_type=port_type, label=port.get("name", "Portefeuille"), port=port)
                render_review(rev)
                vetoed = rev["verdict"] == "veto"
                if vetoed:
                    st.error("⛔ Le comité oppose son veto : ce modèle ne convient pas à la politique "
                             "d'investissement de ce portefeuille. Choisissez un modèle plus adapté à votre profil.")
            except Exception as e:  # noqa: BLE001
                st.caption(f"Avis du comité indisponible ({e}).")
                vetoed = True
        ok = st.checkbox("Je confirme l'exécution simulée de ces ordres (chacun est contrôlé par la conformité)",
                         key="etf_model_ok", disabled=rev is None or vetoed)
        if st.button("🧺 INVESTIR DANS CE MODÈLE", disabled=not ok or rev is None or vetoed, key="etf_model_go",
                     use_container_width=True):
            from utils.committee import summary_for_storage
            port["committee"] = summary_for_storage(rev)
            errs = execute_orders(port, orders, tag=f"modèle ETF {name}")
            persist()
            if errs:
                st.warning("Ordres partiellement exécutés :\n\n- " + "\n- ".join(errs))
            else:
                st.success(f"✅ {len(orders)} ordres exécutés — modèle « {name} ».")


def _spot_desk(port, state, team_id, port_id, assets_df, port_type="Libre"):
    section_title("ORDRE SPOT", "📈")
    _etf_models(port, port_type)
    col_l, col_r = st.columns([1, 1])

    with col_l:
        univ = st.radio("Univers", list(UNIVERSES), horizontal=True, key="spot_universe")
        cats = UNIVERSES[univ]
        if cats == "THEMES":
            from utils.themes import THEMES, theme_universe
            th_name = st.selectbox("Thème", list(THEMES), key="spot_theme",
                                   format_func=lambda n: f"{THEMES[n]['emoji']} {n}")
            st.caption(THEMES[th_name]["idee"] + f" Risque commun : {THEMES[th_name]['risque_commun']}.")
            df_u = assets_df[assets_df["ticker"].isin(theme_universe(th_name))]
        else:
            df_u = assets_df if not cats or "category" not in assets_df.columns \
                else assets_df[assets_df["category"].isin(cats)]
        if df_u.empty:
            df_u = assets_df
        ticker_opts = {f'{r["ticker"]} — {r.get("name",r["ticker"])}': r["ticker"]
                       for _, r in df_u.iterrows()}
        sel    = st.selectbox("Actif", list(ticker_opts.keys()), key="spot_asset")
        ticker = ticker_opts[sel]
        a_row  = assets_df[assets_df["ticker"]==ticker]
        a_s    = a_row.iloc[0] if not a_row.empty else pd.Series({"category":"Equities"})
        if str(a_s.get("category", "")) == "ETF":
            _etf_card(ticker)

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

        # v5.8 : coûts de transaction estimés (écart, courtage, taxes de bourse)
        from utils.costs import spot_costs
        _c = spot_costs(ticker, "BUY" if is_buy else "SELL", qty, price)
        _net = qty * _c["prix"] + (_c["frais"] if is_buy else -_c["frais"])
        st.markdown(
            f'<div style="border-left:3px solid #ffd700;background:rgba(255,215,0,.05);border-radius:4px;'
            f'padding:6px 12px;font-family:Share Tech Mono;font-size:.7rem;color:#cbd5e1;line-height:1.6;margin:4px 0;">'
            f'💸 <b>Coûts estimés</b> — prix d\'exécution {"acheteur" if is_buy else "vendeur"} ${_c["prix"]:,.4f} '
            f'(cours médian ${price:,.4f}) · frais ${_c["frais"]:,.2f}<br>{_c["detail"]}<br>'
            f'<b>{"Débit" if is_buy else "Crédit"} total : ${_net:,.2f}</b></div>', unsafe_allow_html=True)
        # Contrôles de conformité pré-négociation (mêmes contrôles qu'à l'exécution)
        decision = pre_trade_spot(port, ticker, "BUY" if is_buy else "SELL", qty, price,
                                  category=str(a_s.get("category", "Equity")))
        render_decision(decision)
        errors = [c for c in decision.blocks]
        from components.desk_tools_ui import derogation_request, earnings_notice, thesis_form
        derogation_request(port, ticker, decision, str(a_s.get("category", "Equity")), key=f"spot_{port_id}")
        earnings_notice(ticker)
        thesis, _missing = thesis_form(f"spot_th_{port_id}", ticker, is_buy)

        btn_c = "#00ff88" if is_buy else "#ff3b6b"
        st.markdown(
            f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.07);'
            f'border-radius:6px;padding:10px 14px;margin-bottom:10px;font-family:Share Tech Mono;font-size:.76rem;">'
            f'<b style="color:{btn_c}">{"ACHAT" if is_buy else "VENTE"}</b> · '
            f'<b style="color:#00d4ff;">{ticker}</b> · '
            f'<b style="color:#ffd700;">{qty:,.4f} unités @ ${price:,.4f}</b>'
            f'</div>', unsafe_allow_html=True)

        if st.button(f'{"✅ ACHETER" if is_buy else "🔴 VENDRE"} {qty:,.4f} × {ticker}',
                     disabled=bool(errors) or thesis is None, key="spot_exec",
                     type="primary" if not errors and thesis else "secondary"):
            err = record_trade(port, ticker, "BUY" if is_buy else "SELL", qty, price, source="Trading Desk",
                               meta={"these": thesis})
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

    # Contrôles de conformité « produits complexes » (vente non couverte, profil, budget…)
    legs = [{"type": opt_type, "qty": n_contracts if is_buy_opt else -n_contracts,
             "K": float(K), "premium": float(premium)}]
    decision, _an = pre_trade_options(port, ticker, legs, spot=spot, mult=mult, T_days=T_days,
                                      r=r_rate, sigma=sigma)
    render_decision(decision)
    opt_errors = decision.blocks

    if st.button(
        f'{"✅ ACHETER" if is_buy_opt else "🔴 VENDRE"} {n_contracts} × {opt_type.upper()} K=${K:.2f} — ${total_premium:,.2f}',
        disabled=bool(opt_errors), key="opt_submit", type="primary"
    ):
        decision, _an = pre_trade_options(port, ticker, legs, spot=spot, mult=mult, T_days=T_days,
                                          r=r_rate, sigma=sigma)
        log_decision(decision, port, f"{ticker} {opt_type.upper()} K={K:.2f}",
                     "BUY OPTION" if is_buy_opt else "SELL OPTION", n_contracts, premium,
                     executed=decision.allowed, note="Option simple")
        if not decision.allowed:
            st.error("⛔ Ordre bloqué par la conformité : " + decision.short_reason())
            return
        from utils.options import book_option   # une ligne par instrument (v5.5)
        from utils.costs import option_costs    # v5.8 : écart sur la prime + commission par contrat
        from utils import ledger as LG
        _oc = option_costs("BUY" if is_buy_opt else "SELL", n_contracts, premium)
        premium = _oc["prime"]
        total_premium = premium * n_contracts * mult
        if _oc["frais"]:
            LG.add(port, "frais", _oc["frais"], ticker=ticker, detail=f"commission {n_contracts} contrat(s) d'options")
        _book = book_option(port, {
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
            "currency":      "USD",   # v5.8 : primes en USD
        })
        port["cash"] = port.get("cash",0) + (-total_premium if is_buy_opt else total_premium)
        port.setdefault("trades",[]).append({
            "date":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ticker": f"{ticker} {opt_type.upper()} K={K:.2f}",
            "action": "BUY OPTION" if is_buy_opt else "SELL OPTION",
            "qty":    n_contracts, "price": round(premium,6), "total": round(total_premium,2),
        })
        persist()
        st.success(f"✅ Option enregistrée : {n_contracts}× {opt_type.upper()} K=${K:.2f} sur {ticker} ({_book})")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  STRATÉGIES D'OPTIONS SELON LE RÉGIME DE MARCHÉ
# ══════════════════════════════════════════════════════════════════════════════

def _official_regime() -> dict:
    """Régime OFFICIEL du comité (8 facteurs, Jean-Michel TAUX-BAS) ; repli : lecture S&P 500 + VIX."""
    from utils.option_strategies import quick_regime
    try:
        from components.committee_ui import get_context
        ctx = get_context()
        m = ctx["macro"]
        if not ctx.get("data_sim"):
            top = sorted(m.factors.items(), key=lambda kv: -abs(kv[1]))[:3]
            return dict(regime=m.regime, vix=ctx.get("vix"), trend=float("nan"), ok=True,
                        explication=m.regime_text + " Facteurs dominants : "
                        + ", ".join(f"{k} {v:+.1f}" for k, v in top) + ".",
                        source="Régime officiel du comité — Jean-Michel TAUX-BAS, 8 facteurs macro (Hedge Fund Agent).")
    except Exception:
        pass
    out = quick_regime()
    out["source"] = "Lecture simplifiée (tendance S&P 500 + VIX) : données du comité indisponibles."
    return out


def _strategy_desk(port, assets_df):
    from utils.option_strategies import (
        CATALOG, REGIMES, LEVEL_LABEL, recommend, quick_regime, build_legs, usage_level,
    )
    from utils.compliance import OPTION_RANK

    section_title("STRATÉGIES D'OPTIONS SELON LES CONDITIONS DE MARCHÉ", "🎯")
    prof = get_profile()
    allowed_level = HARD_LIMITS[prof["risque"]]["options"]

    # ── 1. Régime de marché ───────────────────────────────────────────────────
    if "strat_regime" not in st.session_state:
        st.session_state["strat_regime"] = _official_regime()
    rg = st.session_state["strat_regime"]
    c1, c2 = st.columns([2, 1])
    with c1:
        col = "#00ff88" if rg["ok"] else "#ffd700"
        st.markdown(
            f'<div style="border-left:3px solid {col};background:rgba(0,0,0,.25);border-radius:4px;'
            f'padding:8px 12px;font-family:Share Tech Mono;font-size:.74rem;color:#cbd5e1;line-height:1.7;">'
            f'<b style="color:{col};">RÉGIME DÉTECTÉ : {rg["regime"].upper()}</b><br>{rg["explication"]}<br>'
            f'<span style="color:#475569;font-size:.66rem;">{rg.get("source", "")}</span></div>',
            unsafe_allow_html=True)
    with c2:
        regime = st.selectbox("Régime retenu", REGIMES,
                              index=REGIMES.index(rg["regime"]) if rg["regime"] in REGIMES else 0,
                              key="strat_regime_sel",
                              help="Vous pouvez remplacer le régime détecté par votre propre lecture du marché.")
        if st.button("🔄 Relire le marché", key="strat_regime_refresh", use_container_width=True):
            st.session_state.pop("strat_regime", None)
            st.rerun()

    # ── 2. Recommandations ────────────────────────────────────────────────────
    recs = recommend(regime, rg.get("vix"))
    st.markdown('<div style="font-family:Rajdhani;font-size:.75rem;color:#7a93b0;letter-spacing:.1em;'
                'margin:10px 0 4px;">STRATÉGIES ADAPTÉES À CE RÉGIME</div>', unsafe_allow_html=True)
    if recs and recs[0].get("vol"):
        st.caption("📊 " + recs[0]["vol"])
    cols = st.columns(len(recs)) if recs else []
    for col, r in zip(cols, recs):
        spec = CATALOG[r["nom"]]
        ok_lvl = OPTION_RANK[spec["niveau"]] <= OPTION_RANK[allowed_level]
        badge = ("✅ autorisée pour votre profil" if ok_lvl else f"🔒 non autorisée (profil {prof['risque']})")
        bc = "#00ff88" if ok_lvl else "#ff3b6b"
        col.markdown(
            f'<div style="border:1px solid rgba(124,58,237,.3);background:rgba(124,58,237,.06);border-radius:8px;'
            f'padding:10px 12px;font-family:Share Tech Mono;font-size:.7rem;color:#94a3b8;line-height:1.6;min-height:170px;">'
            f'<b style="color:#e2e8f0;font-size:.8rem;">{r["nom"]}</b><br>'
            f'<span style="color:#7c3aed;">{spec["vue"]}</span><br>{r["raison"]}<br>'
            f'<span style="color:{bc};font-size:.66rem;">{badge}</span></div>', unsafe_allow_html=True)

    # ── 3. Construction ───────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("CONSTRUIRE ET ANALYSER LA STRATÉGIE", "🧩")
    names = [r["nom"] for r in recs] + [n for n in CATALOG if n not in [r["nom"] for r in recs]]
    if "category" in assets_df.columns:
        und = assets_df[assets_df["category"].isin(["Equity", "Equities", "ETF"])]
    else:
        und = assets_df
    held = [t for t in port.get("holdings", {}) if t in set(und["ticker"])]
    und_opts = held + [t for t in und["ticker"] if t not in held]

    cl, cr = st.columns([1, 1])
    with cl:
        name = st.selectbox("Stratégie", names, key="strat_name")
        spec = CATALOG[name]
        ticker = st.selectbox("Sous-jacent (titres détenus en premier)", und_opts, key="strat_und",
                              format_func=lambda t: f"{t} {'· détenu' if t in held else ''}")
        spot = get_price(ticker)
        mult = get_contract_mult(ticker)
        T_days = st.slider("Échéance (jours)", 7, 365, 45, key="strat_T")
        _v = rg.get("vix")
        _sig0 = float(min(80.0, max(10.0, _v))) if isinstance(_v, (int, float)) and math.isfinite(_v) else 20.0
        sigma = st.slider("Volatilité implicite (%)", 5.0, 120.0, _sig0, 0.5, key="strat_sig",
                          help="Par défaut : niveau du VIX (volatilité implicite du S&P 500).") / 100
        r_rate = st.slider("Taux sans risque (%)", 0.0, 10.0, 4.0, 0.1, key="strat_r") / 100
        n = st.number_input(f"Nombre de contrats (×{mult} titres)", 1, 100, 1, key="strat_n")
        holding = float(port.get("holdings", {}).get(ticker, {}).get("qty", 0.0))
        with_stock = False
        if spec["stock"]:
            need = spec["stock"] * n * mult
            if holding >= need:
                st.caption(f"✅ Vous détenez {holding:,.0f} titres {ticker} : la stratégie s'appuie sur ces titres.")
            else:
                with_stock = st.checkbox(
                    f"Acheter aussi {need - holding:,.0f} titres {ticker} (≈ ${(need - holding) * spot:,.0f}) "
                    f"pour couvrir la stratégie", value=True, key="strat_buy_stock")
    T = T_days / 365.0
    legs = build_legs(name, spot, T, r_rate, sigma, n_contracts=int(n), with_stock=False)
    if with_stock:
        legs.insert(0, {"type": "stock", "qty": (spec["stock"] * n * mult - holding) / mult, "entry": spot})

    decision, an = pre_trade_options(port, ticker, legs, spot=spot, mult=mult, T_days=T_days,
                                     r=r_rate, sigma=sigma)
    # analyse « économique » incluant les titres déjà détenus pour le profil de gain
    covered = min(holding, spec["stock"] * n * mult) if spec["stock"] else 0.0
    view_legs = ([{"type": "stock", "qty": covered / mult, "entry": spot}] if covered else []) + legs
    from utils.option_strategies import analyze
    an_view = analyze(view_legs, spot, mult, T, r_rate, sigma)

    with cr:
        lvl = usage_level(legs, mult, shares_held=holding)
        net = an["net_premium"]
        g_txt = "illimité" if an_view["unlimited_gain"] else f"${an_view['max_gain']:,.0f}"
        l_txt = "illimitée" if an_view["unlimited_loss"] else f"${an_view['max_loss']:,.0f}"
        be_txt = ", ".join(f"${b:,.2f}" for b in an_view["breakevens"][:3]) or "—"
        st.markdown(
            f'<div style="background:rgba(0,0,0,.3);border:1px solid rgba(124,58,237,.3);border-radius:8px;'
            f'padding:12px 14px;font-family:Share Tech Mono;font-size:.74rem;color:#cbd5e1;line-height:1.8;">'
            f'<b style="color:#7c3aed;font-size:.85rem;">{name}</b> · {spec["vue"]}<br>'
            f'Spot {ticker} : <b>${spot:,.2f}</b> · {n} contrat(s) × {mult}<br>'
            f'Prime nette : <b style="color:{"#00ff88" if net >= 0 else "#ff3b6b"};">'
            f'{"+" if net >= 0 else "−"}${abs(net):,.2f} ({"crédit encaissé" if net >= 0 else "débit payé"})</b><br>'
            f'Gain maximal : <b style="color:#00ff88;">{g_txt}</b><br>'
            f'Perte maximale : <b style="color:#ff3b6b;">{l_txt}</b><br>'
            f'Point(s) mort(s) : <b>{be_txt}</b><br>'
            f'Type : <b>{LEVEL_LABEL.get(lvl, lvl)}</b></div>', unsafe_allow_html=True)
        g = an_view["greeks"]
        gc = st.columns(5)
        for c_, (lab, v, f_) in zip(gc, [("Δ", g["delta"], "{:+,.1f}"), ("Γ", g["gamma"], "{:+,.3f}"),
                                         ("Θ/j", g["theta"], "{:+,.2f}"), ("ν/1%", g["vega"], "{:+,.2f}"),
                                         ("ρ/1%", g["rho"], "{:+,.2f}")]):
            c_.metric(lab, f_.format(v))
        st.caption("Grecques en $ (ou titres pour Δ) pour l'ensemble de la position. "
                   f"Quand l'utiliser : {spec['quand']} Risque : {spec['risque']}")

    # Diagramme de gain à l'échéance
    grid, pnl = an_view["grid"], an_view["pnl"]
    m = (grid >= spot * 0.6) & (grid <= spot * 1.4)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=grid[m], y=np.where(pnl[m] >= 0, pnl[m], 0), fill="tozeroy",
                             fillcolor="rgba(0,255,136,.1)", line=dict(color="rgba(0,0,0,0)"),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=grid[m], y=np.where(pnl[m] < 0, pnl[m], 0), fill="tozeroy",
                             fillcolor="rgba(255,59,107,.1)", line=dict(color="rgba(0,0,0,0)"),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=grid[m], y=pnl[m], mode="lines", line=dict(color="#7c3aed", width=2),
                             name="P&L à l'échéance", hovertemplate="$%{x:,.2f} → $%{y:,.0f}<extra></extra>"))
    fig.add_hline(y=0, line_color="rgba(255,255,255,.2)")
    fig.add_vline(x=spot, line_dash="dot", line_color="#ffd700", annotation_text="Spot",
                  annotation_font_color="#ffd700")
    for b in an_view["breakevens"][:3]:
        fig.add_vline(x=b, line_dash="dash", line_color="#94a3b8")
    fig.update_layout(**_P, height=260, xaxis=dict(title="Cours du sous-jacent à l'échéance",
                                                   gridcolor="rgba(255,255,255,.04)"),
                      yaxis=dict(title="P&L $", gridcolor="rgba(255,255,255,.04)"))
    st.plotly_chart(fig, use_container_width=True)

    legs_df = pd.DataFrame([{
        "Jambe": "Titres" if l["type"] == "stock" else l["type"].upper(),
        "Sens": "Achat" if l["qty"] > 0 else "Vente",
        "Quantité": abs(l["qty"]) * mult,
        "Strike": l.get("K", "—"),
        "Prime/unité": round(l.get("premium", 0.0), 4) if l["type"] != "stock" else "—",
    } for l in legs])
    st.dataframe(legs_df, use_container_width=True, hide_index=True)

    # ── 4. Conformité et exécution ────────────────────────────────────────────
    render_decision(decision)
    ok = st.checkbox("J'ai compris le profil de gain et de perte de cette stratégie", key="strat_ack")
    if st.button(f"🎯 EXÉCUTER « {name} » sur {ticker}", disabled=not (ok and decision.allowed),
                 key="strat_exec", type="primary", use_container_width=True):
        decision, an = pre_trade_options(port, ticker, legs, spot=spot, mult=mult, T_days=T_days,
                                         r=r_rate, sigma=sigma)
        log_decision(decision, port, ticker, f"STRATÉGIE {name}", n, an["net_premium"],
                     executed=decision.allowed, note="Stratégie d'options")
        if not decision.allowed:
            st.error("⛔ Stratégie bloquée par la conformité : " + decision.short_reason())
            return
        sid = "S" + uuid.uuid4().hex[:6].upper()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for l in legs:
            if l["type"] == "stock" and l["qty"] > 0:
                err = record_trade(port, ticker, "BUY", l["qty"] * mult, spot, enforce=False,
                                   source=f"stratégie {name} ({sid})")
                if err:
                    st.error(err)
                    return
        from utils.costs import option_costs    # v5.8 : écart sur la prime + commission par contrat
        from utils import ledger as LG
        for l in legs:
            if l["type"] == "stock":
                continue
            buy = l["qty"] > 0
            k = abs(int(l["qty"]))
            _oc = option_costs("BUY" if buy else "SELL", k, l["premium"])
            l = {**l, "premium": _oc["prime"]}
            tot = l["premium"] * k * mult
            if _oc["frais"]:
                LG.add(port, "frais", _oc["frais"], date=now, ticker=ticker, detail=f"commission {name}")
            from utils.options import book_option   # une ligne par instrument (v5.5)
            book_option(port, {
                "date": now, "ticker": ticker, "type": l["type"], "action": "BUY" if buy else "SELL",
                "strike": round(l["K"], 4), "maturity_days": T_days, "sigma": round(sigma * 100, 2),
                "n_contracts": k, "contract_mult": mult, "premium": round(l["premium"], 6),
                "total_premium": round(tot, 2), "spot_at_entry": round(spot, 4),
                "currency": "USD", "strategy": name, "strategy_id": sid,
            })
            port["cash"] = port.get("cash", 0) + (-tot if buy else tot)
        port.setdefault("trades", []).append({
            "date": now, "ticker": f"{ticker} {name}", "action": "STRATÉGIE OPTIONS",
            "qty": n, "price": round(an["net_premium"] / max(n * mult, 1), 6),
            "total": round(an["net_premium"], 2), "source": sid, "conformite": "contrôlé",
        })
        persist()
        st.success(f"✅ Stratégie « {name} » exécutée sur {ticker} ({sid}).")
        st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  EXPOSITION & CONFORMITÉ (sous-onglet des positions)
# ══════════════════════════════════════════════════════════════════════════════

def _exposure_panel(port, live, total_val):
    from utils.advisor import classify_ticker
    prof = get_profile()
    lim = HARD_LIMITS[prof["risque"]]
    holdings = port.get("holdings", {})
    cash = port.get("cash", 0.0)
    if total_val <= 0:
        st.info("Portefeuille vide.")
        return
    rows = []
    for tk, pos in holdings.items():
        val = pos.get("qty", 0) * live.get(tk, (pos.get("avg_price", 0), 0))[0]
        rows.append({"Ligne": tk, "Classe": classify_ticker(tk) or "Autre", "Valeur": val})
    rows.append({"Ligne": "Liquidités", "Classe": "Liquidités", "Valeur": cash})
    df = pd.DataFrame(rows)
    df["Poids"] = df["Valeur"] / total_val
    by_cls = df.groupby("Classe")["Valeur"].sum().sort_values(ascending=False) / total_val

    c1, c2 = st.columns(2)
    with c1:
        section_title("EXPOSITION PAR CLASSE D'ACTIFS", "🧭")
        fig = go.Figure(go.Bar(x=by_cls.values * 100, y=by_cls.index, orientation="h",
                               marker_color="#00d4ff", text=[f"{v:.1%}" for v in by_cls.values],
                               textposition="outside"))
        fig.update_layout(**_P, height=max(180, 32 * len(by_cls)),
                          xaxis=dict(title="% de l'actif net", gridcolor="rgba(255,255,255,.04)"),
                          yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        section_title(f"LIMITES DU PROFIL {prof['risque'].upper()}", "🛡️")
        crypto = df[df["Classe"] == "Crypto"]["Poids"].sum()
        cash_w = df[df["Classe"] == "Liquidités"]["Poids"].sum()
        top = df[df["Ligne"] != "Liquidités"].sort_values("Poids", ascending=False).head(1)
        top_txt = f'{top["Ligne"].iloc[0]} {top["Poids"].iloc[0]:.1%}' if not top.empty else "—"
        opts_paid = sum(o.get("total_premium", 0) for o in port.get("options", []) if o.get("action") == "BUY")
        checks = [
            ("Plus grosse ligne", top_txt, f"≤ {lim['line']:.0%} (ETF diversifié ≤ 70 %)",
             top.empty or top["Poids"].iloc[0] <= max(lim["line"], 0.70)),
            ("Crypto-actifs", f"{crypto:.1%}", f"≤ {lim['crypto']:.0%}", crypto <= lim["crypto"] + 1e-9
             or normalize_port_type(port) == "Crypto Alpha"),
            ("Liquidités (dont monétaire)", f"{cash_w:.1%}", f"≥ {lim['cash_min']:.0%}", cash_w >= lim["cash_min"] - 1e-9),
            ("Primes d'options payées", f"{opts_paid / total_val:.1%}", f"≤ {lim['premium']:.0%}",
             opts_paid / total_val <= lim["premium"] + 1e-9),
        ]
        for lab, val, rule, ok in checks:
            colr = "#00ff88" if ok else "#ffd700"
            st.markdown(f'<div style="font-family:Share Tech Mono;font-size:.74rem;color:#cbd5e1;'
                        f'border-left:3px solid {colr};padding:4px 10px;margin:4px 0;">'
                        f'{"✅" if ok else "⚠️"} {lab} : <b>{val}</b> <span style="color:#475569;">({rule})</span></div>',
                        unsafe_allow_html=True)
        st.caption("Les limites bloquent les nouveaux achats ; une position existante qui dépasse une limite "
                   "(après une hausse de cours) est signalée ici mais n'est pas vendue automatiquement.")

    st.markdown("<br>", unsafe_allow_html=True)
    section_title("JOURNAL DE CONFORMITÉ (MES DERNIÈRES DÉCISIONS)", "📜")
    log = recent_log(50)
    if log:
        st.dataframe(pd.DataFrame(log), use_container_width=True, hide_index=True, height=260)
    else:
        st.info("Aucune décision enregistrée pour l'instant.")
    with st.expander("📘 Règles de conformité et limites par profil"):
        render_rules_reference()


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
    sub_hold, sub_opt, sub_hist, sub_cmp, sub_disc = st.tabs([
        f"📊 HOLDINGS ({len(holdings)} position{'s' if len(holdings)!=1 else ''})",
        f"⚙️ OPTIONS ({len(options)} position{'s' if len(options)!=1 else ''})",
        f"🔄 HISTORIQUE ({len(trades)} trade{'s' if len(trades)!=1 else ''})",
        "🛡️ EXPOSITION & CONFORMITÉ",
        "🧭 DISCIPLINE DE GESTION",
    ])

    with sub_cmp:
        _exposure_panel(port, live, total_val)
    with sub_disc:
        from components.desk_tools_ui import discipline_tab
        discipline_tab(port, live, total_val)

    # ── HOLDINGS ──────────────────────────────────────────────────────────────
    with sub_hold:
        if not holdings:
            st.info("Aucune position spot ouverte. Tradez depuis l'onglet Spot Trading.")
        else:
            hdr = ["TICKER","SECTEUR","QTÉ","PX ENTRÉE","PX ACTUEL","VAR 1J","VALEUR","P&L $","P&L %","POIDS"]
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
                    f'<td style="padding:7px 10px;font-family:Rajdhani;font-size:.72rem;color:#94a3b8;">{_h.escape(sector_of(tk))}</td>'
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
                      f'<td colspan="6" style="padding:7px 10px;font-family:Rajdhani;font-size:.7rem;color:#475569;letter-spacing:.1em;">TOTAL SPOT — {len(holdings)} positions</td>'
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
            hdr_o = ["SOUS-JAC.","SECTEUR / INSTRUMENT","C/P","SENS","STRIKE","EXPIRATION","QTÉ","MULT","PRIME ENTRÉE","PRIME MTM","VALEUR MTM","P&L","DELTA Σ"]
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
                    f'<td style="padding:7px 10px;font-family:Rajdhani;font-size:.72rem;color:#c4b5fd;">{_h.escape(option_sector(o))}</td>'
                    f'<td style="padding:7px 10px;color:{cp_c};font-weight:bold;">{"C" if o["type"]=="call" else "P"}</td>'
                    f'<td style="padding:7px 10px;color:#94a3b8;">{"Achat" if is_long else "Vente"}</td>'
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
                        f'<td colspan="10" style="padding:7px 10px;font-family:Rajdhani;font-size:.7rem;color:#475569;letter-spacing:.1em;">TOTAL OPTIONS — {len(options)} positions</td>'
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
            if "ticker" in df.columns:
                def _sect(row):
                    t, a = str(row.get("ticker", "")), str(row.get("action", "")).upper()
                    base = t.split(" ")[0]
                    if "OPTION" in a or "STRAT" in a or "COUVERTURE" in a:
                        return f"Dérivé — option sur {short_sector(base)} ({base})"
                    return sector_of(base)
                df.insert(df.columns.get_loc("ticker") + 1, "secteur", df.apply(_sect, axis=1))
            st.dataframe(df, use_container_width=True, hide_index=True)
