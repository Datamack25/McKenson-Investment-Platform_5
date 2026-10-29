# components/desk_tools_ui.py  —  MAM v5.6 · Discipline de gestion (Trading Desk)
"""
Affichage (style MAM) des outils de discipline de gestion :

* thesis_form          — thèse d'investissement obligatoire avant un ordre manuel
* earnings_notice      — rappel « période de résultats » sur la ligne de l'ordre
* derogation_request   — demande de dérogation temporaire au plafond par ligne
* discipline_tab       — thèmes / fiches de risques / dérogations / publications de résultats

La logique est dans utils/themes.py, utils/line_risk.py, utils/earnings.py et
utils/compliance.py.
"""
from __future__ import annotations

import html as _h

import pandas as pd
import streamlit as st

_BOX = ('<div style="border-left:3px solid {c};background:{c}0f;border-radius:4px;padding:8px 12px;'
        'font-family:Share Tech Mono;font-size:.72rem;color:#cbd5e1;line-height:1.65;margin:6px 0;">{t}</div>')


def _box(text: str, color: str = "#00d4ff"):
    st.markdown(_BOX.format(c=color, t=text), unsafe_allow_html=True)


def _author() -> str | None:
    u = st.session_state.get("mam_user") or {}
    return u.get("username") or u.get("email")


# ══════════════════════════════════════════════════════════════════════════════
#  THÈSE OBLIGATOIRE AVANT L'ORDRE
# ══════════════════════════════════════════════════════════════════════════════
def thesis_form(key: str, ticker: str, is_buy: bool) -> tuple[dict | None, list[str]]:
    """Champs de thèse. Renvoie (thèse horodatée si complète sinon None, éléments manquants)."""
    from utils.line_risk import HORIZONS, THESIS_FIELDS, stamp_thesis, validate_thesis
    st.markdown('<div style="font-family:Rajdhani;font-size:.75rem;letter-spacing:.12em;color:#ffd700;margin-top:6px">'
                f'📝 THÈSE D\'INVESTISSEMENT — {"ACHAT" if is_buy else "VENTE"} DE {_h.escape(ticker)} '
                '(obligatoire)</div>', unsafe_allow_html=True)
    st.caption("Écrivez pourquoi vous passez cet ordre et ce qui peut mal tourner. La thèse est horodatée et "
               "rattachée à l'ordre : c'est elle qui permettra de montrer, plus tard, quand et pourquoi la décision "
               "a été prise.")
    th = dict(
        pourquoi=st.text_area(THESIS_FIELDS["pourquoi"], key=f"{key}_why", height=70),
        risques=st.text_area(THESIS_FIELDS["risques"], key=f"{key}_risk", height=60),
        invalidation=st.text_input(THESIS_FIELDS["invalidation"], key=f"{key}_inv"),
        horizon=st.selectbox("Horizon de la position", HORIZONS, index=2, key=f"{key}_hor"),
    )
    ok, missing = validate_thesis(th)
    if not ok:
        st.caption("Pour activer l'ordre, il manque : " + " · ".join(missing) + ".")
    return (stamp_thesis(th, _author()) if ok else None), missing


# ══════════════════════════════════════════════════════════════════════════════
#  PÉRIODE DE RÉSULTATS
# ══════════════════════════════════════════════════════════════════════════════
def earnings_notice(ticker: str):
    from utils.earnings import in_earnings_period, next_earnings
    try:
        dates = next_earnings([ticker])
    except Exception:
        return
    d = in_earnings_period(ticker, dates)
    if d:
        _box(f"📅 <b>Période de résultats</b> : {ticker} publie ses résultats le {d:%d/%m/%Y}. Le cours peut "
             "bouger beaucoup plus que d'habitude autour de cette date. Précisez dans votre thèse le scénario attendu "
             "(résultats meilleurs ou moins bons que prévu) et ce que vous ferez dans chaque cas.", "#ffd700")
    elif dates.get(ticker):
        st.caption(f"📅 Prochaine publication de résultats de {ticker} : {dates[ticker]:%d/%m/%Y}.")


