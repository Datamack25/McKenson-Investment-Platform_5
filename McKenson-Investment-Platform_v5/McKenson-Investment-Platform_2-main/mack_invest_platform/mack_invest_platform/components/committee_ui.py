# components/committee_ui.py  —  MAM v5.3 · Affichage du comité virtuel (style MAM)
"""
Cartes des membres, verdict, recommandations, questionnaire IPS et panneau de
validation d'un portefeuille. La logique est dans utils/committee.py.
"""
from __future__ import annotations

import html as _h

import streamlit as st

from utils import committee as C

_CSS = """
<style>
.cm-verdict{border-radius:10px;padding:12px 16px;margin:8px 0 12px;font-family:'Share Tech Mono',monospace}
.cm-verdict .v{font-family:Rajdhani,sans-serif;font-weight:700;font-size:1.15rem;letter-spacing:.12em}
.cm-verdict .s{font-size:.74rem;color:#94a3b8;margin-top:2px}
.cm-card{background:rgba(13,17,23,.85);border:1px solid rgba(0,212,255,.12);border-left:3px solid;border-radius:8px;
         padding:10px 13px;margin:5px 0;font-family:'Share Tech Mono',monospace;font-size:.72rem;color:#94a3b8;line-height:1.6;
         min-height:150px}
.cm-card .hd{display:flex;justify-content:space-between;align-items:center;gap:8px}
.cm-card .nm{font-family:Rajdhani,sans-serif;font-weight:700;font-size:.98rem;color:#e2e8f0;letter-spacing:.04em}
.cm-card .rl{font-family:Rajdhani,sans-serif;font-size:.62rem;letter-spacing:.14em;text-transform:uppercase;color:#64748b}
.cm-card .vt{font-family:Rajdhani,sans-serif;font-weight:700;font-size:.66rem;letter-spacing:.08em;padding:2px 8px;
             border-radius:4px;white-space:nowrap}
.cm-card .tt{color:#e2e8f0;font-size:.78rem;margin:6px 0 4px}
.cm-card ul{margin:0;padding-left:16px}.cm-card li{margin:2px 0}
.cm-card b{color:#cbd5e1}
.cm-persona{background:rgba(124,58,237,.05);border:1px solid rgba(124,58,237,.2);border-radius:8px;padding:10px 13px;
            margin:5px 0;font-family:'Share Tech Mono',monospace;font-size:.7rem;color:#94a3b8;line-height:1.6;min-height:190px}
.cm-persona .q{color:#c4b5fd;font-style:italic;margin-top:6px}
.cm-reco{border-left:3px solid;padding:6px 12px;margin:4px 0;border-radius:4px;background:rgba(255,255,255,.02);
         font-family:'Share Tech Mono',monospace;font-size:.74rem;color:#cbd5e1}
.cm-badge{display:inline-block;font-family:Rajdhani,sans-serif;font-weight:700;font-size:.6rem;letter-spacing:.1em;
          padding:1px 7px;border-radius:3px;margin-left:6px}
</style>
"""


def inject_css():
    st.markdown(_CSS, unsafe_allow_html=True)


def badge(port: dict) -> str:
    """Pastille de statut du comité pour un portefeuille."""
    c = port.get("committee") or {}
    v = c.get("verdict")
    if not v:
        return '<span class="cm-badge" style="color:#ffd700;border:1px solid rgba(255,215,0,.4)">🧑‍⚖️ À VALIDER</span>'
    col = C.VOTE_COLOR[v]
    txt = {"ok": "VALIDÉ", "reserve": "VALIDÉ · RÉSERVES", "veto": "REFUSÉ"}[v]
    return f'<span class="cm-badge" style="color:{col};border:1px solid {col}66">🧑‍⚖️ {txt}</span>'


