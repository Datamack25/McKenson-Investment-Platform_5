# utils/legal.py  —  MAM · Mentions légales, auteur, version et avertissements
"""
Source unique des mentions affichées partout (pied de page, écran de connexion,
rapports PDF / PNG, e-mails, pages IA). Modifier ici met à jour toute la plateforme.
"""
from __future__ import annotations

APP_NAME = "MAM — McKenson Asset Management"
APP_VERSION = "5.6.0"
APP_RELEASE = "octobre 2026"
AUTHOR = "Mackenson CINEUS"
AUTHOR_TITLE = "diplômé d'un MBA Finance de marché"

CREDIT = f"Plateforme créée par {AUTHOR}, {AUTHOR_TITLE} — version {APP_VERSION} ({APP_RELEASE})."

DISCLAIMER = (
    "Plateforme purement éducative : aucune opération n'est exécutée sur un marché réel et rien de ce qui y est "
    "présenté (signaux, allocations, stratégies, rapports, alertes) ne constitue un conseil en investissement, "
    "une recommandation personnalisée ou une sollicitation à acheter ou vendre un instrument financier. "
    f"{AUTHOR} n'est pas responsable des décisions prises par les utilisateurs et n'est pas engagé par les "
    "décisions ou les conseils issus de cette plateforme. Les performances passées ne préjugent pas des "
    "performances futures ; tout investissement réel comporte un risque de perte en capital."
)

# Version courte pour les en-têtes de pages, PNG et e-mails
DISCLAIMER_SHORT = (
    f"Plateforme éducative créée par {AUTHOR} ({AUTHOR_TITLE}) — v{APP_VERSION}. "
    f"Ne constitue pas un conseil en investissement ; {AUTHOR} n'est pas responsable des décisions prises."
)

RISK_WARNINGS = {
    "options": (
        "⚠️ Produits complexes — Les options peuvent faire perdre la totalité de la prime payée ; vendre une "
        "option peut entraîner des pertes supérieures à la prime encaissée. Les ventes non couvertes sont "
        "bloquées sur la plateforme. Simulation éducative uniquement."
    ),
    "crypto": (
        "⚠️ Crypto-actifs — Très forte volatilité, risque de perte totale, absence de garantie du FGDR. "
        "Simulation éducative uniquement."
    ),
    "ia": (
        "⚠️ Modèles quantitatifs — Les signaux reposent sur des données historiques et peuvent se tromper "
        "(changement de régime, sur-apprentissage). Ils ne constituent pas un conseil en investissement."
    ),
}


def text_footer_lines() -> list[str]:
    """Lignes de pied de page pour les documents (PDF / PNG / e-mails texte)."""
    return [CREDIT, DISCLAIMER]


def html_footer(color: str = "#64748b", size: str = "11px") -> str:
    """Bloc HTML d'avertissement pour les e-mails."""
    return (f'<p style="color:{color};font-size:{size};line-height:1.5;margin-top:16px">'
            f'<b>{CREDIT}</b><br>{DISCLAIMER}</p>')


def render_risk_banner(kind: str = "options"):
    """Bandeau d'avertissement Streamlit (options, crypto, ia)."""
    import streamlit as st
    msg = RISK_WARNINGS.get(kind)
    if msg:
        st.markdown(
            f'<div style="border:1px solid rgba(255,215,0,.35);background:rgba(255,215,0,.06);border-radius:6px;'
            f'padding:8px 12px;margin:6px 0 10px;font-family:Share Tech Mono;font-size:.7rem;color:#e2c26b;'
            f'line-height:1.6;">{msg}</div>', unsafe_allow_html=True)


def render_legal_notice(compact: bool = True):
    """Encadré auteur + avertissement (écran de connexion, pages IA)."""
    import streamlit as st
    text = DISCLAIMER_SHORT if compact else DISCLAIMER
    st.markdown(
        f'<div style="border:1px solid rgba(124,58,237,.25);background:rgba(124,58,237,.05);border-radius:6px;'
        f'padding:8px 12px;margin:8px 0;font-family:Share Tech Mono;font-size:.66rem;color:#94a3b8;'
        f'line-height:1.6;">🎓 {text}</div>', unsafe_allow_html=True)
