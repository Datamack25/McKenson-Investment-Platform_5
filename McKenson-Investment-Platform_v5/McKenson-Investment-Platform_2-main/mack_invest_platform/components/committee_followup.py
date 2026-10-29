# components/committee_followup.py  —  MAM v5.6 · Propositions du comité après la création d'un portefeuille
"""
Après la création d'un portefeuille (assistant du Dashboard, Hedge Fund Agent,
administration), le comité réexamine le portefeuille obtenu selon sa politique
d'investissement et le contexte de marché, puis PROPOSE des améliorations :
chaque ordre est expliqué en mots simples (quoi, combien, qui le propose, pourquoi).

Rien n'est exécuté sans validation : l'utilisateur coche les propositions qu'il
retient, les valide, les reporte ou les refuse. La décision est horodatée dans
port["suivi_comite"] et les ordres validés passent un par un par la conformité.
"""
from __future__ import annotations

import html as _h
from datetime import datetime

import pandas as pd
import streamlit as st

PENDING = ("à proposer", "proposée")


def _skey(port: dict) -> str:
    """Propositions mises en commun entre le Dashboard et le Trading Desk (un seul calcul)."""
    return f"fu_{port.get('id') or port.get('name')}"


def mark_pending(port: dict, origine: str = "création"):
    """À appeler juste après la création d'un portefeuille."""
    port["suivi_comite"] = dict(statut="à proposer", depuis=datetime.now().isoformat(timespec="seconds"),
                                origine=origine, historique=(port.get("suivi_comite") or {}).get("historique", []))


def _set(port: dict, statut: str, detail: str = ""):
    sc = port.setdefault("suivi_comite", {})
    hist = sc.setdefault("historique", [])
    hist.append(dict(date=datetime.now().isoformat(timespec="seconds"), statut=statut, detail=detail))
    sc["historique"] = hist[-20:]
    sc["statut"], sc["maj"] = statut, datetime.now().isoformat(timespec="seconds")


def _compute(port: dict) -> dict:
    from components.committee_ui import get_context, portfolio_values
    from utils import committee as CM
    from utils.compliance import get_profile, normalize_port_type
    from utils.data import get_multi_prices
    ctx = get_context()
    vals, cash, _ = portfolio_values(port)
    universe = set(vals) | set(CM.A.CLASS_PROXY.values()) | set(CM.UCITS_PROXY.values()) | set(CM.PEA_PROXY.values())
    live = get_multi_prices(tuple(sorted(universe)))
    ips = port["ips"]
    opt = CM.committee_optimize(vals, cash, ips, ctx, live, 0.5, 0.02)
    common = dict(options=port.get("options", []), options_ok=get_profile().get("options_ok", False),
                  port_type=normalize_port_type(port), label=port.get("name", "Portefeuille"), port=port)
    before = CM.review_portfolio(vals, cash, ips, ctx, **common)
    after = CM.review_portfolio(opt["projete"], opt["cash_apres"], ips, ctx, **common)
    return dict(pid=port.get("id"), opt=opt, before=before, after=after,
                props=CM.improvement_proposals(opt, vals, cash), data_sim=ctx.get("data_sim", False),
                date=datetime.now().strftime("%d/%m/%Y %H:%M"))


def followup_panel(port: dict, key: str, compact: bool = False):
    """Panneau « Le comité propose des améliorations ». compact=True : n'apparaît que s'il y a des
    propositions en attente (Dashboard) ; sinon toujours disponible (Trading Desk)."""
    from components.committee_ui import inject_css, ips_summary, render_ips_form, render_review
    from utils import committee as CM
    from utils.compliance import get_profile
    from utils.data import persist

    sc = port.get("suivi_comite") or {}
    pending = sc.get("statut") in PENDING
    if compact and not pending:
        return
    inject_css()
    head = ("🧑‍⚖️ Le comité a des propositions d'amélioration pour ce portefeuille — à valider"
            if pending else "🧑‍⚖️ Demander au comité des propositions d'amélioration")
    with st.expander(head, expanded=pending):
        if not port.get("ips"):
            st.info("Le comité a besoin de la politique d'investissement de ce portefeuille pour proposer des "
                    "améliorations adaptées à VOTRE profil.")
            ips = render_ips_form(f"{key}_ips", CM.default_ips(get_profile().get("risque", "Équilibré")))
            if ips:
                port["ips"] = ips
                persist()
                st.rerun()
            return
        st.caption("Le comité réexamine le portefeuille selon votre politique d'investissement ("
                   + ips_summary(port["ips"]).replace("**", "") + ") et le contexte de marché. "
                   "Rien n'est exécuté sans votre validation ; chaque ordre retenu repasse par la conformité.")
        skey = _skey(port)
        out = st.session_state.get(skey)
        if out and out.get("pid") != port.get("id"):
            out = None
        if st.button("🧑‍⚖️ " + ("Actualiser les propositions" if out else "Réunir le comité"), key=f"{key}_run") \
                or (pending and out is None):
            with st.spinner("Le comité examine le portefeuille…"):
                try:
                    out = _compute(port)
                except Exception as e:  # noqa: BLE001
                    st.error(f"Le comité n'a pas pu se réunir ({e}).")
                    return
            st.session_state[skey] = out
            if pending and sc.get("statut") == "à proposer":
                _set(port, "proposée", f"{len(out['props'])} proposition(s)")
                persist()
        if not out:
            return
        _render(port, out, key)