# ══════════════════════════════════════════════════════════════════════════════
#  DÉROGATION AU PLAFOND PAR LIGNE
# ══════════════════════════════════════════════════════════════════════════════
def derogation_request(port: dict, ticker: str, decision, category: str, key: str) -> bool:
    """Formulaire affiché quand la règle C04 bloque l'ordre. Renvoie True si une dérogation vient d'être accordée."""
    from utils.compliance import (DEROGATION_MAX_DAYS, DEROGATION_MIN_CHARS, derogation_ceiling, line_cap,
                                  request_derogation)
    if not any(c.code == "C04" for c in decision.blocks):
        return False
    cap, label = line_cap(port, ticker, category)
    ceiling = derogation_ceiling(cap)
    with st.expander(f"🧾 Demander une dérogation temporaire au plafond de {cap:.0%} ({label})"):
        st.markdown(
            f"Un dépassement est possible s'il reste **exceptionnel** : justifié par écrit, plafonné à "
            f"**{ceiling:.0%}**, limité à **{DEROGATION_MAX_DAYS} jours** et **notifié avant l'ordre** (e-mail du "
            "compte). À l'échéance, la ligne doit revenir sous le plafond ; sinon, chaque ordre et chaque rapport "
            "le rappellent.")
        with st.form(f"{key}_derog"):
            c1, c2 = st.columns(2)
            pmax = c1.slider("Poids maximal demandé", min_value=round(cap + 0.01, 2), max_value=float(ceiling),
                             value=float(min(ceiling, cap + 0.05)), step=0.01, format="%.2f")
            jours = c2.slider("Durée (jours)", 1, DEROGATION_MAX_DAYS, 2)
            just = st.text_area(f"Justification (au moins {DEROGATION_MIN_CHARS} caractères) : pourquoi cette "
                                "position mérite de dépasser le plafond, et comment elle sera réduite", height=80)
            conf = st.checkbox("Je confirme que l'investisseur est informé de ce dépassement avant l'ordre")
            sent = st.form_submit_button("🧾 Enregistrer la dérogation", use_container_width=True)
        if sent:
            if not conf:
                st.error("La notification préalable de l'investisseur est obligatoire.")
                return False
            ok, msg = request_derogation(port, ticker, float(pmax), int(jours), just, category=category,
                                         author=_author())
            if ok:
                from utils.data import persist
                persist()
                st.success(msg + " L'ordre est de nouveau contrôlé.")
                st.rerun()
            else:
                st.error(msg)
    return False


def _derogations_section(port: dict, weights: dict):
    from utils.compliance import close_derogation, derogation_status
    from components.ui import section_title
    section_title("DÉROGATIONS DE CONCENTRATION", "🧾")
    rows = derogation_status(port, weights)
    if not rows:
        st.caption("Aucune dérogation : toutes les lignes respectent leur plafond habituel.")
        return
    col = {"active": "#ffd700", "échue — à régulariser": "#ff3b6b", "régularisée": "#00ff88", "close": "#64748b"}
    for d in sorted(rows, key=lambda x: str(x.get("debut")), reverse=True):
        w = d.get("poids_actuel")
        _box(f"<b>{_h.escape(d['ticker'])}</b> · <b style='color:{col.get(d['etat'], '#94a3b8')}'>{d['etat'].upper()}</b> · "
             f"autorisé jusqu'à {d['poids_max']:.0%} (plafond habituel {d['plafond_normal']:.0%}) · "
             f"du {str(d['debut'])[:16].replace('T', ' ')} au {str(d['echeance'])[:16].replace('T', ' ')}"
             + (f" · poids actuel {w:.1%}" if w is not None else "")
             + f"<br>Justification : {_h.escape(d['justification'])}"
             + (f"<br>Clôture : {_h.escape(d['cloture'])}" if d.get("cloture") else ""),
             col.get(d["etat"], "#94a3b8"))
        if d["etat"] in ("active", "échue — à régulariser") and \
                st.button(f"Clôturer la dérogation {d['ticker']}", key=f"derog_close_{d['ticker']}"):
            from utils.data import persist
            close_derogation(port, d["ticker"])
            persist()
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
#  ONGLET « DISCIPLINE DE GESTION »
# ══════════════════════════════════════════════════════════════════════════════
def discipline_tab(port: dict, live: dict, total_val: float):
    from components.ui import section_title
    hold = port.get("holdings", {}) or {}
    values = {t: h.get("qty", 0) * float((live.get(t) or (h.get("avg_price", 0), 0))[0] or h.get("avg_price", 0))
              for t, h in hold.items()}
    weights = {t: v / total_val for t, v in values.items()} if total_val else {}
    st.caption("Les règles qu'un gérant s'impose pour pouvoir, plus tard, expliquer chaque décision : thèses "
               "écrites, risques documentés ligne par ligne, chaînes de valeur surveillées, dépassements encadrés, "
               "calendrier des résultats.")
    _income_section(port)
    _themes_section(values, total_val)
    _sheets_section(port)
    _derogations_section(port, weights)
    _earnings_section(port, weights)
    _journal_section(port)


