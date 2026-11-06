"""v5.13 — Processus de gestion : stress des scénarios, plan par phases, lignes figées, autocritique, données."""
import numpy as np
import pandas as pd
import pytest

from utils import am_process as AM
from utils import core_params as CP
from utils import prices as P
from utils import scenarios as SC


@pytest.fixture(autouse=True)
def _fresh_params(monkeypatch):
    import utils.alerts as AL
    monkeypatch.setattr(AL, "get_state", lambda k: None)
    monkeypatch.setattr(AL, "set_state", lambda k, v: False)
    CP._LOCAL.clear()
    CP.clear_cache()
    yield
    CP._LOCAL.clear()
    CP.clear_cache()


VALS = {"NVDA": 50000.0, "QQQ": 25000.0, "TLT": 10000.0, "MC.PA": 5000.0}


def test_sector_weights():
    assert AM.sector_weights("NVDA") == ({"Semi-conducteurs": 1.0}, True)
    w, ok = AM.sector_weights("QQQ")
    assert ok and abs(sum(w.values()) - 1) < 1e-9 and w["Technologie"] > 0.3
    assert AM.sector_weights("MC.PA")[0] == {"Consommation discrétionnaire": 1.0}
    assert AM.sector_weights("BTC-USD")[0] == {"Bitcoin": 1.0}
    assert AM.sector_weights("ZZZZ")[1] is False


def test_portfolio_scenarios_and_limit():
    scs = CP.scenarios()
    probs = SC.probabilities(-1.0, scs)
    ps = AM.portfolio_scenarios(VALS, 10000.0, scs, probs, perte_max=0.10)
    assert ps["ok"] and ps["worst"] == "baissier"
    assert ps["scen"]["baissier"]["pct"] < -0.10 and ps["breach"]
    assert ps["scen"]["baissier"]["contrib"][0][0] == "NVDA"
    assert ps["scen"]["haussier"]["pct"] > 0


def test_action_plan_phases_and_frozen():
    scs = CP.scenarios()
    probs = SC.probabilities(-1.0, scs)
    ps = AM.portfolio_scenarios(VALS, 10000.0, scs, probs, perte_max=0.10)
    CP.set_values({"plafond_tech_ia": 0.40})
    expo = SC.exposure_profile(VALS, 10000.0)
    plan = AM.action_plan(VALS, 10000.0, dict(probs=probs, main="baissier"), ps, expo, None, {"NVDA"})
    phases = {a["phase"] for a in plan["actions"]}
    assert AM.PHASES[0] in phases and AM.PHASES[1] in phases and AM.PHASES[2] in phases
    assert "NVDA" in plan["frozen_note"]
    for a in plan["actions"]:
        if a["phase"] == AM.PHASES[0] and "limite" in a["action"]:
            assert "NVDA" not in a["lignes"]            # ligne figée jamais proposée à la vente
    red = next(a for a in plan["actions"] if "tech" in a["action"])
    assert red["montant"] > 0 and "palier" in red["action"]


def test_frozen_params_roundtrip():
    ok, _ = CP.set_frozen([dict(ticker="nvda", portefeuille="*", raison="conviction"),
                           dict(ticker="TLT", portefeuille="Retraite")])
    assert ok and CP.frozen_tickers("Autre") == {"NVDA"} and CP.frozen_tickers("Retraite") == {"NVDA", "TLT"}
    assert "lignes figées" in CP.custom_keys()
    CP.reset("frozen")
    assert not CP.frozen()


def test_build_has_process_and_critique():
    from tests.test_v512_analyse_marche import _mixed_calendar_px
    from utils import market_drivers as MD
    px = _mixed_calendar_px(-0.05)
    an = MD.analyse("Nasdaq 100", 1, px, [], [], [], None, "Prudent",
                    port_ctx=dict(vals=VALS, cash=10000.0, port=dict(name="P", options=[]), hist=None))
    sc = an["scen"]
    assert sc["portfolio"]["ok"] and sc["plan"]["ok"]
    cr = sc["critique"]
    assert 1 <= cr["note"] <= 10 and cr["faiblesses"]
    assert len(sc["process"]) == 6 and sc["process"][0]["ok"] is False          # pas d'IPS
    md = SC.note_markdown(an, sc)
    assert "Plan d'action par phases" in md and "Autocritique" in md
    assert MD.build_pdf(an, px)[:4] == b"%PDF"
    an2 = MD.analyse("Nasdaq 100", 1, px, [], [], [], None, "Équilibré")
    assert an2["scen"]["critique"]["note"] < cr["note"] + 1                       # sans portefeuille : pénalité


def test_drop_sparse_rows():
    idx = pd.date_range("2026-11-02", periods=6)
    px = pd.DataFrame({"A": [1, 2, 3, 4, 5, np.nan], "B": [1, 2, 3, 4, 5, np.nan], "C": [1, 2, 3, 4, 5, 6.0]}, index=idx)
    out = P.drop_sparse_rows(px)
    assert len(out) == 5 and out.index[-1] == idx[4]


def test_admin_drives_process_thresholds_and_compositions():
    from utils import am_process as AM
    # compositions surchargées → stress modifié
    ok, errs = CP.set_compositions({"sp500": {"Technologie": 0.5}})
    assert not ok and "100 %" in errs[0]
    ok, _ = CP.set_compositions({"sp500": {"Technologie": 0.5, "Finance": 0.5}, "nasdaq100": {"Technologie": 1.0}})
    assert ok and AM.sector_weights("SPY")[0] == {"Technologie": 0.5, "Finance": 0.5}
    assert "compositions des indices" in CP.custom_keys()
    # seuils d'autocritique et cohérence
    ok, errs = CP.set_values({"critique_note_prudence": 9.0, "critique_note_solide": 8.0})
    assert not ok and any("prudence" in e for e in errs)
    ok, errs = CP.set_values({"option_jours_min": 40})
    assert not ok and any("roulement" in e for e in errs)
    CP.set_values({"marge_cash_deploiement": 0.0})
    scs = CP.scenarios()
    plan = AM.action_plan({"SPY": 50000.0}, 50000.0, dict(probs=SC.probabilities(1.0, scs), main="haussier"),
                          None, SC.exposure_profile({"SPY": 50000.0}, 50000.0), None)
    assert any("Investir les liquidités" in a["action"] for a in plan["actions"])
    CP.reset("all")
    assert AM.sector_weights("SPY")[0]["Technologie"] == pytest.approx(0.24)
