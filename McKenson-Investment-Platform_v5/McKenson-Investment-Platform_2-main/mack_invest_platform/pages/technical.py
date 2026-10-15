# pages/technical.py  —  MAM Technical Analysis
"""
Full technical analysis: RSI, MACD, Bollinger Bands, ATR, Stochastic,
VWAP, GARCH volatility, candlestick charts, signals.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from components.ui import section_title, metric_row
from utils.data import get_history, load_assets, get_multi_prices, get_price
from utils.technical import (
    compute_rsi, compute_macd, compute_bollinger,
    compute_atr, compute_stochastic, compute_vwap,
    compute_ema, compute_sma, garch_vol_estimate, get_signal,
)

_P = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
          font=dict(color="#94a3b8", family="Share Tech Mono"),
          margin=dict(l=8, r=8, t=32, b=8))


def render():
    st.markdown(
        '<h1 style="font-family:Rajdhani,sans-serif;font-size:2rem;letter-spacing:.12em;'
        'color:#00d4ff;margin:0 0 2px;text-shadow:0 0 30px rgba(0,212,255,.4);">'
        '📊 TECHNICAL ANALYSIS — MAM</h1>', unsafe_allow_html=True)

    # ── Asset selection ────────────────────────────────────────────────────────
    assets_df = load_assets()
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        cat = st.selectbox("Catégorie", ["Tous"] + sorted(assets_df["category"].unique().tolist()),
                           key="ta_cat")
    with col2:
        df_f = assets_df if cat == "Tous" else assets_df[assets_df["category"] == cat]
        ticker_map = {f'{r["ticker"]} — {r["name"]}': r["ticker"] for _, r in df_f.iterrows()}
        sel = st.selectbox("Actif", list(ticker_map.keys()), key="ta_asset")
        ticker = ticker_map[sel]
    with col3:
        period = st.selectbox("Période", ["1mo", "3mo", "6mo", "1y", "2y", "5y"],
                              index=3, key="ta_period")

    # ── Fetch data ─────────────────────────────────────────────────────────────
    hist = get_history(ticker, period)
    if hist.empty or len(hist) < 20:
        st.warning(f"Données insuffisantes pour {ticker} sur {period}.")
        return

    close  = hist["Close"]
    high   = hist["High"]
    low    = hist["Low"]
    volume = hist.get("Volume", pd.Series(index=hist.index, data=0))

    # ── Compute indicators ─────────────────────────────────────────────────────
    rsi_ser               = compute_rsi(close)
    macd_line, sig_line, hist_ser = compute_macd(close)
    bb_upper, bb_mid, bb_lower   = compute_bollinger(close)
    atr_ser               = compute_atr(high, low, close)
    stoch_k, stoch_d      = compute_stochastic(high, low, close)
    ema20 = compute_ema(close, 20)
    ema50 = compute_ema(close, 50)
    sma200 = compute_sma(close, 200)
    vwap   = compute_vwap(high, low, close, volume)

    # Current values
    last_close  = float(close.iloc[-1])
    last_rsi    = float(rsi_ser.dropna().iloc[-1]) if not rsi_ser.dropna().empty else 50
    last_macd_h = float(hist_ser.dropna().iloc[-1]) if not hist_ser.dropna().empty else 0
    last_bb_u   = float(bb_upper.dropna().iloc[-1]) if not bb_upper.dropna().empty else last_close * 1.02
    last_bb_l   = float(bb_lower.dropna().iloc[-1]) if not bb_lower.dropna().empty else last_close * 0.98
    last_atr    = float(atr_ser.dropna().iloc[-1]) if not atr_ser.dropna().empty else 0
    last_stoch  = float(stoch_k.dropna().iloc[-1]) if not stoch_k.dropna().empty else 50

    signal, sig_color = get_signal(last_rsi, last_macd_h, last_close, last_bb_u, last_bb_l)

    # ── Summary strip ──────────────────────────────────────────────────────────
    sig_col_map = {"positive": "#00ff88", "negative": "#ff3b6b", "neutral": "#ffd700"}
    sc = sig_col_map.get(sig_color, "#ffd700")

    st.markdown(
        f'<div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:14px;">'
        f'<div style="background:rgba(0,212,255,.06);border:1px solid rgba(0,212,255,.2);'
        f'border-radius:6px;padding:10px 16px;font-family:Share Tech Mono;font-size:.8rem;">'
        f'<span style="color:#7a93b0;">Ticker</span> <b style="color:#00d4ff;">{ticker}</b></div>'
        f'<div style="background:rgba(0,212,255,.06);border:1px solid rgba(0,212,255,.2);'
        f'border-radius:6px;padding:10px 16px;font-family:Share Tech Mono;font-size:.8rem;">'
        f'<span style="color:#7a93b0;">Close</span> <b>${last_close:,.4f}</b></div>'
        f'<div style="background:rgba(0,212,255,.06);border:1px solid rgba(0,212,255,.2);'
        f'border-radius:6px;padding:10px 16px;font-family:Share Tech Mono;font-size:.8rem;">'
        f'<span style="color:#7a93b0;">RSI</span> <b style="color:{"#ff3b6b" if last_rsi>70 else "#00ff88" if last_rsi<30 else "#ffd700"};">{last_rsi:.1f}</b></div>'
        f'<div style="background:rgba(0,212,255,.06);border:1px solid rgba(0,212,255,.2);'
        f'border-radius:6px;padding:10px 16px;font-family:Share Tech Mono;font-size:.8rem;">'
        f'<span style="color:#7a93b0;">ATR</span> <b>${last_atr:.4f}</b></div>'
        f'<div style="background:rgba({("0,255,136" if sig_color=="positive" else "255,59,107" if sig_color=="negative" else "255,215,0")},.12);'
        f'border:1px solid {sc};border-radius:6px;padding:10px 20px;font-family:Rajdhani;'
        f'font-size:.9rem;font-weight:700;letter-spacing:.12em;color:{sc};">{signal}</div>'
        f'</div>', unsafe_allow_html=True)

    # ── Tab layout ─────────────────────────────────────────────────────────────
    tab_price, tab_momentum, tab_vol, tab_garch = st.tabs([
        "🕯️ PRIX & MOYENNES",
        "📡 MOMENTUM (RSI / MACD / Stoch)",
        "📊 VOLATILITÉ & BANDES",
        "🔮 GARCH & RISQUE",
    ])

    with tab_price:
        _price_chart(hist, close, ema20, ema50, sma200, bb_upper, bb_mid, bb_lower, vwap, ticker)

    with tab_momentum:
        _momentum_chart(close, rsi_ser, macd_line, sig_line, hist_ser, stoch_k, stoch_d)

    with tab_vol:
        _vol_chart(close, bb_upper, bb_mid, bb_lower, atr_ser, volume)

    with tab_garch:
        _garch_chart(close)


# ─────────────────────────────────────────────────────────────────────────────
def _price_chart(hist, close, ema20, ema50, sma200, bb_u, bb_m, bb_l, vwap, ticker):
    section_title("CHANDELIER JAPONAIS + MOYENNES MOBILES", "🕯️")

    show_ema20  = st.checkbox("EMA 20",   True, key="ta_ema20")
    show_ema50  = st.checkbox("EMA 50",   True, key="ta_ema50")
    show_sma200 = st.checkbox("SMA 200",  False, key="ta_sma200")
    show_bb     = st.checkbox("Bollinger", True, key="ta_bb")
    show_vwap   = st.checkbox("VWAP",     False, key="ta_vwap")

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.75, 0.25], vertical_spacing=0.02)

    # Candlestick
    fig.add_trace(go.Candlestick(
        x=hist.index,
        open=hist["Open"], high=hist["High"],
        low=hist["Low"],   close=hist["Close"],
        name=ticker,
        increasing_line_color="#00ff88", decreasing_line_color="#ff3b6b",
        increasing_fillcolor="rgba(0,255,136,.7)",
        decreasing_fillcolor="rgba(255,59,107,.7)",
    ), row=1, col=1)

    if show_bb:
        fig.add_trace(go.Scatter(x=hist.index, y=bb_u, name="BB Upper",
            line=dict(color="rgba(124,58,237,.5)", width=1, dash="dot"), showlegend=True), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=bb_m, name="BB Mid",
            line=dict(color="rgba(124,58,237,.8)", width=1)), row=1, col=1)
        fig.add_trace(go.Scatter(x=hist.index, y=bb_l, name="BB Lower",
            line=dict(color="rgba(124,58,237,.5)", width=1, dash="dot"),
            fill="tonexty", fillcolor="rgba(124,58,237,.04)"), row=1, col=1)
    if show_ema20:
        fig.add_trace(go.Scatter(x=hist.index, y=ema20, name="EMA 20",
            line=dict(color="#00d4ff", width=1.2)), row=1, col=1)
    if show_ema50:
        fig.add_trace(go.Scatter(x=hist.index, y=ema50, name="EMA 50",
            line=dict(color="#ffd700", width=1.2)), row=1, col=1)
    if show_sma200:
        fig.add_trace(go.Scatter(x=hist.index, y=sma200, name="SMA 200",
            line=dict(color="#ff8c00", width=1.5, dash="dot")), row=1, col=1)
    if show_vwap:
        fig.add_trace(go.Scatter(x=hist.index, y=vwap, name="VWAP",
            line=dict(color="#ff3b6b", width=1.2, dash="dash")), row=1, col=1)

    # Volume bars
    vol = hist.get("Volume", pd.Series(0, index=hist.index))
    colors = ["rgba(0,255,136,.5)" if c >= o else "rgba(255,59,107,.5)"
              for c, o in zip(hist["Close"], hist["Open"])]
    fig.add_trace(go.Bar(x=hist.index, y=vol, name="Volume",
                         marker_color=colors, showlegend=False), row=2, col=1)

    fig.update_layout(**_P, height=520,
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10)),
        yaxis=dict(gridcolor="rgba(255,255,255,.04)", title="Prix"),
        yaxis2=dict(gridcolor="rgba(255,255,255,.04)", title="Volume"))
    st.plotly_chart(fig, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
def _momentum_chart(close, rsi, macd_l, sig_l, hist_ser, stoch_k, stoch_d):
    section_title("RSI — MACD — STOCHASTIQUE", "📡")

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.33, 0.33, 0.33], vertical_spacing=0.04,
                        subplot_titles=["RSI (14)", "MACD (12,26,9)", "Stochastique (14,3)"])

    # RSI
    fig.add_trace(go.Scatter(x=rsi.index, y=rsi, name="RSI",
        line=dict(color="#00d4ff", width=1.8)), row=1, col=1)
    fig.add_hline(y=70, line_color="#ff3b6b", line_dash="dot", row=1, col=1)
    fig.add_hline(y=30, line_color="#00ff88", line_dash="dot", row=1, col=1)
    fig.add_hline(y=50, line_color="rgba(255,255,255,.15)", row=1, col=1)
    fig.add_hrect(y0=70, y1=100, fillcolor="rgba(255,59,107,.04)", line_width=0, row=1, col=1)
    fig.add_hrect(y0=0, y1=30, fillcolor="rgba(0,255,136,.04)", line_width=0, row=1, col=1)

    # MACD
    colors_hist = ["rgba(0,255,136,.6)" if v >= 0 else "rgba(255,59,107,.6)"
                   for v in hist_ser.fillna(0)]
    fig.add_trace(go.Bar(x=hist_ser.index, y=hist_ser, name="Histogramme",
                          marker_color=colors_hist, showlegend=False), row=2, col=1)
    fig.add_trace(go.Scatter(x=macd_l.index, y=macd_l, name="MACD",
        line=dict(color="#00d4ff", width=1.5)), row=2, col=1)
    fig.add_trace(go.Scatter(x=sig_l.index, y=sig_l, name="Signal",
        line=dict(color="#ff8c00", width=1.5, dash="dot")), row=2, col=1)
    fig.add_hline(y=0, line_color="rgba(255,255,255,.2)", row=2, col=1)

    # Stochastic
    fig.add_trace(go.Scatter(x=stoch_k.index, y=stoch_k, name="%K",
        line=dict(color="#00d4ff", width=1.5)), row=3, col=1)
    fig.add_trace(go.Scatter(x=stoch_d.index, y=stoch_d, name="%D",
        line=dict(color="#ffd700", width=1.5, dash="dot")), row=3, col=1)
    fig.add_hline(y=80, line_color="#ff3b6b", line_dash="dot", row=3, col=1)
    fig.add_hline(y=20, line_color="#00ff88", line_dash="dot", row=3, col=1)

    fig.update_layout(**_P, height=520,
        legend=dict(orientation="h", y=1.02, font=dict(size=10)),
        yaxis=dict(range=[0,100], gridcolor="rgba(255,255,255,.04)"),
        yaxis2=dict(gridcolor="rgba(255,255,255,.04)"),
        yaxis3=dict(range=[0,100], gridcolor="rgba(255,255,255,.04)"))
    fig.update_annotations(font=dict(color="#7a93b0", size=11, family="Rajdhani"))
    st.plotly_chart(fig, use_container_width=True)

    # Interpretation
    last_rsi   = float(rsi.dropna().iloc[-1]) if not rsi.dropna().empty else 50
    last_macd  = float(hist_ser.dropna().iloc[-1]) if not hist_ser.dropna().empty else 0
    last_stoch = float(stoch_k.dropna().iloc[-1]) if not stoch_k.dropna().empty else 50

    def interp_card(title, val, low, high, low_label, high_label, color):
        if val < low:
            state_, col_ = low_label, "#00ff88"
        elif val > high:
            state_, col_ = high_label, "#ff3b6b"
        else:
            state_, col_ = "NEUTRE", "#ffd700"
        return (f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.06);'
                f'border-radius:6px;padding:10px;text-align:center;">'
                f'<div style="font-family:Rajdhani;font-size:.65rem;color:#7a93b0;letter-spacing:.1em;">{title}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:1.1rem;color:{color};font-weight:bold;">{val:.1f}</div>'
                f'<div style="font-family:Rajdhani;font-size:.75rem;font-weight:700;color:{col_};letter-spacing:.08em;">{state_}</div>'
                f'</div>')

    st.markdown(
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:10px;">'
        + interp_card("RSI 14", last_rsi, 30, 70, "SURVENDU", "SURACHETÉ", "#00d4ff")
        + interp_card("MACD Hist.", last_macd, -0.01, 0.01, "HAUSSIER", "BAISSIER", "#ffd700")
        + interp_card("Stoch %K", last_stoch, 20, 80, "SURVENDU", "SURACHETÉ", "#a78bfa")
        + '</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
def _vol_chart(close, bb_u, bb_m, bb_l, atr, volume):
    section_title("BOLLINGER BANDS & ATR", "📊")

    fig = make_subplots(rows=3, cols=1, shared_xaxes=True,
                        row_heights=[0.5, 0.25, 0.25], vertical_spacing=0.04,
                        subplot_titles=["Bollinger Bands (20,2σ)", "ATR (14)", "Volume"])

    # Price + BB
    fig.add_trace(go.Scatter(x=close.index, y=close, name="Prix",
        line=dict(color="#e2e8f0", width=1.5)), row=1, col=1)
    fig.add_trace(go.Scatter(x=bb_u.index, y=bb_u, name="Upper",
        line=dict(color="rgba(124,58,237,.6)", width=1), showlegend=True), row=1, col=1)
    fig.add_trace(go.Scatter(x=bb_l.index, y=bb_l, name="Lower",
        line=dict(color="rgba(124,58,237,.6)", width=1),
        fill="tonexty", fillcolor="rgba(124,58,237,.05)"), row=1, col=1)
    fig.add_trace(go.Scatter(x=bb_m.index, y=bb_m, name="SMA 20",
        line=dict(color="rgba(124,58,237,.9)", width=1, dash="dot")), row=1, col=1)

    # ATR
    fig.add_trace(go.Scatter(x=atr.index, y=atr, name="ATR",
        line=dict(color="#ff8c00", width=1.5),
        fill="tozeroy", fillcolor="rgba(255,140,0,.06)"), row=2, col=1)

    # Volume
    colors = ["rgba(0,255,136,.5)" if c >= close.iloc[max(0, i-1)] else "rgba(255,59,107,.5)"
              for i, c in enumerate(close)]
    fig.add_trace(go.Bar(x=close.index, y=volume, name="Volume",
                          marker_color=colors, showlegend=False), row=3, col=1)

    fig.update_layout(**_P, height=500,
        legend=dict(orientation="h", y=1.02, font=dict(size=10)),
        yaxis=dict(gridcolor="rgba(255,255,255,.04)"),
        yaxis2=dict(gridcolor="rgba(255,255,255,.04)"),
        yaxis3=dict(gridcolor="rgba(255,255,255,.04)"))
    fig.update_annotations(font=dict(color="#7a93b0", size=11, family="Rajdhani"))
    st.plotly_chart(fig, use_container_width=True)

    # BB width indicator
    bw = (bb_u - bb_l) / bb_m
    section_title("LARGEUR DES BANDES (Squeeze)", "🔍")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=bw.index, y=bw, name="BB Width",
        line=dict(color="#a78bfa", width=1.5),
        fill="tozeroy", fillcolor="rgba(124,58,237,.06)",
        hovertemplate="%{x|%d %b}<br>Width: %{y:.4f}<extra></extra>"))
    fig2.update_layout(**_P, height=150,
        yaxis=dict(title="BB Width", gridcolor="rgba(255,255,255,.04)"),
        xaxis=dict(showgrid=False))
    st.plotly_chart(fig2, use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
def _garch_chart(close):
    section_title("GARCH(1,1) — VOLATILITÉ CONDITIONNELLE", "🔮")

    st.markdown("""
    <div style="background:rgba(124,58,237,.06);border:1px solid rgba(124,58,237,.25);
    border-radius:8px;padding:10px 14px;margin-bottom:12px;font-family:Share Tech Mono;
    font-size:.73rem;color:#94a3b8;">
    🔮 <b style="color:#a78bfa;">GARCH(1,1)</b> — Modèle d'hétéroscédasticité conditionnelle.
    σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁<br>
    Paramètres : ω=1e-6, α=0.10, β=0.85 (typiques pour actifs financiers)
    </div>""", unsafe_allow_html=True)

    col_a, col_b, col_c = st.columns(3)
    with col_a:
        omega = st.number_input("ω (omega)", 1e-8, 1e-3, 1e-6, format="%.2e", key="garch_w")
    with col_b:
        alpha = st.slider("α (alpha) — ARCH", 0.01, 0.5, 0.10, 0.01, key="garch_a")
    with col_c:
        beta  = st.slider("β (beta) — GARCH", 0.01, 0.99, 0.85, 0.01, key="garch_b")

    if alpha + beta >= 1:
        st.error("⚠️ α + β doit être < 1 pour la stationnarité du modèle.")
        return

    returns = close.pct_change().dropna()
    garch_vol = garch_vol_estimate(returns, omega=omega, alpha=alpha, beta=beta)

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.5, 0.5], vertical_spacing=0.04,
                        subplot_titles=["Rendements journaliers", "Volatilité GARCH annualisée"])

    # Returns
    ret_colors = ["rgba(0,255,136,.6)" if r >= 0 else "rgba(255,59,107,.6)" for r in returns]
    fig.add_trace(go.Bar(x=returns.index, y=returns * 100, name="Rendements (%)",
                          marker_color=ret_colors, showlegend=False), row=1, col=1)
    fig.add_hline(y=0, line_color="rgba(255,255,255,.2)", row=1, col=1)

    # GARCH vol
    fig.add_trace(go.Scatter(x=garch_vol.index, y=garch_vol * 100, name="GARCH Vol",
        line=dict(color="#ff8c00", width=2),
        fill="tozeroy", fillcolor="rgba(255,140,0,.06)",
        hovertemplate="%{x|%d %b}<br>Vol: %{y:.2f}%<extra></extra>"), row=2, col=1)

    # Rolling 30d realized vol for comparison
    realized = returns.rolling(30).std() * np.sqrt(252) * 100
    fig.add_trace(go.Scatter(x=realized.index, y=realized, name="Vol réalisée (30j)",
        line=dict(color="#00d4ff", width=1.5, dash="dot")), row=2, col=1)

    fig.update_layout(**_P, height=440,
        legend=dict(orientation="h", y=1.02, font=dict(size=10)),
        yaxis=dict(title="Rendement (%)", gridcolor="rgba(255,255,255,.04)"),
        yaxis2=dict(title="Vol annualisée (%)", gridcolor="rgba(255,255,255,.04)"))
    fig.update_annotations(font=dict(color="#7a93b0", size=11, family="Rajdhani"))
    st.plotly_chart(fig, use_container_width=True)

    # Statistics
    last_garch = float(garch_vol.iloc[-1]) if not garch_vol.empty else 0
    last_real  = float(realized.dropna().iloc[-1]) if not realized.dropna().empty else 0
    avg_garch  = float(garch_vol.mean()) if not garch_vol.empty else 0

    metric_row([
        {"label": "Vol. GARCH (actuelle)", "value": f"{last_garch*100:.2f}%", "color": ""},
        {"label": "Vol. réalisée 30j",     "value": f"{last_real:.2f}%", "color": ""},
        {"label": "Vol. GARCH moyenne",    "value": f"{avg_garch*100:.2f}%", "color": ""},
        {"label": "α + β (persistance)",   "value": f"{alpha+beta:.3f}",
         "color": "positive" if alpha+beta < 0.95 else "negative"},
    ])

    # Return distribution
    section_title("DISTRIBUTION DES RENDEMENTS", "📉")
    fig2 = go.Figure()
    fig2.add_trace(go.Histogram(
        x=returns * 100, nbinsx=50,
        marker_color="rgba(0,212,255,.5)", name="Distribution réelle",
        hovertemplate="Rendement: %{x:.2f}%<br>Fréq: %{y}<extra></extra>"))
    var99 = float(returns.quantile(0.01)) * 100
    fig2.add_vline(x=var99, line_dash="dot", line_color="#ff3b6b",
                   annotation_text=f"VaR 99%: {var99:.2f}%",
                   annotation_font_color="#ff3b6b")
    fig2.add_vline(x=0, line_color="rgba(255,255,255,.2)")
    fig2.update_layout(**_P, height=220,
        xaxis=dict(title="Rendement journalier (%)", gridcolor="rgba(255,255,255,.04)"),
        yaxis=dict(title="Fréquence", gridcolor="rgba(255,255,255,.04)"))
    st.plotly_chart(fig2, use_container_width=True)
