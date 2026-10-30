# utils/notifier.py — MAM : notifications email quand un portefeuille bouge
"""
Envoie un email à l'utilisateur connecté (adresse du compte) lorsque :
  1. un portefeuille CHANGE : ordre spot/option exécuté, portefeuille créé /
     supprimé / réinitialisé, cash modifié  → détecté dans persist()
  2. la valeur (NAV) d'un portefeuille varie d'au moins X % depuis la dernière
     alerte (X = nav_alert_pct, 2 % par défaut, 0 = désactivé) → contrôlé à
     chaque rafraîchissement de la page (Streamlit n'a pas de tâche de fond :
     l'alerte de marché ne part que lorsque l'utilisateur est connecté).

CONFIGURATION dans .streamlit/secrets.toml (Streamlit Cloud → Settings → Secrets) :

[email]
smtp_host     = "smtp.gmail.com"
smtp_port     = 587                   # 587 = STARTTLS, 465 = SSL
smtp_user     = "votre.adresse@gmail.com"
smtp_password = "mot-de-passe-d-application"   # Gmail : mot de passe d'application
from_addr     = "MAM <votre.adresse@gmail.com>" # optionnel
security      = "starttls"            # "starttls" | "ssl" | "none"
nav_alert_pct = 2.0                   # optionnel, 0 = pas d'alerte de variation

Sans section [email], la plateforme fonctionne normalement, sans envoyer de mail.
"""
from __future__ import annotations

import html as _html
import smtplib
import ssl
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, parseaddr

import streamlit as st

# Dernier résultat d'envoi (écrit par le thread d'envoi, lu par l'UI)
_LAST: dict = {"ok": None, "msg": "", "time": ""}


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════


def _legal_html() -> str:
    from utils.legal import CREDIT, DISCLAIMER
    return f"<b>{CREDIT}</b><br>{DISCLAIMER}"


def _legal_text() -> str:
    from utils.legal import CREDIT, DISCLAIMER
    return f"{CREDIT}\n{DISCLAIMER}"

def get_config() -> dict | None:
    """Lit la section [email] des secrets. None si non configuré."""
    try:
        e = st.secrets["email"]
        host = str(e.get("smtp_host", "")).strip()
        if not host:
            return None
        user = str(e.get("smtp_user", "")).strip()
        return {
            "host": host,
            "port": int(e.get("smtp_port", 587)),
            "user": user,
            "password": str(e.get("smtp_password", "")),
            "from_addr": str(e.get("from_addr", "")).strip() or user,
            "security": str(e.get("security", "starttls")).lower(),
            "nav_alert_pct": float(e.get("nav_alert_pct", 2.0)),
        }
    except Exception:
        return None


def recipients() -> list[str]:
    """v5.10 — adresse du compte + destinataires supplémentaires choisis dans 🔔 (profil investisseur)."""
    from utils.alerts import parse_recipients
    user = st.session_state.get("mam_user")
    extra = []
    try:
        from utils.compliance import get_profile
        extra = get_profile().get("destinataires") or []
    except Exception:
        pass
    return parse_recipients([(user or {}).get("email", "")] + list(extra))


def _recipient() -> str | None:
    r = recipients()
    return ", ".join(r) if r else None


def save_extra_recipients(value: str) -> list[str]:
    """Enregistre les destinataires supplémentaires dans le profil investisseur (session + base),
    sans toucher au reste du profil (questionnaire, test sur les options)."""
    from utils.alerts import parse_recipients
    from utils.compliance import get_profile
    user = st.session_state.get("mam_user") or {}
    user_mail = (user.get("email") or "").lower()
    lst = [x for x in parse_recipients(value) if x.lower() != user_mail]
    raw = dict(st.session_state.get("mam_investor_profile") or {})
    if not raw:
        get_profile()
        raw = dict(st.session_state.get("mam_investor_profile") or {})
    raw["destinataires"] = lst
    st.session_state["mam_investor_profile"] = raw
    if user.get("id"):
        try:
            from utils.db import save_investor_profile
            save_investor_profile(user["id"], raw)
        except Exception:
            pass
    return lst


def _enabled() -> bool:
    return bool(st.session_state.get("mail_enabled", True))


# ══════════════════════════════════════════════════════════════════════════════
# ENVOI (thread, pour ne jamais bloquer l'interface)
# ══════════════════════════════════════════════════════════════════════════════

