"""
auth_recovery.py — Récupération d'identifiants pour MAM (McKenson Asset Management)

Deux moyens de récupérer son accès :
  1. Code de récupération (affiché une seule fois à la création du compte)
     -> redonne le nom d'utilisateur + permet de choisir un nouveau mot de passe.
     Fonctionne sans aucune configuration e-mail.
  2. Code par e-mail (6 chiffres, valable 15 min, 5 essais max)
     -> envoie le nom d'utilisateur + le code ; permet de réinitialiser le mot de passe.
     Activé seulement si la section [smtp] existe dans st.secrets.

Intégration : voir le bas du fichier.
"""

import hashlib
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage

import bcrypt
import streamlit as st

# ─────────────────────────── Paramètres ───────────────────────────
USERS_TABLE = "users"          # nom de ta table d'utilisateurs Supabase
COL_ID = "id"
COL_USERNAME = "username"
COL_EMAIL = "email"
COL_PASSWORD = "password_hash"  # colonne qui contient le hash du mot de passe
CODE_TTL_MIN = 15
MAX_ATTEMPTS = 5
MIN_PASSWORD_LEN = 8
APP_NAME = "MAM — McKenson Asset Management"


# ─────────────────────── Hachage des mots de passe ───────────────────────
# ⚠️ IMPORTANT : doit être EXACTEMENT la même fonction que celle utilisée
# par ta page de connexion actuelle. Si tu utilises autre chose que bcrypt
# (ex. hashlib.sha256), remplace le contenu de hash_password par ta fonction.
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


# ───────────────────────── Outils internes ─────────────────────────
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O/1/I pour éviter les confusions


def _digest(value: str) -> str:
    """Empreinte SHA-256 d'un code (normalisé). Le code clair n'est jamais stocké."""
    normalized = value.strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def generate_recovery_code() -> str:
    """Code du type ABCD-EFGH-JKLM-NPQR (≈ 80 bits d'entropie)."""
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def _validate_new_password(pw: str, confirm: str) -> str | None:
    if len(pw) < MIN_PASSWORD_LEN:
        return f"Le mot de passe doit contenir au moins {MIN_PASSWORD_LEN} caractères."
    if pw != confirm:
        return "Les deux mots de passe ne correspondent pas."
    return None


def _smtp_enabled() -> bool:
    try:
        return "smtp" in st.secrets
    except Exception:
        return False


def _send_email(to: str, subject: str, body: str) -> None:
    cfg = st.secrets["smtp"]
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg.get("sender", cfg["user"])
    msg["To"] = to
    msg.set_content(body)
    port = int(cfg.get("port", 465))
    if port == 465:
        with smtplib.SMTP_SSL(cfg["host"], port, context=ssl.create_default_context()) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], port) as s:
            s.starttls(context=ssl.create_default_context())
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)


def _too_many_tries(key: str) -> bool:
    """Limite anti-force brute côté session."""
    n = st.session_state.get(key, 0)
    if n >= MAX_ATTEMPTS:
        st.error("Trop de tentatives. Recharge la page et réessaie plus tard.")
        return True
    return False


# ─────────────────────── API publique ───────────────────────
def create_recovery_code(supabase, user_id) -> str:
    """Génère et enregistre un nouveau code de récupération. Retourne le code clair."""
    code = generate_recovery_code()
    supabase.table(USERS_TABLE).update({"recovery_hash": _digest(code)}).eq(COL_ID, user_id).execute()
    return code


def show_recovery_code(code: str) -> None:
    """À afficher juste après la création du compte (ou une régénération)."""
    st.warning(
        "🔐 **Ton code de récupération** — note-le maintenant, il ne sera plus jamais affiché. "
        "Il te permettra de retrouver ton nom d'utilisateur et de changer ton mot de passe."
    )
    st.code(code, language=None)


def render_forgot_tab(supabase) -> None:
    """Contenu de l'onglet « Identifiants oubliés »."""
    st.caption("Retrouve ton nom d'utilisateur et choisis un nouveau mot de passe.")

    methods = ["🧩 J'ai mon code de récupération"]
    if _smtp_enabled():
        methods.append("✉️ Recevoir un code par e-mail")
    method = st.radio("Méthode", methods, horizontal=True, label_visibility="collapsed")

    if method.startswith("🧩"):
        _render_recovery_code_flow(supabase)
    else:
        _render_email_flow(supabase)