def _render(port: dict, out: dict, key: str):
    from components.committee_ui import render_review
    from utils import committee as CM
    from utils.data import persist
    props, before, after, opt = out["props"], out["before"], out["after"], out["opt"]
    vb, va = before["verdict"], after["verdict"]
    rb, ra = before.get("risque") or {}, after.get("risque") or {}

    def _p(x):
        return "—" if x is None or x != x else f"{x:.1%}"
    k = st.columns(4)
    k[0].metric("Avis du comité aujourd'hui", CM.VERDICT_LABEL[vb].split(" ", 1)[1].title())
    k[1].metric("Avis après les améliorations", CM.VERDICT_LABEL[va].split(" ", 1)[1].title())
    k[2].metric("Perte potentielle sur 1 an", _p(ra.get("var95_1an")),
                delta=None if not rb.get("var95_1an") else f"{(ra.get('var95_1an', 0) - rb['var95_1an']) * 100:+.1f} pt",
                delta_color="inverse")
    k[3].metric("Propositions", str(len(props)))
    st.caption(f"Comité réuni le {out['date']}.")

    if not props:
        st.success("Le comité n'a rien à améliorer : le portefeuille est déjà aligné sur votre politique "
                   "d'investissement (dans les bandes de tolérance).")
        if (port.get("suivi_comite") or {}).get("statut") in PENDING and \
                st.button("✅ Noter que le portefeuille est validé", key=f"{key}_noop"):
            _set(port, "validée", "aucune amélioration nécessaire")
            port["committee"] = CM.summary_for_storage(before)
            persist()
            st.rerun()
        return

    st.markdown("##### Ce que le comité vous propose — en clair")
    for i, p in enumerate(props, 1):
        st.markdown(
            f'<div class="cm-reco" style="border-color:{"#00ff88" if p["action"] == "BUY" else "#ff3b6b"}">'
            f'<b>{i}. {_h.escape(p["texte"])}</b> <span style="color:#64748b">({_h.escape(p["classe"])})</span><br>'
            f'{p["emoji"]} {_h.escape(p["pourquoi"])} <span style="color:#64748b">— {_h.escape(p["qui"])}</span></div>',
            unsafe_allow_html=True)
    other = [r for r in after.get("recommandations", []) if r.get("priorite") in ("haute", "moyenne")]
    if other:
        st.markdown("##### Points d'attention que le comité garde après ces ordres")
        for r in other[:4]:
            st.markdown(f'<div class="cm-reco" style="border-color:#ffd700">{r["emoji"]} {_h.escape(CM_plain(r["action"]))}'
                        f'<span style="color:#64748b"> — {_h.escape(r["qui"])}</span></div>', unsafe_allow_html=True)

    df = pd.DataFrame([dict(Valider=True, Ligne=p["ticker"], Sens="Achat" if p["action"] == "BUY" else "Vente",
                            Montant=round(p["montant"], 0), Classe=p["classe"], Proposé_par=p["qui"]) for p in props])
    st.markdown("##### Choisissez ce que vous validez")
    ed = st.data_editor(df, key=f"{key}_ed", hide_index=True, use_container_width=True,
                        disabled=["Ligne", "Sens", "Montant", "Classe", "Proposé_par"],
                        column_config={"Montant": st.column_config.NumberColumn(format="%.0f $"),
                                       "Proposé_par": st.column_config.TextColumn("Proposé par")})
    chosen = [props[i] for i, v in enumerate(ed["Valider"].tolist()) if v]
    with st.expander("Avis détaillé du comité sur le portefeuille APRÈS les améliorations"):
        render_review(after)
    blocked = va == "veto" or not opt.get("allowed", True) or out.get("data_sim")
    if blocked:
        st.error("⛔ Exécution impossible : " + ("données de marché simulées." if out.get("data_sim") or
                                               not opt.get("allowed", True)
                                               else "le comité oppose son veto au portefeuille obtenu."))
    c1, c2, c3 = st.columns([1.4, 1, 1])
    if c1.button(f"✅ Valider {len(chosen)} amélioration(s)", key=f"{key}_ok", type="primary",
                 disabled=blocked or not chosen, use_container_width=True):
        _execute(port, chosen, after, opt, len(props))
    if c2.button("⏸️ Plus tard", key=f"{key}_later", use_container_width=True):
        _set(port, "reportée", "l'utilisateur examinera plus tard")
        persist()
        st.session_state.pop(_skey(port), None)
        st.rerun()
    if c3.button("❌ Refuser", key=f"{key}_no", use_container_width=True):
        _set(port, "refusée", f"{len(props)} proposition(s) refusée(s)")
        persist()
        st.session_state.pop(_skey(port), None)
        st.rerun()


def CM_plain(t: str) -> str:
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"\1", str(t))


def _execute(port: dict, chosen: list[dict], after: dict, opt: dict, n_props: int):
    from utils import committee as CM
    from utils.auto_portfolio import execute_orders
    from utils.data import persist
    orders = pd.DataFrame([dict(ticker=p["ticker"], action=p["action"], qty=p["qty"], price=p["price"],
                                montant=p["montant"]) for p in chosen])
    orders = pd.concat([orders[orders.action == "SELL"], orders[orders.action == "BUY"]], ignore_index=True)
    n_before = len(port.get("trades", []) or [])
    errs = execute_orders(port, orders, tag="Comité MAM — améliorations après création")
    _set(port, "validée", f"{len(chosen) - len(errs)} ordre(s) exécuté(s) sur {n_props} proposé(s)")
    if len(chosen) == n_props:
        port["committee"] = CM.summary_for_storage(after)
    persist()
    try:
        from utils.execution_log import record_execution
        record_execution(port, "Comité MAM — améliorations après création", orders, n_before, errs,
                         target_weights=opt.get("cible_lignes"))
    except Exception:
        pass
    st.session_state.pop(_skey(port), None)
    if errs:
        st.warning("Certains ordres ont été bloqués par la conformité :\n\n- " + "\n- ".join(errs))
    else:
        st.success(f"✅ {len(chosen)} amélioration(s) appliquée(s).")