def _smtp_send(cfg: dict, to: str, subject: str, html_body: str, text_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    name, addr = parseaddr(cfg["from_addr"])
    msg["From"] = formataddr((name or "MAM — McKenson Asset Management", addr))
    msg["To"] = to
    msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    if cfg["security"] == "ssl":
        server = smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=15,
                                  context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(cfg["host"], cfg["port"], timeout=15)
    try:
        server.ehlo()
        if cfg["security"] == "starttls":
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if cfg["user"] and cfg["password"]:
            server.login(cfg["user"], cfg["password"])
        from utils.alerts import parse_recipients
        server.sendmail(addr or cfg["user"], parse_recipients(to) or [to], msg.as_string())
    finally:
        try:
            server.quit()
        except Exception:
            pass


def _send_async(cfg: dict, to: str, subject: str, html_body: str, text_body: str):
    def _worker():
        try:
            _smtp_send(cfg, to, subject, html_body, text_body)
            _LAST.update(ok=True, msg=f"Email envoyé à {to}",
                         time=datetime.now().strftime("%H:%M:%S"))
        except Exception as exc:  # noqa: BLE001
            _LAST.update(ok=False, msg=f"Échec d'envoi : {exc}",
                         time=datetime.now().strftime("%H:%M:%S"))

    threading.Thread(target=_worker, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
# VALORISATION
# ══════════════════════════════════════════════════════════════════════════════

def _valuation(port: dict) -> dict:
    """NAV, P&L et lignes de positions (prix en cache, repli sur le PRU)."""
    from utils.data import get_multi_prices, value_portfolio
    holdings = port.get("holdings", {}) or {}
    prices = {}
    if holdings:
        try:
            prices = get_multi_prices(tuple(holdings.keys()))
        except Exception:
            prices = {}
    val = value_portfolio(port, prices)
    init = float(port.get("initial_cash", 1_000_000) or 0)
    val["initial"] = init
    try:  # v5.8 : résultat hors apports / retraits, performance pondérée dans le temps (GIPS)
        from utils.ledger import net_external
        from utils.performance import since_inception
        val["pnl"] = val["total"] - init - net_external(port)
        r_ = since_inception(port, val["total"])[0]
        val["pnl_pct"] = r_ * 100 if r_ == r_ else 0.0
    except Exception:
        val["pnl"] = val["total"] - init
        val["pnl_pct"] = (val["pnl"] / init * 100) if init else 0.0
    return val


# ══════════════════════════════════════════════════════════════════════════════
# EMAIL : CONTENU
# ══════════════════════════════════════════════════════════════════════════════

def _money(x: float) -> str:
    return f"${x:,.2f}"


def _build_email(port: dict, headline: str, lines: list[str]) -> tuple[str, str]:
    e = _html.escape
    val = _valuation(port)
    col = "#00ff88" if val["pnl"] >= 0 else "#ff3b6b"
    sign = "+" if val["pnl"] >= 0 else ""
    name = f'{port.get("emoji", "📁")} {port.get("name", "Portefeuille")}'

    rows = ""
    for p in val["positions"]:
        c = "#00ff88" if p["unreal_pnl"] >= 0 else "#ff3b6b"
        s = "+" if p["unreal_pnl"] >= 0 else ""
        rows += (
            f'<tr><td style="padding:6px 10px;color:#00d4ff">{e(p["ticker"])}</td>'
            f'<td style="padding:6px 10px;text-align:right">{p["qty"]:,.4g}</td>'
            f'<td style="padding:6px 10px;text-align:right">{p["avg_price"]:,.2f}</td>'
            f'<td style="padding:6px 10px;text-align:right">{p["current_price"]:,.2f}</td>'
            f'<td style="padding:6px 10px;text-align:right;color:{c}">{s}{p["unreal_pnl"]:,.2f}</td></tr>'
        )
    positions = (
        '<table style="width:100%;border-collapse:collapse;font-size:12px;color:#cbd5e1">'
        '<tr style="color:#64748b;text-align:right"><th style="padding:6px 10px;text-align:left">Titre</th>'
        '<th style="padding:6px 10px">Qté</th><th style="padding:6px 10px">PRU</th>'
        '<th style="padding:6px 10px">Prix</th><th style="padding:6px 10px">P&amp;L latent</th></tr>'
        f"{rows}</table>"
        if rows else '<div style="color:#64748b;font-size:12px">Aucune position ouverte.</div>'
    )
    items = "".join(f'<li style="margin:4px 0">{e(l)}</li>' for l in lines)
    html_body = f"""\
<div style="background:#080e1a;padding:24px;font-family:'Courier New',monospace">
 <div style="max-width:620px;margin:auto;background:#0d1117;border:1px solid rgba(0,212,255,.25);border-radius:10px;overflow:hidden">
  <div style="padding:16px 22px;border-bottom:1px solid rgba(0,212,255,.15)">
   <span style="color:#00ff88;font-size:22px;font-weight:bold;letter-spacing:4px">MAM</span>
   <span style="color:#475569;font-size:10px;letter-spacing:3px;margin-left:10px">McKENSON ASSET MANAGEMENT</span>
  </div>
  <div style="padding:20px 22px;color:#e2e8f0">
   <div style="color:#00d4ff;font-size:11px;letter-spacing:2px;text-transform:uppercase">{e(headline)}</div>
   <div style="font-size:18px;font-weight:bold;margin:4px 0 14px">{e(name)}</div>
   <ul style="padding-left:18px;margin:0 0 18px;font-size:13px;color:#cbd5e1">{items}</ul>
   <table style="width:100%;border-collapse:collapse;margin-bottom:16px"><tr>
    <td style="background:#111827;border-radius:6px;padding:10px 12px"><div style="color:#64748b;font-size:10px">VALEUR (NAV)</div><div style="font-size:16px;color:#e2e8f0">{_money(val["total"])}</div></td>
    <td style="width:8px"></td>
    <td style="background:#111827;border-radius:6px;padding:10px 12px"><div style="color:#64748b;font-size:10px">CASH</div><div style="font-size:16px;color:#e2e8f0">{_money(val["cash"])}</div></td>
    <td style="width:8px"></td>
    <td style="background:#111827;border-radius:6px;padding:10px 12px"><div style="color:#64748b;font-size:10px">P&amp;L TOTAL</div><div style="font-size:16px;color:{col}">{sign}{_money(abs(val["pnl"]))} ({sign}{abs(val["pnl_pct"]):.2f}%)</div></td>
   </tr></table>
   {positions}
  </div>
  <div style="padding:12px 22px;border-top:1px solid rgba(0,212,255,.1);color:#475569;font-size:10px">
   Simulation à but pédagogique — aucune opération réelle. Notification envoyée le {datetime.now().strftime("%d/%m/%Y à %H:%M")}.<br>
   {_legal_html()}
  </div>
 </div>
</div>"""
    text_body = (
        f"MAM — {headline}\n{name}\n\n"
        + "\n".join(f"- {l}" for l in lines)
        + f"\n\nNAV : {_money(val['total'])} | Cash : {_money(val['cash'])} | "
        f"P&L : {sign}{_money(abs(val['pnl']))} ({sign}{abs(val['pnl_pct']):.2f}%)\n"
        "Simulation à but pédagogique.\n\n" + _legal_text()
    )
    return html_body, text_body


def _dispatch(port: dict, headline: str, subject: str, lines: list[str]):
    cfg, to = get_config(), _recipient()
    if not cfg or not to or not _enabled():
        return
    html_body, text_body = _build_email(port, headline, lines)
    _send_async(cfg, to, subject, html_body, text_body)


# ══════════════════════════════════════════════════════════════════════════════
# DÉTECTION DES CHANGEMENTS
# ══════════════════════════════════════════════════════════════════════════════

def _signature(port: dict) -> dict:
    return {
        "cash": round(float(port.get("cash", 0) or 0), 2),
        "n_trades": len(port.get("trades", []) or []),
        "n_options": len(port.get("options", []) or []),
        "nav_base": None,
    }


def _all_ports(state: dict):
    for team in (state.get("teams") or {}).values():
        for pid, port in (team.get("portfolios") or {}).items():
            yield pid, port


def init_baseline(state: dict):
    """Mémorise l'état courant comme référence (appelé à chaque rerun, ne fait
    quelque chose qu'une fois par connexion)."""
    if "_mail_known" in st.session_state or not state:
        return
    st.session_state["_mail_known"] = {pid: _signature(p) for pid, p in _all_ports(state)}


def notify_changes(state: dict):
    """À appeler après chaque persist() : envoie un email par portefeuille modifié."""
    if not state or not st.session_state.get("mam_user"):
        return
    known = st.session_state.get("_mail_known")
    if known is None:
        init_baseline(state)
        return

    current = dict(_all_ports(state))
    for pid, port in current.items():
        sig = _signature(port)
        old = known.get(pid)
        label = port.get("name", pid)
        if old is None:
            known[pid] = sig
            _dispatch(port, "Nouveau portefeuille", f"[MAM] Portefeuille « {label} » créé",
                      [f"Portefeuille créé avec un capital de {_money(port.get('initial_cash', 0))}"])
            continue
        if sig["cash"] == old["cash"] and sig["n_trades"] == old["n_trades"] \
                and sig["n_options"] == old["n_options"]:
            continue

        lines: list[str] = []
        trades = port.get("trades", []) or []
        if sig["n_trades"] < old["n_trades"]:
            lines.append("Portefeuille réinitialisé (historique d'ordres effacé)")
        else:
            for t in trades[old["n_trades"]:]:
                lines.append(
                    f'{t.get("date", "")} — {t.get("action", "")} {t.get("qty", "")} × '
                    f'{t.get("ticker", "")} @ {t.get("price", "")} (total {t.get("total", "")})'
                )
        if not lines and sig["cash"] != old["cash"]:
            lines.append(f'Cash modifié : {_money(old["cash"])} → {_money(sig["cash"])}')

        known[pid] = sig  # nav_base remis à None : pas de fausse alerte après un mouvement de cash
        n = max(len(lines), 1)
        _dispatch(port, "Mouvement de portefeuille",
                  f"[MAM] « {label} » — {n} mouvement{'s' if n > 1 else ''}", lines)

    for pid in [k for k in known if k not in current]:
        del known[pid]


def check_nav_moves(state: dict):
    """Alerte si la NAV d'un portefeuille a varié d'au moins nav_alert_pct %
    depuis la dernière alerte (ou depuis le début de la session)."""
    cfg = get_config()
    if not cfg or cfg["nav_alert_pct"] <= 0 or not _recipient() or not _enabled():
        return
    known = st.session_state.get("_mail_known")
    if known is None:
        return
    for pid, port in _all_ports(state):
        sig = known.get(pid)
        if sig is None:
            continue
        try:
            nav = _valuation(port)["total"]
        except Exception:
            continue
        base = sig.get("nav_base")
        if not base:
            sig["nav_base"] = nav
            continue
        move = (nav / base - 1) * 100 if base else 0.0
        if abs(move) >= cfg["nav_alert_pct"]:
            sig["nav_base"] = nav
            arrow = "📈 hausse" if move > 0 else "📉 baisse"
            _dispatch(
                port, "Variation de valeur",
                f"[MAM] « {port.get('name', pid)} » {move:+.2f}%",
                [f"{arrow} de {abs(move):.2f}% depuis la dernière alerte "
                 f"({_money(base)} → {_money(nav)})"],
            )


# ══════════════════════════════════════════════════════════════════════════════
# PANNEAU UI (popover de la barre du haut)
# ══════════════════════════════════════════════════════════════════════════════

def render_settings():
    cfg, to = get_config(), _recipient()
    st.markdown("**🔔 Notifications email**")
    if not cfg:
        st.caption("Email non configuré : ajoutez une section `[email]` dans les Secrets "
                   "(voir le README).")
        return
    if not to:
        st.caption("Connectez-vous avec un compte pour recevoir les notifications.")
        return
    st.toggle("Recevoir un email quand mon portefeuille bouge", value=True, key="mail_enabled")
    st.caption(f"Destinataire(s) : {to}")
    try:
        from utils.compliance import get_profile
        cur = ", ".join(get_profile().get("destinataires") or [])
    except Exception:
        cur = ""
    with st.form("mail_extra_form", border=False):
        val = st.text_input("Autres destinataires (séparés par des virgules)", value=cur,
                            placeholder="adresse2@gmail.com, adresse3@gmail.com")
        if st.form_submit_button("Enregistrer les destinataires", use_container_width=True):
            lst = save_extra_recipients(val)
            st.success(f"{len(lst)} destinataire(s) supplémentaire(s) enregistré(s).")
            st.rerun()
    if cfg["nav_alert_pct"] > 0:
        st.caption(f"Alerte de variation de valeur : ±{cfg['nav_alert_pct']:g} %")
    if st.button("✉️ Envoyer un email de test", key="mail_test", use_container_width=True):
        html_body = ('<div style="background:#080e1a;padding:24px;color:#e2e8f0;font-family:monospace">'
                     '<b style="color:#00ff88">MAM</b> — les notifications email fonctionnent ✅</div>')
        _send_async(cfg, to, "[MAM] Email de test", html_body,
                    "MAM — les notifications email fonctionnent.")
    if _LAST["ok"] is not None:
        (st.success if _LAST["ok"] else st.error)(f'{_LAST["time"]} — {_LAST["msg"]}')