def render_recovery_settings(supabase, user_id) -> None:
    """Pour la page « Mon compte » d'un utilisateur connecté : régénérer son code."""
    with st.expander("🔐 Code de récupération"):
        st.write("Génère un nouveau code (l'ancien ne fonctionnera plus).")
        if st.button("Générer un nouveau code", key="regen_recovery"):
            show_recovery_code(create_recovery_code(supabase, user_id))


# ─────────────────────── Méthode 1 : code de récupération ───────────────────────
def _render_recovery_code_flow(supabase) -> None:
    with st.form("form_recovery_code", clear_on_submit=False):
        code = st.text_input("Code de récupération", placeholder="ABCD-EFGH-JKLM-NPQR")
        new_pw = st.text_input("Nouveau mot de passe", type="password")
        confirm = st.text_input("Confirmer le mot de passe", type="password")
        submitted = st.form_submit_button("🔓 Récupérer mon accès", use_container_width=True)

    if not submitted or _too_many_tries("rec_tries"):
        return

    err = _validate_new_password(new_pw, confirm)
    if err:
        st.error(err)
        return

    res = (supabase.table(USERS_TABLE)
           .select(f"{COL_ID},{COL_USERNAME}")
           .eq("recovery_hash", _digest(code))
           .limit(1).execute())
    if not res.data:
        st.session_state["rec_tries"] = st.session_state.get("rec_tries", 0) + 1
        st.error("Code de récupération invalide.")
        return

    user = res.data[0]
    new_code = generate_recovery_code()  # le code utilisé est consommé et remplacé
    supabase.table(USERS_TABLE).update({
        COL_PASSWORD: hash_password(new_pw),
        "recovery_hash": _digest(new_code),
    }).eq(COL_ID, user[COL_ID]).execute()

    st.session_state["rec_tries"] = 0
    st.success(f"✅ Mot de passe modifié. Ton nom d'utilisateur est : **{user[COL_USERNAME]}**")
    st.info("Ton ancien code de récupération a été remplacé par celui-ci :")
    show_recovery_code(new_code)


# ─────────────────────── Méthode 2 : code par e-mail ───────────────────────
def _render_email_flow(supabase) -> None:
    step = st.session_state.get("reset_step", 1)

    if step == 1:
        with st.form("form_email_request"):
            email = st.text_input("Adresse e-mail du compte")
            send = st.form_submit_button("📨 Envoyer le code", use_container_width=True)
        if send and email.strip():
            _send_reset_code(supabase, email.strip().lower())
            st.session_state["reset_email"] = email.strip().lower()
            st.session_state["reset_step"] = 2
            st.rerun()
        return

    st.info("Si un compte est associé à cette adresse, un e-mail contenant ton nom "
            f"d'utilisateur et un code à 6 chiffres vient d'être envoyé (valable {CODE_TTL_MIN} min).")
    with st.form("form_email_reset"):
        otp = st.text_input("Code reçu par e-mail", max_chars=6)
        new_pw = st.text_input("Nouveau mot de passe", type="password")
        confirm = st.text_input("Confirmer le mot de passe", type="password")
        ok = st.form_submit_button("🔓 Réinitialiser", use_container_width=True)

    if st.button("↩️ Changer d'adresse / renvoyer un code"):
        st.session_state["reset_step"] = 1
        st.rerun()

    if ok:
        err = _validate_new_password(new_pw, confirm)
        if err:
            st.error(err)
            return
        _verify_reset_code(supabase, st.session_state.get("reset_email", ""), otp, new_pw)


def _send_reset_code(supabase, email: str) -> None:
    res = (supabase.table(USERS_TABLE)
           .select(f"{COL_ID},{COL_USERNAME}")
           .ilike(COL_EMAIL, email).limit(1).execute())
    if not res.data:
        return  # message neutre : on ne révèle pas si l'adresse existe

    user = res.data[0]
    otp = f"{secrets.randbelow(10**6):06d}"
    expires = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MIN)
    supabase.table(USERS_TABLE).update({
        "reset_code_hash": _digest(otp),
        "reset_expires": expires.isoformat(),
        "reset_attempts": 0,
    }).eq(COL_ID, user[COL_ID]).execute()

    body = (
        f"Bonjour,\n\n"
        f"Une demande de récupération d'accès a été faite sur {APP_NAME}.\n\n"
        f"Nom d'utilisateur : {user[COL_USERNAME]}\n"
        f"Code de réinitialisation : {otp}\n\n"
        f"Ce code est valable {CODE_TTL_MIN} minutes.\n"
        f"Si tu n'es pas à l'origine de cette demande, ignore simplement cet e-mail.\n"
    )
    try:
        _send_email(email, f"{APP_NAME} — Récupération de ton accès", body)
    except Exception:
        st.error("L'envoi de l'e-mail a échoué. Vérifie la configuration SMTP dans les secrets.")


