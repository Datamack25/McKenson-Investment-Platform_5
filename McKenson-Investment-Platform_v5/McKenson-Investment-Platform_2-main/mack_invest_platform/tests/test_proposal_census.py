"""v5.7 — portefeuille proposé et ajustable (Trading Desk), comparaison de tous les portefeuilles (admin)."""
import pandas as pd
import pytest

from utils import advisor as A
from utils import committee as CM
from utils import portfolio_census as PC
from utils import portfolio_proposal as PP


class _Macro:
    factors = dict(croissance=0.5, inflation=0, monetaire=0, credit=0, stress=0, dollar=0, geopolitique=0, energie=0)
    regime, regime_text, indicators = "Expansion désinflationniste", "", {}


@pytest.fixture(scope="module")
def ctx():
    px = A._simulated_prices(list(A.ALL_TICKERS), n=600, seed=3)
    return dict(macro=_Macro(), cov=A.class_covariance(px), data_sim=False)


@pytest.fixture
def offline(monkeypatch):
    uni = sorted(set(A.CLASS_PROXY.values()) | set(CM.UCITS_PROXY.values()) | {"XLK", "XLI", "AAPL"})
    R = A._simulated_prices(uni, n=600, seed=9).pct_change().iloc[1:]
    monkeypatch.setattr(CM, "line_returns", lambda t, years=2.2: R[sorted({x for x in t if x in R.columns})])
    return {t: (100.0, 0.0) for t in uni}


def test_proposal_respects_profile_and_explains_each_line(ctx, offline):
    out = PP.build_proposal({}, 100_000, CM.default_ips("Dynamique"), ctx, offline)
    lines = out["lignes"]
    assert not lines.empty and lines["poids"].sum() <= 1 + 1e-9
    assert lines["pourquoi"].str.len().min() > 20 and out["contraintes"]["profil"] == "Dynamique"


def test_crypto_excluded_when_ips_excludes_it(ctx, offline):
    ips = CM.default_ips("Dynamique")
    ips["exclusions"] = ["Crypto-actifs"]
    out = PP.build_proposal({}, 100_000, ips, ctx, offline)
    assert not out["lignes"]["ticker"].str.endswith("-USD").any()


def test_sector_tilt_uses_market_conditions(ctx, offline):
    board = pd.DataFrame({"ETF": ["XLK", "XLI", "XLU"], "Score": [80, 70, 30],
                          "Lecture du contexte": ["favorisé", "favorisé", "pénalisé"],
                          "Perf. 3 mois": [0.08, 0.05, -0.02]},
                         index=["Technologie", "Industrie", "Services publics"])
    out = PP.build_proposal({}, 100_000, CM.default_ips("Dynamique"), ctx, offline, 0.5, board)
    t = set(out["lignes"]["ticker"])
    assert {"XLK", "XLI"} <= t and "XLU" not in t
    assert "Secteur porteur" in out["lignes"].set_index("ticker").loc["XLK", "pourquoi"]
    ips = CM.default_ips("Dynamique")
    ips["enveloppe"] = "PEA"
    w, why = PP.sector_tilt(pd.Series({"SPY": 0.4}), board, CM.constraints(ips), 0.5)
    assert not why                                     # pas d'ETF sectoriel US dans un PEA


def test_user_edits_are_normalized():
    ed = pd.DataFrame({"Ligne": ["SPY", "gld", "ZZZ", "TLT", ""], "Poids (%)": [70, 40, 5, 0, 10]})
    w, msgs = PP.normalize_edit(ed, {"SPY", "GLD", "TLT"})
    assert abs(w.sum() - 1.0) < 1e-9 and set(w.index) == {"SPY", "GLD"}
    assert any("ZZZ" in m for m in msgs) and any("100 %" in m for m in msgs)
    prop = pd.DataFrame({"ticker": ["SPY"], "poids": [0.6]})
    assert PP.is_edited(prop, w) and not PP.is_edited(prop, pd.Series({"SPY": 0.6}))


