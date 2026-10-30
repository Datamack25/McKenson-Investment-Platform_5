"""
jobs/weekly_report.py — Rapport hebdomadaire du COMITÉ (PNG + PDF) + alertes, exécuté par GitHub Actions

Pour chaque portefeuille suivi, le comité virtuel (Jean-Michel TAUX-BAS, Mc Henson ALGO-RITHME, Thierry BALANCEMENT,
Aline DE MARGE, Constance Probité, Marc ETING-FINANCIER) examine le portefeuille RÉEL (base MAM :
lignes, liquidités, options, politique d'investissement) et envoie son rapport : graphique vs marché,
avis de chaque professionnel, synthèse et recommandations, décisions à prendre.

    python -m jobs.weekly_report --mode auto      # alertes chaque jour, rapport le lundi
    python -m jobs.weekly_report --mode weekly    # force le rapport hebdomadaire
    python -m jobs.weekly_report --mode alerts    # alertes uniquement
    python -m jobs.weekly_report --mode weekly --dry-run   # génère les PNG sans rien envoyer

Configuration par variables d'environnement (secrets GitHub) :
    DATABASE_URL                       base Supabase (mêmes portefeuilles suivis que dans l'app)
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_SECURITY
    REPORT_TO                          destinataire par défaut (rapport du desk si aucun abonnement)
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   (optionnel)
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import advisor as A  # noqa: E402
from utils import alerts as AL  # noqa: E402
from utils import portfolio_manager as PM  # noqa: E402
from utils.report_png import build_weekly_png  # noqa: E402
from utils import committee_report as CR  # noqa: E402

FAILURES = []
SEV_MIN = {"critique": 3, "important": 2, "info": 1}


def log(*a):
    print(datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def load_context():
    px, missing = A.load_prices()
    news, news_sim = A.load_news()
    macro = A.compute_macro(px, news)
    cov = A.class_covariance(px)
    critical = {"SPY", "^VIX", "^TNX", "^IRX"}
    data_sim = len(missing) >= len(A.ALL_TICKERS) * 0.6 or bool(critical & set(missing))
    return (px, missing, news, news_sim, macro, cov, data_sim)


def load_mam_portfolio(user_key: str, name: str) -> tuple[dict | None, bool]:
    """Portefeuille MAM du propriétaire (e-mail ou identifiant) + test options validé ?"""
    import json
    conn = None
    try:
        conn = A._connect()
        if conn is None:
            return None, False
        with conn.cursor() as cur:
            cur.execute("""SELECT p.id, p.name, p.emoji, p.strategy, p.cash, p.initial_cash, p.holdings, p.options,
                                  p.trades, p.ips, u.investor_profile
                           FROM mam_portfolios p JOIN mam_users u ON u.id = p.user_id
                           WHERE p.name = %s AND (u.email = %s OR u.username = %s)
                           ORDER BY p.updated_at DESC LIMIT 1""", (name, user_key, user_key))
            row = cur.fetchone()
        if not row:
            return None, False
        dec = lambda v, d: (json.loads(v) if isinstance(v, str) else v) if v is not None else d
        port = dict(id=row[0], name=row[1], emoji=row[2], strategy=row[3], cash=float(row[4] or 0),
                    initial_cash=float(row[5] or 0), holdings=dec(row[6], {}), options=dec(row[7], []),
                    trades=dec(row[8], []), ips=dec(row[9], None))
        prof = dec(row[10], {}) or {}
        return port, bool(prof.get("options_ok"))
    except Exception as e:
        log(f"Lecture du portefeuille {name} impossible : {e}")
        return None, False
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def committee_job(email: str, user_key: str, name: str, profile: str, holdings_snapshot: dict,
                  committee_ctx: dict, out_dir: Path, dry_run: bool):
    """Rapport du comité pour un portefeuille suivi."""
    from utils.data import get_multi_prices
    port, options_ok = load_mam_portfolio(user_key, name)
    if port is None:  # repli : copie des lignes enregistrée lors de l'abonnement ({ticker: valeur $})
        snap = dict(holdings_snapshot or {})
        cash = float(snap.pop("CASH", 0.0))
        port = dict(id=None, name=name, cash=cash, initial_cash=cash + sum(snap.values()),
                    holdings={t: {"qty": float(v), "avg_price": 1.0} for t, v in snap.items()},
                    options=[], trades=[], ips=None)
        live = {}
        log(f"{name} : portefeuille MAM introuvable, copie de l'abonnement utilisée")
    else:
        live = get_multi_prices(tuple(sorted(port["holdings"]))) if port["holdings"] else {}
    out = CR.build_for_portfolio(port, committee_ctx, live, options_ok, "S&P 500", profile or "Équilibré")
    stem = f"comite_{name.replace(' ', '_')}_{datetime.now():%Y%m%d}"
    (out_dir / f"{stem}.png").write_bytes(out["png"])
    (out_dir / f"{stem}.pdf").write_bytes(out["pdf"])
    log(f"Rapport du comité généré : {stem} — verdict {out['review']['verdict']}")
    if dry_run or not email:
        return
    err = AL.send_email(email, f"🧑‍⚖️ Rapport hebdomadaire du comité MAM — {name} — {datetime.now():%d/%m/%Y}",
                        out["html"], [(f"{stem}.png", out["png"], "image/png"),
                                      (f"{stem}.pdf", out["pdf"], "application/pdf")])
    log(f"Rapport du comité → {email} : {'OK' if not err else err}")
    if err:
        FAILURES.append(err)
    err = AL.send_telegram(f"Rapport du comité MAM — {name} — {out['review']['verdict_label']}", out["png"])
    if err != "Telegram non configuré":
        log(f"Telegram : {'OK' if not err else err}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["auto", "weekly", "alerts"], default="auto")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default="reports")
    args = ap.parse_args()
    weekly = args.mode == "weekly" or (args.mode == "auto" and datetime.now().weekday() == 0)
    send_alerts = args.mode in ("auto", "alerts")
    out_dir = Path(args.out)
    out_dir.mkdir(exist_ok=True)

    log("Diagnostic des réglages email (les valeurs restent secrètes) :")
    for line in AL.smtp_diagnostic():
        log("   " + line)
    log("Chargement des marchés et de l'actualité…")
    ctx = load_context()
    px, missing, news, news_sim, macro, cov, data_sim = ctx
    log(f"Régime : {macro.regime} · données simulées : {data_sim} · actualités simulées : {news_sim}")
    hist = PM.factor_history(px, news)
    prev_news = AL.get_state("news_intensity") or {}

    # ── Contrôle continu de la qualité des données (v5.4) ────────────────────
    from utils import data_quality as DQ
    dq = DQ.run_checks(px, missing, news, news_sim, A.ALL_TICKERS)
    log(f"Qualité des données : {dq['statut']} — {dq['n_problemes']} remarque(s) sur {dq['n_series']} séries")
    for i in dq["problemes"][:12]:
        log(f"   [{i['gravite']}] {i['serie']} : {i['probleme']} — {i['detail']}")
    if not args.dry_run:
        DQ.save(dq)

    subs = AL.subscriptions()
    log(f"{len(subs)} portefeuille(s) suivi(s)")
    reviews, port_alerts_input = {}, []
    for s in subs:
        try:
            R = PM.full_review(s["portfolio_name"], s["holdings"], s["profile"] or "Équilibré", ctx, [])
            reviews[(s["user_key"], s["portfolio_name"])] = R
            port_alerts_input.append((s["portfolio_name"], R["lines"], R["target"]))
        except Exception as e:
            log(f"Revue impossible pour {s['portfolio_name']} : {e}")

    alerts = AL.compute_alerts(px, missing, news, news_sim, macro, hist, prev_news, port_alerts_input)
    if data_sim:  # pas d'alerte de marché sur données simulées
        alerts = [a for a in alerts if a["regle"] == "actualite"]
    dq_alert = DQ.to_alert(dq)
    if dq_alert:
        alerts.append(dq_alert)
    log(f"{len(alerts)} alerte(s) détectée(s)")
    new_alerts = AL.save_alerts(alerts) if not args.dry_run else alerts
    if not news_sim and not args.dry_run:
        AL.set_state("news_intensity", {k: v["intensity"] for k, v in news.items()})

    # ── Alertes immédiates (critiques / importantes nouvelles) ───────────────
    if send_alerts and new_alerts and not args.dry_run:
        recipients = {}
        for s in subs:
            if not s["alerts"] or not s["email"]:
                continue
            lvl = SEV_MIN.get(s["min_severity"] or "important", 2)
            mine = [a for a in new_alerts if a["rang"] >= lvl and (
                a["categorie"] != "Portefeuille" or a["titre"].startswith(s["portfolio_name"] + " ·"))]
            for addr in AL.parse_recipients(s["email"]):        # v5.10 : plusieurs adresses par abonnement
                recipients.setdefault(addr, {})
                for a in mine:
                    recipients[addr][a["id"]] = a
        if not subs:
            for addr in AL.parse_recipients(os.environ.get("REPORT_TO")):
                recipients[addr] = {a["id"]: a for a in new_alerts if a["rang"] >= 2}
        sent_ids = set()
        for email, amap in recipients.items():
            if not amap:
                continue
            al = sorted(amap.values(), key=lambda a: -a["rang"])
            n_crit = sum(a["gravite"] == "critique" for a in al)
            subject = (f"🔴 {n_crit} alerte(s) critique(s) — MAM" if n_crit else f"🟠 {len(al)} alerte(s) — MAM")
            err = AL.send_email(email, subject, AL.alerts_email_html(al, "Alertes marchés et portefeuille"))
            log(f"Alertes → {email} : {'OK' if not err else err}")
            if err:
                FAILURES.append(err)
            if not err:
                sent_ids |= set(amap)
        if new_alerts:
            txt = "\n\n".join(f"{a['icone']} {a['titre']}\n{a['pourquoi'][:280]}" for a in new_alerts[:5] if a["rang"] >= 2)
            if txt:
                err = AL.send_telegram("Alertes MAM\n\n" + txt)
                log(f"Telegram : {'OK' if not err else err}")
        if sent_ids:
            AL.mark_notified(list(sent_ids))

    # ── Rapport hebdomadaire du comité (un par portefeuille suivi) ───────────
    if weekly:
        committee_ctx = dict(px=px, missing=missing, news=news, news_sim=news_sim, macro=macro, cov=cov,
                             data_sim=data_sim, vix=(macro.indicators or {}).get("vix"))
        followed = [s for s in subs if s["weekly"] and s["email"]]
        for s in followed:
            try:
                committee_job(s["email"], s["user_key"], s["portfolio_name"], s["profile"], s["holdings"],
                              committee_ctx, out_dir, args.dry_run)
            except Exception as e:
                log(f"Rapport du comité impossible pour {s['portfolio_name']} : {e}")
                FAILURES.append(str(e))
        # Aucun portefeuille suivi : rapport macro du desk (comme avant)
        jobs = [] if followed else [(os.environ.get("REPORT_TO"), "Desk MAM", "Équilibré", None)]
        for email, name, profile, R in jobs:
            rel = [a for a in alerts if a["categorie"] != "Portefeuille" or a["titre"].startswith(name + " ·")]
            png = build_weekly_png(macro, news, rel, R, name=name, profile=profile, hist=hist, data_sim=data_sim)
            fname = f"rapport_{name.replace(' ', '_')}_{datetime.now():%Y%m%d}.png"
            (out_dir / fname).write_bytes(png)
            log(f"PNG généré : {fname} ({len(png) // 1024} Ko)")
            if args.dry_run or not email:
                continue
            body = AL.alerts_email_html(rel[:6], f"Rapport hebdomadaire — {name} · régime : {macro.regime}")
            body = body.replace("<div style=\"max-width:720px;margin:auto\">",
                                "<div style=\"max-width:720px;margin:auto\"><p style=\"color:#cbd5e1\">"
                                "Votre rapport hebdomadaire est en pièce jointe (PNG). Principales alertes :</p>", 1)
            err = AL.send_email(email, f"📈 Rapport hebdomadaire MAM — {name} — {datetime.now():%d/%m/%Y}",
                                body, [(fname, png, "image/png")])
            log(f"Rapport → {email} : {'OK' if not err else err}")
            if err:
                FAILURES.append(err)
            err = AL.send_telegram(f"Rapport hebdomadaire MAM — {name} — régime : {macro.regime}", png)
            if err != "Telegram non configuré":
                log(f"Telegram : {'OK' if not err else err}")


if __name__ == "__main__":
    main()
    if FAILURES:
        log(f"ÉCHEC : {len(FAILURES)} envoi(s) n'ont pas abouti (voir ci-dessus).")
        sys.exit(1)