def _verify_reset_code(supabase, email: str, otp: str, new_pw: str) -> None:
    res = (supabase.table(USERS_TABLE)
           .select(f"{COL_ID},{COL_USERNAME},reset_code_hash,reset_expires,reset_attempts")
           .ilike(COL_EMAIL, email).limit(1).execute())
    generic = "Code invalide ou expiré."
    if not res.data:
        st.error(generic)
        return

    u = res.data[0]
    attempts = u.get("reset_attempts") or 0
    expires = u.get("reset_expires")
    expired = (not expires) or datetime.fromisoformat(expires) < datetime.now(timezone.utc)

    if attempts >= MAX_ATTEMPTS or expired or not u.get("reset_code_hash"):
        st.error(generic + " Demande un nouveau code.")
        return

    if _digest(otp) != u["reset_code_hash"]:
        supabase.table(USERS_TABLE).update({"reset_attempts": attempts + 1}).eq(COL_ID, u[COL_ID]).execute()
        st.error(f"{generic} ({MAX_ATTEMPTS - attempts - 1} essai(s) restant(s))")
        return

    supabase.table(USERS_TABLE).update({
        COL_PASSWORD: hash_password(new_pw),
        "reset_code_hash": None,
        "reset_expires": None,
        "reset_attempts": 0,
    }).eq(COL_ID, u[COL_ID]).execute()

    st.session_state["reset_step"] = 1
    st.success(f"✅ Mot de passe modifié. Ton nom d'utilisateur est : **{u[COL_USERNAME]}**. "
               "Tu peux te connecter dans l'onglet Connexion.")


# ═══════════════════════════════════════════════════════════════════
# ESPACE ADMIN : liste des utilisateurs, export CSV, réinitialisation forcée
# ═══════════════════════════════════════════════════════════════════
# Colonnes jamais affichées ni exportées
_SENSITIVE_COLS = {COL_PASSWORD, "recovery_hash", "reset_code_hash",
                   "reset_expires", "reset_attempts"}


def is_admin(username: str | None) -> bool:
    """Admins définis dans les secrets Streamlit :  [admin] usernames = ["jena"]"""
    if not username:
        return False
    try:
        admins = [a.lower() for a in st.secrets["admin"]["usernames"]]
    except Exception:
        return False
    return username.lower() in admins


def generate_temp_password() -> str:
    alphabet = _ALPHABET + "abcdefghjkmnpqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def render_admin_panel(supabase, current_username: str) -> None:
    """Page admin. Ne s'affiche que pour un compte déclaré admin."""
    import pandas as pd

    if not is_admin(current_username):
        st.error("⛔ Accès réservé à l'administrateur.")
        return

    st.subheader("🛡️ Administration des comptes")

    rows = supabase.table(USERS_TABLE).select("*").execute().data or []
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("Aucun utilisateur.")
        return
    df = df.drop(columns=[c for c in _SENSITIVE_COLS if c in df.columns])

    # ── Recherche ──
    query = st.text_input("🔎 Rechercher (nom d'utilisateur ou e-mail)")
    if query:
        q = query.lower()
        mask = df[COL_USERNAME].astype(str).str.lower().str.contains(q, regex=False)
        if COL_EMAIL in df.columns:
            mask |= df[COL_EMAIL].astype(str).str.lower().str.contains(q, regex=False)
        df_view = df[mask]
    else:
        df_view = df

    st.caption(f"{len(df_view)} utilisateur(s) affiché(s) sur {len(df)}")
    st.dataframe(df_view, use_container_width=True, hide_index=True)

    # ── Export CSV (sans aucun mot de passe ni code) ──
    st.download_button(
        "📥 Exporter la liste (CSV)",
        df_view.to_csv(index=False, sep=";").encode("utf-8-sig"),  # lisible dans Excel FR
        file_name=f"mam_utilisateurs_{datetime.now():%Y%m%d}.csv",
        mime="text/csv",
    )

    # ── Réinitialisation forcée ──
    st.divider()
    st.markdown("**🔁 Réinitialiser le mot de passe d'un utilisateur**")
    usernames = df_view[COL_USERNAME].astype(str).tolist()
    if not usernames:
        return
    target = st.selectbox("Utilisateur", usernames)
    confirm = st.checkbox(f"Je confirme vouloir réinitialiser le mot de passe de « {target} »")

    if st.button("Générer un mot de passe temporaire", disabled=not confirm):
        temp = generate_temp_password()
        target_id = df.loc[df[COL_USERNAME].astype(str) == target, COL_ID].iloc[0]
        supabase.table(USERS_TABLE).update({
            COL_PASSWORD: hash_password(temp),
            "must_change_password": True,
            "reset_code_hash": None,
            "reset_expires": None,
            "reset_attempts": 0,
        }).eq(COL_ID, target_id).execute()
        st.success(f"Mot de passe temporaire pour **{target}** (affiché une seule fois) :")
        st.code(temp, language=None)
        st.caption("Transmets-le par un canal sûr. L'utilisateur devra le changer à sa prochaine connexion.")


