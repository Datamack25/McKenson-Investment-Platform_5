from utils.sectors import sector_of, option_sector


def test_sectors():
    assert sector_of("AAPL") == "Technologie"
    assert sector_of("XLV") == "ETF sectoriel — Santé"
    assert sector_of("ES=F").startswith("Dérivé — future")
    assert sector_of("BTC-USD") == "Crypto-actif"
    assert option_sector({"type": "put", "ticker": "QQQ"}) == "Option PUT sur Technologie / Nasdaq 100 (QQQ)"
