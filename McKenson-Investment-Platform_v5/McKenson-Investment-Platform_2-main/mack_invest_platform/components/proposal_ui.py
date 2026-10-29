# components/proposal_ui.py  —  MAM v5.7 · « Portefeuille proposé pour vous » (Trading Desk)
"""
Le comité propose un portefeuille complet, construit à partir du profil de l'utilisateur,
de la politique d'investissement du portefeuille et des conditions de marché réelles.
L'utilisateur reste maître : il modifie les poids, retire ou ajoute des lignes, fait valider
sa version par le comité, puis l'exécute (simulation sur cours réels Yahoo Finance).
La logique est dans utils/portfolio_proposal.py.
"""
from __future__ import annotations

import hashlib
import html as _h

import pandas as pd
import streamlit as st

from utils import portfolio_proposal as PP


def _ips_for(port: dict) -> tuple[dict, str]:
    from utils import committee as CM
    from utils.compliance import get_profile
    if port.get("ips"):
        return port["ips"], "politique d'investissement de ce portefeuille"
    prof = get_profile()
    origin = ("votre profil investisseur" if prof.get("defini")
              else "profil par défaut — remplissez « Mon profil investisseur » pour une proposition personnalisée")
    return CM.default_ips(prof.get("risque", "Équilibré")), origin


def _editor_frame(lines: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"Ligne": lines["ticker"], "Nom": lines["nom"], "Classe": lines["classe"],
                         "Poids (%)": (lines["poids"] * 100).round(1), "Pourquoi": lines["pourquoi"]})


def _hash(w: pd.Series) -> str:
    return hashlib.md5(w.round(5).sort_index().to_json().encode()).hexdigest()


def proposal_panel(port: dict, key: str):
    from components.committee_ui import inject_css, ips_summary
    from components.committee_followup import PENDING
    inject_css()
    pending = (port.get("suivi_comite") or {}).get("statut") in PENDING
    empty = not any((h or {}).get("qty", 0) > 0 for h in (port.get("holdings") or {}).values())
    head = ("🧭 Portefeuille proposé pour vous — à construire" if empty else
            "🧭 Portefeuille proposé pour vous — reconstruire ou rééquilibrer")
    with st.expander(head + (" · propositions du comité en attente" if pending else ""), expanded=empty or pending):
        ips, origin = _ips_for(port)
        st.markdown(
            '<div style="font-family:Share Tech Mono;font-size:.73rem;color:#94a3b8;line-height:1.65">'
            "Le comité construit un portefeuille adapté à <b>votre profil</b>, à la <b>politique d'investissement</b> "
            "et aux <b>conditions de marché actuelles</b> (cours réels Yahoo Finance, différés d'environ 15 min ; "
            "régime économique officiel ; signaux validés hors échantillon). Vous pouvez <b>modifier chaque poids</b>, "
            "<b>retirer</b> ou <b>ajouter</b> des lignes : votre version est revue par le comité avant toute "
            "exécution. Simulation pédagogique : aucun ordre réel n'est passé.</div>", unsafe_allow_html=True)
        st.caption(f"Profil analysé : {ips_summary(ips).replace('**', '')} — source : {origin}.")
        c1, c2 = st.columns([1.2, 1])
        intensity = c1.slider("Prise en compte du contexte de marché", 0.0, 1.0, 0.5, 0.1, key=f"{key}_int",
                              help="0 = allocation de long terme du profil ; 1 = inclinaisons maximales selon le "
                                   "régime de marché du moment.")
        skey = f"{key}_prop"
        if c2.button("🧑‍⚖️ " + ("Actualiser la proposition" if st.session_state.get(skey) else
                                "Construire la proposition"), key=f"{key}_go", use_container_width=True,
                     type="primary"):
            with st.spinner("Le comité analyse votre profil et le marché…"):
                try:
                    st.session_state[skey] = dict(pid=port.get("id"), ips=ips, out=_build(port, ips, intensity))
                except Exception as e:  # noqa: BLE001
                    st.error(f"Le comité n'a pas pu construire la proposition ({e}).")
                    return
            st.session_state.pop(f"{key}_ed", None)
            st.session_state.pop(f"{key}_rev", None)
        state = st.session_state.get(skey)
        if not state or state.get("pid") != port.get("id"):
            return
        _show(port, state["ips"], state["out"], key)