# ── Changement obligatoire après un mot de passe temporaire ──
def must_change_password(user_row: dict) -> bool:
    return bool(user_row.get("must_change_password"))


def render_force_password_change(supabase, user_id) -> bool:
    """Affiche le formulaire de changement obligatoire. Retourne True une fois changé."""
    st.warning("🔐 Tu t'es connecté avec un mot de passe temporaire. Choisis un nouveau mot de passe.")
    with st.form("form_force_change"):
        new_pw = st.text_input("Nouveau mot de passe", type="password")
        confirm = st.text_input("Confirmer le mot de passe", type="password")
        ok = st.form_submit_button("Enregistrer", use_container_width=True)
    if ok:
        err = _validate_new_password(new_pw, confirm)
        if err:
            st.error(err)
            return False
        supabase.table(USERS_TABLE).update({
            COL_PASSWORD: hash_password(new_pw),
            "must_change_password": False,
        }).eq(COL_ID, user_id).execute()
        st.success("✅ Mot de passe mis à jour.")
        return True
    return False


# ═══════════════════════════════════════════════════════════════════
# INTÉGRATION
# ═══════════════════════════════════════════════════════════════════
#
# 1) Supabase → SQL Editor, exécuter une fois :
#
#    alter table users
#      add column if not exists email           text,
#      add column if not exists recovery_hash   text,
#      add column if not exists reset_code_hash text,
#      add column if not exists reset_expires   timestamptz,
#      add column if not exists reset_attempts  int default 0,
#      add column if not exists must_change_password boolean default false,
#      add column if not exists created_at      timestamptz default now();
#    create index if not exists users_recovery_hash_idx on users (recovery_hash);
#
# 2) requirements.txt : ajouter  bcrypt  (et pandas s'il n'y est pas déjà)
#
# 3) Dans main.py, sur l'écran de connexion :
#
#    from auth_recovery import render_forgot_tab, create_recovery_code, show_recovery_code
#
#    tab_login, tab_signup, tab_forgot = st.tabs(
#        ["🔐 Connexion", "📝 Créer un compte", "🔑 Identifiants oubliés"])
#    with tab_forgot:
#        render_forgot_tab(supabase)
#
#    # Dans l'onglet « Créer un compte », ajouter un champ e-mail, puis
#    # juste APRÈS l'insertion réussie du nouvel utilisateur :
#    #     new_id = insert_result.data[0]["id"]
#    #     show_recovery_code(create_recovery_code(supabase, new_id))
#
#    # Juste APRÈS une connexion réussie (user_row = la ligne de l'utilisateur) :
#    #     if must_change_password(user_row):
#    #         if not render_force_password_change(supabase, user_row["id"]):
#    #             st.stop()            # bloque l'accès tant que ce n'est pas fait
#
#    # Espace admin (ex. dans la barre latérale, une fois connecté) :
#    #     from auth_recovery import is_admin, render_admin_panel
#    #     if is_admin(username_connecte):
#    #         if st.sidebar.toggle("🛡️ Administration"):
#    #             render_admin_panel(supabase, username_connecte)
#    #             st.stop()
#
# 4) Secrets Streamlit Cloud → Settings → Secrets — déclarer l'admin (obligatoire) :
#
#    [admin]
#    usernames = ["ton_nom_utilisateur"]
#
# 5) (Optionnel) Envoi par e-mail — même écran Secrets :
#
#    [smtp]
#    host = "smtp.gmail.com"
#    port = 465
#    user = "ton.adresse@gmail.com"
#    password = "mot de passe d'application Google (16 caractères)"
#    sender = "MAM <ton.adresse@gmail.com>"
