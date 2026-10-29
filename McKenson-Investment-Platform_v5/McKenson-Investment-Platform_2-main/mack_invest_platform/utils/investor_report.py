# utils/investor_report.py  —  MAM v5.6 · Rapport mensuel destiné à l'investisseur
"""
Le rapport qu'un gérant envoie chaque mois à son client. Il ne suppose pas que le
lecteur connaît la finance :

1. En bref — a-t-il fait mieux ou moins bien que le marché, et à cause de quoi ;
2. Les chiffres du mois, expliqués ;
3. Les décisions du mois — date, ligne, qui a décidé, POURQUOI et quels dangers
   (thèse horodatée écrite avant chaque ordre manuel) ;
4. Ce qui a marché et ce qui n'a pas marché (contribution de chaque ligne) ;
5. Le respect des règles — dépassements autorisés (dérogations), fiches de risques ;
6. L'avis du comité et les risques ;
7. Les prochaines étapes — publications de résultats à venir, décisions à prendre ;
8. Un petit lexique.

Sans interface : PDF (ReportLab), corps d'e-mail HTML et texte.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

from utils import legal as L
from utils import plain_summary as PS

GLOSSARY = [
    ("Indice de référence", "Un panier d'actions qui représente « le marché » (par exemple le S&P 500). Le comparer au "
                            "portefeuille dit si la gestion a apporté quelque chose."),
    ("Point", "1 % de la valeur du portefeuille. Les points de toutes les lignes (frais et intérêts compris) "
              "s'additionnent pour donner la performance."),
    ("Rendement pondéré dans le temps (TWR)", "La façon standard de mesurer la performance d'un gérant : elle ne "
                                              "dépend pas des sommes ajoutées ou retirées par l'investisseur."),
    ("Frais de transaction", "L'écart entre prix d'achat et de vente, le courtage et les taxes de bourse, payés à "
                             "chaque ordre et déduits de la performance."),
    ("Liquidités", "L'argent non investi. Il est rémunéré au taux monétaire et protège en cas de baisse, mais "
                   "rapporte moins que les actions quand le marché monte."),
    ("Perte potentielle (VaR 95 %)", "La perte qu'on ne devrait dépasser qu'une année sur vingt, d'après le "
                                     "comportement passé des marchés. Ce n'est pas une perte maximale garantie."),
    ("Dérogation", "Un dépassement temporaire, justifié par écrit et notifié à l'avance, de la limite de poids "
                   "d'une ligne. Il doit être corrigé à l'échéance."),
    ("Thèse d'investissement", "La raison écrite, avant l'ordre, pour laquelle on achète ou vend, avec les dangers "
                               "identifiés et ce qui ferait changer d'avis."),
]


METHOD_NOTE = (
    "Méthode (norme GIPS) : performance pondérée dans le temps (TWR), valorisation quotidienne aux cours de "
    "clôture convertis en USD au taux de change du jour, rendements quotidiens chaînés géométriquement ; les "
    "apports et retraits de liquidités sont neutralisés. Performance nette des coûts de transaction (écart "
    "achat-vente, courtage, taxes de bourse) ; dividendes nets de retenue à la source non récupérable et intérêts "
    "monétaires (bons du Trésor américain à 13 semaines) inclus ; impôts personnels non déduits. Aucun rendement "
    "n'est annualisé sur une période de moins d'un an. Indice de référence en rendement total (dividendes "
    "réinvestis), en USD. Données Yahoo Finance différées.")


def month_bounds(label: str | None = None, today: date | None = None) -> tuple[date, date, str]:
    """« Mois en cours » ou « AAAA-MM » → (début, fin, libellé)."""
    today = today or date.today()
    if not label or label == "Mois en cours":
        d0 = today.replace(day=1)
        return d0, today, f"mois en cours ({d0:%m/%Y})"
    y, m = (int(x) for x in label.split("-"))
    d0 = date(y, m, 1)
    d1 = (date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1))
    return d0, min(d1, today), f"{_MOIS[m - 1]} {y}"


_MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
         "novembre", "décembre"]


def month_choices(n: int = 6, today: date | None = None) -> list[str]:
    today = today or date.today()
    out, y, m = ["Mois en cours"], today.year, today.month
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y}-{m:02d}")
    return out


def _fmt_money(x: float) -> str:
    return f"{x:,.0f} $".replace(",", " ")


def build(port: dict, period: str | None = None, bench_name: str = "S&P 500", review: dict | None = None,
          earnings: pd.DataFrame | None = None, det: pd.DataFrame | None = None,
          bench: pd.Series | None = None) -> dict:
    """Contenu du rapport (dict) + PDF + HTML. review : revue du comité déjà calculée (facultatif)."""
    from utils.line_risk import decision_journal, sheets_status, manual_orders_without_thesis
    from utils.compliance import derogation_status
    d0, d1, plabel = month_bounds(period)
    name = port.get("name", "Portefeuille")

    # Synthèse et contributions sur la période (repli : depuis l'origine si le portefeuille est plus récent)
    simple = PS.plain_summary(port, bench_name, start=pd.Timestamp(d0), end=pd.Timestamp(d1) + pd.Timedelta(hours=23),
                              det=det, bench=bench)
    lc = None
    try:
        lc = PS.line_contributions(port, pd.Timestamp(d0), pd.Timestamp(d1) + pd.Timedelta(hours=23), det)
    except Exception:
        lc = None
    journal = decision_journal(port, d0.isoformat(), d1.isoformat())
    nav_s = lc.get("nav") if lc and lc.get("ok") else None
    weights = {}
    if lc and lc.get("ok") and not lc["lignes"].empty:
        tot = lc["nav1"] or 1.0
        weights = {r["ligne"]: r["valeur_fin"] / tot for _, r in lc["lignes"].iterrows()}
    ders = [d for d in derogation_status(port, weights)
            if str(d.get("debut", ""))[:10] <= d1.isoformat() and str(d.get("echeance", ""))[:10] >= d0.isoformat()]
    sheets = sheets_status(port)
    no_thesis = manual_orders_without_thesis(port)

    # ── PDF ──
    b: list[tuple] = []
    b += PS.pdf_blocks(simple, "1. En bref — le mois en mots simples")
    b.append(("h", "2. Les chiffres du mois"))
    if lc and lc.get("ok"):
        mdd = float((nav_s / nav_s.cummax() - 1).min()) if nav_s is not None and len(nav_s) > 1 else float("nan")
        b.append(("kpis", [("Valeur au début", _fmt_money(lc["nav0"])), ("Valeur à la fin", _fmt_money(lc["nav1"])),
                           ("Performance du portefeuille", PS.pct(simple.get("perf"), True)),
                           (f"Indice ({bench_name})", PS.pct(simple.get("perf_indice"), True)),
                           ("Écart avec l'indice", PS.pts(simple.get("ecart"))),
                           ("Plus forte baisse dans le mois", PS.pct(mdd, True)),
                           ("Liquidités en moyenne", PS.pct(lc["cash_moyen"], digits=0)),
                           ("Ordres passés", str(len(journal))),
                           ("Dividendes reçus", _fmt_money(lc.get("dividendes", 0.0))),
                           ("Intérêts sur liquidités", _fmt_money(lc.get("interets", 0.0))),
                           ("Frais de transaction", _fmt_money(lc.get("frais", 0.0))),
                           ("Apports − retraits", _fmt_money(lc.get("apports", 0.0)))]))
        b.append(("note", "« Plus forte baisse dans le mois » : la plus grande chute de valeur entre un sommet et un "
                          "creux pendant le mois. Elle mesure ce qu'un investisseur a pu ressentir, même si le mois "
                          "s'est bien terminé."))
        b.append(("note", METHOD_NOTE))
    else:
        b.append(("p", "Historique insuffisant sur ce mois pour calculer la performance (portefeuille créé récemment "
                       "ou sans transaction)."))

    b.append(("h", "3. Les décisions du mois — quand, qui, pourquoi"))
    if journal:
        rows = [["Date", "Ligne", "Sens", "Montant", "Décidé par", "Pourquoi", "Dangers identifiés"]]
        for e in journal:
            th = e.get("these") or {}
            rows.append([str(e["date"])[:16], e["ticker"], "Achat" if e["action"] == "BUY" else "Vente",
                         _fmt_money(e["montant"]), e["source"],
                         th.get("pourquoi") or ("plan automatique contrôlé par le comité" if e["source"] != "Trading Desk"
                                                else "non renseigné (ordre antérieur à la règle)"),
                         th.get("risques") or "—"])
        b.append(("table", rows, [2.3, 1.5, 1.2, 1.9, 2.6, 4.2, 4.1]))
        b.append(("note", "Chaque ordre passé à la main est précédé d'une thèse écrite et horodatée ; les ordres des "
                          "outils automatiques (desk, comité, modèles ETF) sont contrôlés par le comité et la "
                          "conformité avant exécution."))
    else:
        b.append(("p", "Aucun ordre ce mois-ci : le portefeuille a été conservé tel quel."))

    b.append(("h", "4. Ce qui a marché, ce qui n'a pas marché"))
    if lc and lc.get("ok") and not lc["lignes"].empty:
        df = lc["lignes"].sort_values("contribution", ascending=False)
        rows = [["Ligne", "Type d'actif", "Façon d'investir", "Gain / perte", "Contribution"]]
        rows += [[r["ligne"], r["classe"], r["strategie"], f"{r['resultat']:+,.0f} $".replace(",", " "),
                  PS.pts(r["contribution"])] for _, r in df.iterrows()]
        b.append(("table", rows, [2.4, 3.6, 5.0, 3.0, 3.0]))
    else:
        b.append(("p", "Pas encore de résultat mesurable ce mois-ci."))

    b.append(("h", "5. Le respect des règles"))
    pts_ = []
    if ders:
        for d in ders:
            pts_.append(f"Dérogation sur {d['ticker']} : jusqu'à {d['poids_max']:.0%} au lieu de "
                        f"{d['plafond_normal']:.0%}, du {str(d['debut'])[:10]} au {str(d['echeance'])[:10]} — "
                        f"{d['etat']}. Justification : « {d['justification']} ».")
    else:
        pts_.append("Aucun dépassement de la limite de poids par ligne pendant le mois.")
    if sheets["lignes"]:
        pts_.append(f"Fiches de risques : {len(sheets['lignes']) - len(sheets['manquantes'])} ligne(s) sur "
                    f"{len(sheets['lignes'])} ont leurs risques propres documentés (taux, juridique, dette, change…)"
                    + (f" ; à compléter : {', '.join(sheets['manquantes'][:6])}." if sheets["manquantes"] else "."))
        if sheets["alertes"]:
            pts_.append("Risque élevé non couvert signalé sur : " + ", ".join(sheets["alertes"]) + ".")
    if no_thesis:
        pts_.append(f"{no_thesis} ordre(s) manuel(s) ancien(s) n'ont pas de thèse écrite.")
    b.append(("bullets", pts_))

    b.append(("h", "6. L'avis du comité et les risques"))
    if review:
        risk = review.get("risque") or {}
        cons = review["contraintes"]
        b.append(("p", f"**{PS.strip_md(review['verdict_label'])}** — profil {cons['profil']}, perte maximale "
                       f"acceptable {cons['perte_max']:.0%}."))
        if risk.get("var95_1an") is not None:
            b.append(("p", f"Perte potentielle sur un an (VaR 95 %) : {PS.pct(risk['var95_1an'])}, pour une limite de "
                           f"{cons['perte_max']:.0%}. En clair : d'après le passé, une perte plus forte ne devrait "
                           "arriver qu'environ une année sur vingt."))
        th = review.get("themes") or []
        if th and th[0]["poids"] >= 0.10:
            b.append(("p", th[0]["texte"]))
        recos = review.get("recommandations") or []
        if recos:
            b.append(("bullets", [f"{PS.strip_md(r['action'])} ({r['qui']})" for r in recos[:6]]))
    else:
        b.append(("p", "Revue du comité non jointe à ce rapport."))

    b.append(("h", "7. Les prochaines étapes"))
    nxt = []
    if earnings is not None and not earnings.empty:
        from utils.earnings import earnings_sentences
        nxt += earnings_sentences(earnings, weights)
    for d in ders:
        if d["etat"] == "active":
            nxt.append(f"Ramener {d['ticker']} sous {d['plafond_normal']:.0%} avant le {str(d['echeance'])[:10]}.")
        elif d["etat"].startswith("échue"):
            nxt.append(f"Régulariser {d['ticker']} : la dérogation est échue.")
    for x in (review or {}).get("decisions", [])[:4]:
        nxt.append(PS.strip_md(x))
    b.append(("bullets", nxt or ["Aucune décision particulière à prendre : le portefeuille suit sa politique."]))

    b.append(("h", "8. Petit lexique"))
    b.append(("table", [["Terme", "En clair"]] + [[k, v] for k, v in GLOSSARY], [4.2, 13.2]))
    b.append(("note", "Membres du comité : personnages fictifs. " + L.DISCLAIMER))
    from utils.reporting import make_pdf
    pdf = make_pdf(f"Rapport mensuel — {name}", f"McKenson Asset Management · {plabel} · "
                   f"édité le {datetime.now():%d/%m/%Y}", b)

    html = (f"<html><body style='background:#080e1a;font-family:Arial,sans-serif;padding:18px'>"
            f"<div style='max-width:760px;margin:auto'>"
            f"<div style='color:#00d4ff;font-size:13px;font-weight:700;letter-spacing:2px'>McKENSON ASSET MANAGEMENT</div>"
            f"<div style='color:#e2e8f0;font-size:20px;font-weight:700;margin:6px 0'>Rapport mensuel — {name} — {plabel}</div>"
            f"{PS.html_block(simple)}"
            f"<p style='color:#cbd5e1;font-size:13px'>{len(journal)} décision(s) ce mois-ci ; le détail (raisons, "
            f"dangers, respect des règles, prochaines étapes) est dans le PDF joint.</p>{L.html_footer()}"
            f"</div></body></html>")
    return dict(pdf=pdf, html=html, simple=simple, journal=journal, derogations=ders, periode=plabel,
                debut=d0, fin=d1)
