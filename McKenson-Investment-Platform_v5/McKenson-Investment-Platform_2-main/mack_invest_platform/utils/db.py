# utils/db.py — MAM v4.0 Supabase PostgreSQL Backend
"""
Gestion complète de la persistance via Supabase (PostgreSQL).
- Comptes utilisateurs (login/password hashé)
- Portefeuilles permanents
- Snapshots de performance automatiques
- Toutes les tables créées automatiquement au premier démarrage

CONFIGURATION dans .streamlit/secrets.toml :
[supabase]
url = "https://iwjbydiuklbceuamxqes.supabase.co"
anon_key = "eyJhbGci..."
db_password = "VOTRE_MOT_DE_PASSE_SUPABASE"
"""

from __future__ import annotations
import json
import hashlib
import hmac
import secrets
import string
from datetime import datetime
from typing import Optional
import streamlit as st

try:
    import psycopg2
    import psycopg2.extras
    _PG = True
except ImportError:
    _PG = False

# ══════════════════════════════════════════════════════════════════════════════
# CONNECTION
# ══════════════════════════════════════════════════════════════════════════════

def _get_conn():
    """Retourne une connexion PostgreSQL Supabase.

    Deux façons de configurer (dans les Streamlit Secrets) :

    1) RECOMMANDÉ sur Streamlit Cloud — URL du pooler Supabase (compatible IPv4) :
         [supabase]
         database_url = "postgresql://postgres.<ref>:<MOT_DE_PASSE>@aws-0-<region>.pooler.supabase.com:6543/postgres"
       (Supabase → Project Settings → Database → Connection string → "Transaction pooler")

    2) Ancien mode : url + db_password. Le project_ref est déduit de l'URL et on se
       connecte à db.<ref>.supabase.co:5432 (IPv6 uniquement : peut échouer sur Streamlit Cloud).
    """
    if not _PG:
        raise RuntimeError("psycopg2 non installé")
    try:
        sb = st.secrets["supabase"]
        database_url = sb.get("database_url") if hasattr(sb, "get") else None
        if database_url:
            return psycopg2.connect(
                database_url,
                connect_timeout=8,
                options="-c statement_timeout=10000",
            )
        pw           = sb["db_password"]
        supabase_url = sb["url"]
        project_ref  = supabase_url.replace("https://", "").split(".supabase.co")[0]
        db_host      = f"db.{project_ref}.supabase.co"
        return psycopg2.connect(
            host=db_host,
            port=5432,
            dbname="postgres",
            user="postgres",
            password=pw,
            connect_timeout=8,
            options="-c statement_timeout=10000",
        )
    except Exception as e:
        raise RuntimeError(f"Connexion Supabase impossible : {e}")


def _run(sql: str, params=None, fetch=False):
    """Exécute une requête SQL. Retourne les lignes si fetch=True."""
    conn = _get_conn()
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params or ())
                if fetch:
                    return [dict(r) for r in cur.fetchall()]
                return []
    finally:
        conn.close()

# ══════════════════════════════════════════════════════════════════════════════
# INITIALISATION DES TABLES
# ══════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
-- Utilisateurs
CREATE TABLE IF NOT EXISTS mam_users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'student',  -- student | admin
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login TIMESTAMPTZ
);