def _build(port: dict, ips: dict, intensity: float) -> dict:
    from components.committee_ui import get_context, portfolio_values
    from utils import committee as CM
    from utils.data import get_multi_prices
    ctx = get_context()
    vals, cash, _ = portfolio_values(port)
    universe = set(vals) | set(CM.A.CLASS_PROXY.values()) | set(CM.UCITS_PROXY.values()) | set(CM.PEA_PROXY.values())
    live = get_multi_prices(tuple(sorted(universe)))
    board = None
    try:  # secteurs porteurs : performance récente réelle + lecture du régime
        from datetime import datetime, timedelta
        from utils import performance as PF
        from utils import upload_advisor as U
        hist = PF.price_history(U.board_tickers(), (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d"))
        if hist is not None and not hist.empty:
            board = U.sector_board(hist, ctx["macro"])
            extra = tuple(sorted(set(board["ETF"].head(4)) - set(live)))
            if extra:
                live = {**live, **get_multi_prices(extra)}
    except Exception:
        board = None
    out = PP.build_proposal(vals, cash, ips, ctx, live, intensity, board)
    out["ctx_date"] = pd.Timestamp.now().strftime("%d/%m/%Y %H:%M")
    return out


def _show(port: dict, ips: dict, out: dict, key: str):
    from utils import committee as CM
    lines = out["lignes"]
    cons = out["contraintes"]
    if out["data_sim"]:
        st.error("⛔ Les données de marché sont indisponibles (valeurs simulées) : la proposition est affichée "
                 "pour information mais ne peut pas être exécutée. Réessayez plus tard.")
    else:
        st.success(f"Données de marché réelles au {out['ctx_date']} · régime officiel : « {out['regime']} » · "
                   f"profil {cons['profil']} · perte maximale acceptable {cons['perte_max']:.0%}.")
    with st.expander("Comment le comité a construit la proposition"):
        for who, note in out["notes"]:
            m = CM.MEMBER[who]
            st.markdown(f'<div class="cm-reco" style="border-color:{m["couleur"]}">{m["emoji"]} <b>{m["nom"]}</b> — '
                        f'{_h.escape(note)}</div>', unsafe_allow_html=True)
        cls = out["cible_classes"]
        cls = cls[cls > 0.001].sort_values(ascending=False)
        st.dataframe(pd.DataFrame({"Classe d'actifs": cls.index, "Cible": cls.values})
                     .style.format({"Cible": "{:.1%}"}), use_container_width=True, hide_index=True)
    if lines.empty:
        st.info("Le comité recommande de rester en liquidités pour l'instant (contraintes de la politique "
                "d'investissement ou contexte de marché).")
        return

    st.markdown("##### Proposition du comité — modifiez librement les poids")
    st.caption("Changez un poids, mettez-le à 0 pour retirer une ligne, ou ajoutez une ligne en bas du tableau "
               "(ticker de l'univers de la plateforme, ex. ETN, IWDA.AS, GLD). Ce qui n'est pas investi reste en "
               f"liquidités. Proposition : {out['liquidites']:.0%} de liquidités.")
    ed_key = f"{key}_ed"
    base = _editor_frame(lines)
    edited = st.data_editor(
        base, key=ed_key, num_rows="dynamic", use_container_width=True, hide_index=True,
        disabled=["Nom", "Classe", "Pourquoi"],
        column_config={"Ligne": st.column_config.TextColumn("Ligne", required=True, width="small"),
                       "Poids (%)": st.column_config.NumberColumn("Poids (%)", min_value=0.0, max_value=100.0,
                                                                  step=0.5, format="%.1f"),
                       "Pourquoi": st.column_config.TextColumn("Pourquoi (comité)", width="large")})
    weights, msgs = PP.normalize_edit(edited, PP.known_tickers())
    for m in msgs:
        st.warning(m)
    edited_flag = PP.is_edited(lines, weights)
    k = st.columns(4)
    k[0].metric("Lignes", str(len(weights)))
    k[1].metric("Investi", f"{weights.sum():.0%}")
    k[2].metric("Liquidités", f"{max(0.0, 1 - weights.sum()):.0%}")
    k[3].metric("Version", "ajustée par vous" if edited_flag else "proposée par le comité")
    if edited_flag:
        diff = PP.compare_with_proposal(lines, weights)
        with st.expander(f"Vos ajustements ({len(diff)} ligne(s))"):
            st.dataframe(diff.style.format("{:.1%}", subset=["Proposé", "Votre version"])
                         .format("{:+.1%}", subset=["Écart"]), use_container_width=True)
        if st.button("↩️ Revenir à la proposition du comité", key=f"{key}_reset"):
            st.session_state.pop(ed_key, None)
            st.session_state.pop(f"{key}_rev", None)
            st.rerun()

    # ── Revue de la version (proposée ou ajustée) par le comité ──
    h = _hash(weights)
    rkey = f"{key}_rev"
    rev_state = st.session_state.get(rkey)
    if st.button("🧑‍⚖️ Soumettre " + ("ma version" if edited_flag else "cette proposition") + " au comité",
                 key=f"{key}_review", use_container_width=True):
        with st.spinner("Le comité examine le portefeuille obtenu…"):
            st.session_state[rkey] = rev_state = dict(hash=h, rev=_review(port, ips, weights, out["nav"]))
    if not rev_state or rev_state["hash"] != h:
        st.caption("Le comité doit examiner la version finale avant l'exécution"
                   + (" (la version a changé depuis la dernière revue)." if rev_state else "."))
        return
    rev = rev_state["rev"]
    from components.committee_ui import render_review
    render_review(rev)
    if rev["verdict"] == "veto":
        st.error("⛔ Le comité oppose son veto à cette version : modifiez les poids (par exemple réduisez les lignes "
                 "les plus risquées ou concentrées) puis soumettez-la de nouveau.")
        return
    _execute_block(port, weights, rev, out, edited_flag, key)


def _review(port: dict, ips: dict, weights: pd.Series, nav: float) -> dict:
    from components.committee_ui import get_context
    from utils import committee as CM
    from utils.compliance import get_profile, normalize_port_type
    vals, cash = PP.projected_values(weights, nav)
    return CM.review_portfolio(vals, cash, ips, get_context(), options=port.get("options", []),
                               options_ok=get_profile().get("options_ok", False), port_type=normalize_port_type(port),
                               label=port.get("name", "Portefeuille"), port=port)


def _execute_block(port: dict, weights: pd.Series, rev: dict, out: dict, edited: bool, key: str):
    from utils.auto_portfolio import execute_orders, plan_orders
    from utils.data import get_multi_prices, get_multi_sources, persist
    tick = tuple(sorted(set(weights.index) | set((port.get("holdings") or {}).keys())))
    live = get_multi_prices(tick)
    try:
        src = get_multi_sources(tick)
    except Exception:
        src = {}
    not_live = [t for t in weights.index if src.get(t, "live") != "live"]
    orders = plan_orders(port, weights, live, 1.0, "full", cash_proxy="__none__")
    st.markdown("##### Ordres pour obtenir ce portefeuille")
    if orders.empty:
        st.success("Le portefeuille correspond déjà à cette version : aucun ordre nécessaire.")
        return
    st.dataframe(orders.style.format({"qty": "{:,.4f}", "price": "{:,.2f}", "montant": "{:,.0f}"}),
                 use_container_width=True, hide_index=True)
    if not_live:
        st.warning("Cours réel indisponible pour : " + ", ".join(not_live) + ". Ces ordres seront refusés par la "
                   "conformité (règle C01 : pas d'exécution sur un prix de secours).")
    note = ""
    if edited:
        note = st.text_input("Pourquoi avez-vous ajusté la proposition ? (facultatif, conservé dans le journal)",
                             key=f"{key}_why")
    blocked = out["data_sim"] or not out["allowed"]
    ok = st.checkbox("Je confirme l'exécution simulée de ces ordres (chacun est contrôlé par la conformité)",
                     key=f"{key}_ok", disabled=blocked)
    if st.button("🚀 CONSTRUIRE CE PORTEFEUILLE", key=f"{key}_exec", type="primary", use_container_width=True,
                 disabled=blocked or not ok):
        from utils import committee as CM
        from components.committee_followup import _set
        tag = "Portefeuille proposé (ajusté par l'utilisateur)" if edited else "Portefeuille proposé par le comité"
        n_before = len(port.get("trades", []) or [])
        errs = execute_orders(port, orders, tag=tag)
        port["committee"] = CM.summary_for_storage(rev)
        _set(port, "validée", f"{tag} — {len(orders) - len(errs)} ordre(s)" + (f" · « {note} »" if note else ""))
        persist()
        try:
            from utils.execution_log import record_execution
            record_execution(port, tag, orders, n_before, errs, target_weights=weights)
        except Exception:
            pass
        for k_ in (f"{key}_prop", f"{key}_ed", f"{key}_rev"):
            st.session_state.pop(k_, None)
        if errs:
            st.warning("Ordres partiellement exécutés (bloqués par la conformité) :\n\n- " + "\n- ".join(errs))
        else:
            st.success(f"✅ Portefeuille construit : {len(orders)} ordre(s) exécuté(s).")
