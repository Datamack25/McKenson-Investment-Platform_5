"""
jobs/weekly_report.py — Rapport hebdomadaire PNG + alertes, exécuté par GitHub Actions

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

    log("Chargement des marchés et de l'actualité…")
    ctx = load_context()
    px, missing, news, news_sim, macro, cov, data_sim = ctx
    log(f"Régime : {macro.regime} · données simulées : {data_sim} · actualités simulées : {news_sim}")
    hist = PM.factor_history(px, news)
    prev_news = AL.get_state("news_intensity") or {}

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
            recipients.setdefault(s["email"], {})
            for a in mine:
                recipients[s["email"]][a["id"]] = a
        if not subs and os.environ.get("REPORT_TO"):
            recipients[os.environ["REPORT_TO"]] = {a["id"]: a for a in new_alerts if a["rang"] >= 2}
        sent_ids = set()
        for email, amap in recipients.items():
            if not amap:
                continue
            al = sorted(amap.values(), key=lambda a: -a["rang"])
            n_crit = sum(a["gravite"] == "critique" for a in al)
            subject = (f"🔴 {n_crit} alerte(s) critique(s) — MAM" if n_crit else f"🟠 {len(al)} alerte(s) — MAM")
            err = AL.send_email(email, subject, AL.alerts_email_html(al, "Alertes marchés et portefeuille"))
            log(f"Alertes → {email} : {'OK' if not err else err}")
            if not err:
                sent_ids |= set(amap)
        if new_alerts:
            txt = "\n\n".join(f"{a['icone']} {a['titre']}\n{a['pourquoi'][:280]}" for a in new_alerts[:5] if a["rang"] >= 2)
            if txt:
                err = AL.send_telegram("Alertes MAM\n\n" + txt)
                log(f"Telegram : {'OK' if not err else err}")
        if sent_ids:
            AL.mark_notified(list(sent_ids))

    # ── Rapport hebdomadaire PNG ──────────────────────────────────────────────
    if weekly:
        jobs = []
        for s in subs:
            if s["weekly"] and s["email"]:
                R = reviews.get((s["user_key"], s["portfolio_name"]))
                jobs.append((s["email"], s["portfolio_name"], s["profile"] or "Équilibré", R))
        if not jobs:
            jobs.append((os.environ.get("REPORT_TO"), "Desk MAM", "Équilibré", None))
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
            err = AL.send_telegram(f"Rapport hebdomadaire MAM — {name} — régime : {macro.regime}", png)
            if err != "Telegram non configuré":
                log(f"Telegram : {'OK' if not err else err}")


if __name__ == "__main__":
    main()