-- Équipes
CREATE TABLE IF NOT EXISTS mam_teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '🏢',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Portefeuilles
CREATE TABLE IF NOT EXISTS mam_portfolios (
    id TEXT PRIMARY KEY,
    team_id TEXT REFERENCES mam_teams(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES mam_users(id),
    name TEXT NOT NULL,
    emoji TEXT DEFAULT '📁',
    strategy TEXT DEFAULT 'Libre',
    asset_types JSONB DEFAULT '[]',
    cash DOUBLE PRECISION DEFAULT 1000000,
    initial_cash DOUBLE PRECISION DEFAULT 1000000,
    holdings JSONB DEFAULT '{}',
    options JSONB DEFAULT '[]',
    trades JSONB DEFAULT '[]',
    history JSONB DEFAULT '[]',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Snapshots de performance (automatiques)
CREATE TABLE IF NOT EXISTS mam_snapshots (
    id SERIAL PRIMARY KEY,
    portfolio_id TEXT REFERENCES mam_portfolios(id) ON DELETE CASCADE,
    snapshot_date DATE NOT NULL,
    nav DOUBLE PRECISION,
    cash DOUBLE PRECISION,
    spot_value DOUBLE PRECISION,
    total_pnl DOUBLE PRECISION,
    pnl_pct DOUBLE PRECISION,
    n_positions INTEGER,
    positions_json JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(portfolio_id, snapshot_date)
);

-- Journal de connexions
CREATE TABLE IF NOT EXISTS mam_auth_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES mam_users(id),
    username TEXT,
    event TEXT,  -- register | login | logout
    ip_hint TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Récupération d'identifiants (ajout sans toucher aux comptes existants)
ALTER TABLE mam_users ADD COLUMN IF NOT EXISTS recovery_hash TEXT;
ALTER TABLE mam_users ADD COLUMN IF NOT EXISTS reset_code_hash TEXT;
ALTER TABLE mam_users ADD COLUMN IF NOT EXISTS reset_expires TIMESTAMPTZ;
ALTER TABLE mam_users ADD COLUMN IF NOT EXISTS reset_attempts INTEGER DEFAULT 0;
ALTER TABLE mam_users ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN DEFAULT FALSE;

-- Index
CREATE INDEX IF NOT EXISTS idx_users_recovery ON mam_users(recovery_hash);
CREATE INDEX IF NOT EXISTS idx_portfolios_team ON mam_portfolios(team_id);
CREATE INDEX IF NOT EXISTS idx_portfolios_user ON mam_portfolios(user_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_port ON mam_snapshots(portfolio_id);
CREATE INDEX IF NOT EXISTS idx_snapshots_date ON mam_snapshots(snapshot_date);
"""


@st.cache_resource(show_spinner=False)
def init_db():
    """Crée toutes les tables si elles n'existent pas."""
    try:
        conn = _get_conn()
        with conn:
            with conn.cursor() as cur:
                cur.execute(SCHEMA_SQL)
        conn.close()
        return True
    except Exception as e:
        st.warning(f"⚠️ DB init: {e}")
        return False


@st.cache_data(ttl=20, show_spinner=False)
def _db_status() -> tuple[bool, str]:
    """(disponible, message d'erreur). Mis en cache 20 s pour ne pas ouvrir une
    connexion à chaque rerun Streamlit."""
    try:
        _run("SELECT 1")
        return True, ""
    except Exception as e:
        return False, str(e)


def is_db_available() -> bool:
    """Vérifie si la DB est accessible."""
    return _db_status()[0]


def db_last_error() -> str:
    """Dernière erreur de connexion (pour affichage de diagnostic)."""
    return _db_status()[1]

# ══════════════════════════════════════════════════════════════════════════════
# AUTHENTIFICATION
# ══════════════════════════════════════════════════════════════════════════════

def _hash_password(password: str) -> str:
    salt = "mam_eslsca_2026"
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def create_user(username: str, email: str, password: str, role: str = "student") -> dict:
    """Crée un nouvel utilisateur. Retourne {'ok': bool, 'msg': str}."""
    if len(username) < 3:
        return {"ok": False, "msg": "Nom d'utilisateur trop court (min 3 caractères)"}
    if len(password) < 6:
        return {"ok": False, "msg": "Mot de passe trop court (min 6 caractères)"}
    try:
        rows = _run(
            "INSERT INTO mam_users (username, email, password_hash, role) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (username.strip().lower(), email.strip().lower(), _hash_password(password), role),
            fetch=True,
        )
        user_id = rows[0]["id"] if rows else None
        recovery_code = None
        if user_id is not None:
            try:
                recovery_code = set_recovery_code(user_id)
            except Exception:
                recovery_code = None
        _log_event(user_id, username, "register")
        return {
            "ok": True,
            "msg": f"Compte '{username}' créé avec succès !",
            "recovery_code": recovery_code,
        }
    except psycopg2.errors.UniqueViolation:
        return {"ok": False, "msg": "Ce nom d'utilisateur ou email existe déjà."}
    except Exception as e:
        return {"ok": False, "msg": f"Erreur : {e}"}


def login_user(username: str, password: str) -> Optional[dict]:
    """Vérifie les credentials. Retourne le dict utilisateur ou None."""
    rows = _run(
        "SELECT * FROM mam_users WHERE username=%s AND password_hash=%s",
        (username.strip().lower(), _hash_password(password)),
        fetch=True,
    )
    if not rows:
        return None
    user = rows[0]
    _run("UPDATE mam_users SET last_login=NOW() WHERE id=%s", (user["id"],))
    _log_event(user["id"], username, "login")
    # On ne garde jamais les empreintes secrètes en session
    for _k in _SECRET_COLUMNS:
        user.pop(_k, None)
    return user


def get_all_users() -> list[dict]:
    """Liste des comptes (vue admin) — sans aucun mot de passe ni code."""
    return _run(
        "SELECT id, username, email, role, created_at, last_login, "
        "(recovery_hash IS NOT NULL) AS has_recovery_code, "
        "COALESCE(must_change_password, FALSE) AS must_change_password "
        "FROM mam_users ORDER BY created_at DESC",
        fetch=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
# RÉCUPÉRATION D'IDENTIFIANTS
# ══════════════════════════════════════════════════════════════════════════════
# Les codes ne sont jamais stockés en clair : seule leur empreinte SHA-256 l'est.
# Les mots de passe restent hachés avec _hash_password (même fonction qu'à la
# connexion), donc les comptes existants continuent de fonctionner.

MIN_PASSWORD_LEN = 6
RESET_CODE_TTL_MIN = 15
RESET_MAX_ATTEMPTS = 5
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O/1/I
_SECRET_COLUMNS = ("password_hash", "recovery_hash", "reset_code_hash")


def _digest(value: str) -> str:
    normalized = (value or "").strip().upper().replace("-", "").replace(" ", "")
    return hashlib.sha256(normalized.encode()).hexdigest()


def _check_new_password(password: str) -> Optional[str]:
    if not password or len(password) < MIN_PASSWORD_LEN:
        return f"Mot de passe trop court (min {MIN_PASSWORD_LEN} caractères)."
    return None


def generate_recovery_code() -> str:
    """Code du type ABCD-EFGH-JKLM-NPQR."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(16))
    return "-".join(raw[i:i + 4] for i in range(0, 16, 4))


def generate_temp_password() -> str:
    alphabet = _CODE_ALPHABET + "abcdefghjkmnpqrstuvwxyz"
    return "".join(secrets.choice(alphabet) for _ in range(12))


def set_recovery_code(user_id: int) -> str:
    """Crée (ou remplace) le code de récupération d'un compte. Retourne le code clair."""
    code = generate_recovery_code()
    _run("UPDATE mam_users SET recovery_hash=%s WHERE id=%s", (_digest(code), user_id))
    return code


def recover_with_code(code: str, new_password: str) -> dict:
    """Code de récupération → nom d'utilisateur + nouveau mot de passe.
    Le code utilisé est remplacé par un nouveau, renvoyé dans 'new_code'."""
    err = _check_new_password(new_password)
    if err:
        return {"ok": False, "msg": err}
    rows = _run(
        "SELECT id, username FROM mam_users WHERE recovery_hash=%s",
        (_digest(code),),
        fetch=True,
    )
    if not rows:
        return {"ok": False, "msg": "Code de récupération invalide.", "bad_code": True}
    user = rows[0]
    new_code = generate_recovery_code()
    _run(
        "UPDATE mam_users SET password_hash=%s, recovery_hash=%s, must_change_password=FALSE, "
        "reset_code_hash=NULL, reset_expires=NULL, reset_attempts=0 WHERE id=%s",
        (_hash_password(new_password), _digest(new_code), user["id"]),
    )
    _log_event(user["id"], user["username"], "recovery_code")
    return {"ok": True, "msg": "Mot de passe modifié.",
            "username": user["username"], "new_code": new_code}


def create_email_reset(email: str) -> Optional[dict]:
    """Prépare un code à 6 chiffres pour l'adresse donnée.
    Retourne {'username', 'email', 'otp'} ou None si l'adresse est inconnue."""
    rows = _run(
        "SELECT id, username, email FROM mam_users WHERE email=%s",
        ((email or "").strip().lower(),),
        fetch=True,
    )
    if not rows:
        return None
    user = rows[0]
    otp = f"{secrets.randbelow(10**6):06d}"
    _run(
        "UPDATE mam_users SET reset_code_hash=%s, "
        "reset_expires=NOW() + (%s * INTERVAL '1 minute'), reset_attempts=0 WHERE id=%s",
        (_digest(otp), RESET_CODE_TTL_MIN, user["id"]),
    )
    _log_event(user["id"], user["username"], "reset_request")
    return {"username": user["username"], "email": user["email"], "otp": otp}


def reset_with_email_code(email: str, otp: str, new_password: str) -> dict:
    """Vérifie le code reçu par e-mail et change le mot de passe."""
    err = _check_new_password(new_password)
    if err:
        return {"ok": False, "msg": err}
    generic = "Code invalide ou expiré."
    rows = _run(
        "SELECT id, username, reset_code_hash, COALESCE(reset_attempts, 0) AS attempts, "
        "(reset_expires > NOW()) AS still_valid FROM mam_users WHERE email=%s",
        ((email or "").strip().lower(),),
        fetch=True,
    )
    if not rows:
        return {"ok": False, "msg": generic}
    user = rows[0]
    attempts = user["attempts"]
    if not user["reset_code_hash"] or not user["still_valid"] or attempts >= RESET_MAX_ATTEMPTS:
        return {"ok": False, "msg": generic + " Demande un nouveau code."}
    if not hmac.compare_digest(_digest(otp), user["reset_code_hash"]):
        _run(
            "UPDATE mam_users SET reset_attempts=COALESCE(reset_attempts, 0) + 1 WHERE id=%s",
            (user["id"],),
        )
        left = max(RESET_MAX_ATTEMPTS - attempts - 1, 0)
        return {"ok": False, "msg": f"{generic} ({left} essai(s) restant(s))"}
    _run(
        "UPDATE mam_users SET password_hash=%s, must_change_password=FALSE, "
        "reset_code_hash=NULL, reset_expires=NULL, reset_attempts=0 WHERE id=%s",
        (_hash_password(new_password), user["id"]),
    )
    _log_event(user["id"], user["username"], "reset_email")
    return {"ok": True, "msg": "Mot de passe modifié.", "username": user["username"]}


def admin_reset_password(user_id: int, username: Optional[str] = None) -> str:
    """Admin : génère un mot de passe temporaire, à changer à la prochaine connexion."""
    temp = generate_temp_password()
    _run(
        "UPDATE mam_users SET password_hash=%s, must_change_password=TRUE, "
        "reset_code_hash=NULL, reset_expires=NULL, reset_attempts=0 WHERE id=%s",
        (_hash_password(temp), user_id),
    )
    _log_event(user_id, username, "admin_reset")
    return temp


def change_password(user_id: int, new_password: str) -> dict:
    """Changement de mot de passe par l'utilisateur (ex. après un mot de passe temporaire)."""
    err = _check_new_password(new_password)
    if err:
        return {"ok": False, "msg": err}
    _run(
        "UPDATE mam_users SET password_hash=%s, must_change_password=FALSE WHERE id=%s",
        (_hash_password(new_password), user_id),
    )
    _log_event(user_id, None, "password_change")
    return {"ok": True, "msg": "Mot de passe mis à jour."}


def _log_event(user_id, username, event):
    try:
        _run(
            "INSERT INTO mam_auth_log (user_id, username, event) VALUES (%s, %s, %s)",
            (user_id, username, event),
        )
    except Exception:
        pass

# ══════════════════════════════════════════════════════════════════════════════
# ÉQUIPES
# ══════════════════════════════════════════════════════════════════════════════

def upsert_team(team_id: str, name: str, emoji: str = "🏢"):
    _run(
        "INSERT INTO mam_teams (id, name, emoji) VALUES (%s, %s, %s) "
        "ON CONFLICT (id) DO UPDATE SET name=%s, emoji=%s",
        (team_id, name, emoji, name, emoji),
    )


def get_all_teams() -> list[dict]:
    return _run("SELECT * FROM mam_teams ORDER BY created_at", fetch=True)

# ══════════════════════════════════════════════════════════════════════════════
# PORTEFEUILLES
# ══════════════════════════════════════════════════════════════════════════════

def save_portfolio(port_id: str, team_id: str, user_id: int, port_data: dict):
    """Upsert complet d'un portefeuille."""
    _run("""
        INSERT INTO mam_portfolios
            (id, team_id, user_id, name, emoji, strategy, asset_types,
             cash, initial_cash, holdings, options, trades, history, updated_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
        ON CONFLICT (id) DO UPDATE SET
            cash=%s, holdings=%s, options=%s, trades=%s, history=%s, updated_at=NOW()
    """, (
        port_id, team_id, user_id,
        port_data.get("name", ""),
        port_data.get("emoji", "📁"),
        port_data.get("strategy", "Libre"),
        json.dumps(port_data.get("asset_types", [])),
        port_data.get("cash", 0),
        port_data.get("initial_cash", 1_000_000),
        json.dumps(port_data.get("holdings", {})),
        json.dumps(port_data.get("options", [])),
        json.dumps(port_data.get("trades", [])),
        json.dumps(port_data.get("history", [])),
        # ON CONFLICT values
        port_data.get("cash", 0),
        json.dumps(port_data.get("holdings", {})),
        json.dumps(port_data.get("options", [])),
        json.dumps(port_data.get("trades", [])),
        json.dumps(port_data.get("history", [])),
    ))


def load_portfolios_for_user(user_id: int) -> list[dict]:
    """Charge tous les portefeuilles d'un utilisateur."""
    rows = _run(
        "SELECT * FROM mam_portfolios WHERE user_id=%s ORDER BY created_at",
        (user_id,),
        fetch=True,
    )
    result = []
    for r in rows:
        r["holdings"]   = r["holdings"]   if isinstance(r["holdings"], dict)  else json.loads(r["holdings"]   or "{}")
        r["options"]    = r["options"]    if isinstance(r["options"], list)    else json.loads(r["options"]    or "[]")
        r["trades"]     = r["trades"]     if isinstance(r["trades"], list)     else json.loads(r["trades"]     or "[]")
        r["history"]    = r["history"]    if isinstance(r["history"], list)    else json.loads(r["history"]    or "[]")
        r["asset_types"]= r["asset_types"]if isinstance(r["asset_types"], list)else json.loads(r["asset_types"]or "[]")
        result.append(r)
    return result


def load_all_portfolios() -> list[dict]:
    """Charge tous les portefeuilles (vue admin)."""
    rows = _run("""
        SELECT p.*, u.username, t.name as team_name, t.emoji as team_emoji
        FROM mam_portfolios p
        LEFT JOIN mam_users u ON p.user_id=u.id
        LEFT JOIN mam_teams t ON p.team_id=t.id
        ORDER BY p.created_at
    """, fetch=True)
    for r in rows:
        for field in ["holdings", "options", "trades", "history", "asset_types"]:
            v = r.get(field)
            if isinstance(v, str):
                r[field] = json.loads(v or ("{}" if field == "holdings" else "[]"))
    return rows


def delete_portfolio(port_id: str):
    _run("DELETE FROM mam_portfolios WHERE id=%s", (port_id,))

# ══════════════════════════════════════════════════════════════════════════════
# SNAPSHOTS DE PERFORMANCE (automatiques)
# ══════════════════════════════════════════════════════════════════════════════

def save_snapshot(
    portfolio_id: str,
    nav: float,
    cash: float,
    spot_value: float,
    total_pnl: float,
    pnl_pct: float,
    n_positions: int,
    positions: list,
):
    """Sauvegarde un snapshot de performance (upsert par date)."""
    today = datetime.now().date().isoformat()
    _run("""
        INSERT INTO mam_snapshots
            (portfolio_id, snapshot_date, nav, cash, spot_value,
             total_pnl, pnl_pct, n_positions, positions_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (portfolio_id, snapshot_date) DO UPDATE SET
            nav=%s, cash=%s, spot_value=%s, total_pnl=%s,
            pnl_pct=%s, n_positions=%s, positions_json=%s
    """, (
        portfolio_id, today, nav, cash, spot_value,
        total_pnl, pnl_pct, n_positions, json.dumps(positions),
        nav, cash, spot_value, total_pnl,
        pnl_pct, n_positions, json.dumps(positions),
    ))


def get_snapshots(portfolio_id: str, days: int = 365) -> list[dict]:
    """Récupère l'historique de performance d'un portefeuille."""
    return _run("""
        SELECT * FROM mam_snapshots
        WHERE portfolio_id=%s
          AND snapshot_date >= CURRENT_DATE - INTERVAL '%s days'
        ORDER BY snapshot_date
    """, (portfolio_id, days), fetch=True)


def get_auth_log(limit: int = 100) -> list[dict]:
    return _run(
        "SELECT * FROM mam_auth_log ORDER BY created_at DESC LIMIT %s",
        (limit,),
        fetch=True,
    )