def _themes_section(values: dict, nav: float):
    from utils.themes import THEMES, theme_exposure
    from components.ui import section_title
    section_title("CHAÎNES DE VALEUR ET THÈMES", "🔌")
    th = theme_exposure(values, nav)
    if not th:
        st.caption("Aucune ligne ne relève des thèmes suivis.")
    for t in th:
        _box(f"{t['emoji']} <b>{_h.escape(t['theme'])}</b> — {t['poids']:.0%} du portefeuille "
             f"({t['n_segments']} segment(s))<br>{_h.escape(t['texte'])}",
             "#ff3b6b" if t["alerte"] else "#00d4ff")
        if t["segments"]:
            st.dataframe(pd.DataFrame({"Segment": list(t["segments"]), "Poids": list(t["segments"].values())})
                         .style.format({"Poids": "{:.1%}"}), use_container_width=True, hide_index=True)
    with st.expander("📚 Paniers thématiques disponibles"):
        for name, d in THEMES.items():
            st.markdown(f"**{d['emoji']} {name}** — {d['idee']}  \n"
                        f"_Moteur commun : {d['moteur_commun']} · risque commun : {d['risque_commun']}._")
            st.dataframe(pd.DataFrame([{"Segment": s, "Actifs": ", ".join(tk)} for s, tk in d["segments"].items()]),
                         use_container_width=True, hide_index=True)
        st.caption("Ces actifs sont proposés dans le Trading Desk (univers « 🔌 Thèmes »). Un panier thématique "
                   "n'est pas une recommandation : c'est une grille de lecture des risques communs.")