def test_census_from_state_and_aggregates():
    state = {"teams": {"__solo__": {"name": "Solo", "portfolios": {
        "P1": {"name": "A", "strategy": "growth", "cash": 10_000, "initial_cash": 100_000,
               "holdings": {"SPY": {"qty": 200, "avg_price": 450}},
               "trades": [{"date": "2026-09-01", "ticker": "SPY", "action": "BUY", "qty": 200, "price": 450,
                           "total": 90_000, "source": "Hedge Fund Agent"}],
               "ips": CM.default_ips("Dynamique"), "committee": {"verdict": "ok"}},
        "P2": {"name": "B", "strategy": "income", "cash": 100_000, "initial_cash": 100_000, "holdings": {},
               "trades": []}}}}}
    items = PC.from_state(state, "jena")
    df = PC.summary_table(items, {"SPY": (500.0, 0.0)})
    a = df.set_index("Portefeuille").loc["📁 A"]
    assert abs(a["Performance"] - 0.10) < 1e-9 and a["Profil"] == "Dynamique" and a["Avis du comité"] == "Validé"
    assert a["Construit surtout par"].startswith("Allocation du desk")
    ag = PC.aggregate(df, "Stratégie")
    assert set(ag.index) == {"Growth", "Income"} and ag.index[0] == "Growth"
    assert any("Meilleur portefeuille" in x for x in PC.plain_ranking(df))


def test_census_from_db_rows():
    rows = [dict(id="P9", name="C", emoji="🚀", strategy="Libre", cash=5.0, initial_cash=10.0,
                 holdings='{"AAPL": {"qty": 1, "avg_price": 5}}', options="[]", trades="[]", history="[]",
                 asset_types="[]", ips=None, committee='{"verdict": "veto"}',
                 extras='{"suivi_comite": {"statut": "validée"}}', username="max", team_name="Bulls", team_emoji="🐂",
                 created_at="2026-10-01 10:00")]
    it = PC.from_db_rows(rows)[0]
    assert it["proprietaire"] == "max" and it["port"]["suivi_comite"]["statut"] == "validée"
    r = PC.summary_row(it, {})
    assert r["Avis du comité"] == "Refusé" and r["Valeur"] == 10.0


def test_admin_tab_renders_without_database(monkeypatch):
    from streamlit.testing.v1 import AppTest

    def app():
        import streamlit as st
        from utils import data as D
        state = {"teams": {"__solo__": {"name": "Solo", "portfolios": {
            "P1": {"id": "P1", "name": "A", "strategy": "growth", "cash": 10_000, "initial_cash": 100_000,
                   "holdings": {"SPY": {"qty": 200, "avg_price": 450}},
                   "trades": [{"date": "2026-09-01", "ticker": "SPY", "action": "BUY", "qty": 200, "price": 450,
                               "total": 90_000}]}}}}}
        D.get_or_init_state = lambda: state
        D.get_multi_prices = lambda t: {"SPY": (500.0, 0.0)}
        from components.admin_portfolios import all_portfolios_tab
        all_portfolios_tab()

    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("TOUS LES PORTEFEUILLES" in m.value for m in at.markdown)


def test_trading_desk_proposal_panel_flow():
    """Construire la proposition, la soumettre au comité, voir les ordres — sans réseau."""
    from streamlit.testing.v1 import AppTest

    def app():
        import pandas as pd
        from utils import advisor as A, committee as CM, data as D, performance as PF
        from components import committee_ui as CU

        class _M:
            factors = dict(croissance=0.5, inflation=0, monetaire=0, credit=0, stress=0, dollar=0, geopolitique=0,
                           energie=0)
            regime, regime_text, indicators = "Expansion désinflationniste", "", {}
        px = A._simulated_prices(list(A.ALL_TICKERS), n=600, seed=3)
        uni = sorted(set(A.CLASS_PROXY.values()) | set(CM.UCITS_PROXY.values()) | set(CM.PEA_PROXY.values()))
        R = A._simulated_prices(uni, n=600, seed=9).pct_change().iloc[1:]
        CM.line_returns = lambda t, years=2.2: R[sorted({x for x in t if x in R.columns})]
        CU.get_context = lambda: dict(macro=_M(), cov=A.class_covariance(px), data_sim=False)
        D.get_multi_prices = lambda t: {x: (100.0, 0.0) for x in t}
        D.get_multi_sources = lambda t: {x: "live" for x in t}
        PF.price_history = lambda t, s: pd.DataFrame()
        port = {"id": "PX", "name": "Nouveau", "strategy": "Libre", "cash": 100_000.0, "initial_cash": 100_000.0,
                "holdings": {}, "trades": [], "options": [], "ips": CM.default_ips("Équilibré")}
        from components.proposal_ui import proposal_panel
        proposal_panel(port, "tp")

    at = AppTest.from_function(app, default_timeout=120).run()
    assert not at.exception, [e.value for e in at.exception]
    next(b for b in at.button if "Construire la proposition" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    next(b for b in at.button if "Soumettre" in b.label).click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert any("CONSTRUIRE CE PORTEFEUILLE" in b.label for b in at.button)
