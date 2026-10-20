# components/calibration_ui.py  —  MAM v5.4 · Onglet « Calibration » du Hedge Fund Agent
"""Confronte les hypothèses d'expert à l'historique et, pour un administrateur, applique
la calibration à toute la plateforme (et au traitement planifié)."""
from __future__ import annotations

import html as _h

import numpy as np
import pandas as pd
import streamlit as st

from utils import advisor as A
from utils import calibration as C

try:
    import plotly.graph_objects as go
    _PLOTLY = True
except Exception:  # pragma: no cover
    _PLOTLY = False

_SHORT = {"croissance": "Croiss.", "inflation": "Infl.", "monetaire": "Monét.", "credit": "Crédit",
          "stress": "Stress", "dollar": "Dollar", "geopolitique": "Géopo.", "energie": "Énergie"}


def _is_admin() -> bool:
    user = st.session_state.get("mam_user") or {}
    return bool(st.session_state.get("admin_authenticated") or user.get("role") == "admin")


def _pct(x, d=0):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{d}%}"


def _heat(m: pd.DataFrame, title: str, key: str, zmin=-1, zmax=1, fmt="+.1f"):
    m = m.rename(columns=_SHORT)
    if not _PLOTLY:
        st.caption(title); st.dataframe(m, use_container_width=True); return
    z = m.values.astype(float)
    txt = [["" if not np.isfinite(v) else format(v, fmt) for v in row] for row in z]
    fig = go.Figure(go.Heatmap(z=z, x=list(m.columns), y=list(m.index), zmin=zmin, zmax=zmax,
                               colorscale=[[0, "#ff3b6b"], [0.5, "#0f172a"], [1, "#00ff88"]],
                               text=txt, texttemplate="%{text}", showscale=False, hoverongaps=False))
    fig.update_layout(title=title, height=380, margin=dict(l=10, r=10, t=40, b=10),
                      paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(color="#cbd5e1", size=11), yaxis=dict(autorange="reversed"))
    st.plotly_chart(fig, use_container_width=True, key=key)


def _status():
    act = C.active()
    if not act:
        st.info("Aucune calibration appliquée : la plateforme utilise les **hypothèses d'expert** "
                "(matrice de sensibilité, volatilités des stratégies, couvertures, seuils d'alerte).")
        return
    parts = []
    if act.get("sensibilite"):
        parts.append(f"matrice de sensibilité mixte ({act['sensibilite'].get('poids', 0):.0%} estimée)")
    if act.get("strategies"):
        parts.append(f"volatilités de {len(act['strategies'])} stratégies")
    if act.get("couvertures"):
        parts.append(f"paramètres de {len(act['couvertures'])} couvertures")
    if act.get("alertes"):
        parts.append("seuils d'alerte")
    st.success(f"Calibration appliquée le {act.get('date', '?')} : " + (", ".join(parts) or "aucun élément") + ".")


def render():
    t_cal, t_bt = st.tabs(["🧪 Calibration des hypothèses", "📊 Backtest du desk"])
    with t_cal:
        _render_calibration()
    with t_bt:
        _render_backtest()