def render_personas():
    """Présentation des membres du comité (personnages fictifs) et de leurs inspirations."""
    inject_css()
    cols = st.columns(3)
    for i, m in enumerate(C.MEMBERS):
        q = m.get("citation")
        quote = (f'<div class="q">« {_h.escape(q[0])} »<br><span style="color:#64748b">— {_h.escape(q[1])}'
                 f'{" (personnage fictif)" if q[1] == "Mc Henson ALGO-RITHME" else ""}</span></div>') if q else ""
        if m.get("citation2"):
            q2 = m["citation2"]
            quote += f'<div class="q">« {_h.escape(q2[0])} »<br><span style="color:#64748b">— {_h.escape(q2[1])}</span></div>'
        if m.get("maximes"):
            quote += ('<div style="margin-top:6px;color:#a78bfa">Maximes : '
                      + " · ".join(f"« {_h.escape(x)} »" for x in m["maximes"][1:]) + "</div>")
        cols[i % 3].markdown(
            f'<div class="cm-persona" style="border-left:3px solid {m["couleur"]}">'
            f'<div class="nm" style="font-family:Rajdhani;font-weight:700;font-size:1rem;color:#e2e8f0">'
            f'{m["emoji"]} {_h.escape(m["nom"])} <span style="color:{m["couleur"]};font-size:.75rem">{_h.escape(m["surnom"])}</span></div>'
            f'<div style="font-family:Rajdhani;font-size:.62rem;letter-spacing:.14em;color:#64748b;text-transform:uppercase">'
            f'{_h.escape(m["role"])}{" · droit de veto" if m["veto"] else ""}</div>'
            f'<div style="margin-top:5px">{_h.escape(m["style"])}</div>'
            f'<div style="margin-top:5px;color:#64748b">Inspiration : {_h.escape(m["inspiration"])}</div>{quote}</div>',
            unsafe_allow_html=True)
    st.caption("Les membres du comité sont des personnages fictifs. Les citations attribuées à de vrais investisseurs "
               "illustrent le style dont chaque rôle s'inspire ; les maximes de Mc Henson ALGO-RITHME sont les siennes.")


def render_review(rev: dict, show_recos: bool = True):
    """Verdict + cartes des 6 membres + recommandations et décisions."""
    inject_css()
    v = rev["verdict"]
    col = C.VOTE_COLOR[v]
    cons = rev.get("contraintes", {})
    st.markdown(
        f'<div class="cm-verdict" style="border:1px solid {col}66;background:{col}0f">'
        f'<div class="v" style="color:{col}">🧑‍⚖️ {rev["verdict_label"]}</div>'
        f'<div class="s">Comité du {rev["date"]} · régime officiel : {_h.escape(str(rev.get("regime", "—")))} · profil '
        f'{cons.get("profil", "—")} · perte maximale acceptable {cons.get("perte_max", 0):.0%}'
        f'{" · droit de veto : Aline DE MARGE (risques) et Constance Probité (conformité)" if v == "veto" else ""}</div>'
        f'</div>', unsafe_allow_html=True)
    cols = st.columns(3)
    for i, a in enumerate(rev["avis"]):
        vc = C.VOTE_COLOR[a["vote"]]
        pts = "".join(f"<li>{_md(p)}</li>" for p in a["points"][:6])
        cols[i % 3].markdown(
            f'<div class="cm-card" style="border-left-color:{a["couleur"]}">'
            f'<div class="hd"><div><div class="nm">{a["emoji"]} {_h.escape(a["nom"])}</div>'
            f'<div class="rl">{_h.escape(a["role"])}</div></div>'
            f'<span class="vt" style="color:{vc};border:1px solid {vc}66;background:{vc}12">{C.VOTE_LABEL[a["vote"]]}</span></div>'
            f'<div class="tt">{_h.escape(a["titre"])}</div><ul>{pts}</ul></div>', unsafe_allow_html=True)
    if show_recos and (rev.get("recommandations") or rev.get("decisions")):
        c1, c2 = st.columns([1.4, 1])
        with c1:
            st.markdown('<div style="font-family:Rajdhani;font-size:.75rem;letter-spacing:.14em;color:#ff8c00;'
                        'margin:10px 0 4px">🎙️ SYNTHÈSE DES RECOMMANDATIONS — GASPARD CLAIRVOIX</div>',
                        unsafe_allow_html=True)
            pc = {"haute": "#ff3b6b", "moyenne": "#ffd700", "basse": "#00d4ff"}
            for r in rev.get("recommandations", []) or [dict(qui="", emoji="✅", action="Aucune action nécessaire.",
                                                             priorite="basse")]:
                st.markdown(f'<div class="cm-reco" style="border-color:{pc[r["priorite"]]}">{r["emoji"]} {_md(r["action"])}'
                            f'<span style="color:#64748b"> — {_h.escape(r["qui"])}</span></div>', unsafe_allow_html=True)
        with c2:
            if rev.get("decisions"):
                st.markdown('<div style="font-family:Rajdhani;font-size:.75rem;letter-spacing:.14em;color:#00d4ff;'
                            'margin:10px 0 4px">🧭 CE QUE VOUS DEVEZ DÉCIDER</div>', unsafe_allow_html=True)
                for d in rev["decisions"]:
                    st.markdown(f'<div class="cm-reco" style="border-color:#00d4ff">☐ {_md(d)}</div>', unsafe_allow_html=True)


