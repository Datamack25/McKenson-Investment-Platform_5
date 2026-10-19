"""
utils/alerts.py — Système d'alertes du Hedge Fund Agent
=========================================================

Détecte ce qui mérite l'attention d'un gérant et EXPLIQUE chaque alerte :
    • pourquoi c'est important,
    • l'impact probable par classe d'actifs,
    • ce qu'il faut surveiller ou faire.

Familles d'alertes
    Marchés        mouvements anormaux à la hausse ou à la baisse (en écarts-types),
                   franchissement de la moyenne 200 jours
    Volatilité     pic du VIX, passage de seuils
    Taux           mouvement fort du 10 ans, inversion / ré-pentification de courbe
    Économie       facteurs macro qui bougent vite, changement de régime
    Géopolitique   montée de tension dans l'actualité (conflits, sanctions, droits de
                   douane, instabilité politique, énergie, stress bancaire)
    Portefeuille   ligne en forte baisse, dérive d'allocation, concentration

Gravité : 🔴 Critique · 🟠 Important · 🔵 Info
Outil pédagogique : ne constitue pas un conseil en investissement.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd

from utils import advisor as A

SEVERITY = {"critique": (3, "🔴", "Critique"), "important": (2, "🟠", "Important"),
            "info": (1, "🔵", "Info")}

# Actifs surveillés pour les mouvements de marché
WATCH = {
    "SPY": "Actions US (S&P 500)", "VGK": "Actions Europe", "EEM": "Actions émergentes",
    "TLT": "Obligations US long terme", "HYG": "High yield US", "GLD": "Or",
    "CL=F": "Pétrole WTI", "BTC-USD": "Bitcoin", "DX-Y.NYB": "Dollar US", "EURUSD=X": "EUR/USD",
}
# Impact des actifs sur les classes (pour expliquer les mouvements)
ASSET_READ = {
    "SPY": "Un mouvement de cette ampleur sur le marché actions américain se propage en général aux autres "
           "places et modifie l'appétit pour le risque de l'ensemble des investisseurs.",
    "VGK": "Les actions européennes sont sensibles à l'énergie, à la géopolitique et à la BCE.",
    "EEM": "Les émergents réagissent fortement au dollar, aux matières premières et au sentiment mondial.",
    "TLT": "Les obligations longues reflètent les anticipations d'inflation et de politique monétaire ; "
           "elles jouent le rôle d'amortisseur en cas de crise.",
    "HYG": "Le high yield est un baromètre du risque de crédit : sa baisse précède souvent un stress de marché.",
    "GLD": "L'or monte typiquement sur la peur, la baisse des taux réels ou la faiblesse du dollar.",
    "CL=F": "Le pétrole pèse sur l'inflation, les marges des entreprises et les pays importateurs (Europe).",
    "BTC-USD": "Le bitcoin est un indicateur avancé de la liquidité et de l'appétit pour le risque spéculatif.",
    "DX-Y.NYB": "Un dollar fort durcit les conditions financières mondiales et pèse sur émergents et matières premières.",
    "EURUSD=X": "L'euro/dollar influence la compétitivité européenne et la valeur en euros des actifs américains.",
}

THEME_READ = {
    "conflits": ("Une escalade militaire augmente la prime de risque, soutient l'or, le dollar et le pétrole, "
                 "et pèse sur les actions, surtout européennes et émergentes."),
    "sanctions": ("De nouvelles sanctions perturbent le commerce, l'énergie et les paiements internationaux ; "
                  "elles exposent aussi les établissements financiers à un risque de conformité."),
    "commerce": ("Les droits de douane renchérissent les importations (inflation) et freinent la croissance "
                 "mondiale ; les exportateurs et les émergents sont les plus touchés."),
    "politique": ("L'instabilité politique (élections, crises gouvernementales, shutdown) accroît la volatilité "
                  "et peut écarter les spreads souverains."),
    "banques_c": ("Les décisions et discours des banques centrales déplacent les taux, le dollar et la "
                  "valorisation de tous les actifs."),
    "inflation": "Une inflation qui accélère retarde les baisses de taux et pénalise les obligations longues.",
    "recession": ("Les signaux de récession poussent vers les obligations d'État et la qualité, au détriment "
                  "des actions cycliques et du high yield."),
    "croissance": "Des nouvelles de croissance favorisent les actions cycliques et le crédit.",
    "energie": ("Un choc énergétique alimente l'inflation et pèse sur l'Europe, importatrice nette ; "
                "il favorise les matières premières."),
    "banques": ("Un stress bancaire ou de dette peut se propager rapidement (contagion) : surveiller les "
                "spreads de crédit et la liquidité."),
    "desescalade": ("Une désescalade réduit la prime de risque : favorable aux actions, défavorable à l'or "
                    "et au pétrole."),
}



def _legal_footer() -> str:
    from utils.legal import html_footer
    return html_footer()

def _alert(rule, key, severity, category, direction, title, why, impact, watch, value=None):
    day = datetime.now().strftime("%Y-%m-%d")
    aid = hashlib.md5(f"{rule}|{key}|{day}".encode()).hexdigest()[:16]
    rank, ico, label = SEVERITY[severity]
    return dict(id=aid, date=datetime.now().isoformat(timespec="seconds"), regle=rule, cle=key,
                gravite=severity, rang=rank, icone=ico, gravite_label=label, categorie=category,
                sens=direction, titre=title, pourquoi=why, impact=impact, a_surveiller=watch,
                valeur=value)


def _impact_from_factor(k: str, sign: float) -> str:
    s = (A.SENSITIVITY[k] * sign).sort_values()
    up = ", ".join(s.index[-3:][::-1])
    down = ", ".join(s.index[:3])
    return f"Classes plutôt favorisées : {up}. Classes plutôt pénalisées : {down}."


# ══════════════════════════════════════════════════════════════════════════════
# Règles
# ══════════════════════════════════════════════════════════════════════════════
def market_alerts(px: pd.DataFrame, missing: list) -> list:
    out = []
    for t, name in WATCH.items():
        if t not in px.columns or t in missing:
            continue
        s = px[t].dropna()
        if len(s) < 260:
            continue
        r = np.log(s).diff().dropna()
        sd = r.tail(252).std()
        if not sd or not np.isfinite(sd):
            continue
        r1, r5 = float(r.iloc[-1]), float(r.tail(5).sum())
        z1, z5 = r1 / sd, r5 / (sd * np.sqrt(5))
        for horizon, ret, z in (("séance", r1, z1), ("semaine", r5, z5)):
            if abs(z) < 2.0:
                continue
            sev = "critique" if abs(z) >= 3.5 else ("important" if abs(z) >= 2.5 else "info")
            up = ret > 0
            pct = np.expm1(ret)
            out.append(_alert(
                "mouvement", f"{t}-{horizon}", sev, "Marchés", "hausse" if up else "baisse",
                f"{name} : {pct:+.1%} sur la {horizon} ({abs(z):.1f} écarts-types)",
                f"Mouvement {'haussier' if up else 'baissier'} inhabituel : {abs(z):.1f} fois la variation "
                f"normale de cet actif. {ASSET_READ.get(t, '')}",
                "À relier au contexte : un mouvement isolé peut se résorber, plusieurs mouvements dans le même "
                "sens sur des actifs différents signalent un changement de régime.",
                "Vérifier si le mouvement se confirme sur 2–3 séances et s'il est accompagné par le VIX et les "
                "spreads de crédit avant d'ajuster.", round(pct, 4)))
        # Franchissement de la moyenne 200 jours sur la dernière semaine
        if len(s) > 210 and t in ("SPY", "VGK", "EEM", "GLD", "BTC-USD", "TLT"):
            ma = s.rolling(200).mean()
            above_now, above_before = s.iloc[-1] > ma.iloc[-1], s.iloc[-6] > ma.iloc[-6]
            if above_now != above_before:
                out.append(_alert(
                    "ma200", t, "important", "Marchés", "hausse" if above_now else "baisse",
                    f"{name} {'repasse au-dessus' if above_now else 'casse'} sa moyenne 200 jours",
                    "La moyenne 200 jours sépare conventionnellement tendance haussière et baissière ; de "
                    "nombreux gérants et algorithmes ajustent leur exposition à ce signal.",
                    "Changement de tendance de fond possible sur cette classe d'actifs.",
                    "Confirmation si le prix reste du même côté pendant plusieurs semaines ; "
                    + ("envisager de réduire la sous-pondération." if above_now else
                       "envisager de réduire l'exposition ou de couvrir.")))
    return out


def volatility_alerts(px: pd.DataFrame, missing: list) -> list:
    out = []
    if "^VIX" not in px.columns or "^VIX" in missing:
        return out
    v = px["^VIX"].dropna()
    if len(v) < 10:
        return out
    now, wk = float(v.iloc[-1]), float(v.iloc[-6])
    chg = now / wk - 1 if wk else 0
    if now >= 30:
        sev = "critique"
    elif now >= 25 or chg >= 0.35:
        sev = "important"
    elif chg <= -0.25 and wk >= 22:
        sev = "info"
    else:
        return out
    up = chg >= 0
    out.append(_alert(
        "vix", "niveau", sev, "Volatilité", "hausse" if up else "baisse",
        f"VIX à {now:.1f} ({chg:+.0%} sur une semaine)",
        ("Le VIX mesure la peur des investisseurs sur les actions américaines. Au-dessus de 25, le marché "
         "entre en zone de stress ; au-dessus de 30, les ventes forcées et la baisse de liquidité deviennent "
         "fréquentes." if up else
         "La volatilité reflue après un épisode de tension : le marché retrouve son appétit pour le risque."),
        _impact_from_factor("stress", 1 if up else -1),
        ("Prioriser la réduction de risque (lignes concentrées, crypto, high yield), garder des liquidités, "
         "éviter de vendre dans la panique les positions de qualité." if up else
         "Fenêtre pour réinvestir progressivement les liquidités excédentaires."), round(now, 2)))
    return out


def rates_alerts(px: pd.DataFrame, missing: list) -> list:
    out = []
    if "^TNX" in px.columns and "^TNX" not in missing:
        t = px["^TNX"].dropna()
        if len(t) > 6:
            d = float(t.iloc[-1] - t.iloc[-6])
            if abs(d) >= 0.20:
                up = d > 0
                out.append(_alert(
                    "taux10", "5j", "important" if abs(d) >= 0.30 else "info", "Taux", "hausse" if up else "baisse",
                    f"Taux 10 ans US {'en hausse' if up else 'en baisse'} de {abs(d) * 100:.0f} pb en une semaine "
                    f"({t.iloc[-1]:.2f} %)",
                    ("Une hausse rapide des taux longs renchérit le financement et fait baisser la valeur des "
                     "obligations et des actions de croissance." if up else
                     "Une baisse rapide des taux longs traduit souvent une fuite vers la qualité ou des "
                     "anticipations de baisse des taux directeurs."),
                    "Obligations longues " + ("pénalisées" if up else "favorisées") + " ; actions de croissance "
                    + ("sous pression." if up else "soutenues."),
                    "Surveiller la cause : inflation (mauvaise nouvelle) ou croissance forte (moins inquiétant).",
                    round(d, 3)))
    if all(x in px.columns and x not in missing for x in ("^TNX", "^IRX")):
        curve = (px["^TNX"] - px["^IRX"]).dropna()
        if len(curve) > 6 and np.sign(curve.iloc[-1]) != np.sign(curve.iloc[-6]):
            inv = curve.iloc[-1] < 0
            out.append(_alert(
                "courbe", "signe", "important", "Taux", "baisse" if inv else "hausse",
                f"Courbe des taux 10 ans – 3 mois {'inversée' if inv else 'ré-pentifiée'} ({curve.iloc[-1]:+.2f} pt)",
                ("Une courbe inversée a précédé la plupart des récessions américaines récentes : le marché "
                 "anticipe des baisses de taux futures." if inv else
                 "La ré-pentification après une inversion intervient souvent en fin de cycle, quand la banque "
                 "centrale commence à baisser ses taux."),
                _impact_from_factor("croissance", -1 if inv else 1),
                "Croiser avec l'emploi et les indicateurs avancés avant de modifier fortement l'allocation.",
                round(float(curve.iloc[-1]), 3)))
    return out


def macro_alerts(macro, hist: pd.DataFrame) -> list:
    out = []
    if hist is None or hist.empty or "Il y a 1 semaine" not in hist.columns:
        return out
    if "Il y a 1 mois" in hist.columns and hist.loc["Régime", "Il y a 1 mois"] != macro.regime:
        out.append(_alert(
            "regime", macro.regime, "critique", "Économie", "—",
            f"Changement de régime : {hist.loc['Régime', 'Il y a 1 mois']} → {macro.regime}",
            f"Le régime économique conditionne les classes d'actifs gagnantes. {macro.regime_text}",
            "L'allocation cible du gérant change : voir l'onglet Allocation et la revue de portefeuille.",
            "Lancer une revue de portefeuille et comparer l'allocation actuelle à la nouvelle cible."))
    for k in A.F_KEYS:
        a, b = float(hist.loc[k, "Il y a 1 semaine"]), float(macro.factors[k])
        d = b - a
        if abs(d) < 0.5:
            continue
        label = A.FACTORS[k][0]
        cat = "Géopolitique" if k == "geopolitique" else ("Finance" if k in ("credit", "stress", "dollar")
                                                           else "Économie")
        out.append(_alert(
            "facteur", k, "important" if abs(d) >= 0.8 else "info", cat, "hausse" if d > 0 else "baisse",
            f"{label} : {a:+.1f} → {b:+.1f} en une semaine",
            f"Ce facteur a bougé nettement ({A.FACTORS[k][1]}). Éléments : " + " ; ".join(macro.evidence[k][:2]) + ".",
            _impact_from_factor(k, np.sign(d)),
            "Si le mouvement se confirme la semaine prochaine, il justifie un ajustement tactique."))
    return out


def news_alerts(news: dict, news_sim: bool, prev: dict | None = None) -> list:
    out = []
    if news_sim:
        return out
    prev = prev or {}
    for k, th in news.items():
        lvl = th["intensity"]
        jump = lvl - prev.get(k, lvl)
        if lvl >= 85:
            sev = "critique"
        elif lvl >= 70 or jump >= 25:
            sev = "important"
        else:
            continue
        heads = [h["title"] for h in th["headlines"][:3]]
        cat = "Géopolitique" if th["factor"] == "geopolitique" else (
            "Finance" if th["factor"] in ("credit", "monetaire") else "Économie")
        out.append(_alert(
            "actualite", k, sev, cat, "hausse",
            f"{th['label']} : intensité {lvl:.0f}/100" + (f" (+{jump:.0f} depuis le dernier relevé)" if jump >= 10 else ""),
            THEME_READ.get(k, "") + (" Titres récents : « " + " » ; « ".join(heads) + " »." if heads else ""),
            _impact_from_factor(th["factor"], -1 if k == "desescalade" else 1),
            "Distinguer le bruit médiatique d'un vrai changement : surveiller la réaction du pétrole, de l'or, "
            "du dollar et du VIX.", round(lvl, 1)))
    return out


def portfolio_alerts(name: str, lines: pd.DataFrame, target: pd.Series, band: float = 0.05) -> list:
    out = []
    if lines is None or lines.empty:
        return out
    for t, r in lines.iterrows():
        p1 = r.get("Perf. 1 mois")
        if r["Classe"] != "Liquidités" and p1 is not None and np.isfinite(p1) and abs(p1) >= 0.12:
            up = p1 > 0
            out.append(_alert(
                "ligne", f"{name}-{t}", "important" if abs(p1) >= 0.2 else "info", "Portefeuille",
                "hausse" if up else "baisse",
                f"{name} · {t} : {p1:+.0%} sur un mois",
                (f"Forte hausse : la ligne pèse désormais {r['Poids']:.0%} du portefeuille et "
                 f"{r['Contribution au risque']:.0%} de son risque." if up else
                 f"Forte baisse : {r['Motif']}."),
                "Risque de concentration accru." if up else "Perte de valeur et tendance dégradée.",
                ("Envisager une prise de bénéfices partielle pour revenir au poids cible." if up else
                 "Réexaminer la thèse d'investissement : conserver si elle tient, sinon alléger.")))
        if r["Classe"] != "Liquidités" and r["Poids"] > 0.25:
            out.append(_alert(
                "concentration", f"{name}-{t}", "important", "Portefeuille", "hausse",
                f"{name} · {t} représente {r['Poids']:.0%} du portefeuille",
                "Au-delà de 20–25 %, une seule ligne peut faire perdre une part importante du capital sur une "
                "mauvaise nouvelle spécifique.", "Risque idiosyncratique élevé.",
                "Ramener progressivement la ligne vers 15 % maximum."))
    cw = lines.groupby("Classe")["Poids"].sum().reindex(A.CLASSES).fillna(0)
    drift = (cw - target.reindex(A.CLASSES).fillna(0))
    for c, d in drift.items():
        if abs(d) >= band:
            out.append(_alert(
                "derive", f"{name}-{c}", "info", "Portefeuille", "hausse" if d > 0 else "baisse",
                f"{name} · {c} {'au-dessus' if d > 0 else 'en dessous'} de la cible de {abs(d):.0%}",
                "L'allocation s'est écartée de la cible du gérant (mouvements de marché ou changement de contexte).",
                "Le profil de risque réel ne correspond plus au profil choisi.",
                "Voir le plan d'ajustement dans la revue de portefeuille."))
    return out


def compute_alerts(px, missing, news, news_sim, macro, hist, prev_news=None,
                   portfolios: list | None = None) -> list:
    """portfolios = [(nom, lignes analysées, cible)]"""
    al = (volatility_alerts(px, missing) + rates_alerts(px, missing) + market_alerts(px, missing)
          + macro_alerts(macro, hist) + news_alerts(news, news_sim, prev_news))
    for name, lines, target in portfolios or []:
        al += portfolio_alerts(name, lines, target)
    seen, uniq = set(), []
    for a in sorted(al, key=lambda a: -a["rang"]):
        if a["id"] not in seen:
            seen.add(a["id"])
            uniq.append(a)
    return uniq


# ══════════════════════════════════════════════════════════════════════════════
# Stockage (Supabase) : historique des alertes, état, abonnements au rapport
# ══════════════════════════════════════════════════════════════════════════════
_READY = False


def _ensure(conn):
    global _READY
    if _READY:
        return
    with conn.cursor() as cur:
        cur.execute("""CREATE TABLE IF NOT EXISTS hedge_fund_alerts (
            id TEXT PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            severity TEXT, category TEXT, notified BOOLEAN DEFAULT FALSE, payload JSONB NOT NULL)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS hedge_fund_state (
            key TEXT PRIMARY KEY, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), value JSONB)""")
        cur.execute("""CREATE TABLE IF NOT EXISTS hedge_fund_subscriptions (
            id BIGSERIAL PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            user_key TEXT NOT NULL, email TEXT, portfolio_name TEXT NOT NULL, profile TEXT,
            holdings JSONB NOT NULL, weekly BOOLEAN DEFAULT TRUE, alerts BOOLEAN DEFAULT TRUE,
            min_severity TEXT DEFAULT 'important', active BOOLEAN DEFAULT TRUE,
            UNIQUE (user_key, portfolio_name))""")
    conn.commit()
    _READY = True


def _with_db(fn, default=None):
    conn = None
    try:
        conn = A._connect()
        if conn is None:
            return default
        _ensure(conn)
        return fn(conn)
    except Exception:
        return default
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def save_alerts(alerts: list) -> list:
    """Enregistre les nouvelles alertes. Renvoie celles qui n'existaient pas encore."""
    def run(conn):
        new = []
        with conn.cursor() as cur:
            for a in alerts:
                cur.execute("INSERT INTO hedge_fund_alerts (id, severity, category, payload) "
                            "VALUES (%s, %s, %s, %s::jsonb) ON CONFLICT (id) DO NOTHING RETURNING id",
                            (a["id"], a["gravite"], a["categorie"], json.dumps(a, ensure_ascii=False, default=str)))
                if cur.fetchone():
                    new.append(a)
        conn.commit()
        return new
    return _with_db(run, default=alerts)


