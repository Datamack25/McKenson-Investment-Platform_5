# pages/education.py  —  MAM Education & Tools
"""
Complete investment education hub for beginners and advanced investors.
Covers: equities, bonds, ETFs, derivatives (options, futures, swaps),
portfolio theory, risk management, trading strategies, macroeconomics.
Fixed: uses df["category"] not df["type"].
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from components.ui import section_title, metric_row
from utils.data import get_price, load_assets, get_history
from utils.options import bs_price, bs_greeks, STRATEGY_META, build_strategy_legs, payoff_at_expiry

_P = dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
          font=dict(color="#94a3b8", family="Share Tech Mono"),
          margin=dict(l=8, r=8, t=28, b=8))

# ─────────────────────────────────────────────────────────────────────────────
# Styling helpers
# ─────────────────────────────────────────────────────────────────────────────

def _info_box(text: str, color: str = "#00d4ff"):
    st.markdown(
        f'<div style="background:rgba(0,212,255,.05);border-left:4px solid {color};'
        f'border-radius:0 8px 8px 0;padding:12px 16px;margin:10px 0;'
        f'font-family:Share Tech Mono;font-size:.75rem;color:#94a3b8;line-height:1.9;">'
        f'{text}</div>', unsafe_allow_html=True)


def _concept_card(title: str, body: str, icon: str = "📖", color: str = "#00d4ff"):
    st.markdown(
        f'<div style="background:rgba(0,0,0,.25);border:1px solid rgba(255,255,255,.07);'
        f'border-top:3px solid {color};border-radius:0 0 8px 8px;'
        f'padding:14px 16px;margin-bottom:10px;">'
        f'<div style="font-family:Rajdhani;font-size:1rem;font-weight:700;'
        f'color:{color};margin-bottom:6px;">{icon} {title}</div>'
        f'<div style="font-family:Share Tech Mono;font-size:.73rem;color:#94a3b8;'
        f'line-height:1.85;">{body}</div>'
        f'</div>', unsafe_allow_html=True)


def _formula_box(formula: str, label: str = ""):
    st.markdown(
        f'<div style="background:rgba(124,58,237,.08);border:1px solid rgba(124,58,237,.25);'
        f'border-radius:6px;padding:12px 18px;margin:8px 0;text-align:center;">'
        f'{"<div style=\\'font-family:Rajdhani;font-size:.65rem;color:#7a93b0;margin-bottom:4px;\\'>" + label + "</div>" if label else ""}'
        f'<div style="font-family:Share Tech Mono;font-size:.9rem;color:#a78bfa;">{formula}</div>'
        f'</div>', unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
def render():
    st.markdown(
        '<h1 style="font-family:Rajdhani,sans-serif;font-size:2rem;letter-spacing:.12em;'
        'color:#00d4ff;margin:0 0 2px;text-shadow:0 0 30px rgba(0,212,255,.4);">'
        '🎓 ÉDUCATION & OUTILS — MAM</h1>', unsafe_allow_html=True)

    st.markdown(
        '<div style="font-family:Share Tech Mono;font-size:.75rem;color:#7a93b0;'
        'margin-bottom:18px;">Formation complète — du débutant à l\'investisseur avancé</div>',
        unsafe_allow_html=True)

    tab_basics, tab_products, tab_derivatives, tab_strategies, \
        tab_portfolio, tab_risk, tab_fv, tab_glossary = st.tabs([
        "🏫 LES BASES",
        "📦 PRODUITS FINANCIERS",
        "⚗️ DÉRIVÉS & OPTIONS",
        "🎯 STRATÉGIES D'INVEST.",
        "🧮 THÉORIE DU PORTEFEUILLE",
        "📐 OUTILS DE RISQUE",
        "💡 FAIR VALUE CALCULATOR",
        "📚 GLOSSAIRE",
    ])

    with tab_basics:
        _basics_tab()
    with tab_products:
        _products_tab()
    with tab_derivatives:
        _derivatives_tab()
    with tab_strategies:
        _strategies_tab()
    with tab_portfolio:
        _portfolio_theory_tab()
    with tab_risk:
        _risk_tools_tab()
    with tab_fv:
        _fair_value_tab()
    with tab_glossary:
        _glossary_tab()


# ═════════════════════════════════════════════════════════════════════════════
# TAB 1 — LES BASES
# ═════════════════════════════════════════════════════════════════════════════

def _basics_tab():
    section_title("COMPRENDRE LES MARCHÉS FINANCIERS", "🏫")

    level = st.radio("Niveau", ["🟢 Débutant", "🟡 Intermédiaire", "🔴 Avancé"],
                     horizontal=True, key="edu_level")

    if "Débutant" in level:
        _basics_beginner()
    elif "Intermédiaire" in level:
        _basics_intermediate()
    else:
        _basics_advanced()


def _basics_beginner():
    _info_box(
        "Bienvenue ! Cette section vous guide pas à pas dans l'univers de l'investissement. "
        "Aucune connaissance préalable n'est requise."
    )

    _concept_card("Qu'est-ce qu'un marché financier ?", """
Un marché financier est un lieu (physique ou électronique) où des acheteurs et des vendeurs échangent
des actifs financiers : actions, obligations, devises, matières premières, crypto-monnaies.<br><br>
<b style="color:#00d4ff;">Principaux marchés :</b><br>
• <b>Marché actions (equity)</b> — achat/vente de parts d'entreprises (ex: NYSE, Euronext, NASDAQ)<br>
• <b>Marché obligataire</b> — titres de dette d'États et d'entreprises<br>
• <b>Marché des changes (Forex)</b> — échange de devises, $5 000 Mds/jour<br>
• <b>Marché des matières premières</b> — pétrole, or, blé, cuivre…<br>
• <b>Marché des crypto-actifs</b> — Bitcoin, Ethereum, altcoins (24h/24)
    """, "🌍", "#00d4ff")

    _concept_card("Pourquoi investir ?", """
<b style="color:#ffd700;">L'inflation érode le pouvoir d'achat de l'argent qui ne travaille pas.</b><br>
Si l'inflation est à 3%/an, 100 000€ en cash valent 74 000€ en pouvoir d'achat dans 10 ans.<br><br>
<b style="color:#00ff88;">Investir permet de :</b><br>
• Protéger son capital contre l'inflation<br>
• Générer des revenus passifs (dividendes, coupons)<br>
• Créer de la richesse à long terme grâce aux intérêts composés<br>
• Participer à la croissance économique mondiale<br><br>
<b>La règle des 72 :</b> pour estimer combien d'années il faut pour doubler son capital :<br>
Années = 72 / Taux de rendement annuel. Ex: à 8%/an → 72/8 = 9 ans.
    """, "💡", "#ffd700")

    _formula_box("Capital final = Capital initial × (1 + r)ⁿ", "Formule des intérêts composés")

    # Compound interest interactive demo
    section_title("SIMULATION — INTÉRÊTS COMPOSÉS", "🧮")
    col1, col2, col3 = st.columns(3)
    with col1:
        capital_init = st.number_input("Capital initial ($)", 1_000, 10_000_000, 10_000, 1_000, key="ci_init")
    with col2:
        taux_annuel  = st.slider("Rendement annuel (%)", 1.0, 20.0, 8.0, 0.5, key="ci_rate")
    with col3:
        horizon_ci   = st.slider("Durée (années)", 5, 40, 20, key="ci_years")

    years_arr  = np.arange(0, horizon_ci + 1)
    cap_comp   = capital_init * (1 + taux_annuel / 100) ** years_arr
    cap_simple = capital_init * (1 + taux_annuel / 100 * years_arr)

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=years_arr, y=cap_comp, name="Intérêts composés",
        line=dict(color="#00d4ff", width=2.5),
        fill="tozeroy", fillcolor="rgba(0,212,255,.06)",
        hovertemplate="Année %{x}<br>Capital: $%{y:,.0f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=years_arr, y=cap_simple, name="Intérêts simples",
        line=dict(color="#7a93b0", width=1.5, dash="dot"),
        hovertemplate="Année %{x}<br>Capital: $%{y:,.0f}<extra></extra>"))
    fig.update_layout(**_P, height=260,
        xaxis=dict(title="Années", gridcolor="rgba(255,255,255,.04)"),
        yaxis=dict(title="Capital ($)", gridcolor="rgba(255,255,255,.04)"),
        legend=dict(orientation="h", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True)

    metric_row([
        {"label": "Capital final (composé)",  "value": f"${cap_comp[-1]:,.0f}", "color": "positive"},
        {"label": "Capital final (simple)",   "value": f"${cap_simple[-1]:,.0f}", "color": ""},
        {"label": "Gain des intérêts composés", "value": f"${cap_comp[-1]-cap_simple[-1]:,.0f}", "color": "positive"},
        {"label": "Gain total",              "value": f"×{cap_comp[-1]/capital_init:.1f}", "color": "positive"},
    ])

    _concept_card("Le triangle risque/rendement/liquidité", """
Tout investissement se caractérise selon 3 axes :<br><br>
• 🎯 <b style="color:#00ff88;">Rendement</b> — combien cela rapporte (dividendes, plus-values)<br>
• ⚠️ <b style="color:#ff3b6b;">Risque</b> — probabilité de perdre du capital (volatilité, défaut)<br>
• 💧 <b style="color:#00d4ff;">Liquidité</b> — facilité à transformer l'actif en cash rapidement<br><br>
<b>Règle d'or :</b> on ne peut pas maximiser les 3 simultanément. Un rendement élevé implique
toujours soit un risque plus grand, soit une liquidité réduite.
    """, "⚖️", "#a78bfa")


def _basics_intermediate():
    _concept_card("Analyse fondamentale vs technique", """
<b style="color:#00d4ff;">Analyse fondamentale</b> — Évalue la valeur intrinsèque d'une entreprise.<br>
On examine : états financiers (compte de résultat, bilan, flux de trésorerie), secteur,
avantages concurrentiels (moat), management, valorisation (P/E, EV/EBITDA, DCF).<br>
→ Vision long terme. Question : "Cette entreprise vaut-elle ce prix ?"<br><br>
<b style="color:#ffd700;">Analyse technique</b> — Étudie les mouvements de prix et de volume.<br>
On utilise : moyennes mobiles, RSI, MACD, supports/résistances, figures chartistes.<br>
→ Vision court/moyen terme. Question : "Où va le prix aller maintenant ?"<br><br>
<b style="color:#00ff88;">Analyse quantitative</b> — Modèles mathématiques et statistiques.<br>
Facteurs (valeur, momentum, qualité), backtesting, arbitrage statistique.
    """, "🔬", "#00d4ff")

    _concept_card("Les indicateurs clés de valorisation", """
• <b>P/E (Price-to-Earnings)</b> = Cours / BPA — combien on paye par $ de bénéfice. S&P 500 historique : ~17×<br>
• <b>P/B (Price-to-Book)</b> = Cours / Valeur comptable — actifs tangibles. Banques souvent <1<br>
• <b>EV/EBITDA</b> = Valeur d'entreprise / EBITDA — neutralise l'effet de la dette<br>
• <b>PEG Ratio</b> = P/E / Taux de croissance BPA — P/E ajusté de la croissance<br>
• <b>Dividend Yield</b> = Dividende / Cours — rendement dividende<br>
• <b>FCF Yield</b> = FCF par action / Cours — rendement du cash réel généré<br><br>
<b style="color:#ffd700;">Règle :</b> ces ratios n'ont de sens qu'en comparaison sectorielle.
Un P/E de 30× peut être normal pour un SaaS mais excessif pour une utility.
    """, "📊", "#ffd700")

    _concept_card("Les cycles de marché", """
Les marchés traversent des cycles récurrents :<br><br>
🟢 <b>Expansion</b> → croissance économique, profits en hausse, marchés haussiers (bull market)<br>
📈 <b>Pic (Peak)</b> → valorisations élevées, euphorie, VIX bas, taux en hausse<br>
🔴 <b>Contraction</b> → récession, profits en baisse, marchés baissiers (bear market = -20%+)<br>
📉 <b>Creux (Trough)</b> → pessimisme maximal, valorisations basses, meilleur point d'entrée<br><br>
<b style="color:#00d4ff;">Secteurs cycliques vs défensifs :</b><br>
• Cycliques (surperforment en expansion) : technologie, consommation discrétionnaire, industrie<br>
• Défensifs (résistent en contraction) : santé, utilities, alimentation, télécom
    """, "🔄", "#a78bfa")


def _basics_advanced():
    _concept_card("Efficience des marchés (EMH)", """
