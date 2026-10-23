import io

import numpy as np
import pandas as pd
import pytest

from utils import advisor as A, upload_advisor as U


def test_template_roundtrip_csv_and_xlsx():
    for data, name in ((U.template_csv(), "m.csv"), (U.template_xlsx(), "m.xlsx")):
        p = U.parse_file(data, name)
        assert p["ok"] and not p["erreurs"]
        assert set(p["lignes"]["ticker"]) == {"SPY", "AAPL", "CW8.PA", "TLT", "GLD", "BTC-USD"}
        assert p["cash"] == 8000


def test_synonyms_french_numbers_duplicates_and_errors():
    csv = ("Symbole;Quantité;Valeur;PRU;Commentaire\n"
           "aapl;10;;150,5;x\nAAPL;5;;;y\nMSFT;;1 234,50 €;;z\nBAD TICKER!;1;;;\nTSLA;-3;;;\nLiquidités;;2 000;;\n").encode()
    p = U.parse_file(csv, "f.csv")
    assert p["ok"] and p["cash"] == 2000
    li = p["lignes"].set_index("ticker")
    assert li.loc["AAPL", "quantite"] == 15 and abs(li.loc["MSFT", "montant"] - 1234.5) < 1e-9
    assert any("invalide" in e for e in p["erreurs"]) and any("négatif" in e for e in p["erreurs"])
    assert any("double" in n for n in p["remarques"]) and any("ignorées" in n for n in p["remarques"])


def test_missing_required_columns():
    assert not U.parse_file(b"nom;devise\nApple;USD\n", "f.csv")["ok"]
    assert not U.parse_file(b"ticker;nom\nAAPL;Apple\n", "f.csv")["ok"]


def test_valuation_prefers_live_price_and_falls_back_on_amount():
    p = U.parse_file(b"ticker;quantite;montant;prix_achat\nAAPL;10;;100\nXYZ;;500;\nNOPX;3;;\n", "f.csv")
    df, notes = U.value_lines(p, {"AAPL": (200.0, 0.0)}, {"AAPL": "live"})
    v = df.set_index("Ticker")
    assert v.loc["AAPL", "Valeur"] == 2000 and abs(v.loc["AAPL", "Plus-value %"] - 1.0) < 1e-12
    assert v.loc["XYZ", "Valeur"] == 500
    assert "NOPX" not in v.index and any("NOPX" in n for n in notes)
    assert abs(df["Poids"].sum() - 1) < 1e-9


def test_boards_and_scenarios():
    class M:
        regime = "Stagflation"
        factors = dict(croissance=-0.5, inflation=0.8, monetaire=0.5, credit=-0.2, stress=0.4, dollar=0.3,
                       geopolitique=0.5, energie=0.7)
    idx = pd.bdate_range("2025-06-02", periods=320)
    rng = np.random.default_rng(1)
    px = pd.DataFrame({t: 100 * np.exp(np.cumsum(rng.normal(3e-4, 0.01, len(idx)))) for t in U.board_tickers()}, index=idx)
    s = U.sector_board(px, M())
    assert len(s) == 11 and s["Score"].between(0, 100).all() and s.loc["Énergie", "Lecture du contexte"] == "favorisé"
    r = U.region_board(px, M())
    assert len(r) == len(U.REGIONS) and r["ISO3"].str.len().eq(3).all()
    assert U.sector_board(None, M())["Perf. 3 mois"].isna().all()           # sans historique : contexte seul
    wb = U.class_weights({"SPY": 60_000, "TLT": 30_000}, 10_000)
    sc = U.scenarios(wb, wb, {"Actions": -0.2}, 100_000)
    assert abs(sc.loc["Scénario personnalisé", "Portefeuille actuel"] + 0.12) < 1e-9


def test_warning_names_author():
    assert "PAS UN CONSEIL FINANCIER" in U.WARNING and "Mackenson CINEUS" in U.WARNING