def mark_notified(ids: list):
    def run(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE hedge_fund_alerts SET notified = TRUE WHERE id = ANY(%s)", (list(ids),))
        conn.commit()
    _with_db(run)


def alert_history(days: int = 30, limit: int = 300) -> list:
    def run(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT payload FROM hedge_fund_alerts WHERE created_at > NOW() - (%s || ' days')::interval "
                        "ORDER BY created_at DESC LIMIT %s", (str(days), limit))
            return [p if isinstance(p, dict) else json.loads(p) for (p,) in cur.fetchall()]
    return _with_db(run, default=[])


def get_state(key: str):
    def run(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM hedge_fund_state WHERE key = %s", (key,))
            row = cur.fetchone()
            return (row[0] if isinstance(row[0], (dict, list)) else json.loads(row[0])) if row else None
    return _with_db(run)


def set_state(key: str, value):
    def run(conn):
        with conn.cursor() as cur:
            cur.execute("INSERT INTO hedge_fund_state (key, value) VALUES (%s, %s::jsonb) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()",
                        (key, json.dumps(value, ensure_ascii=False, default=str)))
        conn.commit()
        return True
    return _with_db(run, default=False)


def subscribe(user_key: str, email: str, name: str, profile: str, holdings: dict,
              weekly: bool = True, alerts: bool = True, min_severity: str = "important") -> bool:
    def run(conn):
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO hedge_fund_subscriptions
                (user_key, email, portfolio_name, profile, holdings, weekly, alerts, min_severity, active)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s, TRUE)
                ON CONFLICT (user_key, portfolio_name) DO UPDATE SET email = EXCLUDED.email,
                  profile = EXCLUDED.profile, holdings = EXCLUDED.holdings, weekly = EXCLUDED.weekly,
                  alerts = EXCLUDED.alerts, min_severity = EXCLUDED.min_severity, active = TRUE""",
                        (user_key, email, name, profile, json.dumps(holdings), weekly, alerts, min_severity))
        conn.commit()
        return True
    return _with_db(run, default=False)


def unsubscribe(user_key: str, name: str) -> bool:
    def run(conn):
        with conn.cursor() as cur:
            cur.execute("UPDATE hedge_fund_subscriptions SET active = FALSE "
                        "WHERE user_key = %s AND portfolio_name = %s", (user_key, name))
        conn.commit()
        return True
    return _with_db(run, default=False)


def subscriptions(user_key: str | None = None) -> list:
    def run(conn):
        with conn.cursor() as cur:
            q = ("SELECT user_key, email, portfolio_name, profile, holdings, weekly, alerts, min_severity "
                 "FROM hedge_fund_subscriptions WHERE active")
            args = ()
            if user_key:
                q += " AND user_key = %s"
                args = (user_key,)
            cur.execute(q + " ORDER BY id", args)
            cols = ["user_key", "email", "portfolio_name", "profile", "holdings", "weekly", "alerts", "min_severity"]
            out = []
            for row in cur.fetchall():
                d = dict(zip(cols, row))
                if isinstance(d["holdings"], str):
                    d["holdings"] = json.loads(d["holdings"])
                out.append(d)
            return out
    return _with_db(run, default=[])


# ══════════════════════════════════════════════════════════════════════════════
# Envoi : email (SMTP) et Telegram (optionnel)
# ══════════════════════════════════════════════════════════════════════════════
def _cfg(section: str, key: str, env: str, default=None):
    v = os.environ.get(env)
    if v:
        return v
    try:
        import streamlit as st
        return st.secrets[section].get(key, default)
    except Exception:
        return default


def _clean(v):
    """Nettoie une valeur de secret : espaces, guillemets copiés par erreur, retours à la ligne."""
    if v is None:
        return None
    return str(v).strip().strip('"').strip("'").strip()


def smtp_config() -> dict | None:
    host = _clean(_cfg("email", "smtp_host", "SMTP_HOST"))
    user = _clean(_cfg("email", "smtp_user", "SMTP_USER"))
    pwd = _clean(_cfg("email", "smtp_password", "SMTP_PASSWORD"))
    sec = (_clean(_cfg("email", "security", "SMTP_SECURITY", "starttls")) or "starttls").lower()
    try:
        port = int(_clean(_cfg("email", "smtp_port", "SMTP_PORT", 587)) or 587)
    except ValueError:
        port = 587
    if host and "gmail" in host.lower() and pwd:
        pwd = pwd.replace(" ", "")          # mot de passe d'application Gmail : espaces à retirer
    c = dict(host=host, port=port, user=user, password=pwd, security=sec)
    return c if c["host"] and c["user"] and c["password"] else None


def _smtp_attempts(cfg: dict) -> list:
    """Méthodes à essayer, dans l'ordre : la configuration déclarée, puis les deux
    méthodes standard (STARTTLS sur 587, SSL sur 465)."""
    first = ("ssl" if cfg["security"] == "ssl" or cfg["port"] == 465 else
             "none" if cfg["security"] == "none" else "starttls", cfg["port"])
    tries = [first, ("starttls", 587), ("ssl", 465)]
    out = []
    for t in tries:
        if t not in out:
            out.append(t)
    return out


def send_email(to: str, subject: str, html_body: str, attachments: list | None = None) -> str | None:
    """attachments = [(nom_fichier, bytes, 'image/png')]. Renvoie None si OK, sinon l'erreur."""
    import smtplib
    import ssl
    from email.message import EmailMessage
    cfg = smtp_config()
    if not cfg:
        return "SMTP non configuré"
    to = _clean(to)
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = subject, f"MAM Hedge Fund Agent <{cfg['user']}>", to
    msg.set_content("Ce message est au format HTML.")
    msg.add_alternative(html_body, subtype="html")
    for fname, data, mime in attachments or []:
        maintype, subtype = mime.split("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=fname)

    errors = []
    for mode, port in _smtp_attempts(cfg):
        stage = "connexion"
        try:
            ctx = ssl.create_default_context()
            if mode == "ssl":
                with smtplib.SMTP_SSL(cfg["host"], port, context=ctx, timeout=40) as s:
                    stage = "présentation (EHLO)"
                    s.ehlo()
                    stage = "authentification (login)"
                    s.login(cfg["user"], cfg["password"])
                    stage = "envoi du message"
                    s.send_message(msg)
            else:
                with smtplib.SMTP(cfg["host"], port, timeout=40) as s:
                    stage = "présentation (EHLO)"
                    s.ehlo()
                    if mode == "starttls":
                        stage = "chiffrement (STARTTLS)"
                        s.starttls(context=ctx)
                        s.ehlo()
                    if s.has_extn("auth"):
                        stage = "authentification (login)"
                        s.login(cfg["user"], cfg["password"])
                    stage = "envoi du message"
                    s.send_message(msg)
            return None
        except smtplib.SMTPAuthenticationError as e:
            # identifiants refusés : inutile d'essayer un autre port
            return ("Identifiants refusés par le serveur (SMTP_USER / SMTP_PASSWORD). Pour Gmail, il faut un "
                    f"mot de passe d'application de 16 lettres. Détail : {e.smtp_code} {e.smtp_error!r}")
        except Exception as e:
            label = "STARTTLS-587" if (mode, port) == ("starttls", 587) else f"{mode.upper()}-{port}"
            errors.append(f"[{label}] coupé à l'étape « {stage} » → {e.__class__.__name__}: {e}")
    return " | ".join(errors)


def smtp_diagnostic() -> list:
    """Vérifications des réglages SMTP SANS afficher les valeurs secrètes."""
    host = _clean(_cfg("email", "smtp_host", "SMTP_HOST"))
    user = _clean(_cfg("email", "smtp_user", "SMTP_USER"))
    pwd = _clean(_cfg("email", "smtp_password", "SMTP_PASSWORD"))
    sec = _clean(_cfg("email", "security", "SMTP_SECURITY", "starttls"))
    port = _clean(_cfg("email", "smtp_port", "SMTP_PORT", 587))
    to = _clean(os.environ.get("REPORT_TO"))
    raw_pwd = _cfg("email", "smtp_password", "SMTP_PASSWORD") or ""
    p = (pwd or "").replace(" ", "")
    ok = lambda b: "OK " if b else "PROBLÈME"
    out = [
        f"{ok(bool(host))} SMTP_HOST renseigné",
        f"{ok((host or '').lower() == 'smtp.gmail.com')} SMTP_HOST vaut exactement « smtp.gmail.com » "
        f"(longueur lue : {len(host or '')} caractères, attendu 14)",
        f"{ok(str(port) in ('587', '465'))} SMTP_PORT vaut 587 ou 465",
        f"{ok((sec or '').lower() in ('starttls', 'ssl'))} SMTP_SECURITY vaut starttls ou ssl",
        f"{ok('@' in (user or ''))} SMTP_USER contient un @",
        f"{ok((user or '').lower().endswith(('@gmail.com', '@googlemail.com')))} SMTP_USER est une adresse Gmail",
        f"{ok(user == (user or '').strip())} SMTP_USER sans espace parasite",
        f"{ok(len(p) == 16)} SMTP_PASSWORD fait 16 caractères hors espaces (lu : {len(p)})",
        f"{ok(p.isalpha() and p.islower())} SMTP_PASSWORD ne contient que des lettres minuscules",
        f"{ok(raw_pwd == raw_pwd.strip())} SMTP_PASSWORD sans espace ni retour à la ligne au début/à la fin",
        f"{ok(bool(to) and '@' in (to or ''))} REPORT_TO contient une adresse email",
    ]
    return out


def send_telegram(text: str, png: bytes | None = None) -> str | None:
    import requests
    token = _cfg("telegram", "bot_token", "TELEGRAM_BOT_TOKEN")
    chat = _cfg("telegram", "chat_id", "TELEGRAM_CHAT_ID")
    if not token or not chat:
        return "Telegram non configuré"
    try:
        if png:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendPhoto", timeout=30,
                              data={"chat_id": chat, "caption": text[:1000]},
                              files={"photo": ("rapport.png", png, "image/png")})
        else:
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=30,
                              data={"chat_id": chat, "text": text[:4000]})
        r.raise_for_status()
        return None
    except Exception as e:
        return f"{e.__class__.__name__}: {e}"


