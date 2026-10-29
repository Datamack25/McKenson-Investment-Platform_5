from utils import compliance as CP

LIVE = dict(price_source="live")


def test_crypto_blocked_for_prudent(port_basic):
    d = CP.pre_trade_spot(port_basic, "BTC-USD", "BUY", 0.1, 60_000, profile={"risque": "Prudent"},
                          prices={"SPY": 500, "TLT": 90, "BTC-USD": 60_000}, **LIVE)
    assert not d.allowed and "C05" in [c.code for c in d.blocks]


def test_concentration_limit(port_basic):
    # 30 000 $ de SPY supplémentaires → ligne > 20 % pour un profil Équilibré
    d = CP.pre_trade_spot(port_basic, "AAPL", "BUY", 150, 200, profile={"risque": "Équilibré"},
                          prices={"SPY": 500, "TLT": 90, "AAPL": 200}, **LIVE)
    assert "C04" in [c.code for c in d.blocks]


def test_no_overdraft(port_basic):
    d = CP.pre_trade_spot(port_basic, "TLT", "BUY", 5_000, 90, profile={"risque": "Agressif"},
                          prices={"SPY": 500, "TLT": 90}, **LIVE)
    assert "C07" in [c.code for c in d.blocks]


def test_sanctioned_instrument(port_basic):
    d = CP.pre_trade_spot(port_basic, "SBER.ME", "BUY", 1, 10, profile={"risque": "Agressif"},
                          prices={"SPY": 500, "TLT": 90, "SBER.ME": 10}, **LIVE)
    assert "C02" in [c.code for c in d.blocks]


def test_small_valid_order_allowed(port_basic):
    d = CP.pre_trade_spot(port_basic, "GLD", "BUY", 10, 200, profile={"risque": "Équilibré"},
                          prices={"SPY": 500, "TLT": 90, "GLD": 200}, **LIVE)
    assert d.allowed, d.short_reason()


def test_naked_call_always_blocked(port_basic):
    legs = [{"type": "call", "qty": -1, "K": 550.0, "premium": 5.0}]
    d, _ = CP.pre_trade_options(port_basic, "SPY", legs, spot=500, mult=100, T_days=60, r=0.04, sigma=0.2,
                                profile={"risque": "Agressif", "options_ok": True}, prices={"SPY": 500, "TLT": 90},
                                **LIVE)
    assert "O03" in [c.code for c in d.blocks]


def test_rules_catalogue_complete():
    assert len(CP.RULES) == 17 and all(len(v) == 3 for v in CP.RULES.values())