def _render_calibration():
    st.markdown("Le desk repose sur des **hypothèses d'expert** (sensibilités, volatilités typiques, chocs, seuils). "
                "Cet onglet les confronte à **10 ans d'historique réel** et propose des valeurs calibrées. "
                "On ne calibre jamais sur des données simulées ; une calibration ne s'applique qu'après validation "
                "d'un administrateur, et les valeurs d'expert restent le repli.")
    _status()
    c1, c2 = st.columns([1, 2])
    run = c1.button("🧪 Lancer la calibration (10 ans)", key="cal_run", use_container_width=True, type="primary")
    c2.caption("Téléchargement d'environ 30 séries sur 10 ans (mis en cache une heure), puis régressions et "
               "calculs de fréquence : compter de quelques secondes à une minute.")
    if run:
        with st.spinner("Calibration en cours…"):
            px, missing = C.load_history()
            st.session_state["cal_res"] = dict(
                sens=C.estimate_sensitivity(px, missing), strat=C.calibrate_strategy_vols(px, missing),
                hedge=C.calibrate_hedges(px, missing), alerts=C.calibrate_alerts(px, missing),
                n_sim=len(missing), periode=(str(px.index[0].date()), str(px.index[-1].date())))
    res = st.session_state.get("cal_res")
    if not res:
        return
    if res["n_sim"]:
        st.warning(f"{res['n_sim']} série(s) sans historique réel (repli simulé) : les éléments qui en dépendent "
                   "gardent la valeur d'expert.")
    st.caption(f"Historique utilisé : du {res['periode'][0]} au {res['periode'][1]}.")
    tabs = st.tabs(["🧭 Matrice de sensibilité", "📐 Volatilité des stratégies", "🛡️ Couvertures",
                    "🔔 Seuils d'alerte", "✅ Appliquer"])

    # ── 1. Matrice ───────────────────────────────────────────────────────────
    with tabs[0]:
        r = res["sens"]
        if not r.get("ok"):
            st.info(r.get("detail"))
        else:
            k = st.columns(4)
            k[0].metric("Semaines analysées", f"{r['n_semaines']}")
            k[1].metric("Corrélation expert / estimée", f"{r['correlation']:+.2f}")
            k[2].metric("Signes concordants", _pct(r["accord_signes"]),
                        help="Parmi les cellules où l'expert est net (|coef| ≥ 0,3) et l'estimation significative (|t| ≥ 2).")
            k[3].metric("Fenêtres de 3 ans", f"{r['fenetres']}")
            a, b = st.columns(2)
            with a:
                _heat(A.SENSITIVITY, "Matrice d'expert", "cal_h1")
            with b:
                _heat(r["estimee"], "Matrice estimée (historique)", "cal_h2")
            a, b = st.columns(2)
            with a:
                _heat(r["t"], "Statistique t (|t| ≥ 2 : significatif)", "cal_h3", -4, 4, "+.1f")
            with b:
                _heat(r["stabilite"] * 2 - 1, "Stabilité du signe sur les fenêtres (vert = stable)", "cal_h4", -1, 1, "+.1f")
            if r["desaccords"]:
                st.markdown("**Désaccords nets entre l'expert et l'historique**")
                st.dataframe(pd.DataFrame(r["desaccords"]).rename(columns={
                    "classe": "Classe", "facteur": "Facteur", "expert": "Expert", "estime": "Estimé",
                    "t": "t", "stabilite": "Stabilité du signe"}), use_container_width=True, hide_index=True)
            else:
                st.success("Aucun désaccord net de signe entre l'expert et l'historique.")
            st.caption(r["note"])

    # ── 2. Stratégies ────────────────────────────────────────────────────────
    with tabs[1]:
        d = res["strat"].copy()
        st.markdown("Volatilité typique utilisée par **Aline DE MARGE** dans la revue de création "
                    "(perte potentielle à un an = 1,645 × volatilité).")
        show = pd.DataFrame({
            "Stratégie": d["strategie"], "Panier représentatif": d["panier"],
            "Expert": d["expert"].map(lambda v: _pct(v)), "Calibrée": d["calibree"].map(lambda v: _pct(v, 1)),
            "Vol. en période agitée (90e centile)": d["vol_stress"].map(lambda v: _pct(v)),
            "Perte max historique": d["perte_max"].map(lambda v: _pct(v)), "Années": d["annees"].round(1),
            "Source": d["source"]})
        st.dataframe(show, use_container_width=True, hide_index=True)

    # ── 3. Couvertures ───────────────────────────────────────────────────────
    with tabs[2]:
        h = res["hedge"].copy()
        st.markdown("Pour chaque panier : volatilité de l'ETF de couverture rapportée au VIX, choc de référence "
                    "(5 % des pires rendements à 3 mois) et lien entre le **niveau de risque du panier** et la "
                    "**probabilité d'une forte baisse** dans les 3 mois (régression logistique).")
        rows = []
        for cle, x in h.iterrows():
            ok = x.get("source") == "historique"
            rows.append({
                "Panier": x["panier"], "ETF": x["etf"],
                "Multiplicateur de vol. (expert → calibré)": f"{x['vol_expert']:.2f} → {x['vol_calibre']:.2f}" if ok else f"{x['vol_expert']:.2f}",
                "Choc (expert → calibré)": f"{x['choc_expert']:.0%} → {x['choc_calibre']:.0%}" if ok else f"{x['choc_expert']:.0%}",
                "Forte baisse (fréquence)": f"{_pct(x.get('frequence'))} (≤ {x['seuil_perte']:.0%})" if ok else "—",
                "Proba. si risque 0 / 1": (f"{_pct(x.get('p_risque_0'))} / {_pct(x.get('p_risque_1'))}"
                                           if ok and pd.notna(x.get("p_risque_0")) else "—"),
                "Le risque prédit-il les baisses ?": ("oui" if x.get("predictif") else "non : part de base 25 %") if ok else "—",
                "Seuil de recommandation": (f"{x['seuil_reco']:+.2f}" if ok and pd.notna(x.get("seuil_reco")) else "—"),
                "Source": x.get("source", "—")})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption("Règle calibrée : part couverte = 25 % + 25 % × (probabilité de forte baisse / probabilité moyenne − 1), "
                   "bornée entre 25 et 75 % ; une probabilité doublée → 50 %, triplée → 75 %. La couverture est "
                   "recommandée au-delà du seuil où la probabilité dépasse la moyenne. Si le niveau de risque ne "
                   "prédit pas les baisses sur l'historique, la règle d'expert est conservée.")

    # ── 4. Alertes ───────────────────────────────────────────────────────────
    with tabs[3]:
        al = res["alerts"]
        if not al.get("ok"):
            st.info(al.get("detail"))
        else:
            st.markdown(f"Seuils choisis pour atteindre une **fréquence cible** d'alertes (sur {al['mois']:.0f} mois "
                        "d'historique, tous actifs surveillés confondus).")
            df = pd.DataFrame(al["lignes"])
            fmt = lambda v: "—" if isinstance(v, float) and not np.isfinite(v) else (f"{v:.1f}" if isinstance(v, float) else v)
            st.dataframe(pd.DataFrame({
                "Règle": df["regle"], "Gravité": df["gravite"], "Seuil expert": df["expert"].map(fmt),
                "Alertes / mois (expert)": df["freq_expert"].map(fmt), "Seuil calibré": df["calibre"].map(fmt),
                "Alertes / mois (calibré)": df["freq_calibree"].map(fmt), "Cible / mois": df["cible"].map(fmt)}),
                use_container_width=True, hide_index=True)

    # ── 5. Appliquer ─────────────────────────────────────────────────────────
    with tabs[4]:
        if not _is_admin():
            st.info("Seul un administrateur peut appliquer une calibration : elle modifie le comportement de la "
                    "plateforme pour tous les utilisateurs et du traitement planifié.")
            return
        r = res["sens"]
        use_s = st.checkbox("Matrice de sensibilité mixte", value=bool(r.get("ok")), disabled=not r.get("ok"), key="cal_ap_s")
        w = st.slider("Poids de la matrice estimée", 0.0, 1.0, 0.5, 0.05, disabled=not (use_s and r.get("ok")),
                      key="cal_w", help="0 = expert seul · 1 = historique seul. Une cellule non estimée garde l'expert.")
        sv = res["strat"]
        n_sv = int((sv["source"] == "historique").sum())
        use_v = st.checkbox(f"Volatilités des stratégies ({n_sv} calibrée(s))", value=n_sv > 0, disabled=n_sv == 0, key="cal_ap_v")
        hd = res["hedge"]
        n_h = int((hd["source"] == "historique").sum())
        use_h = st.checkbox(f"Paramètres des couvertures ({n_h} panier(s))", value=n_h > 0, disabled=n_h == 0, key="cal_ap_h")
        al = res["alerts"]
        use_a = st.checkbox("Seuils d'alerte", value=bool(al.get("ok")), disabled=not al.get("ok"), key="cal_ap_a")
        b1, b2 = st.columns(2)
        if b1.button("✅ Appliquer la calibration", key="cal_apply", type="primary", use_container_width=True):
            payload = {}
            if use_s and r.get("ok"):
                payload["sensibilite"] = dict(poids=w, matrice=C.blend(r["estimee"], w).to_dict(),
                                              periode=r["periode"], correlation=r["correlation"])
            if use_v and n_sv:
                payload["strategies"] = {k: float(v) for k, v in sv["calibree"].dropna().items()}
            if use_h and n_h:
                keep = ["vol_calibre", "choc_calibre", "seuil_perte", "frequence", "predictif", "logit_a", "logit_b", "seuil_reco"]
                payload["couvertures"] = {k: {c: (bool(x[c]) if c == "predictif" else float(x[c]))
                                              for c in keep if c in x and pd.notna(x[c])}
                                          for k, x in hd[hd["source"] == "historique"].iterrows()}
            if use_a and al.get("ok"):
                payload["alertes"] = al["seuils"]
            if not payload:
                st.warning("Rien à appliquer.")
            elif C.save_active(payload):
                st.success("Calibration appliquée à la plateforme et au traitement planifié.")
                st.rerun()
            else:
                st.error("Enregistrement impossible : la base de données n'est pas joignable.")
        if b2.button("↩️ Revenir aux hypothèses d'expert", key="cal_reset", use_container_width=True):
            if C.save_active({}):
                st.success("Hypothèses d'expert rétablies.")
                st.rerun()
            else:
                st.error("Enregistrement impossible : la base de données n'est pas joignable.")