def _md(t: str) -> str:
    """Échappe le HTML et rend le **gras** markdown."""
    import re
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _h.escape(str(t)))


def render_ips_form(key: str, current: dict | None = None, submit_label: str = "💾 Enregistrer la politique") -> dict | None:
    """Questionnaire de politique d'investissement. Renvoie l'IPS à l'envoi, sinon None."""
    O, L = C.IPS_OPTIONS, C.IPS_LABELS
    cur = {**C.default_ips(), **(current or {})}

    def _i(k):
        try:
            return O[k].index(cur.get(k))
        except Exception:
            return 0

    with st.form(f"ips_{key}"):
        st.markdown('<div style="font-family:Rajdhani;font-size:.8rem;letter-spacing:.12em;color:#00d4ff">'
                    '📋 DÉCLARATION DE POLITIQUE D\'INVESTISSEMENT</div>', unsafe_allow_html=True)
        st.caption("Comme chez un gérant réglementé (questionnaire d'adéquation MiFID II, IPS du CFA Institute), "
                   "ces réponses fixent les limites que le comité appliquera à ce portefeuille.")
        c1, c2 = st.columns(2)
        objectif = c1.selectbox(L["objectif"], O["objectif"], index=_i("objectif"), key=f"{key}_obj")
        horizon = c2.selectbox(L["horizon"], O["horizon"], index=_i("horizon"), key=f"{key}_hor")
        perte = c1.select_slider(L["perte_max"], O["perte_max"], value=min(O["perte_max"], key=lambda x: abs(x - float(cur.get("perte_max", .15)))),
                                 format_func=lambda x: f"−{x:.0%}", key=f"{key}_pm")
        reaction = c2.selectbox(L["reaction"], O["reaction"], index=_i("reaction"), key=f"{key}_rea")
        liquidite = c1.selectbox(L["liquidite"], O["liquidite"], index=_i("liquidite"), key=f"{key}_liq")
        patrimoine = c2.selectbox(L["patrimoine"], O["patrimoine"], index=_i("patrimoine"), key=f"{key}_pat")
        experience = c1.selectbox(L["experience"], O["experience"], index=_i("experience"), key=f"{key}_exp")
        esg = c2.selectbox(L["esg"], O["esg"], index=_i("esg"), key=f"{key}_esg")
        exclusions = c1.multiselect(L["exclusions"], O["exclusions"], default=[x for x in cur.get("exclusions", []) if x in O["exclusions"]],
                                    key=f"{key}_exc")
        enveloppe = c2.selectbox(L["enveloppe"], O["enveloppe"], index=_i("enveloppe"), key=f"{key}_env")
        couvertures = st.radio(L["couvertures"], O["couvertures"], index=_i("couvertures"), horizontal=True, key=f"{key}_cov")
        ok = st.form_submit_button(submit_label, use_container_width=True)
    if not ok:
        return None
    ips = dict(objectif=objectif, horizon=horizon, perte_max=float(perte), reaction=reaction, liquidite=liquidite,
               patrimoine=patrimoine, experience=experience, esg=esg, exclusions=exclusions, enveloppe=enveloppe,
               couvertures=couvertures)
    if esg == "ESG strict":
        ips["exclusions"] = sorted(set(exclusions) | {"Énergies fossiles", "Armement", "Tabac"})
    return ips


