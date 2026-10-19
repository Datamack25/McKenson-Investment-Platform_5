# pages/auth.py — MAM v4.1 Authentification
"""
Page de login / inscription / récupération affichée avant tout accès à la plateforme.
Stocke l'utilisateur connecté dans st.session_state["mam_user"].

Récupération d'identifiants (onglet « 🔑 Identifiants oubliés ») :
  1. Code de récupération (affiché une seule fois à l'inscription)
  2. Code à 6 chiffres envoyé par e-mail (si la section [smtp] existe dans les Secrets)
  3. En dernier recours : l'admin génère un mot de passe temporaire (page Administration)
"""

from __future__ import annotations
import smtplib
import ssl
from email.message import EmailMessage

import streamlit as st
from utils.db import (
    init_db, create_user, login_user, is_db_available, db_last_error,
    recover_with_code, create_email_reset, reset_with_email_code, change_password,
    RESET_CODE_TTL_MIN,
)

APP_NAME = "MAM — McKenson Asset Management"
_MAX_TRIES = 5


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
    .auth-info {
        background: rgba(0,212,255,.06);
        border: 1px solid rgba(0,212,255,.25);
        border-radius: 6px;
        padding: 9px 14px;
        font-family: 'Share Tech Mono', monospace;
        font-size: .74rem;
        color: #94a3b8;
        margin: 8px 0;
        line-height: 1.6;
    }
    .auth-warn {
        background: rgba(255,215,0,.06);
        border: 1px solid rgba(255,215,0,.35);
        border-radius: 6px;
        padding: 10px 14px;
        font-family: 'Share Tech Mono', monospace;
        font-size: .74rem;
        color: #ffd700;
        margin: 10px 0 6px;
        line-height: 1.6;
    }
    .auth-hint {
        font-family: 'Share Tech Mono', monospace;
        font-size: .66rem;
        color: #475569;
        margin-top: 14px;
        line-height: 1.6;
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


def _box(kind: str, html: str):
    st.markdown(f'<div class="auth-{kind}">{html}</div>', unsafe_allow_html=True)


def _logo():
    st.markdown("""
    <div class="auth-logo">
        <div class="title">MAM</div>
        <div class="sub">McKENSON ASSET MANAGEMENT</div>
    </div>
    """, unsafe_allow_html=True)


# ── E-mail (optionnel) ─────────────────────────────────────────────────────────
def _smtp_cfg():
    """Section [smtp] des Streamlit Secrets, ou None si absente."""
    try:
        cfg = st.secrets["smtp"]
        return cfg if cfg.get("host") and cfg.get("user") and cfg.get("password") else None
    except Exception:
        return None


def _send_email(to: str, subject: str, body: str) -> None:
    cfg = _smtp_cfg()
    if not cfg:
        raise RuntimeError("SMTP non configuré")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("sender", cfg["user"])
    msg["To"] = to
    msg.set_content(body)
    port = int(cfg.get("port", 465))
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(cfg["host"], port, context=ctx, timeout=15) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], port, timeout=15) as s:
            s.starttls(context=ctx)
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)


# ── Connexion finalisée ────────────────────────────────────────────────────────
def _finalize_login(user: dict):
    st.session_state["mam_user"]    = user
    st.session_state["mam_user_id"] = user["id"]
    # Forcer le rechargement des portefeuilles depuis la base
    for _k in ("mam_state", "mam_db_loaded_for", "_mail_known"):
        st.session_state.pop(_k, None)
    st.rerun()


def _render_forced_change():
    """Après un mot de passe temporaire donné par l'admin : changement obligatoire."""
    pending = st.session_state["mam_pending_user"]
    _logo()
    _box("warn",
         f"🔐 Bonjour <b>{pending['username']}</b>, tu t'es connecté avec un mot de passe "
         "temporaire.<br>Choisis ton nouveau mot de passe pour continuer.")
    p1 = st.text_input("Nouveau mot de passe", type="password", key="fc_pass1",
                       placeholder="Min. 6 caractères")
    p2 = st.text_input("Confirmer le mot de passe", type="password", key="fc_pass2",
                       placeholder="••••••••")
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("💾 Enregistrer et continuer", key="btn_fc_save",
                     use_container_width=True, type="primary"):
            if p1 != p2:
                _box("err", "❌ Les mots de passe ne correspondent pas.")
            else:
                res = change_password(pending["id"], p1)
                if res["ok"]:
                    st.session_state.pop("mam_pending_user", None)
                    pending["must_change_password"] = False
                    _finalize_login(pending)
                else:
                    _box("err", f"❌ {res['msg']}")
    with c2:
        if st.button("↩️ Annuler", key="btn_fc_cancel", use_container_width=True):
            st.session_state.pop("mam_pending_user", None)
            st.rerun()


