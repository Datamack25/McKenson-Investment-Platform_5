# components/smart_money_ui.py  —  MAM v5.11 · Briques d'interface « Tracking Best AM »
"""Chargement des 13F, top 5, cartes d'avis du comité et comparaison portefeuille(s) MIP ↔ meilleurs gérants.
Utilisé par l'onglet 🐋 Tracking Best AM, le sous-onglet de 📥 Conseil portefeuille et la page 📄 Rapports."""
from __future__ import annotations

import html as _h
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from components.ai_shared import PLOT, kpi, kpi_row, md_bold
from components.ui import section_title
from utils import smart_money as SM

_YMAP = {"technology": "Technologie", "communication_services": "Communication & médias",
         "consumer_cyclical": "Consommation discrétionnaire", "consumer_defensive": "Consommation de base",
         "financial_services": "Finance", "healthcare": "Santé", "energy": "Énergie", "industrials": "Industrie",
         "basic_materials": "Matériaux", "utilities": "Services publics", "realestate": "Immobilier"}


def limits_box():
    st.markdown(
        '<div style="border-left:3px solid #ffd700;background:rgba(255,215,0,.05);border-radius:6px;padding:8px 14px;'
        'margin:6px 0 10px;font-family:Share Tech Mono;font-size:.72rem;color:#cbd5e1;line-height:1.55">'
        f'⏳ <b style="color:#ffd700">À LIRE AVANT D\'INTERPRÉTER</b> — {_h.escape(SM.LIMITS_TEXT)}</div>',
        unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  CHARGEMENT DES DONNÉES
# ══════════════════════════════════════════════════════════════════════════════
def current() -> dict | None:
    snap = st.session_state.get("sm_snap")
    if not snap:
        snap = SM.load_cached_snapshot()
        if snap:
            st.session_state["sm_snap"] = snap
    return snap


def loader(key: str = "sm", compact: bool = False) -> tuple[dict | None, list[str]]:
    """Sélection des gérants + téléchargement SEC (ou import de fichier). Renvoie (relevé, gérants analysés)."""
    snap = current()
    with st.expander("📡 Gérants suivis et chargement des données 13F" + (" — données chargées" if snap else ""),
                     expanded=not snap and not compact):
        c1, c2 = st.columns([1, 2])
        preset = c1.selectbox("Sélection rapide", list(SM.PRESETS), key=f"{key}_preset")
        codes = c2.multiselect("Gérants", [m["code"] for m in SM.MANAGERS], default=SM.PRESETS[preset],
                               format_func=lambda c: f"{SM.MANAGER[c]['manager']} — {SM.MANAGER[c]['fund']}",
                               key=f"{key}_codes_{preset}")
        hq = st.slider("Historique (trimestres) — pour savoir depuis quand une position est détenue ou vendue", 2, 8, 4,
                       key=f"{key}_hq", help="Plus de trimestres = réponse plus précise à « depuis quand », chargement plus long")
        c3, c4, c5 = st.columns([1, 1.4, 1])
        cik = c3.text_input("Autre gérant : n° CIK SEC", key=f"{key}_cik", placeholder="ex. 1067983")
        cname = c4.text_input("Nom de ce gérant", key=f"{key}_cname", placeholder="ex. Mon fonds préféré")
        c5.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        go_ = c5.button("📡 Charger depuis la SEC", key=f"{key}_load", type="primary", use_container_width=True)
        st.caption("Les n° CIK se trouvent sur sec.gov/edgar (recherche par nom), Dataroma ou WhaleWisdom. Chargement : "
                   "≈ 1 à 2 s par gérant, plus l'identification des secteurs la première fois (mise en cache ensuite). "
                   "Les grandes sociétés de gestion ont des fichiers très volumineux.")
        if go_:
            custom = []
            if cik.strip().isdigit():
                custom.append(dict(code=f"CIK{int(cik)}", cik=int(cik), manager=cname or f"CIK {int(cik)}",
                                   fund=cname or f"CIK {int(cik)}", style="value", key=""))
            if not codes and not custom:
                st.warning("Choisissez au moins un gérant.")
            else:
                with st.status("Téléchargement des formulaires 13F (SEC EDGAR)…", expanded=True) as stat:
                    snap = SM.build_snapshot(codes, custom, progress=lambda m: stat.write(m), history_quarters=hq)
                    if snap["managers"]:
                        SM.save_snapshot(snap)
                        st.session_state["sm_snap"] = snap
                        stat.update(label=f"{len(snap['managers'])} gérant(s) chargé(s)", state="complete")
                    else:
                        stat.update(label="Aucune donnée reçue de la SEC", state="error")
                for c, e in snap.get("errors", {}).items():
                    st.caption(f"⚠️ {SM.MANAGER.get(c, {}).get('fund', c)} : {e}")
                if not snap["managers"]:
                    st.error("La SEC est injoignable depuis ce serveur (ou l'accès a été refusé). Ajoutez le secret "
                             "`[sec] user_agent = \"Votre nom votre@adresse.com\"`, réessayez plus tard, ou importez un "
                             "fichier ci-dessous.")
                    snap = current()
        st.markdown("**Pas d'accès à la SEC ? Importer un fichier** (export Dataroma, WhaleWisdom, TIKR…)")
        st.dataframe(pd.DataFrame(SM.IMPORT_COLUMNS, columns=["Colonne", "Statut", "Contenu", "Exemple"]),
                     hide_index=True, use_container_width=True)
        i1, i2 = st.columns([2, 1])
        up = i1.file_uploader("Fichier CSV ou Excel", type=["csv", "xlsx"], key=f"{key}_imp", label_visibility="collapsed")
        i2.download_button("⬇️ Modèle CSV", SM.import_template(), "modele_gerants_MAM.csv", "text/csv",
                           key=f"{key}_tpl", use_container_width=True)
        if up is not None and st.session_state.get(f"{key}_imp_done") != up.name:
            s2, errs = SM.parse_import(up.getvalue(), up.name)
            for e in errs:
                st.error(e)
            if s2:
                try:
                    s2["assets_sync"] = SM.sync_assets(s2)
                except Exception:
                    pass
                st.session_state["sm_snap"] = s2
                st.session_state[f"{key}_imp_done"] = up.name
                snap = s2
                st.success(f"{len(s2['managers'])} gérant(s) importé(s).")
    if not snap:
        return None, []
    loaded = list(snap["managers"])
    age = snap.get("age_days")
    periods = sorted({m.get("period") for m in snap["managers"].values() if m.get("period")})
    st.caption(f"📊 Source : {snap.get('source')} · {len(loaded)} gérant(s) · trimestre(s) déclaré(s) : "
               f"{', '.join(periods[-2:]) or '—'} · relevé du {snap.get('built_at')}"
               + (f" (il y a {age} j)" if age else "")
               + (" · ⚠️ trimestres différents selon les gérants" if len(periods) > 1 else ""))
    sync = snap.get("assets_sync") or {}
    if sync.get("ok"):
        st.caption(f"🧺 Univers MIP alimenté : {sync['n']} actif(s) des gérants dans data/assets_best_am.csv "
                   f"({sync.get('new', 0)} nouveau(x)) → Trading Desk, univers « 🐋 Best AM ».")
    newer = [m["fund"] for m in snap["managers"].values() if m.get("newer")]
    if newer:
        st.caption("🆕 Un trimestre plus récent est déjà publié pour : " + ", ".join(newer) +
                   " (non utilisé pour garder une comparaison sur le même trimestre).")
    sel = st.multiselect("Gérants inclus dans l'analyse", loaded, default=loaded, key=f"{key}_use",
                         format_func=lambda c: snap["managers"][c]["fund"])
    return snap, sel or loaded


@st.cache_data(ttl=3600, show_spinner=False)
def _perf(tickers: tuple, start: str) -> dict:
    from utils import performance as PF
    px = PF.price_history(tickers, start)
    out = {}
    if px is None or px.empty:
        return out
    for t in tickers:
        if t in px and px[t].dropna().shape[0] >= 2:
            s = px[t].dropna()
            out[t] = float(s.iloc[-1] / s.iloc[0] - 1)
    return out


def perf_since(snap: dict, codes: list[str], n: int = 15) -> dict:
    """Évolution des titres les plus partagés depuis la fin du trimestre déclaré (effet du délai de 45 jours)."""
    cs = SM.consensus(snap, codes)
    if cs.empty:
        return {}
    periods = sorted({snap["managers"][c].get("period") for c in codes if snap["managers"][c].get("period")})
    if not periods:
        return {}
    tk = tuple(t for t in cs.head(n)["Titre"].astype(str) if t and len(t) <= 6)
    try:
        return _perf(tk, periods[-1])
    except Exception:
        return {}


@st.cache_data(ttl=7 * 86400, show_spinner=False)
def etf_lookthrough(tickers: tuple) -> dict:
    out = {}
    try:
        import yfinance as yf
    except Exception:
        return out
    for t in tickers:
        try:
            sw = yf.Ticker(t).funds_data.sector_weightings
            d = {_YMAP.get(k, "Non classé"): float(v) for k, v in (sw or {}).items() if v}
            if d:
                out[t] = d
        except Exception:
            continue
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def sector_perf_3m() -> dict:
    try:
        from utils import performance as PF
        px = PF.price_history(tuple(SM.SECTOR_ETF.values()), (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d"))
        inv = {v: k for k, v in SM.SECTOR_ETF.items()}
        return {inv[t]: float(px[t].dropna().iloc[-1] / px[t].dropna().iloc[0] - 1) for t in px if px[t].dropna().shape[0] > 2}
    except Exception:
        return {}


def regime() -> str | None:
    try:
        from components.committee_ui import get_context
        return get_context()["macro"].regime
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  AFFICHAGES COMMUNS
# ══════════════════════════════════════════════════════════════════════════════
def top5_cards(snap: dict, codes: list[str]):
    t5 = SM.top5(snap, codes)
    if not t5.get("ok"):
        st.info("Données insuffisantes pour le top 5.")
        return

    def card(title, items, color):
        li = "".join(f'<div style="display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid '
                     f'rgba(255,255,255,.04)"><span style="color:#e2e8f0">{i + 1}. {_h.escape(a)}</span>'
                     f'<span style="color:{color};font-family:Share Tech Mono">{_h.escape(b)}</span></div>'
                     for i, (a, b) in enumerate(items))
        return (f'<div style="flex:1;min-width:250px;border:1px solid {color}44;background:{color}0d;border-radius:10px;'
                f'padding:10px 14px"><div style="font-family:Rajdhani;font-weight:700;letter-spacing:.12em;color:{color};'
                f'font-size:.8rem;margin-bottom:6px">{title}</div><div style="font-size:.8rem">{li}</div></div>')
    sec = [(s, f"{w:.1%}" + (f" · {f * 100:+.1f} pt" if f == f else "")) for s, w, f, _ in t5["sectors"]]
    ass = [(f"{a} · {s}", f"{n} gérant(s) · {w:.1%}") for a, s, n, w, _ in t5["assets"]]
    buys = [(b[0], f"{b[1]} nouv. · {b[2]} renf.") for b in t5["buys"]] or [("—", "")]
    sells = [(s[0], f"{s[1]} all. · {s[2]} sold.") for s in t5["sells"]] or [("—", "")]
    st.markdown('<div style="display:flex;gap:10px;flex-wrap:wrap;margin:6px 0">'
                + card("🏭 TOP 5 SECTEURS (poids moyen · flux)", sec, "#00d4ff")
                + card("💎 TOP 5 ACTIFS", ass, "#00ff88")
                + card("🟢 ACHATS DU TRIMESTRE", buys, "#7cf0b5")
                + card("🔴 VENTES DU TRIMESTRE", sells, "#ff8c9f") + "</div>", unsafe_allow_html=True)


def platforms_box(n: int | None = None):
    rows = "".join(
        f'<tr><td style="padding:6px 8px"><a href="{p["url"]}" target="_blank" style="color:#00d4ff;font-weight:700;'
        f'text-decoration:none">{_h.escape(p["nom"])}</a><div style="font-size:.6rem;color:#64748b">'
        f'{"gratuit" if p["gratuit"] else "en partie payant"}</div></td>'
        f'<td style="padding:6px 8px;color:#cbd5e1;font-size:.74rem">{_h.escape(p["quoi"])}</td>'
        f'<td style="padding:6px 8px;color:#94a3b8;font-size:.72rem">{_h.escape(p["regarder"])}</td></tr>'
        for p in SM.PLATFORMS[:n])
    st.markdown('<div class="mam-table-wrap"><table class="mam-table"><thead><tr>'
                + "".join(f'<th style="font-family:Rajdhani;font-size:.64rem;color:#00d4ff;letter-spacing:.1em;padding:7px 8px;'
                          f'background:rgba(0,212,255,.06);text-align:left">{c}</th>' for c in ["Plateforme", "Ce qu'on y trouve", "Où regarder"])
                + f"</tr></thead><tbody>{rows}</tbody></table></div>", unsafe_allow_html=True)


def avis_cards(avis: list[dict]):
    for i in range(0, len(avis), 2):
        cols = st.columns(2)
        for col, a in zip(cols, avis[i:i + 2]):
            pts = "".join(f"<li style='margin:3px 0'>{md_bold(p)}</li>" for p in a["points"])
            col.markdown(
                f'<div style="border:1px solid {a.get("couleur", "#94a3b8")}55;border-left:4px solid {a.get("couleur", "#94a3b8")};'
                f'background:rgba(0,0,0,.25);border-radius:8px;padding:10px 14px;margin:5px 0;min-height:150px">'
                f'<div style="font-family:Rajdhani;font-weight:700;color:{a.get("couleur", "#e2e8f0")};font-size:.95rem">'
                f'{a.get("emoji", "")} {_h.escape(a.get("nom", ""))}</div>'
                f'<div style="font-family:Share Tech Mono;font-size:.64rem;color:#64748b;margin-bottom:4px">{_h.escape(a["titre"])}</div>'
                f'<ul style="margin:0;padding-left:18px;font-size:.76rem;color:#cbd5e1;line-height:1.5">{pts}</ul></div>',
                unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
#  COMPARAISON PORTEFEUILLE(S) ↔ MEILLEURS GÉRANTS
# ══════════════════════════════════════════════════════════════════════════════
def _sources(extra: dict | None) -> dict:
    from components.ai_shared import all_portfolios
    out = {f"mip::{pid}": (lab, p) for pid, (lab, p) in all_portfolios().items()}
    for k, v in (extra or {}).items():
        out[f"ext::{k}"] = v
    return out


def _values(src_key: str, obj) -> tuple[dict, float, str, dict | None]:
    """(valeurs par ticker, liquidités, profil, portefeuille MIP ou None)."""
    from utils import committee as CM
    from utils.compliance import get_profile
    if src_key.startswith("mip::"):
        from components.committee_ui import portfolio_values
        vals, cash, _ = portfolio_values(obj)
        try:
            prof = CM.constraints(obj.get("ips") or CM.default_ips(get_profile().get("risque", "Équilibré")))["profil"]
        except Exception:
            prof = get_profile().get("risque", "Équilibré")
        return vals, cash, prof, obj
    return dict(obj.get("values", {})), float(obj.get("cash", 0.0)), obj.get("profil", get_profile().get("risque", "Équilibré")), None


def analyse_one(snap, codes, vals, cash, prof, bmode, reg, lookthrough_on) -> dict:
    lt = {}
    if lookthrough_on:
        cand = tuple(sorted(t for t in vals if SM.sector_for_ticker(t) == "ETF & fonds indiciels"))
        if cand:
            lt = etf_lookthrough(cand)
    expo = SM.portfolio_exposure(vals, cash, lt)
    bench = SM.benchmark(snap, codes, bmode)
    comp = SM.compare(expo, bench, snap, codes)
    reasons = SM.explain_differences(expo, comp, bench, snap, codes, reg, prof, sector_perf_3m())
    sugg = SM.suggestions(comp, reg, snap, codes)
    return dict(expo=expo, bench=bench, comp=comp, reasons=reasons, sugg=sugg, profil=prof)


def render_comparison(snap: dict, codes: list[str], key: str = "smc", extra: dict | None = None):
    """Comparer un ou plusieurs portefeuilles (MIP ou importé) aux allocations des meilleurs gérants."""
    srcs = _sources(extra)
    if not srcs:
        st.info("Aucun portefeuille : créez-en un depuis le Dashboard ou importez un fichier dans Conseil portefeuille.")
        return
    active = f"mip::{st.session_state.get('active_portfolio')}"
    default = [k for k in srcs if k.startswith("ext::")][:1] or ([active] if active in srcs else list(srcs)[:1])
    c1, c2 = st.columns([2, 1.3])
    sel = c1.multiselect("Portefeuille(s) à comparer", list(srcs), default=default, format_func=lambda k: srcs[k][0],
                         key=f"{key}_ports", max_selections=6)
    bkind = c2.radio("Référence", ["Moyenne des gérants", "Pondérée par les montants", "Un gérant", "Un style"],
                     key=f"{key}_bk", horizontal=False)
    bcodes, blabel = list(codes), "moyenne des gérants sélectionnés"
    if bkind == "Un gérant":
        g = st.selectbox("Gérant de référence", codes, format_func=lambda c: snap["managers"][c]["fund"], key=f"{key}_one")
        bcodes, blabel = [g], snap["managers"][g]["fund"]
    elif bkind == "Un style":
        styles = sorted({snap["managers"][c].get("style") for c in codes})
        s = st.selectbox("Style", styles, format_func=lambda x: SM.STYLES.get(x, x), key=f"{key}_sty")
        bcodes = [c for c in codes if snap["managers"][c].get("style") == s]
        blabel = SM.STYLES.get(s, s)
    bmode = "Pondérée par les montants" if bkind == "Pondérée par les montants" else "Moyenne des gérants"
    lt_on = st.checkbox("Décomposer les ETF diversifiés par secteur (composition Yahoo Finance)", value=True, key=f"{key}_lt")
    if not sel:
        return
    reg = regime()
    with st.spinner("Comparaison avec les gérants…"):
        res = {}
        for k in sel:
            vals, cash, prof, port = _values(k, srcs[k][1])
            if sum(v for v in vals.values() if v) + cash <= 0:
                continue
            res[k] = analyse_one(snap, bcodes, vals, cash, prof, bmode, reg, lt_on)
            res[k]["port"] = port
    if not res:
        st.info("Les portefeuilles choisis sont vides.")
        return
    st.caption(f"Référence : {blabel} ({len(bcodes)} gérant(s), {bmode.lower()}) · régime officiel du comité : {reg or '—'}")

    # ── Vue d'ensemble (plusieurs portefeuilles) ──
    secs = [s for s in SM.SECTORS if any(s in r["comp"]["sectors"].index for r in res.values())]
    tab = pd.DataFrame({srcs[k][0]: [r["comp"]["sectors"]["Mon portefeuille"].get(s, 0.0) for s in secs] for k, r in res.items()},
                       index=secs)
    first = next(iter(res.values()))
    tab["🐋 Meilleurs gérants"] = [first["bench"]["sectors"].get(s, 0.0) for s in secs]
    fig = go.Figure()
    pal = ["#00d4ff", "#ff8c00", "#7c3aed", "#00ff88", "#ff3b6b", "#ffd700"]
    for i, c in enumerate(tab.columns):
        fig.add_bar(name=c, y=tab.index, x=tab[c] * 100, orientation="h",
                    marker_color="#94a3b8" if c.startswith("🐋") else pal[i % len(pal)])
    fig.update_layout(**PLOT, barmode="group", height=120 + 26 * len(secs) * max(1, len(tab.columns) / 2),
                      legend=dict(orientation="h", y=1.06), title="Poche actions : allocation sectorielle comparée (%)")
    fig.update_yaxes(autorange="reversed")
    st.plotly_chart(fig, use_container_width=True, key=f"{key}_all")
    summ = pd.DataFrame([{"Portefeuille": srcs[k][0], "Poche actions": r["expo"]["equity_share"],
                          "Recouvrement": r["comp"]["overlap"], "Part active": r["comp"]["active_share"],
                          "Titres en commun": len(r["comp"]["common"]), "Top 10 (poche actions)": r["comp"]["top10"],
                          "Lignes": r["expo"]["n_lines"], "Profil": r["profil"]} for k, r in res.items()])
    st.dataframe(summ.style.format({"Poche actions": "{:.0%}", "Recouvrement": "{:.0%}", "Part active": "{:.0%}",
                                    "Top 10 (poche actions)": "{:.0%}"}), hide_index=True, use_container_width=True)
    st.caption("Recouvrement = part de la poche actions investie exactement comme la référence (Σ min des poids) ; "
               "part active = ½ Σ |écarts| (0 % = copie, 100 % = rien en commun).")

    # ── Détail par portefeuille ──
    tabs = st.tabs([srcs[k][0][-38:] for k in res])
    for i, (tb, (k, r)) in enumerate(zip(tabs, res.items())):
        with tb:
            _detail(srcs[k][0], r, snap, bcodes, key=f"{key}_d{i}", reg=reg)


def _detail(name: str, r: dict, snap: dict, codes: list[str], key: str, reg: str | None):
    expo, comp = r["expo"], r["comp"]
    kpi_row([kpi("Poche actions", f"{expo['equity_share']:.0%}", "seule partie comparable aux 13F"),
             kpi("Recouvrement", f"{comp['overlap']:.0%}", "investi comme les gérants"),
             kpi("Part active", f"{comp['active_share']:.0%}", "différence de composition"),
             kpi("Titres en commun", str(len(comp["common"])), ", ".join(comp["common"][:4])),
             kpi("Top 10 de la poche actions", f"{comp['top10']:.0%}", f"gérants : {r['bench'].get('top10', np.nan):.0%}")])
    cl = pd.Series(expo["classes"]).sort_values(ascending=False)
    if len(cl):
        st.caption("Classes d'actifs : " + " · ".join(f"{k} {v:.0%}" for k, v in cl.items()))
    sec = comp["sectors"]
    c1, c2 = st.columns([1.3, 1])
    with c1:
        fig = go.Figure()
        fig.add_bar(name="Mon portefeuille", y=sec.index, x=sec["Mon portefeuille"] * 100, orientation="h", marker_color="#00d4ff")
        fig.add_bar(name="Meilleurs gérants", y=sec.index, x=sec["Meilleurs gérants"] * 100, orientation="h", marker_color="#64748b")
        fig.update_layout(**PLOT, barmode="group", height=70 + 30 * len(sec), legend=dict(orientation="h", y=1.08))
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True, key=f"{key}_bar")
    with c2:
        gap = sec["Écart (pts)"].sort_values()
        fig = go.Figure(go.Bar(x=gap.values * 100, y=gap.index, orientation="h",
                               marker_color=["#ff3b6b" if v < 0 else "#00ff88" for v in gap.values],
                               text=[f"{v * 100:+.0f}" for v in gap.values], textposition="auto"))
        fig.update_layout(**PLOT, height=70 + 30 * len(sec), title="Écart (points) : + = vous êtes au-dessus")
        st.plotly_chart(fig, use_container_width=True, key=f"{key}_gap")
    st.dataframe(sec.style.format({"Mon portefeuille": "{:.1%}", "Meilleurs gérants": "{:.1%}", "Écart (pts)": "{:+.1%}",
                                   "Flux des gérants (pts)": "{:+.2%}"}, na_rep="—"), use_container_width=True)
    if expo.get("lookthrough"):
        st.caption("ETF décomposés par secteur : " + ", ".join(expo["lookthrough"]))

    section_title("POURQUOI CETTE DIFFÉRENCE ?", "🔍")
    icon = {"structure": "🧱", "secteur": "🏭", "style": "🎯", "synthese": "🔗", "alerte": "⚠️"}
    for x in r["reasons"]:
        st.markdown(f'<div style="border:1px solid rgba(255,255,255,.07);border-radius:8px;padding:8px 12px;margin:4px 0;'
                    f'background:rgba(0,0,0,.2)"><b style="color:#e2e8f0;font-family:Rajdhani">{icon.get(x["type"], "•")} '
                    f'{_h.escape(x["titre"])}</b><div style="font-size:.78rem;color:#cbd5e1;line-height:1.55;margin-top:3px">'
                    f'{_h.escape(x["texte"])}</div></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**💎 Titres très partagés par les gérants que vous ne détenez pas**")
        miss = comp["missing"]
        if isinstance(miss, pd.DataFrame) and len(miss):
            st.dataframe(miss[["Titre", "Secteur", "Gérants", "Poids dans la moyenne des gérants", "Nouvelles", "Renforcées"]]
                         .style.format({"Poids dans la moyenne des gérants": "{:.1%}"}), hide_index=True, use_container_width=True)
    with c2:
        st.markdown("**🧭 Vos lignes absentes des portefeuilles des gérants**")
        st.write(", ".join(comp["mine_only"][:20]) or "—")
        if comp["selling"]:
            st.markdown("**⚠️ Vos titres que plusieurs gérants vendent**")
            for k, a, s in comp["selling"]:
                st.caption(f"{k} : {a} allègent · {s} soldent")

    section_title("PISTES DU COMITÉ — À VALIDER PAR VOUS (AUCUN ORDRE N'EST PASSÉ)", "🧑‍⚖️")
    chosen = []
    for i, s in enumerate(r["sugg"]):
        if st.checkbox(f"{s['sens']} — {s['texte']}  ·  ({s['qui']})", key=f"{key}_s{i}", value=False):
            chosen.append(s)
    port = r.get("port")
    b1, b2, b3 = st.columns(3)
    if port is not None and b1.button("✅ Enregistrer mes décisions", key=f"{key}_save", use_container_width=True,
                                      disabled=not chosen):
        from utils.data import persist
        port.setdefault("suivi_gerants", []).append(dict(
            date=datetime.now().strftime("%Y-%m-%d %H:%M"), reference=r["bench"]["label"],
            pistes=[f"{s['sens']} : {s['texte']}" for s in chosen]))
        persist()
        st.success(f"{len(chosen)} décision(s) enregistrée(s) dans le journal du portefeuille. Passez les ordres vous-même "
                   "dans le Trading Desk : chaque ordre sera contrôlé par la conformité.")
    if port is not None and port.get("suivi_gerants"):
        with st.expander(f"📒 Journal des décisions « meilleurs gérants » ({len(port['suivi_gerants'])})"):
            for d in reversed(port["suivi_gerants"][-10:]):
                st.markdown(f"**{d['date']}** · référence : {d['reference']}")
                for p in d["pistes"]:
                    st.caption("• " + p)
    try:
        pdf = SM.build_pdf(snap, codes, reg, name, expo, comp, r["reasons"], r["sugg"], perf_since(snap, codes))
        b2.download_button("📄 Rapport PDF de la comparaison", pdf, f"MAM_vs_gerants_{datetime.now():%Y%m%d}.pdf",
                           "application/pdf", use_container_width=True, key=f"{key}_pdf")
    except Exception as e:
        b2.caption(f"PDF indisponible ({type(e).__name__}).")
    try:
        b3.download_button("📗 Excel", SM.build_excel(snap, codes, comp), f"MAM_vs_gerants_{datetime.now():%Y%m%d}.xlsx",
                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True, key=f"{key}_xlsx")
    except Exception as e:
        b3.caption(f"Excel indisponible ({type(e).__name__}).")