def ips_summary(ips: dict) -> str:
    cons = C.constraints(ips)
    capped = (" · plafonné : " + "; ".join(cons["plafonne_par"])) if cons["plafonne_par"] else ""
    return (f"Profil **{cons['profil']}** (score {cons['score']}/21){capped} · horizon {ips.get('horizon')} · perte max "
            f"−{cons['perte_max']:.0%} · actions ≤ {cons['equity_max']:.0%} · crypto ≤ {cons['crypto_max']:.0%} · "
            f"liquidités ≥ {cons['cash_min']:.0%} · volatilité cible ≤ {cons['vol_cible']:.0%} · {cons['enveloppe']}"
            + (f" · exclusions : {', '.join(sorted(cons['exclusions']))}" if cons["exclusions"] else ""))


@st.cache_data(ttl=1800, show_spinner=False)
def _ctx_cached():
    return C.market_context()


def get_context() -> dict:
    with st.spinner("🧑‍⚖️ Le comité réunit ses données (marchés, actualités, régime)…"):
        return _ctx_cached()


def portfolio_values(port: dict) -> tuple[dict, float, dict]:
    from utils.data import get_multi_prices
    hold = port.get("holdings", {}) or {}
    live = get_multi_prices(tuple(sorted(hold))) if hold else {}
    vals = {t: h.get("qty", 0) * float((live.get(t) or (h.get("avg_price", 0), 0))[0] or h.get("avg_price", 0))
            for t, h in hold.items()}
    return vals, float(port.get("cash", 0.0)), live


def run_review(port: dict, ctx: dict | None = None, store: bool = True) -> dict:
    """Revue complète du portefeuille (IPS du portefeuille ou IPS par défaut du profil)."""
    from utils.compliance import get_profile, normalize_port_type
    ctx = ctx or get_context()
    ips = port.get("ips") or C.default_ips(get_profile().get("risque", "Équilibré"))
    vals, cash, _ = portfolio_values(port)
    perf = None
    try:
        from utils import performance as PF
        s, _ = PF.portfolio_series(port)
        if len(s) >= 2:
            perf = PF.metrics(s, PF.benchmark_series("S&P 500", s.index.min()))
    except Exception:
        perf = None
    rev = C.review_portfolio(vals, cash, ips, ctx, options=port.get("options", []),
                             options_ok=get_profile().get("options_ok", False),
                             port_type=normalize_port_type(port), label=port.get("name", "Portefeuille"), perf=perf)
    if store:
        port["committee"] = C.summary_for_storage(rev)
    return rev


def committee_panel(port: dict, key: str, expanded: bool = False):
    """Panneau « Comité MAM » d'un portefeuille existant : IPS + revue + validation."""
    from utils.data import persist
    inject_css()
    c = port.get("committee") or {}
    head = ("🧑‍⚖️ Comité MAM — " + ({"ok": "validé", "reserve": "validé avec réserves", "veto": "refusé"}[c["verdict"]]
                                    + f" le {c['date']}" if c.get("verdict") else "portefeuille à valider"))
    with st.expander(head, expanded=expanded or not c):
        with st.expander("🏛️ Comité de gestion MIP — l'équipe du desk"):
            render_personas()
        if port.get("ips"):
            st.markdown("**Politique d'investissement :** " + ips_summary(port["ips"]))
            edit = st.checkbox("Modifier la politique d'investissement", key=f"{key}_edit_ips")
        else:
            st.info("Ce portefeuille n'a pas encore de politique d'investissement : remplissez-la pour que le comité "
                    "puisse le juger selon VOS objectifs.")
            edit = True
        if edit:
            new = render_ips_form(f"{key}_ips", port.get("ips"))
            if new:
                port["ips"] = new
                port.pop("committee", None)
                persist()
                st.session_state.pop(f"{key}_rev", None)
                st.success("Politique enregistrée. Soumettez maintenant le portefeuille au comité.")
                st.rerun()
        if port.get("ips") and st.button("🧑‍⚖️ Soumettre au comité", key=f"{key}_submit", use_container_width=True):
            st.session_state[f"{key}_rev"] = run_review(port, store=True)
            persist()
        rev = st.session_state.get(f"{key}_rev")
        if rev and rev.get("label") == port.get("name"):
            render_review(rev)
            if rev["verdict"] != "ok":
                st.caption("Pour appliquer le plan du comité automatiquement : onglet 📈 Optimizer → "
                           "« Optimisation par le comité ».")