La théorie des marchés efficients (Fama, 1970) postule que les prix reflètent <i>toute</i>
l'information disponible. Il existerait 3 formes :<br><br>
• <b>Faible</b> — les prix passés ne prédisent pas les prix futurs (AT inefficace)<br>
• <b>Semi-forte</b> — l'information publique est déjà dans les prix (AF tardive)<br>
• <b>Forte</b> — même l'information privée est reflétée (insider trading inutile)<br><br>
<b style="color:#ff3b6b;">Anomalies prouvées contredisant l'EMH :</b> momentum, value premium,
small-cap premium, calendar effects (janvier), post-earnings drift, low volatility anomaly.<br><br>
<b>Implication pratique :</b> même si les marchés sont globalement efficaces, des poches
d'inefficience exploitables existent, surtout sur les marchés moins suivis.
    """, "🎓", "#00d4ff")

    _concept_card("Modèles factoriels (CAPM → Fama-French)", """
<b>CAPM (1964) :</b> E(Ri) = Rf + βi × [E(Rm) − Rf]<br>
Rendement attendu = taux sans risque + β × prime de risque marché<br><br>
<b>Fama-French 3 facteurs (1992) :</b><br>
E(Ri) = Rf + β₁×MKT + β₂×SMB + β₃×HML<br>
MKT = marché, SMB = small minus big (prime small cap), HML = high minus low (prime value)<br><br>
<b>Carhart 4 facteurs (1997) :</b> + WML (winners minus losers = momentum)<br><br>
<b>Fama-French 5 facteurs (2015) :</b> + RMW (profitabilité) + CMA (investissement)<br><br>
<b style="color:#ffd700;">Usage pratique :</b> décomposer la performance d'un fonds entre
alpha pur et exposition aux facteurs connus (smart beta).
    """, "⚛️", "#ffd700")

    _formula_box("E(Ri) = Rf + β₁·MKT + β₂·SMB + β₃·HML + β₄·WML", "Modèle Carhart 4 facteurs")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 2 — PRODUITS FINANCIERS
# ═════════════════════════════════════════════════════════════════════════════

def _products_tab():
    section_title("LES PRODUITS FINANCIERS", "📦")

    product = st.selectbox("Choisir un produit", [
        "📈 Actions (Equities)",
        "🏛️ Obligations (Bonds)",
        "📊 ETF & Fonds indiciels",
        "₿ Crypto-actifs",
        "🛢️ Matières premières (Commodities)",
        "💱 Forex (Change)",
        "🏠 REITs (Immobilier coté)",
    ], key="edu_product")

    if "Actions" in product:
        _product_equities()
    elif "Obligations" in product:
        _product_bonds()
    elif "ETF" in product:
        _product_etf()
    elif "Crypto" in product:
        _product_crypto()
    elif "Matières" in product:
        _product_commodities()
    elif "Forex" in product:
        _product_forex()
    elif "REITs" in product:
        _product_reits()


def _product_equities():
    _concept_card("Actions — Participer à la croissance des entreprises", """
Une <b>action</b> représente une fraction de propriété d'une entreprise. En achetant une action AAPL,
vous devenez copropriétaire d'Apple avec droits sur les bénéfices futurs et droit de vote.<br><br>
<b style="color:#00ff88;">Sources de rendement :</b><br>
• <b>Plus-value (capital gain)</b> — revente à un prix plus élevé<br>
• <b>Dividendes</b> — distribution d'une partie des bénéfices (ex: MSFT 0.8%/an)<br><br>
<b style="color:#ffd700;">Types d'actions :</b><br>
• <b>Actions ordinaires</b> — droit de vote, dernier rang en liquidation<br>
• <b>Actions préférentielles</b> — dividende prioritaire, souvent sans vote<br>
• <b>Actions de croissance (growth)</b> — entreprises réinvestissant tout (NVDA, AMZN)<br>
• <b>Actions de valeur (value)</b> — sous-évaluées, souvent avec dividendes (JPM, KO)<br><br>
<b style="color:#00d4ff;">Métriques clés :</b> P/E, P/B, ROE, ROA, marge nette, croissance du BPA,
dette/EBITDA, FCF par action.
    """, "📈", "#00ff88")

    # Interactive P/E valuation
    section_title("SIMULATEUR DE VALORISATION PAR P/E", "🎯")
    col1, col2 = st.columns(2)
    with col1:
        eps_val  = st.number_input("BPA (EPS) $", 0.01, 1000.0, 5.0, 0.5, key="eq_eps")
        pe_ratio = st.slider("P/E cible", 5, 80, 20, key="eq_pe")
    with col2:
        growth_eps = st.slider("Croissance BPA (%/an)", -20, 50, 10, key="eq_g")
        years_eq   = st.slider("Horizon (années)", 1, 10, 5, key="eq_yr")

    fair_px = eps_val * pe_ratio
    future_eps = eps_val * (1 + growth_eps/100) ** years_eq
    future_px  = future_eps * pe_ratio

    metric_row([
        {"label": "Valorisation actuelle", "value": f"${fair_px:,.2f}", "color": ""},
        {"label": f"BPA dans {years_eq}ans", "value": f"${future_eps:,.2f}", "color": "positive"},
        {"label": f"Prix futur (P/E {pe_ratio}×)", "value": f"${future_px:,.2f}", "color": "positive"},
        {"label": "Gain potentiel",         "value": f"{(future_px/fair_px-1)*100:+.1f}%", "color": "positive"},
    ])


def _product_bonds():
    _concept_card("Obligations — Prêter de l'argent contre des intérêts", """
Une <b>obligation</b> est un titre de dette. L'émetteur (État ou entreprise) emprunte votre argent
et s'engage à vous verser des intérêts réguliers (<b>coupons</b>) puis à rembourser le capital
(<b>valeur nominale</b>) à l'échéance.<br><br>
<b style="color:#00d4ff;">Caractéristiques :</b><br>
• <b>Valeur nominale (face value)</b> — capital remboursé à maturité (ex: 1 000$)<br>
• <b>Coupon</b> — taux d'intérêt annuel (ex: 4% = 40$/an)<br>
• <b>Maturité</b> — durée jusqu'au remboursement (1 mois à 30+ ans)<br>
• <b>YTM (Yield to Maturity)</b> — rendement réel si détenu jusqu'à l'échéance<br><br>
<b style="color:#ff3b6b;">Relation prix/taux (fondamentale) :</b><br>
Quand les taux montent → prix des obligations baissent. Et vice-versa.<br>
Un taux de coupon fixé à 4% vaut moins si le marché offre 6%.<br><br>
<b style="color:#ffd700;">Types :</b> bons du Trésor (T-Bills/Notes/Bonds), OAT, Bunds,
obligations d'entreprise (investment grade ≥BBB, high yield/junk <BB), obligations indexées inflation.
    """, "🏛️", "#ffd700")

    # Duration & Yield interactive
    section_title("CALCULATEUR DE PRIX D'OBLIGATION", "🧮")
    col1, col2, col3 = st.columns(3)
    with col1:
        face_val = st.number_input("Valeur nominale ($)", 100.0, 10_000.0, 1_000.0, key="bond_fv")
        coupon   = st.slider("Taux coupon (%)", 0.0, 15.0, 4.0, 0.25, key="bond_c") / 100
    with col2:
        ytm      = st.slider("YTM / Taux marché (%)", 0.1, 20.0, 4.5, 0.1, key="bond_ytm") / 100
        n_years  = st.slider("Maturité (années)", 1, 30, 10, key="bond_n")
    with col3:
        freq     = st.radio("Fréquence coupon", ["Annuelle", "Semestrielle"], key="bond_freq")

    periods = n_years * (2 if freq == "Semestrielle" else 1)
    c_amt   = face_val * coupon / (2 if freq == "Semestrielle" else 1)
    y_per   = ytm / (2 if freq == "Semestrielle" else 1)

    # Price = PV of coupons + PV of face value
    pv_coupons = c_amt * (1 - (1 + y_per)**(-periods)) / y_per if y_per else c_amt * periods
    pv_face    = face_val / (1 + y_per)**periods
    bond_price = pv_coupons + pv_face

    # Modified duration
    dur_num = sum(t * c_amt / (1+y_per)**t for t in range(1, periods+1))
    dur_num += periods * face_val / (1+y_per)**periods
    macaulay_dur = dur_num / bond_price / (2 if freq == "Semestrielle" else 1)
    mod_dur = macaulay_dur / (1 + y_per)

    metric_row([
        {"label": "Prix de l'obligation", "value": f"${bond_price:,.2f}",
         "color": "positive" if bond_price >= face_val else "negative"},
        {"label": "Prime / Décote",       "value": f"${bond_price-face_val:+,.2f}", "color": ""},
        {"label": "Duration Macaulay",    "value": f"{macaulay_dur:.2f} ans", "color": ""},
        {"label": "Duration Modifiée",    "value": f"{mod_dur:.2f}", "color": ""},
    ])

    _info_box(
        f"⚡ Sensibilité : si les taux montent de <b>+1%</b>, le prix de l'obligation "
        f"baisserait d'environ <b style='color:#ff3b6b;'>−{mod_dur:.2f}%</b> "
        f"(soit <b style='color:#ff3b6b;'>−${bond_price*mod_dur/100:,.2f}</b>).",
        "#ff3b6b"
    )


def _product_etf():
    _concept_card("ETF — Diversification instantanée à faible coût", """
Un <b>ETF (Exchange-Traded Fund)</b> est un fonds coté en bourse qui réplique un indice,
un secteur ou une stratégie. C'est l'innovation la plus importante pour les investisseurs particuliers.<br><br>
<b style="color:#00ff88;">Avantages :</b><br>
• <b>Diversification immédiate</b> — SPY = 500 entreprises US en 1 ticker<br>
• <b>Frais très bas</b> — TER souvent entre 0.03% et 0.20%/an<br>
• <b>Liquidité</b> — s'achète/se vend comme une action en bourse<br>
• <b>Transparence</b> — composition publiée quotidiennement<br><br>
<b style="color:#ffd700;">Types d'ETF :</b><br>
• <b>Indiciels</b> — SPY (S&P 500), QQQ (NASDAQ-100), IWDA (World)<br>
• <b>Sectoriels</b> — XLK (tech), XLV (santé), XLE (énergie)<br>
• <b>Obligataires</b> — AGG, TLT, HYG<br>
• <b>Matières premières</b> — GLD (or), SLV (argent), USO (pétrole)<br>
• <b>Crypto</b> — IBIT (Bitcoin spot), FETH (Ethereum spot)<br>
• <b>Factoriels (Smart Beta)</b> — MTUM (momentum), VLUE (value), QUAL (qualité)<br>
• <b>Leveragés/Inversés</b> — TQQQ (3×NASDAQ), SQQQ (−3×NASDAQ) — très risqués !
    """, "📊", "#00d4ff")


def _product_crypto():
    _concept_card("Crypto-actifs — La nouvelle classe d'actifs", """
Les <b>crypto-actifs</b> sont des actifs numériques basés sur la technologie blockchain
(registre distribué et immuable). Classe d'actifs émergente depuis 2009.<br><br>
<b style="color:#ffd700;">Principales catégories :</b><br>
• <b>Bitcoin (BTC)</b> — réserve de valeur numérique, offre limitée à 21M, PoW<br>
• <b>Ethereum (ETH)</b> — plateforme de contrats intelligents, PoS depuis 2022<br>
• <b>Stablecoins</b> — USDC, USDT (indexés au dollar), risque de contrepartie<br>
• <b>DeFi tokens</b> — protocoles de finance décentralisée (UNI, AAVE, CRV)<br>
• <b>Altcoins</b> — SOL, ADA, AVAX — spéculation élevée<br><br>
<b style="color:#ff3b6b;">Risques spécifiques :</b><br>
• Volatilité extrême (BTC a perdu -80% plusieurs fois)<br>
• Risque réglementaire (interdictions, taxation)<br>
• Risque de garde (exchange hack, perte de clés privées)<br>
• Liquidité variable sur petites capitalisations<br><br>
<b style="color:#00d4ff;">Allocation recommandée :</b> 1-5% du portefeuille pour la plupart des investisseurs.
    """, "₿", "#ff8c00")


def _product_commodities():
    _concept_card("Matières premières — Actifs réels et protection inflation", """
