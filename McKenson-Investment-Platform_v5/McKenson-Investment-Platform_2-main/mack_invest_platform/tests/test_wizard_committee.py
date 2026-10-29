"""v5.9 — étape 5 de l'assistant : analyse du comité, boutons vers l'étape à corriger, ajustement proposé."""
from streamlit.testing.v1 import AppTest

from utils import committee as CM


class _M:
    factors = dict(croissance=0, inflation=0, monetaire=0, credit=0, stress=0, dollar=0, geopolitique=0, energie=0)
    regime, regime_text, indicators = "Expansion désinflationniste", "", {}


STRATS = {"growth": ["equity", "etf"], "macro": ["mixed"], "income": ["bond", "etf", "equity"],
          "balanced": ["equity", "bond", "etf"], "etf": ["etf"], "hedging": ["etf", "bond", "forex"],
          "arbitrage": ["equity", "etf", "forex"], "crypto": ["crypto"]}


def test_corrections_point_to_steps():
    ips = CM.default_ips("Équilibré")
    ips["exclusions"] = ["Crypto-actifs"]
    rev = CM.review_creation(ips, "macro", ["mixed", "crypto", "bond"], dict(macro=_M()), True)
    assert rev["verdict"] == "veto"
    assert {c["etape"] for c in rev["corrections"] if c["gravite"] == "veto"} == {3, 4}


def test_fix_keeps_policy_when_possible():
    ips = CM.default_ips("Équilibré")
    ips["exclusions"] = ["Crypto-actifs"]
    fx = CM.propose_creation_fix(ips, "macro", ["mixed", "crypto", "bond"], dict(macro=_M()), True, STRATS)
    assert fx and fx["revue"]["verdict"] != "veto" and not fx["touche_politique"]
    assert "crypto" not in fx["classes"] and fx["strategie"] == "macro"


def test_fix_resolves_contradictory_policy():
    ips = CM.default_ips("Dynamique")
    ips["perte_max"] = 0.10
    ips["objectif"] = CM.IPS_OPTIONS["objectif"][3]            # croissance forte avec 10 % de perte max
    fx = CM.propose_creation_fix(ips, "growth", ["equity"], dict(macro=_M()), True, STRATS)
    assert fx and fx["touche_politique"] and fx["revue"]["verdict"] != "veto"


def test_wizard_step5_flow():
    def app():
        import streamlit as st
        from utils import committee as CM
        from components import committee_ui as CU

        class _M2:
            factors = dict(croissance=0, inflation=0, monetaire=0, credit=0, stress=0, dollar=0, geopolitique=0,
                           energie=0)
            regime, regime_text, indicators = "Expansion désinflationniste", "", {}
        CU.get_context = lambda: dict(macro=_M2())
        ips = CM.default_ips("Équilibré")
        ips["exclusions"] = ["Crypto-actifs"]
        st.session_state.setdefault("wizard_step", 5)
        st.session_state.setdefault("wiz_strat", "macro")
        st.session_state.setdefault("wiz_types", ["mixed", "crypto", "bond"])
        st.session_state.setdefault("wiz_ips", ips)
        st.session_state.setdefault("wiz_name_ok", "Horizon")
        from pages import dashboard
        dashboard._wizard({"teams": {}})

    at = AppTest.from_function(app, default_timeout=60).run()
    assert not at.exception, [e.value for e in at.exception]
    labels = [b.label for b in at.button]
    assert "📦 Modifier les classes d'actifs (étape 3)" in labels
    assert "📋 Modifier la politique d'investissement (étape 4)" in labels
    create = next(b for b in at.button if b.label == "✅ Créer le portefeuille")
    assert create.disabled
    next(b for b in at.button if b.label.startswith("✅ Accepter l'ajustement")).click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert "crypto" not in at.session_state["wiz_types"]
    assert not next(b for b in at.button if b.label == "✅ Créer le portefeuille").disabled
    # bouton « Modifier » : retour à l'étape, puis retour direct au comité
    at2 = AppTest.from_function(app, default_timeout=60).run()
    next(b for b in at2.button if b.label.startswith("📦 Modifier")).click().run()
    assert at2.session_state["wizard_step"] == 3
    assert any(b.label.startswith("🧑‍⚖️ Revenir directement") for b in at2.button)