def _sheets_section(port: dict):
    from utils.data import persist
    from utils.line_risk import (COVERAGE, LEVELS, RISK_TYPES, get_sheet, needs_sheet, save_sheet, sheet_score,
                                 sheets_status)
    from components.ui import section_title
    section_title("FICHES DE RISQUES PAR LIGNE", "🗂️")
    status = sheets_status(port)
    if not status["lignes"]:
        st.caption("Aucune action détenue : les ETF larges, devises, futures et crypto-actifs se lisent au niveau "
                   "du marché, sans fiche par entreprise.")
        return
    rows = []
    for t in status["lignes"]:
        sh = (port.get("fiches_risque") or {}).get(t)
        sc = sheet_score(sh) if sh else None
        rows.append({"Ligne": t, "Fiche": "à remplir" if t in status["manquantes"] else
                     ("complète" if sc and sc["complete"] else "à compléter"),
                     "Risques élevés": ", ".join(RISK_TYPES[k].split(" — ")[0] for k in (sc or {}).get("eleves", [])) or "—",
                     "Élevés non couverts": len((sc or {}).get("non_couverts", [])),
                     "Mise à jour": (sh or {}).get("maj") or "—"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    t = st.selectbox("Ligne à documenter", status["lignes"], key="lr_sel")
    sh = get_sheet(port, t)
    st.caption(f"Secteur : {sh.get('secteur', '—')}. Risques pré-sélectionnés selon le secteur ; ajoutez ou retirez-en.")
    chosen = st.multiselect("Risques examinés", list(RISK_TYPES), default=list(sh["risques"]),
                            format_func=lambda k: RISK_TYPES[k].split(" — ")[0], key=f"lr_types_{t}")
    with st.form(f"lr_form_{t}"):
        new = {}
        for k in chosen:
            cur = sh["risques"].get(k, dict(niveau="Moyen", couverture="Inconnu", note=""))
            st.markdown(f"**{RISK_TYPES[k]}**")
            c1, c2, c3 = st.columns([1, 1.2, 2.4])
            niv = c1.selectbox("Niveau", LEVELS, index=LEVELS.index(cur.get("niveau", "Moyen")), key=f"lr_{t}_{k}_n")
            cov = c2.selectbox("L'entreprise le couvre ?", COVERAGE, index=COVERAGE.index(cur.get("couverture", "Inconnu")),
                               key=f"lr_{t}_{k}_c")
            note = c3.text_input("Comment (en une phrase)", value=cur.get("note", ""), key=f"lr_{t}_{k}_t")
            new[k] = dict(niveau=niv, couverture=cov, note=note)
        synth = st.text_area("Synthèse : pourquoi ce risque global reste acceptable pour ce portefeuille",
                             value=sh.get("synthese", ""), key=f"lr_{t}_syn", height=60)
        if st.form_submit_button("💾 Enregistrer la fiche", use_container_width=True):
            save_sheet(port, t, {**sh, "risques": new, "synthese": synth}, _author())
            persist()
            st.success(f"Fiche de {t} enregistrée.")
            st.rerun()


def _earnings_section(port: dict, weights: dict):
    from utils.earnings import earnings_window, next_earnings
    from components.ui import section_title
    section_title("PUBLICATIONS DE RÉSULTATS À VENIR (30 JOURS)", "📅")
    hold = list((port.get("holdings") or {}).keys())
    if not hold:
        st.caption("Aucune position.")
        return
    with st.spinner("Calendrier des résultats…"):
        df = earnings_window(next_earnings(hold), 30)
    if df.empty:
        st.caption("Aucune publication de résultats connue dans les 30 prochains jours pour les actions détenues "
                   "(ou calendrier indisponible).")
        return
    df = df.assign(Poids=[weights.get(t) for t in df["ticker"]])
    st.dataframe(df.rename(columns={"ticker": "Ligne", "date": "Date", "libelle": "Quand", "periode": "Période de résultats"})
                 [["Ligne", "Date", "Quand", "Poids", "Période de résultats"]]
                 .style.format({"Poids": lambda x: "—" if x is None or x != x else f"{x:.1%}"}),
                 use_container_width=True, hide_index=True)
    st.caption("Autour d'une publication, le cours peut bouger fortement : relisez la thèse de la ligne et décidez à "
               "l'avance de ce que vous ferez si les résultats sont meilleurs ou moins bons que prévu.")


def _journal_section(port: dict):
    from utils.line_risk import decision_journal
    from components.ui import section_title
    section_title("JOURNAL DES DÉCISIONS", "📜")
    j = decision_journal(port)
    if not j:
        st.caption("Aucun ordre pour l'instant.")
        return
    rows = []
    for e in reversed(j[-60:]):
        th = e.get("these") or {}
        rows.append({"Date": e["date"], "Ligne": e["ticker"], "Sens": e["action"], "Montant": e["montant"],
                     "Décidé par": e["source"], "Pourquoi": th.get("pourquoi", "—" if e["source"] == "Trading Desk"
                                                                      else "plan automatique contrôlé par le comité"),
                     "Dangers identifiés": th.get("risques", "—"), "Horizon": th.get("horizon", "—")})
    st.dataframe(pd.DataFrame(rows).style.format({"Montant": "{:,.0f}"}), use_container_width=True, hide_index=True)


def _income_section(port: dict):
    """v5.8 — revenus (dividendes, intérêts), frais et flux externes, avec le journal des mouvements."""
    from components.ui import section_title
    from utils import ledger as LG
    from utils.costs import describe
    from utils.income import income_summary
    section_title("LIQUIDITÉS, REVENUS ET FRAIS", "💵")
    inc = income_summary(port)
    k = st.columns(5)
    k[0].metric("Dividendes reçus", f"{inc['dividendes']:,.0f} $".replace(",", " "))
    k[1].metric("Intérêts reçus", f"{inc['interets']:,.0f} $".replace(",", " "))
    k[2].metric("Taux monétaire", "—" if inc["taux"] is None else f"{inc['taux']:.2%}",
                help="Bons du Trésor américain à 13 semaines (^IRX), base exact/360.")
    k[3].metric("Frais payés", f"{inc['frais']:,.0f} $".replace(",", " "))
    k[4].metric("Apports − retraits", f"{inc['apports'] - inc['retraits']:,.0f} $".replace(",", " "))
    st.caption("Les liquidités sont rémunérées chaque jour au taux monétaire du marché ; les dividendes sont versés "
               "à la date de détachement, nets de la retenue à la source non récupérable (hypothèse : résident fiscal "
               "français). Les apports et retraits ne modifient pas la performance (TWR, norme GIPS).")
    mv = LG.movements(port)
    if not mv.empty:
        show = mv.sort_values("date", ascending=False).head(200).copy()
        show["type"] = show["type"].map(LG.LABEL).fillna(show["type"])
        cols = [c for c in ("date", "type", "ticker", "montant", "detail") if c in show]
        st.dataframe(show[cols].rename(columns={"date": "Date", "type": "Mouvement", "ticker": "Ligne",
                                                "montant": "Montant", "detail": "Détail"})
                     .style.format({"Montant": "{:+,.2f}"}), use_container_width=True, hide_index=True, height=260)
    with st.expander("Barème des coûts de transaction appliqués"):
        for x in describe():
            st.markdown(f"- {x}")
