# pages/auth.py — MAM v4.0 Authentification
"""
Page de login / inscription affichée avant tout accès à la plateforme.
Stocke l'utilisateur connecté dans st.session_state["mam_user"].
"""

from __future__ import annotations
import streamlit as st
from utils.db import init_db, create_user, login_user, is_db_available, db_last_error


def _css():
    st.markdown("""
    <style>
    .auth-card {
        max-width: 420px;
        margin: 60px auto 0;
        background: rgba(13,17,23,0.95);
        border: 1px solid rgba(0,212,255,0.25);
        border-radius: 16px;
        padding: 36px 40px;
        box-shadow: 0 0 40px rgba(0,212,255,0.1);
    }
    .auth-logo {
        text-align: center;
        margin-bottom: 28px;
    }
    .auth-logo .title {
        font-family: Rajdhani, sans-serif;
        font-size: 2.4rem;
        font-weight: 700;
        letter-spacing: .2em;
        color: #00d4ff;
        text-shadow: 0 0 30px rgba(0,212,255,.5);
    }
    .auth-logo .sub {
        font-family: 'Share Tech Mono', monospace;
        font-size: .65rem;
        color: #7c3aed;
        letter-spacing: .2em;
        margin-top: 2px;
    }
    .auth-divider {
        border: none;
        border-top: 1px solid rgba(0,212,255,.15);
        margin: 20px 0;
    }
    .auth-err {
        background: rgba(255,59,107,.1);
        border: 1px solid rgba(255,59,107,.35);
        border-radius: 6px;
        padding: 9px 14px;
        font-family: 'Share Tech Mono', monospace;
        font-size: .76rem;
        color: #ff3b6b;
        margin-top: 8px;
    }
    .auth-ok {
        background: rgba(0,255,136,.08);
        border: 1px solid rgba(0,255,136,.3);
        border-radius: 6px;
        padding: 9px 14px;
        font-family: 'Share Tech Mono', monospace;
        font-size: .76rem;
        color: #00ff88;
        margin-top: 8px;
    }
    .stTextInput > div > div > input {
        background: rgba(26,35,50,.9) !important;
        border: 1px solid rgba(0,212,255,.2) !important;
        color: #e2e8f0 !important;
        font-family: 'Share Tech Mono', monospace !important;
        border-radius: 6px !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: rgba(0,212,255,.6) !important;
        box-shadow: 0 0 0 1px rgba(0,212,255,.3) !important;
    }
    </style>
    """, unsafe_allow_html=True)


def render_auth() -> bool:
    """
    Affiche l'écran d'authentification si l'utilisateur n'est pas connecté.
    Retourne True si l'utilisateur est authentifié.
    """
    _css()

    # Déjà connecté (ou mode sans sauvegarde choisi explicitement)
    if st.session_state.get("mam_user") or st.session_state.get("mam_guest"):
        return True

    # Vérification DB
    if not is_db_available():
        st.error(
            "⚠️ Base de données Supabase inaccessible : les portefeuilles ne pourraient pas "
            "être sauvegardés de façon permanente."
        )
        st.code(db_last_error() or "Erreur inconnue", language="text")
        st.markdown(
            "Dans **Streamlit Cloud → Settings → Secrets**, collez l'URL du *Transaction pooler* "
            "Supabase (Project Settings → Database → Connection string) :\n"
            "```toml\n[supabase]\n"
            "database_url = \"postgresql://postgres.<ref>:<MOT_DE_PASSE>@aws-0-<region>.pooler.supabase.com:6543/postgres\"\n```"
        )
        if st.button("Continuer sans sauvegarde permanente", key="btn_guest"):
            st.session_state["mam_guest"] = True
            st.rerun()
        return False

    # Initialise les tables
    init_db()

    st.markdown("""
    <div class="auth-logo">
        <div class="title">MAM</div>
        <div class="sub">McKENSON ASSET MANAGEMENT</div>
    </div>
    """, unsafe_allow_html=True)

    tab_login, tab_register = st.tabs(["🔐 Connexion", "📝 Créer un compte"])

    # ── LOGIN ────────────────────────────────────────────────────────────────
    with tab_login:
        st.markdown("<br>", unsafe_allow_html=True)
        username_l = st.text_input(
            "Nom d'utilisateur", key="login_user", placeholder="ex: jean.dupont"
        )
        password_l = st.text_input(
            "Mot de passe", type="password", key="login_pass", placeholder="••••••••"
        )
        if st.button("🔑 Se connecter", key="btn_login", use_container_width=True, type="primary"):
            if not username_l or not password_l:
                st.markdown(
                    '<div class="auth-err">❌ Remplissez tous les champs.</div>',
                    unsafe_allow_html=True,
                )
            else:
                user = login_user(username_l, password_l)
                if user:
                    st.session_state["mam_user"]    = user
                    st.session_state["mam_user_id"] = user["id"]
                    # Forcer le rechargement des portefeuilles depuis la base
                    for _k in ("mam_state", "mam_db_loaded_for", "_mail_known"):
                        st.session_state.pop(_k, None)
                    st.success(f"✅ Bienvenue, {user['username']} !")
                    st.rerun()
                else:
                    st.markdown(
                        '<div class="auth-err">❌ Identifiants incorrects.</div>',
                        unsafe_allow_html=True,
                    )

    # ── REGISTER ─────────────────────────────────────────────────────────────
    with tab_register:
        st.markdown("<br>", unsafe_allow_html=True)
        username_r  = st.text_input("Nom d'utilisateur *", key="reg_user",  placeholder="ex: jean.dupont")
        email_r     = st.text_input("Email *",             key="reg_email", placeholder="jean.dupont@eslsca.fr")
        password_r  = st.text_input("Mot de passe *",      type="password", key="reg_pass",  placeholder="Min. 6 caractères")
        password_r2 = st.text_input("Confirmer le mot de passe *", type="password", key="reg_pass2", placeholder="••••••••")
        st.markdown(
            '<div style="font-family:Share Tech Mono;font-size:.65rem;'
            'color:#475569;margin:6px 0 12px;">* Champs obligatoires</div>',
            unsafe_allow_html=True,
        )
        if st.button("✅ Créer mon compte", key="btn_register", use_container_width=True, type="primary"):
            if not all([username_r, email_r, password_r, password_r2]):
                st.markdown(
                    '<div class="auth-err">❌ Remplissez tous les champs.</div>',
                    unsafe_allow_html=True,
                )
            elif password_r != password_r2:
                st.markdown(
                    '<div class="auth-err">❌ Les mots de passe ne correspondent pas.</div>',
                    unsafe_allow_html=True,
                )
            elif "@" not in email_r:
                st.markdown(
                    '<div class="auth-err">❌ Email invalide.</div>',
                    unsafe_allow_html=True,
                )
            else:
                res = create_user(username_r, email_r, password_r)
                if res["ok"]:
                    st.markdown(
                        f'<div class="auth-ok">✅ {res["msg"]}<br>'
                        f'Connectez-vous dans l\'onglet Connexion.</div>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown(
                        f'<div class="auth-err">❌ {res["msg"]}</div>',
                        unsafe_allow_html=True,
                    )

    return False
