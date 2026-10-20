import pandas as pd

from utils import committee as CM


def test_ips_most_prudent_constraint_wins():
    ips = CM.default_ips("Agressif")
    ips["horizon"] = "Moins de 2 ans"
    prof, score, why = CM.ips_profile(ips)
    assert prof == "Prudent" and why


def test_vol_target_respects_max_loss():
    ips = CM.default_ips("Équilibré")
    ips["perte_max"] = 0.10
    c = CM.constraints(ips)
    assert abs(c["vol_cible"] * 1.645 - 0.10) < 1e-9 or c["vol_cible"] * 1.645 < 0.10


def test_crypto_exclusion_sets_cap_to_zero():
    ips = CM.default_ips("Dynamique")
    ips["exclusions"] = ["Crypto-actifs"]
    assert CM.constraints(ips)["crypto_max"] == 0.0


def test_only_cro_and_compliance_can_veto():
    a = CM._avis("eco", "veto", "t", [])
    assert a["vote"] == "reserve"
    assert CM._avis("cro", "veto", "t", [])["vote"] == "veto"


def test_creation_veto_for_crypto_with_prudent_profile():
    class M:
        factors = dict(croissance=0, inflation=0, monetaire=0, credit=0, stress=0, dollar=0, geopolitique=0, energie=0)
        regime, regime_text = "Expansion désinflationniste", ""
    rev = CM.review_creation(CM.default_ips("Prudent"), "crypto", ["crypto"], dict(macro=M()), True)
    assert rev["verdict"] == "veto"


def test_biases_detected():
    b = CM.behavioral_biases({"NVDA": 60_000, "BTC-USD": 20_000}, 20_000)
    assert any("concentration" in x for x in b) and any("FOMO" in x for x in b)