def alerts_email_html(alerts: list, title: str) -> str:
    colors = {"critique": "#ff3b6b", "important": "#f59e0b", "info": "#38bdf8"}
    rows = []
    for a in alerts:
        c = colors[a["gravite"]]
        rows.append(f"""
        <div style="border-left:4px solid {c};background:#0d1626;padding:12px 14px;margin:10px 0;border-radius:4px">
          <div style="font-size:12px;color:{c};font-weight:700">{a['icone']} {a['gravite_label'].upper()} · {a['categorie']}</div>
          <div style="font-size:15px;color:#e2e8f0;font-weight:700;margin:4px 0">{a['titre']}</div>
          <div style="font-size:13px;color:#cbd5e1"><b>Pourquoi c'est important :</b> {a['pourquoi']}</div>
          <div style="font-size:13px;color:#cbd5e1;margin-top:4px"><b>Impact probable :</b> {a['impact']}</div>
          <div style="font-size:13px;color:#cbd5e1;margin-top:4px"><b>À surveiller / faire :</b> {a['a_surveiller']}</div>
        </div>""")
    return f"""<html><body style="background:#080e1a;font-family:Arial,sans-serif;padding:18px">
      <div style="max-width:720px;margin:auto">
        <div style="color:#00d4ff;font-size:20px;font-weight:700">McKenson Asset Management</div>
        <div style="color:#e2e8f0;font-size:16px;margin:4px 0 12px">{title}</div>
        {''.join(rows)}
        <p style="color:#64748b;font-size:11px;margin-top:18px">Outil pédagogique d'aide à la décision sur une
        plateforme de simulation : ne constitue pas un conseil en investissement.</p>
        {_legal_footer()}
      </div></body></html>"""