# ── Page principale ────────────────────────────────────────────────────────────
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

    # Initialise les tables (et ajoute les colonnes de récupération si besoin)
    init_db()

    # Changement de mot de passe obligatoire en attente
    if st.session_state.get("mam_pending_user"):
        _render_forced_change()
        return False

    _logo()

    tab_login, tab_register, tab_forgot = st.tabs(
        ["🔐 Connexion", "📝 Créer un compte", "🔑 Identifiants oubliés"]
    )

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
                _box("err", "❌ Remplissez tous les champs.")
            else:
                user = login_user(username_l, password_l)
                if user:
                    if user.get("must_change_password"):
                        st.session_state["mam_pending_user"] = user
                        st.rerun()
                    else:
                        _finalize_login(user)
                else:
                    _box("err", "❌ Identifiants incorrects.")
        st.markdown(
            '<div class="auth-hint">Identifiants oubliés ? Utilise l\'onglet '
            '<b style="color:#00d4ff;">🔑 Identifiants oubliés</b>.</div>',
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
                _box("err", "❌ Remplissez tous les champs.")
            elif password_r != password_r2:
                _box("err", "❌ Les mots de passe ne correspondent pas.")
            elif "@" not in email_r:
                _box("err", "❌ Email invalide.")
            else:
                res = create_user(username_r, email_r, password_r)
                if res["ok"]:
                    _box("ok", f"✅ {res['msg']}<br>Connectez-vous dans l'onglet Connexion.")
                    if res.get("recovery_code"):
                        st.session_state["mam_new_recovery_code"] = (
                            username_r.strip().lower(), res["recovery_code"]
                        )
                else:
                    _box("err", f"❌ {res['msg']}")

        # Code de récupération : affiché jusqu'à ce que l'utilisateur confirme l'avoir noté
        if st.session_state.get("mam_new_recovery_code"):
            uname, code = st.session_state["mam_new_recovery_code"]
            _box("warn",
                 f"🔐 <b>Code de récupération du compte « {uname} »</b><br>"
                 "Note-le maintenant (copie-le ou fais une capture d'écran) : "
                 "il ne sera plus jamais affiché.<br>"
                 "Il te permettra de retrouver ton nom d'utilisateur et de changer "
                 "ton mot de passe si tu les oublies.")
            st.code(code, language=None)
            if st.button("✅ J'ai noté mon code", key="btn_code_noted", use_container_width=True):
                st.session_state.pop("mam_new_recovery_code", None)
                st.rerun()

    # ── IDENTIFIANTS OUBLIÉS ─────────────────────────────────────────────────
    with tab_forgot:
        st.markdown("<br>", unsafe_allow_html=True)
        _render_forgot()

    return False


# ── Identifiants oubliés ───────────────────────────────────────────────────────
def _render_forgot():
    modes = ["🧩 Code de récupération", "✉️ Code par e-mail"]
    mode = st.radio("Méthode", modes, horizontal=True, key="fg_mode",
                    label_visibility="collapsed")
    if mode == modes[0]:
        _forgot_with_code()
    else:
        _forgot_with_email()
    st.markdown(
        '<div class="auth-hint">Ni code de récupération, ni accès à ton e-mail ? '
        'Contacte l\'administrateur : il peut te générer un mot de passe temporaire.</div>',
        unsafe_allow_html=True,
    )


def _forgot_with_code():
    # Résultat d'une récupération réussie : reste affiché tant que le nouveau code n'est pas noté
    result = st.session_state.get("fg_code_result")
    if result:
        _box("ok", f"✅ Mot de passe modifié.<br>Ton nom d'utilisateur est : "
                   f"<b>{result['username']}</b>")
        _box("warn", "🔐 Ton ancien code de récupération ne fonctionne plus. "
                     "Voici le nouveau — note-le, il ne sera plus affiché :")
        st.code(result["new_code"], language=None)
        if st.button("✅ J'ai noté mon nouveau code", key="btn_fg_code_noted",
                     use_container_width=True):
            st.session_state.pop("fg_code_result", None)
            st.rerun()
        return

    _box("info", "Saisis le code reçu à la création de ton compte "
                 "(format ABCD-EFGH-JKLM-NPQR).")
    code = st.text_input("Code de récupération", key="fg_code",
                         placeholder="ABCD-EFGH-JKLM-NPQR")
    p1 = st.text_input("Nouveau mot de passe", type="password", key="fg_code_p1",
                       placeholder="Min. 6 caractères")
    p2 = st.text_input("Confirmer le mot de passe", type="password", key="fg_code_p2",
                       placeholder="••••••••")
    if st.button("🔓 Récupérer mon accès", key="btn_fg_code",
                 use_container_width=True, type="primary"):
        if st.session_state.get("fg_code_tries", 0) >= _MAX_TRIES:
            _box("err", "❌ Trop de tentatives. Recharge la page et réessaie plus tard.")
        elif not code or not p1 or not p2:
            _box("err", "❌ Remplissez tous les champs.")
        elif p1 != p2:
            _box("err", "❌ Les mots de passe ne correspondent pas.")
        else:
            res = recover_with_code(code, p1)
            if res["ok"]:
                st.session_state["fg_code_tries"] = 0
                st.session_state["fg_code_result"] = res
                st.rerun()
            else:
                if res.get("bad_code"):
                    st.session_state["fg_code_tries"] = st.session_state.get("fg_code_tries", 0) + 1
                _box("err", f"❌ {res['msg']}")


def _forgot_with_email():
    if not _smtp_cfg():
        _box("info", "✉️ L'envoi d'e-mails n'est pas encore activé sur la plateforme.<br>"
                     "Utilise ton code de récupération, ou contacte l'administrateur.")
        return

    step = st.session_state.get("fg_email_step", 1)

    if step == 1:
        _box("info", "Saisis l'adresse e-mail de ton compte : tu recevras ton nom "
                     f"d'utilisateur et un code à 6 chiffres valable {RESET_CODE_TTL_MIN} min.")
        email = st.text_input("Adresse e-mail", key="fg_email", placeholder="jean.dupont@eslsca.fr")
        if st.button("📨 Envoyer le code", key="btn_fg_send", use_container_width=True, type="primary"):
            if "@" not in (email or ""):
                _box("err", "❌ Email invalide.")
                return
            info = create_email_reset(email)
            if info:
                body = (
                    "Bonjour,\n\n"
                    f"Une demande de récupération d'accès a été faite sur {APP_NAME}.\n\n"
                    f"Nom d'utilisateur : {info['username']}\n"
                    f"Code de réinitialisation : {info['otp']}\n\n"
                    f"Ce code est valable {RESET_CODE_TTL_MIN} minutes.\n"
                    "Si tu n'es pas à l'origine de cette demande, ignore simplement cet e-mail : "
                    "ton mot de passe actuel reste valable.\n"
                )
                try:
                    _send_email(info["email"], f"{APP_NAME} — Récupération de ton accès", body)
                except Exception:
                    _box("err", "❌ L'envoi de l'e-mail a échoué. Réessaie plus tard "
                                "ou contacte l'administrateur.")
                    return
            # Même message que l'adresse existe ou non (on ne révèle pas les comptes)
            st.session_state["fg_email_addr"] = email.strip().lower()
            st.session_state["fg_email_step"] = 2
            st.rerun()
        return

    _box("info", "Si un compte est associé à <b>"
                 f"{st.session_state.get('fg_email_addr', '')}</b>, un e-mail contenant ton nom "
                 "d'utilisateur et un code à 6 chiffres vient d'être envoyé. "
                 "Pense à vérifier tes spams.")
    otp = st.text_input("Code reçu par e-mail", key="fg_otp", max_chars=6, placeholder="123456")
    p1 = st.text_input("Nouveau mot de passe", type="password", key="fg_mail_p1",
                       placeholder="Min. 6 caractères")
    p2 = st.text_input("Confirmer le mot de passe", type="password", key="fg_mail_p2",
                       placeholder="••••••••")
    c1, c2 = st.columns([2, 1])
    with c1:
        if st.button("🔓 Réinitialiser", key="btn_fg_reset", use_container_width=True, type="primary"):
            if not otp or not p1 or not p2:
                _box("err", "❌ Remplissez tous les champs.")
            elif p1 != p2:
                _box("err", "❌ Les mots de passe ne correspondent pas.")
            else:
                res = reset_with_email_code(st.session_state.get("fg_email_addr", ""), otp, p1)
                if res["ok"]:
                    st.session_state["fg_email_step"] = 1
                    _box("ok", f"✅ Mot de passe modifié. Ton nom d'utilisateur est : "
                               f"<b>{res['username']}</b>.<br>"
                               "Tu peux te connecter dans l'onglet Connexion.")
                else:
                    _box("err", f"❌ {res['msg']}")
    with c2:
        if st.button("↩️ Renvoyer", key="btn_fg_back", use_container_width=True):
            st.session_state["fg_email_step"] = 1
            st.rerun()