def _render_backtest():
    from utils import backtest_desk as B
    st.markdown("Rejoue **mois par mois, sans information future**, la chaîne du desk (facteurs → régime → "
                "inclinaisons → moteur de risque) sur l'historique réel, et la compare à l'**allocation "
                "stratégique** du profil. Le portefeuille intermédiaire « stratégique + moteur de risque » isole "
                "l'apport du contrôle des risques de celui de la vue macro.")
    c = st.columns([1.2, 1, 1, 1.2])
    prof = c[0].selectbox("Profil", list(A.PROFILES), index=1, key="bt_prof")
    lam = c[1].slider("Intensité tactique", 0.0, 1.0, 0.5, 0.1, key="bt_int")
    cost = c[2].number_input("Coût (pb par ordre)", 0.0, 50.0, 10.0, 1.0, key="bt_cost")
    mat = c[3].radio("Matrice de sensibilité", ["Expert", "Active (calibrée)"], key="bt_mat",
                     help="La matrice estimée l'est sur toute la période : la backtester avec elle revient à "
                          "utiliser de l'information future (résultat flatteur).")
    if st.button("▶️ Lancer le backtest", key="bt_run", type="primary"):
        with st.spinner("Backtest walk-forward en cours…"):
            px, missing = C.load_history()
            st.session_state["bt_res"] = B.run(px, missing, prof, lam,
                                               matrix=None if mat == "Expert" else C.active_sensitivity(),
                                               cost_bp=cost)
            st.session_state["bt_mat_used"] = mat
    r = st.session_state.get("bt_res")
    if not r:
        return
    if not r.get("ok"):
        st.info(r.get("detail"))
        return
    if st.session_state.get("bt_mat_used", "Expert") != "Expert" and C.active().get("sensibilite"):
        st.warning("Backtest réalisé avec la matrice calibrée sur toute la période : résultat en partie « en "
                   "échantillon », donc optimiste.")
    nav = r["nav"]
    if _PLOTLY:
        fig = go.Figure()
        for n, col, dash in zip(B.NAMES, ["#e2e8f0", "#ffd700", "#00ff88"], ["dash", "dot", "solid"]):
            fig.add_trace(go.Scatter(x=nav.index, y=nav[n] * 100, name=n, mode="lines",
                                     line=dict(color=col, dash=dash, width=2)))
        fig.update_layout(height=340, margin=dict(l=8, r=8, t=10, b=8), paper_bgcolor="rgba(0,0,0,0)",
                          plot_bgcolor="rgba(0,0,0,0)", font=dict(color="#94a3b8"), hovermode="x unified",
                          legend=dict(orientation="h", y=1.1), yaxis=dict(title="Base 100", gridcolor="#1e293b"))
        st.plotly_chart(fig, use_container_width=True, key="bt_fig")
    st_ = r["stats"]
    d, s0 = st_.loc["Desk complet"], st_.loc["Allocation stratégique"]
    k = st.columns(4)
    k[0].metric("Valeur ajoutée annuelle du desk", f"{d['Rendement annualisé'] - s0['Rendement annualisé']:+.2%}")
    ir = d["Ratio d'information"]
    k[1].metric("Ratio d'information", "—" if pd.isna(ir) else f"{ir:.2f}")
    k[2].metric("Mois gagnants", f"{r['mois_gagnants']:.0%}", help=f"Sur {r['n_mois']} mois.")
    k[3].metric("Perte max (desk / stratégique)", f"{d['Perte max']:.0%} / {s0['Perte max']:.0%}")
    st.dataframe(st_.style.format({"Rendement annualisé": "{:+.2%}", "Volatilité": "{:.2%}", "Sharpe": "{:.2f}",
                                   "Perte max": "{:.1%}", "Écart de suivi": "{:.2%}",
                                   "Ratio d'information": "{:.2f}", "Rotation moyenne / mois": "{:.1%}"}, na_rep="—"),
                 use_container_width=True)
    a, b = st.columns(2)
    with a:
        st.markdown("**Par régime économique (desk − stratégique)**")
        st.dataframe(r["par_regime"].style.format({"Surperformance moyenne / mois": "{:+.2%}", "Mois gagnants": "{:.0%}"}),
                     use_container_width=True)
    with b:
        st.markdown("**Par année**")
        st.dataframe(r["annuel"].style.format("{:+.1%}"), use_container_width=True)
    st.caption(f"Profil {r['profil']}, intensité {r['intensite']:.0%}, du {r['periode'][0]} au {r['periode'][1]}, "
               f"coût {r['cout_bp']:.0f} pb par unité de rotation. Rééquilibrage mensuel, facteurs sans composante "
               "actualité (pas d'historique), facteur géopolitique à 0 : le backtest mesure la partie « marché » du "
               "desk. Les performances passées ne préjugent pas des performances futures.")