Les <b>commodities</b> sont des matières premières standardisées échangées sur des marchés à terme.<br><br>
<b style="color:#ffd700;">Catégories principales :</b><br>
• <b>Métaux précieux</b> — Or (GC=F), Argent (SI=F) → valeur refuge, protection inflation<br>
• <b>Énergie</b> — Pétrole WTI (CL=F), Brent (BZ=F), Gaz naturel (NG=F)<br>
• <b>Métaux industriels</b> — Cuivre (HG=F), Aluminium → indicateur de la santé économique<br>
• <b>Agricoles</b> — Blé, Maïs, Soja, Café, Cacao → sensibles aux conditions météo<br><br>
<b style="color:#00d4ff;">Modes d'exposition :</b><br>
• Acheter l'actif physique (or lingot) — coûteux en stockage<br>
• ETF sur matières premières (GLD, SLV, USO)<br>
• Futures et options sur commodities<br>
• Actions de producteurs (compagnies minières, pétrolières)<br><br>
<b style="color:#00ff88;">Rôle dans un portefeuille :</b> diversification (corrélation faible avec actions),
protection contre l'inflation, couverture géopolitique.
    """, "🛢️", "#ff8c00")


def _product_forex():
    _concept_card("Forex — Le plus grand marché au monde", """
Le <b>marché des changes (Forex)</b> est le marché où s'échangent les devises. Avec
~$7 500 milliards de transactions par jour, c'est de loin le plus grand marché financier.<br><br>
<b style="color:#00d4ff;">Mécanismes :</b><br>
• Les paires de devises s'expriment ainsi : EUR/USD = 1.08 signifie 1€ = 1.08$<br>
• <b>Devise de base</b> (gauche) / <b>Devise cotée</b> (droite)<br>
• <b>Spread</b> = différence entre prix d'achat (ask) et de vente (bid) → coût de transaction<br>
• <b>Pip</b> = 4ème décimale = 0.0001 (unité de mesure des mouvements)<br>
• <b>Lot standard</b> = 100 000 unités de devise de base<br><br>
<b style="color:#ffd700;">Principaux déterminants du taux de change :</b><br>
• Différentiel de taux d'intérêt (carry trade)<br>
• Balance commerciale et balance des paiements<br>
• Inflation relative (Parité de Pouvoir d'Achat)<br>
• Politique monétaire des banques centrales (Fed, BCE, BoJ)<br>
• Sentiment risk-on/risk-off (USD, CHF, JPY : devises refuges)
    """, "💱", "#a78bfa")


def _product_reits():
    _concept_card("REITs — Investir dans l'immobilier sans acheter de bien", """
Un <b>REIT (Real Estate Investment Trust)</b> est une société cotée qui détient et gère
des biens immobiliers générant des revenus locatifs. Obligation légale de distribuer
≥90% des revenus imposables aux actionnaires.<br><br>
<b style="color:#00ff88;">Types de REITs :</b><br>
• <b>Equity REITs</b> — détiennent des propriétés physiques (commerces, bureaux, résidentiel)<br>
• <b>mREITs (mortgage)</b> — investissent dans des créances hypothécaires<br>
• <b>Diversifiés</b> — mixte<br><br>
<b style="color:#ffd700;">Sous-secteurs :</b> data centers (EQIX, DLR), tours cellulaires (AMT, CCI),
santé (Welltower), entrepôts logistiques (Prologis), commerces (Realty Income).<br><br>
<b style="color:#00d4ff;">Avantages :</b> rendements dividendes élevés (4-7%), liquidité vs
immobilier direct, diversification, inflation hedge (loyers indexés).<br>
<b style="color:#ff3b6b;">Risques :</b> sensibles aux taux d'intérêt (coût de financement),
dépréciations cycliques, risque locatif.
    """, "🏠", "#00ff88")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 3 — DÉRIVÉS & OPTIONS
# ═════════════════════════════════════════════════════════════════════════════

def _derivatives_tab():
    section_title("DÉRIVÉS — OPTIONS, FUTURES, SWAPS", "⚗️")

    deriv = st.radio("Produit dérivé", [
        "🎯 Options (intro)", "📐 Black-Scholes & Grecques",
        "🎯 Stratégies options (payoff)", "📅 Futures & Forwards", "🔄 Swaps & Autres"
    ], horizontal=True, key="edu_deriv")

    if "intro" in deriv:
        _deriv_options_intro()
    elif "Black" in deriv:
        _deriv_bs_greeks()
    elif "Stratégies" in deriv:
        _options_strategies_tab()
    elif "Futures" in deriv:
        _deriv_futures()
    else:
        _deriv_swaps()


def _deriv_options_intro():
    _concept_card("Qu'est-ce qu'une option ?", """
Une <b>option</b> est un contrat donnant le <i>droit</i> (mais pas l'obligation) :<br><br>
• <b>Option CALL</b> — droit d'<b>acheter</b> un actif à un prix fixé (strike K) avant ou à la date d'expiration<br>
• <b>Option PUT</b> — droit de <b>vendre</b> un actif à un prix fixé (strike K) avant ou à la date d'expiration<br><br>
<b style="color:#ffd700;">Termes fondamentaux :</b><br>
• <b>Prime (premium)</b> — prix payé pour acheter l'option<br>
• <b>Strike (K)</b> — prix d'exercice convenu dans le contrat<br>
• <b>Expiration (T)</b> — date limite d'exercice<br>
• <b>Sous-jacent (S)</b> — actif sur lequel porte l'option (action, indice, matière première)<br>
• <b>In-the-money (ITM)</b> — call: S>K / put: S<K → l'option a une valeur intrinsèque<br>
• <b>Out-of-the-money (OTM)</b> — call: S<K / put: S>K → valeur uniquement temporelle<br>
• <b>At-the-money (ATM)</b> — S ≈ K<br><br>
<b style="color:#00d4ff;">Options européennes vs américaines :</b><br>
• Européenne → exercice uniquement à l'expiration (MAM utilise ce modèle)<br>
• Américaine → exercice possible à tout moment avant expiration
    """, "🎯", "#a78bfa")

    _concept_card("Valeur d'une option = Valeur intrinsèque + Valeur temporelle", """
<b>Valeur intrinsèque</b> = max(S − K, 0) pour un call, max(K − S, 0) pour un put<br>
C'est le gain immédiat si l'option était exercée maintenant.<br><br>
<b>Valeur temporelle (time value)</b> = Prime − Valeur intrinsèque<br>
C'est la prime payée pour la probabilité que l'option finisse ITM avant expiration.<br>
Elle diminue avec le temps (time decay, mesuré par Theta θ).<br><br>
<b style="color:#ffd700;">Facteurs influençant la prime :</b><br>
• ↑ Prix du sous-jacent → ↑ Call, ↓ Put<br>
• ↑ Strike → ↓ Call, ↑ Put<br>
• ↑ Temps restant → ↑ Prime (+ de valeur temporelle)<br>
• ↑ Volatilité implicite → ↑ Prime (les deux sens)<br>
• ↑ Taux d'intérêt → ↑ Call légèrement, ↓ Put légèrement<br>
• ↑ Dividendes → ↓ Call, ↑ Put
    """, "💎", "#00d4ff")


def _deriv_bs_greeks():
    section_title("BLACK-SCHOLES & LES GRECQUES — PRICER INTERACTIF", "📐")

    _info_box(
        "Le modèle de <b>Black-Scholes-Merton (1973)</b> permet de calculer le prix théorique "
        "d'une option européenne et ses sensibilités (Grecques). Hypothèses : volatilité constante, "
        "marché sans friction, pas de dividendes, distribution log-normale des prix."
    )

    _formula_box(
        "C = S·N(d₁) − K·e⁻ʳᵀ·N(d₂)<br>"
        "d₁ = [ln(S/K) + (r + σ²/2)·T] / (σ√T)<br>"
        "d₂ = d₁ − σ√T",
        "Formule de Black-Scholes (Call européen)"
    )

    assets_df = load_assets()
    # FIXED: use "category" not "type"
    opt_assets = assets_df[assets_df["category"].isin(["Equities", "ETF", "Crypto"])]
    ticker_opts = {f'{r["ticker"]} — {r["name"]}': r["ticker"] for _, r in opt_assets.iterrows()}

    col1, col2 = st.columns([1, 1])
    with col1:
        section_title("PARAMÈTRES", "⚙️")
        sel = st.selectbox("Sous-jacent", list(ticker_opts.keys()), key="bs_underlying")
        ticker = ticker_opts[sel]
        price  = get_price(ticker)
        st.markdown(
            f'<div style="font-family:Share Tech Mono;font-size:.78rem;color:#7a93b0;margin:4px 0 10px;">'
            f'Spot actuel : <b style="color:#00d4ff;">${price:,.4f}</b></div>', unsafe_allow_html=True)

        opt_type = st.radio("Type", ["call", "put"], horizontal=True, key="bs_type")
        K   = st.number_input("Strike (K $)", 0.01, 1e7, round(price, 2), 0.5, key="bs_K")
        T   = st.slider("Maturité (jours)", 1, 730, 45, key="bs_T") / 365
        r   = st.slider("Taux sans risque (%)", 0.0, 10.0, 4.25, 0.05, key="bs_r") / 100
        sig = st.slider("Volatilité implicite (%)", 1.0, 200.0, 25.0, 0.5, key="bs_sig") / 100

    with col2:
        section_title("RÉSULTATS & GRECQUES", "📊")
        prem    = bs_price(price, K, T, r, sig, opt_type)
        greeks  = bs_greeks(price, K, T, r, sig, opt_type)

        st.markdown(
            f'<div style="background:rgba(124,58,237,.08);border:1px solid rgba(124,58,237,.3);'
            f'border-radius:8px;padding:16px;text-align:center;margin-bottom:14px;">'
            f'<div style="font-family:Rajdhani;font-size:.65rem;color:#7a93b0;letter-spacing:.1em;">PRIME</div>'
            f'<div style="font-family:Share Tech Mono;font-size:2.2rem;color:#a78bfa;font-weight:bold;">'
            f'${prem:,.4f}</div></div>', unsafe_allow_html=True)

        greek_explanations = {
            "Δ DELTA":  (greeks["delta"], "Variation prime / Variation S (+$1)"),
            "Γ GAMMA":  (greeks["gamma"], "Variation delta / Variation S (convexité)"),
            "Θ THETA":  (greeks["theta"], "Perte de valeur par jour (time decay)"),
            "ν VEGA":   (greeks["vega"],  "Variation prime si vol +1%"),
            "ρ RHO":    (greeks["rho"],   "Variation prime si taux +1%"),
        }
        for name, (val, desc) in greek_explanations.items():
            col_g = "#00ff88" if val > 0 else ("#ff3b6b" if val < 0 else "#ffd700")
            st.markdown(
                f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.05);'
                f'border-radius:5px;padding:8px 12px;margin-bottom:5px;display:flex;'
                f'justify-content:space-between;align-items:center;">'
                f'<div><div style="font-family:Rajdhani;font-size:.68rem;color:#7a93b0;">{name}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:.62rem;color:#475569;">{desc}</div></div>'
                f'<div style="font-family:Share Tech Mono;font-size:1rem;color:{col_g};font-weight:bold;">'
                f'{val:+.4f}</div>'
                f'</div>', unsafe_allow_html=True)

    # Sensitivity heatmap (price vs vol)
    section_title("HEATMAP PRIX OPTION — Spot × Volatilité", "🔥")
    spots_grid = np.linspace(price * 0.7, price * 1.3, 12)
    vols_grid  = np.linspace(0.05, 0.70, 12)
    z_grid     = np.zeros((len(vols_grid), len(spots_grid)))
    for i, v in enumerate(vols_grid):
        for j, s in enumerate(spots_grid):
            z_grid[i, j] = bs_price(s, K, T, r, v, opt_type)

    fig_hm = go.Figure(go.Heatmap(
        z=z_grid,
        x=[f"${s:,.0f}" for s in spots_grid],
        y=[f"{v*100:.0f}%" for v in vols_grid],
        colorscale="Viridis",
        colorbar=dict(title="Prime $", tickfont=dict(size=9, family="Share Tech Mono")),
        hovertemplate="Spot: %{x}<br>Vol: %{y}<br>Prime: $%{z:.4f}<extra></extra>"))
    fig_hm.update_layout(**_P, height=300,
        xaxis=dict(title="Prix spot"), yaxis=dict(title="Volatilité"))
    st.plotly_chart(fig_hm, use_container_width=True)


def _deriv_futures():
    _concept_card("Futures & Forwards — S'engager sur un prix futur", """
Un <b>contrat à terme (future/forward)</b> est un accord d'acheter ou de vendre un actif
à une date future à un prix fixé aujourd'hui.<br><br>
<b style="color:#00d4ff;">Future vs Forward :</b><br>
• <b>Future</b> — standardisé, coté en bourse (CME, ICE), marked-to-market quotidien, dépôt de garantie<br>
• <b>Forward</b> — OTC (de gré à gré), personnalisé, règlement à échéance, risque de contrepartie<br><br>
<b style="color:#ffd700;">Mécanismes clés :</b><br>
• <b>Prix futur théorique</b> = Spot × e^(r-q)T (modèle cost-of-carry)<br>
• <b>Basis</b> = Prix futur − Prix spot (contango si >0, backwardation si <0)<br>
• <b>Marge initiale (initial margin)</b> — caution déposée à l'ouverture<br>
• <b>Appel de marge (margin call)</b> — si les pertes dépassent la marge de maintenance<br>
• <b>Effet de levier</b> — contrôle un gros notionnel avec peu de capital<br><br>
<b style="color:#00ff88;">Usages :</b><br>
• <b>Couverture (hedging)</b> — un producteur de blé vend des futures pour sécuriser son prix<br>
• <b>Spéculation</b> — trader directionnellement avec levier<br>
• <b>Arbitrage</b> — exploiter les écarts entre contrats et actifs sous-jacents
    """, "📅", "#ffd700")

    _formula_box(
        "F = S × e^(r−q)×T",
        "Prix théorique d'un future (modèle cost-of-carry) — q = rendement de dividende"
    )


def _deriv_swaps():
    _concept_card("Swaps, CFDs & Produits Structurés", """
<b style="color:#00d4ff;">SWAP</b> — Échange de flux financiers entre deux parties.<br>
• <b>IRS (Interest Rate Swap)</b> — échange taux fixe vs taux variable (EURIBOR/SOFR)<br>
• <b>CDS (Credit Default Swap)</b> — assurance contre le défaut d'un émetteur<br>
• <b>Currency Swap</b> — échange de flux dans deux devises différentes<br>
• <b>Total Return Swap</b> — échange de la performance totale d'un actif<br><br>
<b style="color:#ffd700;">CFD (Contract for Difference)</b> — contrat sur la différence de prix :<br>
• Pas de livraison de l'actif réel<br>
• Accès à de nombreux marchés avec levier<br>
• Disponibles 24h/24 sur certains brokers<br>
• <b style="color:#ff3b6b;">Risque élevé : 70-80% des CFD traders perdent de l'argent</b><br><br>
<b style="color:#a78bfa;">Produits structurés</b> — combinaison d'obligations + dérivés :<br>
• Capital garanti + participation à la hausse d'un indice<br>
• Autocall / Phoenix — remboursement anticipé si barrière franchie<br>
• Reverse convertible — coupon élevé mais risque de livraison d'actions
    """, "🔄", "#a78bfa")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 4 — STRATÉGIES D'INVESTISSEMENT
# ═════════════════════════════════════════════════════════════════════════════

def _strategies_tab():
    section_title("STRATÉGIES D'INVESTISSEMENT", "🎯")

    strat_cat = st.selectbox("Catégorie de stratégie", [
        "📈 Investissement Long Terme (Buy & Hold)",
        "📊 Investissement factoriel (Factor Investing)",
        "🏃 Trading actif & Momentum",
        "🛡️ Stratégies défensives & Couverture",
        "🎯 Stratégies options avancées (multi-jambes)",
        "🌍 Allocation macro globale",
    ], key="edu_strat_cat")

    if "Buy" in strat_cat:
        _strat_buy_hold()
    elif "factoriel" in strat_cat:
        _strat_factor()
    elif "Trading" in strat_cat:
        _strat_trading()
    elif "défensives" in strat_cat:
        _strat_defensive()
    elif "options" in strat_cat:
        _options_strategies_tab()
    else:
        _strat_macro()


def _strat_buy_hold():
    _concept_card("Buy & Hold — La stratégie des millionnaires silencieux", """
Acheter des actifs de qualité et les conserver à long terme, indépendamment des fluctuations.<br><br>
<b style="color:#00ff88;">Fondements :</b><br>
• Les marchés montent sur le long terme (~10%/an pour le S&P 500 sur 100 ans)<br>
• Le market timing est quasi-impossible même pour les professionnels<br>
• Les frais de transaction et l'imposition des gains réduisent la performance du trading actif<br>
• "Time in the market > Timing the market"<br><br>
<b style="color:#ffd700;">Mise en œuvre :</b><br>
• <b>DCA (Dollar Cost Averaging)</b> — investir une somme fixe régulièrement (mensuel)<br>
• Diversification géographique : US, Europe, marchés émergents<br>
• Réallocation annuelle (rééquilibrage) pour maintenir le profil de risque cible<br><br>
<b style="color:#00d4ff;">Portefeuille modèle 60/40 :</b><br>
60% actions mondiales (IWDA, SPY, VT) + 40% obligations (AGG, BND)<br>
Rendement historique : ~8%/an, volatilité ~10%/an, max drawdown ~-30%
    """, "📈", "#00ff88")

    # DCA simulator
    section_title("SIMULATEUR DCA", "🧮")
    col1, col2 = st.columns(2)
    with col1:
        monthly_inv = st.number_input("Investissement mensuel ($)", 100, 100_000, 500, 100, key="dca_mo")
        years_dca   = st.slider("Durée (années)", 5, 40, 20, key="dca_yr")
    with col2:
        ret_ann     = st.slider("Rendement annuel (%)", 1.0, 20.0, 8.0, 0.5, key="dca_ret")
        init_dca    = st.number_input("Capital initial ($)", 0, 1_000_000, 0, 1_000, key="dca_init")

    monthly_rate = ret_ann / 100 / 12
    months       = years_dca * 12
    capitals     = [init_dca]
    invested     = [init_dca]

    c = init_dca
    total_inv = init_dca
    for m in range(1, months + 1):
        c = c * (1 + monthly_rate) + monthly_inv
        total_inv += monthly_inv
        if m % 12 == 0:
            capitals.append(c)
            invested.append(total_inv)

    years_arr = list(range(len(capitals)))

    fig_dca = go.Figure()
    fig_dca.add_trace(go.Scatter(x=years_arr, y=capitals, name="Valeur du portefeuille",
        line=dict(color="#00d4ff", width=2.5),
        fill="tozeroy", fillcolor="rgba(0,212,255,.07)",
        hovertemplate="Année %{x}<br>Valeur: $%{y:,.0f}<extra></extra>"))
    fig_dca.add_trace(go.Scatter(x=years_arr, y=invested, name="Capital investi",
        line=dict(color="#7a93b0", width=1.5, dash="dot"),
        hovertemplate="Année %{x}<br>Investi: $%{y:,.0f}<extra></extra>"))
    fig_dca.update_layout(**_P, height=250,
        xaxis=dict(title="Années", gridcolor="rgba(255,255,255,.04)"),
        yaxis=dict(title="Valeur ($)", gridcolor="rgba(255,255,255,.04)"),
        legend=dict(orientation="h", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig_dca, use_container_width=True)

    metric_row([
        {"label": "Capital investi total",  "value": f"${invested[-1]:,.0f}", "color": ""},
        {"label": "Valeur finale",           "value": f"${capitals[-1]:,.0f}", "color": "positive"},
        {"label": "Gains des intérêts",      "value": f"${capitals[-1]-invested[-1]:,.0f}", "color": "positive"},
        {"label": "Multiplicateur",          "value": f"×{capitals[-1]/max(invested[-1],1):.1f}", "color": "positive"},
    ])


def _strat_factor():
    _concept_card("Factor Investing — Les moteurs prouvés de la surperformance", """
Le <b>factor investing</b> consiste à investir en ciblant des caractéristiques (facteurs)
qui ont historiquement généré une prime de rendement ajusté du risque.<br><br>
<b style="color:#00d4ff;">Les 6 facteurs principaux :</b><br><br>
📈 <b>Marché (Market Beta)</b> — Détenir des actions vs cash. Prima : ~5-7%/an (compensation du risque systémique)<br><br>
💰 <b>Valeur (Value)</b> — Acheter des actions bon marché (P/B, P/E faibles). Prima : ~3-5%/an<br>
→ ETFs : VLUE, IWD, SPYV<br><br>
🏃 <b>Momentum</b> — Acheter les gagnants récents (3-12 mois). Prima : ~4-6%/an<br>
→ ETFs : MTUM, PDP<br><br>
📏 <b>Taille (Size)</b> — Small caps surperforment les large caps. Prima : ~2-3%/an<br>
→ ETFs : IWM, VBK<br><br>
⭐ <b>Qualité (Quality)</b> — ROE élevé, bilan solide, croissance stable<br>
→ ETFs : QUAL, DGRW<br><br>
📉 <b>Faible volatilité (Low Vol)</b> — Contre-intuitif : les actifs peu volatils surperforment à long terme<br>
→ ETFs : SPLV, USMV
    """, "📊", "#a78bfa")


def _strat_trading():
    _concept_card("Trading actif — Momentum, trend following, mean reversion", """
<b style="color:#ff3b6b;">Avertissement :</b> 80-90% des traders actifs sous-performent le marché à long terme.
Le trading nécessite discipline, gestion du risque rigoureuse et avantage statistique prouvé.<br><br>
<b style="color:#00d4ff;">Principales approches :</b><br><br>
🏃 <b>Trend Following (Suivi de tendance)</b><br>
• Acheter ce qui monte, vendre ce qui baisse<br>
• Indicateurs : EMA, ADX, Ichimoku, Canal de Donchian<br>
• Timeframe : daily/weekly, durée de position : semaines à mois<br><br>
🔄 <b>Mean Reversion (Retour à la moyenne)</b><br>
• Acheter les actifs en survente, vendre les suracheté<br>
• Indicateurs : RSI, Bandes de Bollinger, Z-score<br>
• Fonctionne sur des marchés en range (sans tendance)<br><br>
⚡ <b>Momentum court terme</b><br>
• Jouer les mouvements post-earnings, post-catalyst<br>
• Nécessite un gestionnaire d'ordres rapide et une excellente maîtrise des risques<br><br>
📊 <b>Arbitrage statistique (Pairs Trading)</b><br>
• Identifier deux actifs coïntégrés, acheter le retardataire, vendre le leader<br>
• Ex: AAPL vs MSFT, SPY vs QQQ
    """, "🏃", "#ffd700")


def _strat_defensive():
    _concept_card("Stratégies défensives & Couverture (Hedging)", """
<b>Couvrir</b> son portefeuille signifie réduire le risque en prenant une position opposée.<br><br>
<b style="color:#00d4ff;">Instruments de couverture :</b><br><br>
🛡️ <b>Options PUT protectrices (Protective Put)</b><br>
• Acheter des puts sur ses positions longues → assurance contre la baisse<br>
• Coût : la prime de l'option (=coût de l'assurance)<br><br>
📊 <b>Vente de calls couverts (Covered Call)</b><br>
• Vendre des calls sur ses positions longues → générer du revenu<br>
• Plafonne le gain à la hausse, réduit le coût de portage<br><br>
📉 <b>ETF inverses</b><br>
• SQQQ (−3× NASDAQ), SH (−1× S&P 500) → couverture temporaire<br>
• Ne pas détenir longtemps (volatility drag)<br><br>
💛 <b>Actifs refuges (Safe Havens)</b><br>
• Or, CHF, JPY, Bons du Trésor US → apprécient en période de stress<br><br>
📈 <b>VIX (Fear Index)</b><br>
• Quand le VIX monte, les marchés baissent généralement<br>
• UVXY, VIXY : ETFs sur la volatilité — très spéculatifs
    """, "🛡️", "#00ff88")


def _strat_macro():
    _concept_card("Allocation Macro Globale (Global Macro)", """
Stratégie qui prend des positions larges en fonction des tendances macroéconomiques mondiales.<br><br>
<b style="color:#00d4ff;">Cadre d'analyse :</b><br><br>
🏦 <b>Cycle des banques centrales</b><br>
• Hausse des taux → favorise les obligations courtes, le dollar, défavorise les growth stocks<br>
• Baisse des taux → favorable aux actions, obligations longues, gold<br><br>
🌍 <b>Cycle économique</b><br>
• Expansion → surpondérer les cycliques (tech, industrie, financières)<br>
• Récession → sous-pondérer les cycliques, favoriser défensifs + or + obligations<br><br>
💹 <b>Carry trade Forex</b><br>
• Emprunter dans une devise à bas taux (JPY, CHF), placer dans une devise à haut taux<br>
• Risque de dénouement brutal lors des épisodes de stress<br><br>
📊 <b>Indicateurs macro clés à suivre :</b><br>
• PMI manufacturier et des services → activité économique<br>
• CPI / PCE → inflation → politique monétaire<br>
• Courbe des taux (2s10s) → signal de récession si inversée<br>
• DXY (indice dollar) → force du USD → impact marchés émergents et commodities
    """, "🌍", "#00d4ff")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 5 — THÉORIE DU PORTEFEUILLE
# ═════════════════════════════════════════════════════════════════════════════

def _portfolio_theory_tab():
    section_title("THÉORIE MODERNE DU PORTEFEUILLE", "🧮")

    _concept_card("Markowitz (1952) — Optimisation Moyenne-Variance", """
Harry Markowitz a démontré mathématiquement qu'un portefeuille diversifié est toujours
préférable à un actif unique pour un niveau de rendement attendu donné.<br><br>
<b style="color:#00d4ff;">Concepts clés :</b><br>
• <b>Rendement espéré du portefeuille</b> = Σ (wᵢ × μᵢ)<br>
• <b>Variance du portefeuille</b> = Σᵢ Σⱼ wᵢ wⱼ σᵢⱼ (tient compte des corrélations !)<br>
• <b>Frontière efficiente</b> — ensemble de portefeuilles offrant le max de rendement pour chaque niveau de risque<br>
• <b>Portefeuille tangent (Max Sharpe)</b> — point de la frontière tangent à la Capital Market Line<br>
• <b>Capital Market Line (CML)</b> — droite passant par le taux sans risque et le portefeuille tangent<br><br>
<b style="color:#ffd700;">Intuition clé sur la diversification :</b><br>
La corrélation entre actifs détermine le bénéfice de la diversification.<br>
Si corr = +1 → pas de réduction du risque. Si corr = −1 → couverture parfaite possible.
    """, "🧮", "#00d4ff")

    _formula_box(
        "SR = (E[Rp] − Rf) / σp",
        "Sharpe Ratio — Rendement ajusté du risque"
    )

    _concept_card("Mesures de performance ajustées du risque", """
<b>Sharpe Ratio</b> = (Rp − Rf) / σp<br>
Rendement excédentaire par unité de risque total. >1 = bon, >2 = excellent.<br><br>
<b>Sortino Ratio</b> = (Rp − Rf) / σ_downside<br>
Comme Sharpe mais pénalise uniquement la volatilité baissière. Plus adapté aux stratégies asymétriques.<br><br>
<b>Calmar Ratio</b> = Rendement annuel / |Max Drawdown|<br>
Évalue le rendement par rapport à la pire perte historique.<br><br>
<b>Information Ratio</b> = (Rp − Rbenchmark) / Tracking Error<br>
Mesure la capacité du gérant à surperformer son benchmark de manière consistante.<br><br>
<b>Treynor Ratio</b> = (Rp − Rf) / βp<br>
Rendement excédentaire par unité de risque systémique (bêta).<br><br>
<b>Maximum Drawdown (MDD)</b> = pire baisse pic-à-creux sur la période.<br>
Indicateur de résilience : un fonds avec MDD de -50% exige +100% de gain pour revenir au pair.
    """, "📊", "#a78bfa")

    # TWR vs MWR explanation
    _concept_card("TWR vs MWR — Mesurer la performance correctement", """
<b style="color:#00d4ff;">TWR (Time-Weighted Return)</b> — Standard CFA / GIPS<br>
Élimine l'impact du timing des flux de trésorerie. Mesure la performance du gérant<br>
indépendamment du comportement de l'investisseur (dépôts/retraits).<br>
Calcul : TWR = ∏ (1 + Rᵢ) − 1 (produit des sous-périodes)<br><br>
<b style="color:#ffd700;">MWR (Money-Weighted Return)</b> — Taux de Rendement Interne<br>
Tient compte du timing et de la taille des flux. Mesure la performance réelle de l'investisseur.<br>
Si l'investisseur injecte des fonds au mauvais moment, le MWR sera inférieur au TWR.<br><br>
<b>Exemple :</b><br>
• Gérant : +20% T1, -10% T2. TWR = (1.2 × 0.9) − 1 = 8%<br>
• Investisseur a doublé sa mise juste avant T2 → MWR négatif malgré le gérant performant<br><br>
→ <b>Pour évaluer un gérant : utiliser TWR. Pour évaluer votre propre résultat : utiliser MWR.</b>
    """, "⚖️", "#ffd700")


# ═════════════════════════════════════════════════════════════════════════════
# TAB 6 — OUTILS DE RISQUE
# ═════════════════════════════════════════════════════════════════════════════

def _risk_tools_tab():
    section_title("OUTILS DE RISQUE INTERACTIFS", "📐")

    tool = st.radio("Outil", [
        "📉 VaR Paramétrique",
        "🎲 Simulation Monte Carlo",
        "β Corrélation & Beta",
        "🔮 GARCH — Volatilité",
    ], horizontal=True, key="risk_tool")

    if "VaR" in tool:
        _var_tool()
    elif "Monte" in tool:
        _monte_carlo_tool()
    elif "Beta" in tool:
        _beta_tool()
    else:
        _garch_tool()


def _var_tool():
    section_title("VALUE AT RISK — PARAMÉTRIQUE", "📉")
    _info_box(
        "La <b>VaR paramétrique</b> assume une distribution normale des rendements.<br>"
        "<b>VaR(α) = μ − z_α × σ</b> &nbsp;|&nbsp; "
        "<b>CVaR = E[L | L > VaR]</b> (perte moyenne au-delà de la VaR)"
    )

    col1, col2 = st.columns(2)
    with col1:
        portfolio_val = st.number_input("Valeur du portefeuille ($)", 10_000.0, 100_000_000.0,
                                         1_000_000.0, 10_000.0, key="var_pv")
        ann_vol       = st.slider("Volatilité annualisée (%)", 1.0, 100.0, 15.0, 0.5, key="var_vol") / 100
        horizon       = st.slider("Horizon (jours)", 1, 252, 1, key="var_hor")
    with col2:
        conf_level    = st.slider("Niveau de confiance (%)", 90.0, 99.9, 95.0, 0.1, key="var_conf") / 100

    from scipy import stats
    daily_vol   = ann_vol / np.sqrt(252)
    h_vol       = daily_vol * np.sqrt(horizon)
    z           = stats.norm.ppf(1 - conf_level)
    var_pct     = abs(z) * h_vol
    var_dollar  = portfolio_val * var_pct
    cvar_pct    = stats.norm.pdf(z) / (1 - conf_level) * h_vol
    cvar_dollar = portfolio_val * cvar_pct

    metric_row([
        {"label": f"VaR {conf_level*100:.0f}% ({horizon}j) %",  "value": f"{var_pct*100:.2f}%",   "color": "negative"},
        {"label": f"VaR {conf_level*100:.0f}% ({horizon}j) $",  "value": f"${var_dollar:,.0f}",   "color": "negative"},
        {"label": f"CVaR (ES) {conf_level*100:.0f}%",            "value": f"${cvar_dollar:,.0f}",  "color": "negative"},
        {"label": "Volatilité journalière",                       "value": f"{daily_vol*100:.2f}%", "color": ""},
    ])

    x = np.linspace(-4 * h_vol, 4 * h_vol, 500)
    y = stats.norm.pdf(x, 0, h_vol)

    fig = go.Figure()
    x_var_zone = x[x <= -var_pct]
    fig.add_trace(go.Scatter(
        x=x_var_zone * 100, y=stats.norm.pdf(x_var_zone, 0, h_vol),
        fill="tozeroy", fillcolor="rgba(255,59,107,.3)",
        line=dict(width=0), name=f"Zone VaR {conf_level*100:.0f}%"))
    fig.add_trace(go.Scatter(x=x * 100, y=y,
        mode="lines", line=dict(color="#00d4ff", width=2), name="Distribution"))
    fig.add_vline(x=-var_pct * 100, line_color="#ff3b6b", line_dash="dash",
                  annotation_text=f"VaR: -{var_pct*100:.2f}%", annotation_font_color="#ff3b6b")
    fig.add_vline(x=0, line_color="rgba(255,255,255,.2)")
    fig.update_layout(**_P, height=250,
        xaxis=dict(title="Rendement (%)", gridcolor="rgba(255,255,255,.04)"),
        yaxis=dict(title="Densité", gridcolor="rgba(255,255,255,.04)"),
        legend=dict(orientation="h", y=1.02))
    st.plotly_chart(fig, use_container_width=True)


def _monte_carlo_tool():
    section_title("SIMULATION MONTE CARLO — PRIX FUTUR", "🎲")
    _info_box(
        "La <b>simulation de Monte Carlo</b> génère des milliers de scénarios possibles "
        "basés sur un processus de mouvement brownien géométrique (GBM) : "
        "<b>dS = μ·S·dt + σ·S·dW</b>"
    )

    assets_df   = load_assets()
    # FIXED: use "category" not "type"
    ticker_opts = {f'{r["ticker"]} — {r["name"]}': r["ticker"] for _, r in assets_df.iterrows()}
    sel    = st.selectbox("Actif", list(ticker_opts.keys()), key="mc_asset")
    ticker = ticker_opts[sel]
    price  = get_price(ticker)

    col1, col2 = st.columns(2)
    with col1:
        n_sim   = st.slider("Simulations", 100, 2000, 500, 100, key="mc_nsim")
        horizon = st.slider("Horizon (jours)", 10, 252, 60, key="mc_hor")
    with col2:
        mu_ann  = st.slider("Rendement espéré (% an)", -30.0, 50.0, 8.0, 0.5, key="mc_mu") / 100
        sig_ann = st.slider("Volatilité (% an)", 5.0, 100.0, 20.0, 0.5, key="mc_sig") / 100

    mu_d  = mu_ann / 252
    sig_d = sig_ann / np.sqrt(252)
    np.random.seed(42)
    paths = np.zeros((n_sim, horizon + 1))
    paths[:, 0] = price
    for t in range(1, horizon + 1):
        z = np.random.standard_normal(n_sim)
        paths[:, t] = paths[:, t-1] * np.exp((mu_d - 0.5 * sig_d**2) + sig_d * z)

    final_prices = paths[:, -1]
    p5, p25, p50, p75, p95 = (np.percentile(final_prices, q) for q in [5, 25, 50, 75, 95])

    fig = go.Figure()
    show_n = min(n_sim, 150)
    for i in range(show_n):
        fig.add_trace(go.Scatter(x=list(range(horizon+1)), y=paths[i],
            mode="lines", line=dict(color="rgba(0,212,255,0.04)", width=0.8), showlegend=False))

    pct_df = pd.DataFrame(paths.T)
    fig.add_trace(go.Scatter(x=list(range(horizon+1)), y=pct_df.quantile(0.95, axis=1),
        name="P95", line=dict(color="#00ff88", width=2, dash="dash")))
    fig.add_trace(go.Scatter(x=list(range(horizon+1)), y=pct_df.quantile(0.50, axis=1),
        name="Médiane", line=dict(color="#ffd700", width=2.5)))
    fig.add_trace(go.Scatter(x=list(range(horizon+1)), y=pct_df.quantile(0.05, axis=1),
        name="P5", line=dict(color="#ff3b6b", width=2, dash="dash")))
    fig.add_hline(y=price, line_color="rgba(255,255,255,.3)", line_dash="dot")
    fig.update_layout(**_P, height=300,
        title=dict(text=f"Monte Carlo — {ticker} ({n_sim} simulations, {horizon}j)",
                   font=dict(color="#00d4ff", size=12), x=0.01),
        xaxis=dict(title="Jours", gridcolor="rgba(255,255,255,.04)"),
        yaxis=dict(title="Prix ($)", gridcolor="rgba(255,255,255,.04)"),
        legend=dict(orientation="h", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True)

    metric_row([
        {"label": "P5 (pessimiste)",  "value": f"${p5:,.2f}",  "color": "negative"},
        {"label": "P25",              "value": f"${p25:,.2f}", "color": ""},
        {"label": "Médiane (P50)",    "value": f"${p50:,.2f}", "color": ""},
        {"label": "P75",              "value": f"${p75:,.2f}", "color": ""},
        {"label": "P95 (optimiste)",  "value": f"${p95:,.2f}", "color": "positive"},
    ])


def _beta_tool():
    section_title("CORRÉLATION & BETA vs INDICE", "β")

    assets_df   = load_assets()
    # FIXED: use "category" not "type"
    ticker_opts = {f'{r["ticker"]} — {r["name"]}': r["ticker"] for _, r in assets_df.iterrows()}

    col1, col2, col3 = st.columns(3)
    with col1:
        sel1 = st.selectbox("Actif", list(ticker_opts.keys()), key="beta_a1")
        ticker1 = ticker_opts[sel1]
    with col2:
        defaults = [k for k in ticker_opts if k.startswith("SPY")]
        idx = list(ticker_opts.keys()).index(defaults[0]) if defaults else 0
        sel2 = st.selectbox("Benchmark", list(ticker_opts.keys()), index=idx, key="beta_bm")
        ticker2 = ticker_opts[sel2]
    with col3:
        period = st.selectbox("Période", ["3mo", "6mo", "1y", "2y"], index=2, key="beta_per")

    with st.spinner("⏳ Chargement…"):
        h1 = get_history(ticker1, period)
        h2 = get_history(ticker2, period)

    if h1.empty or h2.empty:
        st.error("Données insuffisantes.")
        return

    df = pd.DataFrame({"a1": h1["Close"], "bm": h2["Close"]}).dropna()
    ret = df.pct_change().dropna()

    corr = float(ret.corr().iloc[0, 1])
    cov  = np.cov(ret["a1"], ret["bm"])
    beta = float(cov[0, 1] / cov[1, 1]) if cov[1, 1] != 0 else 0
    alpha_ann = float((ret["a1"].mean() - beta * ret["bm"].mean()) * 252 * 100)

    metric_row([
        {"label": "Corrélation",     "value": f"{corr:.4f}", "color": "positive" if corr > 0.7 else ""},
        {"label": "Beta (β)",        "value": f"{beta:.4f}", "color": "positive" if 0 < beta < 1.2 else "negative"},
        {"label": "Alpha annualisé", "value": f"{alpha_ann:+.2f}%",
         "color": "positive" if alpha_ann >= 0 else "negative"},
    ])

    fig = go.Figure(go.Scatter(
        x=ret["bm"] * 100, y=ret["a1"] * 100, mode="markers",
        marker=dict(size=4, color="rgba(0,212,255,.5)"),
        hovertemplate=f"{ticker2}: %{{x:.2f}}%<br>{ticker1}: %{{y:.2f}}%<extra></extra>"))
    x_line = np.linspace(ret["bm"].min(), ret["bm"].max(), 100)
    y_line = alpha_ann / 252 / 100 + beta * x_line
    fig.add_trace(go.Scatter(x=x_line*100, y=y_line*100,
        mode="lines", line=dict(color="#ff8c00", width=2, dash="dot"), name="Régression"))
    fig.add_hline(y=0, line_color="rgba(255,255,255,.1)")
    fig.add_vline(x=0, line_color="rgba(255,255,255,.1)")
    fig.update_layout(**_P, height=300,
        title=dict(text=f"{ticker1} vs {ticker2} — β={beta:.3f}", font=dict(color="#00d4ff", size=12), x=0.01),
        xaxis=dict(title=f"{ticker2} (%)", gridcolor="rgba(255,255,255,.04)"),
        yaxis=dict(title=f"{ticker1} (%)", gridcolor="rgba(255,255,255,.04)"),
        legend=dict(orientation="h", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True)


def _garch_tool():
    section_title("GARCH(1,1) — VOLATILITÉ CONDITIONNELLE", "🔮")
    _formula_box("σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁", "GARCH(1,1) — ω + α + β < 1 requis")

    assets_df   = load_assets()
    ticker_opts = {f'{r["ticker"]} — {r["name"]}': r["ticker"] for _, r in assets_df.iterrows()}
    sel    = st.selectbox("Actif", list(ticker_opts.keys()), key="garch_asset")
    ticker = ticker_opts[sel]

    hist = get_history(ticker, "2y")
    if hist.empty:
        st.warning("Données insuffisantes.")
        return

    close   = hist["Close"]
    returns = close.pct_change().dropna()

    col_a, col_b, col_c = st.columns(3)
    with col_a: omega = st.number_input("ω", 1e-8, 1e-3, 1e-6, format="%.2e", key="garch_w")
    with col_b: alpha = st.slider("α (ARCH)", 0.01, 0.5, 0.10, 0.01, key="garch_a")
    with col_c: beta  = st.slider("β (GARCH)", 0.01, 0.99, 0.85, 0.01, key="garch_b")

    if alpha + beta >= 1:
        st.error("⚠️ α + β doit être < 1 pour la stationnarité.")
        return

    # GARCH estimation
    n = len(returns)
    var_series = np.zeros(n)
    var_series[0] = float(returns.var())
    ret_arr = returns.values
    for t in range(1, n):
        var_series[t] = omega + alpha * ret_arr[t-1]**2 + beta * var_series[t-1]
    garch_vol = pd.Series(np.sqrt(var_series) * np.sqrt(252), index=returns.index)

    realized = returns.rolling(30).std() * np.sqrt(252) * 100

    fig = make_subplots(rows=2, cols=1, shared_xaxes=True,
                        row_heights=[0.4, 0.6], vertical_spacing=0.04,
                        subplot_titles=["Rendements journaliers", "Volatilité GARCH vs Réalisée"])
    ret_colors = ["rgba(0,255,136,.6)" if r >= 0 else "rgba(255,59,107,.6)" for r in ret_arr]
    fig.add_trace(go.Bar(x=returns.index, y=ret_arr*100, marker_color=ret_colors, showlegend=False), row=1, col=1)
    fig.add_trace(go.Scatter(x=garch_vol.index, y=garch_vol*100, name="GARCH Vol",
        line=dict(color="#ff8c00", width=2)), row=2, col=1)
    fig.add_trace(go.Scatter(x=realized.index, y=realized, name="Vol réalisée 30j",
        line=dict(color="#00d4ff", width=1.5, dash="dot")), row=2, col=1)
    fig.update_layout(**_P, height=420,
        legend=dict(orientation="h", y=1.02, font=dict(size=10)),
        yaxis=dict(title="Rendement (%)", gridcolor="rgba(255,255,255,.04)"),
        yaxis2=dict(title="Vol ann. (%)", gridcolor="rgba(255,255,255,.04)"))
    fig.update_annotations(font=dict(color="#7a93b0", size=11, family="Rajdhani"))
    st.plotly_chart(fig, use_container_width=True)

    metric_row([
        {"label": "Vol GARCH actuelle",  "value": f"{float(garch_vol.iloc[-1])*100:.2f}%", "color": ""},
        {"label": "Vol réalisée 30j",    "value": f"{float(realized.dropna().iloc[-1]):.2f}%" if not realized.dropna().empty else "—", "color": ""},
        {"label": "α + β (persistance)", "value": f"{alpha+beta:.3f}",
         "color": "positive" if alpha+beta < 0.95 else "negative"},
        {"label": "Vol long terme",      "value": f"{np.sqrt(omega/(1-alpha-beta))*np.sqrt(252)*100:.2f}%", "color": ""},
    ])


# ═════════════════════════════════════════════════════════════════════════════
# TAB 7 — FAIR VALUE CALCULATOR
# ═════════════════════════════════════════════════════════════════════════════

def _fair_value_tab():
    section_title("CALCULATEUR DE JUSTE VALEUR", "💡")

    _info_box(
        "💡 Trois méthodes d'évaluation fondamentale :<br>"
        "<b style='color:#00d4ff;'>DCF</b> — Discounted Cash Flow (actualisation des flux futurs)<br>"
        "<b style='color:#00d4ff;'>Gordon Growth</b> — Modèle de croissance des dividendes<br>"
        "<b style='color:#00d4ff;'>Multiples</b> — Comparaison par ratios (P/E, P/B, P/S)"
    )

    method = st.radio("Méthode", ["DCF", "Gordon Growth", "Multiples de marché"],
                       horizontal=True, key="fv_method")

    assets_df = load_assets()
    # FIXED: use "category" not "type"
    eq_assets = assets_df[assets_df["category"].isin(["Equities", "ETF"])]
    ticker_opts = {f'{r["ticker"]} — {r["name"]}': r["ticker"] for _, r in eq_assets.iterrows()}
    sel    = st.selectbox("Actif à évaluer", list(ticker_opts.keys()), key="fv_asset")
    ticker = ticker_opts[sel]
    price  = get_price(ticker)

    st.markdown(
        f'<div style="font-family:Share Tech Mono;font-size:.78rem;color:#7a93b0;'
        f'margin-bottom:12px;">Prix marché actuel : <b style="color:#00d4ff;">${price:,.4f}</b></div>',
        unsafe_allow_html=True)

    if method == "DCF":
        _dcf_calculator(ticker, price)
    elif method == "Gordon Growth":
        _gordon_growth_calculator(price)
    else:
        _multiples_calculator(price)


def _dcf_calculator(ticker: str, market_price: float):
    section_title("DCF — ACTUALISATION DES FLUX DE TRÉSORERIE", "🧮")
    _formula_box("Valeur = Σ FCFₜ/(1+WACC)ᵗ + TV/(1+WACC)ᴺ", "TV = FCF_N × (1+g) / (WACC − g)")

    col1, col2 = st.columns(2)
    with col1:
        fcf_base    = st.number_input("FCF de base (M$)", 100.0, 1_000_000.0, 5_000.0, 100.0, key="dcf_fcf")
        growth_1_5  = st.slider("Croissance an 1–5 (%)", -20.0, 50.0, 10.0, 0.5, key="dcf_g1") / 100
        growth_6_10 = st.slider("Croissance an 6–10 (%)", -10.0, 30.0, 6.0, 0.5, key="dcf_g2") / 100
        terminal_g  = st.slider("Taux terminal (%)", 0.0, 5.0, 2.5, 0.1, key="dcf_gt") / 100
    with col2:
        wacc        = st.slider("WACC (%)", 5.0, 20.0, 9.5, 0.25, key="dcf_wacc") / 100
        shares      = st.number_input("Actions (M)", 1.0, 100_000.0, 10_000.0, 100.0, key="dcf_sh")
        net_debt    = st.number_input("Dette nette (M$)", -100_000.0, 100_000.0, 5_000.0, 100.0, key="dcf_debt")

    fcf_proj = []
    cf = fcf_base
    for yr in range(1, 11):
        cf *= (1 + (growth_1_5 if yr <= 5 else growth_6_10))
        fcf_proj.append(cf)

    pv_fcfs      = [c / (1 + wacc)**yr for yr, c in enumerate(fcf_proj, 1)]
    terminal_val = fcf_proj[-1] * (1 + terminal_g) / (wacc - terminal_g) if wacc > terminal_g else 0
    pv_terminal  = terminal_val / (1 + wacc)**10

    enterprise_val       = sum(pv_fcfs) + pv_terminal
    equity_val           = enterprise_val - net_debt
    fair_value_per_share = equity_val / shares if shares else 0
    updown = (fair_value_per_share - market_price) / market_price * 100 if market_price else 0
    fv_col = "#00ff88" if updown > 0 else "#ff3b6b"
    fv_lbl = "SOUS-ÉVALUÉ" if updown > 10 else ("SUR-ÉVALUÉ" if updown < -10 else "JUSTE VALEUR")

    col_a, col_b, col_c = st.columns(3)
    for col_x, label, val in [
        (col_a, "Valeur entreprise", enterprise_val),
        (col_b, "Valeur equity",     equity_val),
        (col_c, "Valeur terminale",  pv_terminal),
    ]:
        with col_x:
            st.markdown(
                f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.06);'
                f'border-radius:8px;padding:14px;text-align:center;">'
                f'<div style="font-family:Rajdhani;font-size:.65rem;color:#7a93b0;">{label}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:1.1rem;color:#e2e8f0;">'
                f'${val:,.0f}M</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown(
        f'<div style="background:rgba({("0,255,136" if updown>0 else "255,59,107")},.08);'
        f'border:1px solid rgba({("0,255,136" if updown>0 else "255,59,107")},.3);'
        f'border-radius:10px;padding:20px;text-align:center;max-width:350px;margin:0 auto;">'
        f'<div style="font-family:Rajdhani;font-size:.7rem;color:#7a93b0;letter-spacing:.1em;">'
        f'JUSTE VALEUR PAR ACTION</div>'
        f'<div style="font-family:Share Tech Mono;font-size:2.5rem;color:{fv_col};font-weight:bold;">'
        f'${fair_value_per_share:,.2f}</div>'
        f'<div style="font-family:Rajdhani;font-size:.8rem;font-weight:700;color:{fv_col};'
        f'letter-spacing:.1em;">{fv_lbl}</div>'
        f'<div style="font-family:Share Tech Mono;font-size:.72rem;color:{fv_col};margin-top:4px;">'
        f'{"+" if updown>0 else ""}{updown:.1f}% vs ${market_price:,.2f}</div>'
        f'</div>', unsafe_allow_html=True)

    # FCF chart
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("PROJECTION FCF 10 ANS", "📊")
    fig = go.Figure()
    fig.add_trace(go.Bar(x=list(range(1,11)), y=fcf_proj, name="FCF (M$)",
        marker_color="rgba(0,212,255,.6)",
        text=[f"${v:,.0f}M" for v in fcf_proj], textposition="outside",
        hovertemplate="An %{x}<br>FCF: $%{y:,.0f}M<extra></extra>"))
    fig.add_trace(go.Scatter(x=list(range(1,11)), y=pv_fcfs, name="PV FCF",
        line=dict(color="#ffd700", width=2, dash="dot")))
    fig.update_layout(**_P, height=240,
        xaxis=dict(title="Année", showgrid=False),
        yaxis=dict(title="M$", gridcolor="rgba(255,255,255,.04)"),
        legend=dict(orientation="h", y=1.02, font=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True)


def _gordon_growth_calculator(market_price: float):
    section_title("GORDON GROWTH MODEL", "🌱")
    _formula_box("P = D₁ / (Ke − g) = D₀ × (1+g) / (Ke − g)", "Prix = Dividende futur / (Taux requis − Croissance)")

    col1, col2 = st.columns(2)
    with col1:
        d0 = st.number_input("Dividende actuel (D₀) $", 0.01, 1000.0, 2.50, 0.01, key="gg_d0")
        g  = st.slider("Croissance perpétuelle (%)", 0.0, 15.0, 3.5, 0.1, key="gg_g") / 100
    with col2:
        ke = st.slider("Taux requis Ke (%)", 5.0, 25.0, 9.0, 0.25, key="gg_ke") / 100

    if ke <= g:
        st.error("⚠️ Ke doit être supérieur à g.")
        return

    d1 = d0 * (1 + g)
    fv = d1 / (ke - g)
    updown = (fv - market_price) / market_price * 100 if market_price else 0

    metric_row([
        {"label": "D₁ (prochain dividende)", "value": f"${d1:.4f}", "color": ""},
        {"label": "Juste valeur (Gordon)",    "value": f"${fv:.2f}",
         "color": "positive" if updown >= 0 else "negative"},
        {"label": "vs Prix marché",           "value": f'{updown:+.2f}%',
         "color": "positive" if updown >= 0 else "negative"},
        {"label": "Verdict",                  "value": "SOUS-ÉVALUÉ" if updown > 10 else "SUR-ÉVALUÉ" if updown < -10 else "JUSTE VALEUR", "color": ""},
    ])

    # Sensitivity
    section_title("SENSIBILITÉ g vs Ke", "📊")
    g_range  = [max(g-0.01, 0), g, g+0.01, g+0.02]
    ke_range = [ke-0.02, ke-0.01, ke, ke+0.01, ke+0.02]
    rows = []
    for g_ in g_range:
        row = {"g": f"{g_*100:.1f}%"}
        for ke_ in ke_range:
            if ke_ > g_ and ke_ > 0:
                row[f"Ke={ke_*100:.1f}%"] = f"${d1/(ke_-g_):.2f}"
            else:
                row[f"Ke={ke_*100:.1f}%"] = "N/A"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def _multiples_calculator(market_price: float):
    section_title("ÉVALUATION PAR MULTIPLES", "📊")

    col1, col2 = st.columns(2)
    with col1:
        eps   = st.number_input("EPS ($)", -100.0, 1000.0, 5.0, 0.1, key="mult_eps")
        bvps  = st.number_input("BVPS ($)", 0.0, 10000.0, 30.0, 1.0, key="mult_bvps")
        sales = st.number_input("Revenue/action ($)", 0.0, 10000.0, 25.0, 0.5, key="mult_sales")
    with col2:
        pe = st.number_input("P/E sectoriel", 5.0, 100.0, 22.0, 0.5, key="mult_pe")
        pb = st.number_input("P/B sectoriel", 0.5, 20.0, 3.5, 0.1, key="mult_pb")
        ps = st.number_input("P/S sectoriel", 0.5, 30.0, 4.0, 0.1, key="mult_ps")

    estimates = []
    if eps > 0:
        estimates.append(("P/E", eps * pe, "#00d4ff"))
    estimates.append(("P/B", bvps * pb, "#a78bfa"))
    estimates.append(("P/S", sales * ps, "#ffd700"))

    avg_fv = np.mean([e[1] for e in estimates])
    updown = (avg_fv - market_price) / market_price * 100 if market_price else 0

    cols_out = st.columns(len(estimates) + 1)
    for i, (label, val, color) in enumerate(estimates):
        ud = (val - market_price) / market_price * 100 if market_price else 0
        with cols_out[i]:
            st.markdown(
                f'<div style="background:rgba(0,0,0,.2);border:1px solid rgba(255,255,255,.06);'
                f'border-radius:8px;padding:12px;text-align:center;">'
                f'<div style="font-family:Rajdhani;font-size:.65rem;color:#7a93b0;">{label}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:1.2rem;color:{color};">${val:.2f}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:.7rem;'
                f'color:{"#00ff88" if ud>=0 else "#ff3b6b"};">{ud:+.1f}%</div>'
                f'</div>', unsafe_allow_html=True)
    with cols_out[-1]:
        fv_col = "#00ff88" if updown >= 0 else "#ff3b6b"
        st.markdown(
            f'<div style="background:rgba(255,215,0,.06);border:1px solid rgba(255,215,0,.3);'
            f'border-radius:8px;padding:12px;text-align:center;">'
            f'<div style="font-family:Rajdhani;font-size:.65rem;color:#7a93b0;">MOYENNE</div>'
            f'<div style="font-family:Share Tech Mono;font-size:1.2rem;color:#ffd700;">${avg_fv:.2f}</div>'
            f'<div style="font-family:Share Tech Mono;font-size:.7rem;color:{fv_col};">{updown:+.1f}%</div>'
            f'</div>', unsafe_allow_html=True)


# ═════════════════════════════════════════════════════════════════════════════
# TAB 8 — STRATÉGIES OPTIONS (appelé depuis l'onglet Dérivés aussi)
# ═════════════════════════════════════════════════════════════════════════════

def _options_strategies_tab():
    section_title("STRATÉGIES OPTIONS — PAYOFF INTERACTIF", "🎯")

    strategy_list = list(STRATEGY_META.keys())
    assets_df     = load_assets()
    # FIXED: use "category" not "type"
    eq_assets     = assets_df[assets_df["category"].isin(["Equities", "ETF", "Crypto"])]
    ticker_opts   = {f'{r["ticker"]} — {r["name"]}': r["ticker"] for _, r in eq_assets.iterrows()}

    col1, col2 = st.columns([1, 1])
    with col1:
        strat_sel = st.selectbox("Stratégie", strategy_list, key="edu_strat")
        meta      = STRATEGY_META.get(strat_sel, {})
        st.markdown(
            f'<div style="background:rgba(0,0,0,.2);border-left:3px solid {meta.get("color","#00d4ff")};'
            f'padding:10px 14px;margin:8px 0;font-family:Share Tech Mono;font-size:.73rem;color:#94a3b8;">'
            f'<b style="color:{meta.get("color","#00d4ff")};">{meta.get("cat","")}</b><br>{meta.get("use","")}'
            f'</div>', unsafe_allow_html=True)

        sel    = st.selectbox("Sous-jacent", list(ticker_opts.keys()), key="edu_underlying")
        ticker = ticker_opts[sel]
        spot   = get_price(ticker)
        st.markdown(f'<div style="font-family:Share Tech Mono;font-size:.75rem;color:#7a93b0;">'
                    f'Spot: <b style="color:#00d4ff;">${spot:,.4f}</b></div>', unsafe_allow_html=True)

        K   = st.number_input("Strike ($)", 0.01, 1e7, round(spot, 2), key="edu_K")
        T   = st.slider("Maturité (jours)", 7, 365, 45, key="edu_T") / 365.0
        r   = st.slider("Taux sans risque (%)", 0.0, 10.0, 4.25, 0.1, key="edu_r") / 100
        sig = st.slider("Volatilité (%)", 5.0, 150.0, 25.0, 0.5, key="edu_sig") / 100

    with col2:
        section_title("PAYOFF À L'EXPIRATION", "📉")
        legs   = build_strategy_legs(strat_sel, spot, K, T, r, sig)
        spots2 = np.linspace(max(spot * 0.6, 0.01), spot * 1.4, 400)
        pnl2   = payoff_at_expiry(legs, spots2)
        color  = meta.get("color", "#00d4ff")

        pnl2_pos = np.where(pnl2 >= 0, pnl2, np.nan)
        pnl2_neg = np.where(pnl2 < 0,  pnl2, np.nan)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=spots2, y=pnl2_pos,
            mode="lines", line=dict(width=0, color="rgba(0,255,136,0)"),
            fill="tozeroy", fillcolor="rgba(0,255,136,.07)", showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=spots2, y=pnl2_neg,
            mode="lines", line=dict(width=0, color="rgba(255,59,107,0)"),
            fill="tozeroy", fillcolor="rgba(255,59,107,.07)", showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=spots2, y=pnl2, name="P&L",
            mode="lines", line=dict(color=color, width=2.5),
            hovertemplate="Spot: $%{x:,.2f}<br>P&L: $%{y:,.2f}<extra></extra>"))
        fig.add_hline(y=0, line_color="rgba(255,255,255,.3)")
        fig.add_vline(x=spot, line_color="#ffd700", line_dash="dash",
                      annotation_text=f"Spot ${spot:,.2f}", annotation_font_color="#ffd700")
        fig.add_vline(x=K, line_color="#ff3b6b", line_dash="dot",
                      annotation_text=f"Strike ${K:,.2f}", annotation_font_color="#ff3b6b")
        fig.update_layout(**_P, height=300,
            xaxis=dict(title="Prix spot ($)", gridcolor="rgba(255,255,255,.04)"),
            yaxis=dict(title="P&L ($)", gridcolor="rgba(255,255,255,.04)"))
        st.plotly_chart(fig, use_container_width=True)

    # All strategies overview
    st.markdown("<br>", unsafe_allow_html=True)
    section_title("TOUTES LES STRATÉGIES OPTIONS", "📚")

    for strat, meta_ in STRATEGY_META.items():
        color_ = meta_.get("color", "#00d4ff")
        with st.expander(f'{strat}  —  {meta_.get("cat","")}'):
            st.markdown(
                f'<div style="font-family:Share Tech Mono;font-size:.73rem;color:#94a3b8;'
                f'border-left:3px solid {color_};padding:8px 14px;line-height:1.8;">'
                f'<b style="color:{color_};">Catégorie :</b> {meta_.get("cat","")}<br>'
                f'<b style="color:{color_};">Usage :</b> {meta_.get("use","")}'
                f'</div>', unsafe_allow_html=True)
            try:
                legs_p = build_strategy_legs(strat, 100.0, 100.0, 30/365, 0.0425, 0.25)
                sp_p   = np.linspace(70, 130, 200)
                pnl_p  = payoff_at_expiry(legs_p, sp_p)
                fig_m  = go.Figure(go.Scatter(x=sp_p, y=pnl_p, mode="lines",
                    line=dict(color=color_, width=2),
                    hovertemplate="Spot: $%{x:.1f}<br>P&L: $%{y:.2f}<extra></extra>"))
                fig_m.add_hline(y=0, line_color="rgba(255,255,255,.2)")
                fig_m.update_layout(**_P, height=140, showlegend=False,
                    margin=dict(l=4, r=4, t=4, b=4),
                    xaxis=dict(showgrid=False, showticklabels=False),
                    yaxis=dict(showgrid=False, showticklabels=False))
                st.plotly_chart(fig_m, use_container_width=True)
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════════
# TAB 9 — GLOSSAIRE
# ═════════════════════════════════════════════════════════════════════════════

def _glossary_tab():
    section_title("GLOSSAIRE FINANCIER COMPLET", "📚")

    terms = [
        ("Alpha (α)", "Rendement excédentaire d'un portefeuille par rapport à son benchmark après ajustement du risque. α > 0 = surperformance."),
        ("ATR (Average True Range)", "Volatilité moyenne des mouvements de prix sur N périodes. Utile pour dimensionner les stops-loss."),
        ("Autocall", "Produit structuré remboursé automatiquement si le sous-jacent dépasse une barrière à une date d'observation."),
        ("Beta (β)", "Sensibilité d'un actif aux mouvements du marché. β=1 suit le marché, β>1 amplifie, β<1 amortit."),
        ("Black-Scholes", "Modèle de pricing d'options européennes (1973) : C = S·N(d₁) − K·e⁻ʳᵀ·N(d₂). Hypothèses : vol constante, log-normalité."),
        ("Bollinger Bands", "Bandes de ±2σ autour d'une MM20. Squeeze (rétrécissement) précède souvent un fort mouvement directionnel."),
        ("Calmar Ratio", "Rendement annualisé divisé par le Max Drawdown absolu. Mesure l'efficacité par rapport à la pire perte."),
        ("Capital Market Line", "Droite dans l'espace risque/rendement passant par le taux sans risque et le portefeuille tangent (Max Sharpe)."),
        ("Carry Trade", "Emprunter dans une devise à taux bas (ex: JPY) pour investir dans une devise à taux élevé."),
        ("CDS (Credit Default Swap)", "Contrat dérivé assurant contre le défaut d'un émetteur. L'acheteur paie une prime périodique."),
        ("Covered Call", "Vendre un call sur une position longue déjà détenue. Génère du revenu mais plafonne le gain à la hausse."),
        ("CVaR / Expected Shortfall", "Perte moyenne conditionnelle au-delà de la VaR. Plus conservatrice car intègre l'épaisseur des queues."),
        ("DCF", "Discounted Cash Flow : valeur d'une entreprise = somme des flux de trésorerie futurs actualisés au WACC."),
        ("Delta (Δ)", "Sensibilité du prix de l'option au prix du sous-jacent. Call ∈ [0,1], Put ∈ [-1,0]."),
        ("DCA (Dollar Cost Averaging)", "Investissement régulier d'une somme fixe indépendamment des conditions de marché. Lisse le prix d'entrée."),
        ("Drawdown", "Baisse de valeur depuis un pic jusqu'au creux suivant. Max Drawdown = pire baisse historique."),
        ("Duration", "Sensibilité du prix d'une obligation aux variations de taux. Duration modifiée = variation % du prix pour +1% de taux."),
        ("EBITDA", "Bénéfices avant intérêts, impôts, dépréciation et amortissement. Proxy du cash-flow opérationnel."),
        ("EPS (Earnings Per Share)", "Bénéfice net / Nombre d'actions. Indicateur central de la profitabilité par action."),
        ("ETF", "Exchange-Traded Fund : fonds indiciel coté en bourse, à frais très faibles. Diversification instantanée."),
        ("EV/EBITDA", "Valeur d'entreprise / EBITDA. Multiple de valorisation neutre sur la structure de capital."),
        ("FCF (Free Cash Flow)", "Cash généré par l'exploitation après investissements. Mesure la vraie capacité à créer de la valeur."),
        ("Frontière Efficiente", "Ensemble de portefeuilles offrant le rendement maximum pour chaque niveau de risque (Markowitz 1952)."),
        ("Future", "Contrat standardisé d'achat/vente à terme d'un actif à un prix convenu aujourd'hui. Marked-to-market quotidien."),
        ("GARCH(1,1)", "σ²ₜ = ω + α·ε²ₜ₋₁ + β·σ²ₜ₋₁. Modèle de volatilité conditionnelle capturant le clustering de vol."),
        ("Gamma (Γ)", "Taux de variation du Delta. Élevé ATM et proche de l'expiration. Représente la convexité de l'option."),
        ("Gordon Growth Model", "Valeur action = D₁ / (Ke − g). Valide pour les entreprises matures à dividendes stables."),
        ("Implied Volatility (IV)", "Volatilité incorporée dans le prix de marché d'une option. Reflète les anticipations futures du marché."),
        ("Information Ratio", "(Rp − Rbenchmark) / Tracking Error. Mesure la régularité de la surperformance relative."),
        ("Iron Condor", "Stratégie options 4 jambes : vendre un call spread + vendre un put spread. Profit si le sous-jacent reste dans un range."),
        ("IRS (Interest Rate Swap)", "Échange de flux entre taux fixe et taux variable (SOFR, EURIBOR). Instrument de gestion du risque de taux."),
        ("MACD", "EMA12 − EMA26 avec signal = EMA9(MACD). Indicateur de momentum/tendance. Croisement = signal."),
        ("Markowitz", "Théorie Moderne du Portefeuille (1952) : minimiser le risque pour un rendement donné via la diversification."),
        ("Max Drawdown (MDD)", "Perte maximale pic-à-creux sur la période. Indicateur du pire scénario historique vécu."),
        ("Momentum", "Facteur d'investissement : les actifs qui ont bien performé (3-12 mois) continuent de surperformer à court terme."),
        ("Monte Carlo", "Simulation de milliers de trajectoires possibles pour modéliser l'incertitude et calculer des probabilités."),
        ("MWR (Money-Weighted Return)", "Taux de rendement interne tenant compte du timing et de la taille des flux. Perf. réelle de l'investisseur."),
        ("P/E Ratio", "Price-to-Earnings : cours / BPA. Mesure la cherté relative. Contexte sectoriel indispensable."),
        ("PEG Ratio", "P/E / Taux de croissance du BPA. PEG < 1 souvent considéré comme attractif."),
        ("Pip", "Plus petite unité de variation d'une paire forex. Pour EUR/USD : 0.0001."),
        ("Put", "Option donnant le droit de vendre un actif au strike K. Profite d'une baisse du sous-jacent."),
        ("REITs", "Real Estate Investment Trusts : sociétés immobilières cotées distribuant ≥90% de leurs revenus."),
        ("Rho (ρ)", "Sensibilité de l'option aux taux d'intérêt. Importance croissante sur les longues maturités."),
        ("Risk Parity", "Allouer le capital pour égaliser la contribution au risque de chaque actif. Ex: portefeuille All Weather."),
        ("RSI", "Oscillateur de momentum [0-100]. >70 = surachat (signal de vente possible). <30 = survente (signal d'achat possible)."),
        ("Sharpe Ratio", "(Rp − Rf) / σp. Rendement ajusté du risque total. >1 = bon. >2 = excellent. <0 = sous-performance."),
        ("Short Selling", "Vendre un actif qu'on ne possède pas (emprunté) en espérant le racheter moins cher. Risque théoriquement illimité."),
        ("Sortino Ratio", "(Rp − Rf) / σ_downside. Variante du Sharpe pénalisant uniquement la volatilité négative."),
        ("Spread", "1) Écart entre bid et ask (coût de transaction). 2) Différence de rendement entre deux obligations."),
        ("Stop-Loss", "Ordre automatique de vente déclenché si le prix atteint un niveau préfixé. Gestion essentielle du risque."),
        ("Straddle", "Achat d'un call + put même strike, même maturité. Profite d'un fort mouvement dans n'importe quel sens."),
        ("Strangle", "Achat d'un call OTM + put OTM. Moins cher qu'un straddle mais nécessite un mouvement plus important."),
        ("Swap", "Échange de flux financiers entre deux contreparties (taux, devises, rendement total, crédit)."),
        ("Theta (Θ)", "Décroissance temporelle de la prime. Les acheteurs d'options perdent de la valeur chaque jour (négatif)."),
        ("Tracking Error", "Écart-type de la différence de rendements entre un portefeuille et son benchmark. Mesure la fidélité."),
        ("TWR (Time-Weighted Return)", "Rendement géométrique chaîné, indépendant des flux. Standard CFA pour évaluer les gérants."),
        ("VaR (Value at Risk)", "Perte maximale avec un niveau de confiance α sur un horizon donné. VaR 95% 1j = 2% signifie max -2% dans 95% des cas."),
        ("VWAP", "Volume Weighted Average Price. Prix moyen pondéré par le volume. Référence institutionnelle pour l'exécution."),
        ("Vega (ν)", "Sensibilité de l'option à la volatilité implicite. Long option = long vega (bénéficie d'une hausse de vol)."),
        ("Volatilité", "Mesure de la dispersion des rendements (σ). Annualisée = σ_journalière × √252. L'indicateur de risque le plus utilisé."),
        ("WACC", "Weighted Average Cost of Capital : coût moyen pondéré des sources de financement. Taux d'actualisation du DCF."),
        ("YTM (Yield to Maturity)", "Rendement actuariel d'une obligation si détenue jusqu'à l'échéance. Taux interne de rentabilité."),
    ]

    search_gl = st.text_input("🔍 Rechercher", "", key="gl_search",
                               placeholder="ex: Sharpe, Delta, VaR, Momentum…")

    filtered = [
        (k, v) for k, v in sorted(terms, key=lambda x: x[0])
        if not search_gl
        or search_gl.lower() in k.lower()
        or search_gl.lower() in v.lower()
    ]

    st.markdown(
        f'<div style="font-family:Share Tech Mono;font-size:.7rem;color:#7a93b0;margin-bottom:10px;">'
        f'{len(filtered)} termes</div>', unsafe_allow_html=True)

    for term, definition in filtered:
        with st.expander(f"📖 {term}"):
            st.markdown(
                f'<div style="font-family:Share Tech Mono;font-size:.75rem;color:#94a3b8;'
                f'line-height:1.85;padding:8px;">{definition}</div>',
                unsafe_allow_html=True)
