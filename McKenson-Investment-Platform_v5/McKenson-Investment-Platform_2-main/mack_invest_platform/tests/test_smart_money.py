"""v5.11 — Tracking Best AM : lecture des 13F, consensus, secteurs, comparaison, rapports (sans réseau)."""
import numpy as np
import pandas as pd
import pytest

from utils import smart_money as SM

NS = "http://www.sec.gov/edgar/document/thirteenf/informationtable"


def _xml(rows):
    body = "".join(
        f"<infoTable><nameOfIssuer>{n}</nameOfIssuer><titleOfClass>{c}</titleOfClass><cusip>{cu}</cusip>"
        f"<value>{v}</value><shrsOrPrnAmt><sshPrnamt>{s}</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>"
        + (f"<putCall>{pc}</putCall>" if pc else "") +
        "<investmentDiscretion>SOLE</investmentDiscretion></infoTable>"
        for n, c, cu, v, s, pc in rows)
    return f'<?xml version="1.0"?><informationTable xmlns="{NS}">{body}</informationTable>'.encode()


def test_parse_and_aggregate():
    xml = _xml([("APPLE INC", "COM", "037833100", 1_000_000, 5000, ""),
                ("APPLE INC", "COM", "037833100", 500_000, 2500, ""),     # deux lignes (discrétion différente)
                ("SPDR S&amp;P 500 ETF TR", "TR UNIT", "78462F103", 300_000, 600, "Put")])
    df = SM.parse_infotable(xml, "2026-05-15")
    assert len(df) == 3 and df["value"].sum() == 1_800_000
    eq, op = SM.aggregate(df)
    assert len(eq) == 1 and eq.iloc[0]["shares"] == 7500
    assert len(op) == 1 and op.iloc[0]["put_call"] == "Put"


def test_value_in_thousands_before_2023():
    df = SM.parse_infotable(_xml([("APPLE INC", "COM", "037833100", 1500, 10, "")]), "2022-11-14")
    assert df.iloc[0]["value"] == 1_500_000


def test_quarter_moves():
    cur = pd.DataFrame(dict(cusip=["A", "B", "C"], issuer=["a", "b", "c"], cls="", value=[60.0, 30.0, 10.0],
                            shares=[120.0, 30.0, 10.0]))
    prev = pd.DataFrame(dict(cusip=["A", "B", "D"], issuer=["a", "b", "d"], cls="", value=[50.0, 40.0, 10.0],
                             shares=[100.0, 40.0, 5.0]))
    h, sold = SM.compare_quarters(cur, prev)
    st = dict(zip(h["cusip"], h["status"]))
    assert st == {"A": "Renforcée", "B": "Allégée", "C": "Nouvelle"}
    assert list(sold["cusip"]) == ["D"]
    assert h["weight"].sum() == pytest.approx(1.0)


def test_name_matching():
    names = {SM.norm_name("Alphabet Inc."): [("GOOGL", 1652044), ("GOOG", 1652044)],
             SM.norm_name("BERKSHIRE HATHAWAY INC"): [("BRK-B", 1067983), ("BRK-A", 1067983)],
             SM.norm_name("AT&T INC."): [("T", 732717)]}
    assert SM.match_ticker("ALPHABET INC", "CAP STK CL C", names)[0] == "GOOG"
    assert SM.match_ticker("ALPHABET INC", "CAP STK CL A", names)[0] == "GOOGL"
    assert SM.match_ticker("BERKSHIRE HATHAWAY INC DEL", "CL B NEW", names)[0] == "BRK-B"
    assert SM.match_ticker("AT&T INC", "COM", names)[0] == "T"


def test_sectors():
    assert SM.sic_sector(3674) == "Technologie"
    assert SM.sic_sector(2834) == "Santé"
    assert SM.sic_sector(6798) == "Immobilier"
    assert SM.sic_sector(1311) == "Énergie"
    assert SM.sic_sector(5331) == "Consommation de base"
    assert SM.sector_for_ticker("UBER") == "Industrie"
    assert SM.sector_for_ticker("XLV") == "Santé"
    assert SM.sector_for_ticker("SPY") == "ETF & fonds indiciels"


@pytest.fixture
def snap():
    rows = []
    for code, fund, style, pos in [
        ("BRK", "Berkshire Hathaway", "value", [("AAPL", 40, "Allégée"), ("AXP", 20, "Inchangée"), ("KO", 15, "Inchangée"),
                                                 ("OXY", 15, "Renforcée"), ("UNH", 10, "Nouvelle")]),
        ("PSC", "Pershing Square", "value", [("UBER", 30, "Renforcée"), ("AMZN", 25, "Nouvelle"), ("GOOGL", 25, "Renforcée"),
                                              ("QSR", 20, "Inchangée")]),
        ("COATUE", "Coatue", "growth", [("NVDA", 30, "Renforcée"), ("AMZN", 25, "Renforcée"), ("META", 25, "Nouvelle"),
                                         ("UNH", 20, "Nouvelle")]),
    ]:
        for t, w, s in pos:
            rows.append(dict(code=code, manager=fund, fund=fund, style=style, ticker=t, weight=w / 100, status=s,
                             period="2026-06-30"))
    return SM.build_from_holdings(rows, "test")


def test_consensus_and_top5(snap):
    cs = SM.consensus(snap)
    assert cs.loc["AMZN", "Gérants"] == 2 and cs.loc["UNH", "Nouvelles"] == 2
    t5 = SM.top5(snap)
    assert t5["ok"] and len(t5["sectors"]) == 5 and len(t5["assets"]) == 5
    assert t5["assets"][0][0] == "AMZN"
    sg = SM.signals(snap)
    assert set(sg["cluster"].index) >= {"AMZN", "UNH"}
    sa = SM.sector_allocation(snap)
    assert sa["Moyenne des gérants"].sum() == pytest.approx(1.0)


def test_compare_and_explain(snap):
    vals = {"AAPL": 30_000, "MSFT": 20_000, "TLT": 30_000, "GLD": 10_000, "MC.PA": 10_000}
    expo = SM.portfolio_exposure(vals, 20_000)
    assert 0 < expo["equity_share"] < 1
    assert sum(expo["tickers"].values()) == pytest.approx(1.0)
    bench = SM.benchmark(snap)
    comp = SM.compare(expo, bench, snap)
    assert 0 <= comp["overlap"] <= 1 and 0 <= comp["active_share"] <= 1
    assert "AAPL" in comp["common"]
    rs = SM.explain_differences(expo, comp, bench, snap, None, "Stagflation", "Équilibré")
    assert rs[0]["type"] == "structure" and any(r["type"] == "secteur" for r in rs)
    sg = SM.suggestions(comp, "Stagflation", snap, None)
    assert sg and sg[-1]["sens"] == "Méthode"


def test_interpret_and_reports(snap):
    it = SM.interpret(snap, None, "Expansion désinflationniste", {"AMZN": 0.05})
    assert it["ok"] and {a["id"] for a in it["avis"]} == {"eco", "quant", "cio", "cro", "cmp", "cpm"}
    expo = SM.portfolio_exposure({"AAPL": 50_000, "NVDA": 50_000}, 0)
    comp = SM.compare(expo, SM.benchmark(snap), snap)
    pdf = SM.build_pdf(snap, None, "Stagflation", "Test", expo, comp,
                       SM.explain_differences(expo, comp, SM.benchmark(snap), snap, None, "Stagflation"),
                       SM.suggestions(comp, "Stagflation", snap, None))
    assert pdf[:4] == b"%PDF" and len(pdf) > 20_000
    assert SM.build_excel(snap, None, comp)[:2] == b"PK"
    blocks = SM.report_blocks(snap)
    assert blocks[0][0] == "h" and any(b[0] == "table" for b in blocks)
    assert SM.report_blocks(None)[1][0] == "p"
    assert "Top 5 secteurs" in SM.report_html(snap)


def test_import_file():
    snap, errs = SM.parse_import(SM.import_template(), "x.csv")
    assert snap and len(snap["managers"]) == 2 and not errs
    bad, errs = SM.parse_import(b"a;b\n1;2", "x.csv")
    assert bad is None and errs


def _hist_snap():
    """Un gérant, 4 trimestres : AAA détenu depuis le début, BBB acheté au T1 2026, CCC vendu progressivement puis soldé."""
    from utils.smart_money import aggregate  # noqa: F401
    q = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"]
    def f(rows):
        return pd.DataFrame(rows, columns=["cusip", "issuer", "cls", "value", "shares"])
    cur = f([("AAPL", "APPLE INC", "COM", 600.0, 60.0), ("MSFT", "MICROSOFT", "COM", 300.0, 30.0),
             ("XOM", "EXXON", "COM", 100.0, 10.0)])
    q1 = f([("AAPL", "APPLE INC", "COM", 500.0, 60.0), ("MSFT", "MICROSOFT", "COM", 200.0, 20.0),
            ("XOM", "EXXON", "COM", 200.0, 25.0), ("KO", "COCA COLA", "COM", 100.0, 10.0)])
    q2 = f([("AAPL", "APPLE INC", "COM", 500.0, 60.0), ("XOM", "EXXON", "COM", 300.0, 40.0), ("KO", "COCA COLA", "COM", 200.0, 20.0)])
    q3 = f([("AAPL", "APPLE INC", "COM", 500.0, 60.0), ("XOM", "EXXON", "COM", 400.0, 50.0), ("KO", "COCA COLA", "COM", 100.0, 20.0)])
    e = SM.manager_entry(SM.MANAGER["BRK"], cur, q1, None, q[0], q[1], "2026-08-14", "BERKSHIRE")
    e["history"] = SM.compact_history(list(zip(q, [cur, q1, q2, q3])))
    for h in e["holdings"] + e["sold"]:
        h["ticker"] = h["cusip"]
        h["sector"] = SM.sector_for_ticker(h["cusip"])
    return dict(version="1", source="test", built_at="2026-10-30 10:00", managers={"BRK": e}, errors={})


def test_since_and_most_sold():
    snap = _hist_snap()
    assert SM.quarter_label("2026-06-30") == "T2 2026"
    ph = SM.position_history(snap).set_index("key")
    assert ph.loc["AAPL", "before_window"] and ph.loc["AAPL", "since"] == "2025-09-30"
    assert ph.loc["MSFT", "since"] == "2026-03-31" and not ph.loc["MSFT", "before_window"]
    assert ph.loc["XOM", "selling_since"] == "2025-12-31" and ph.loc["XOM", "sold_pct"] == pytest.approx(0.8)
    assert ph.loc["KO", "sold_out"]
    ms = SM.most_sold(snap).set_index("Titre")
    assert ms.loc["XOM", "Ventes depuis"] == "T4 2025" and ms.loc["XOM", "Part vendue (moyenne)"] == pytest.approx(0.8)
    assert ms.loc["KO", "Soldé par"] == "Berkshire Hathaway"
    mh = SM.most_held(snap).set_index("Titre")
    assert mh.loc["AAPL", "Détenu depuis"] == "avant T3 2025"


def test_equivalents_and_assets_csv(tmp_path):
    snap = _hist_snap()
    eq = SM.equivalents("XOM", "Énergie")
    assert eq["direct"] == "XOM" and eq["etf_us"] == "XLE" and eq["etf_ucits"] == "IUES.L"
    assert SM.equivalents("AAPL", "Technologie")["etf_pea"] == "PANX.PA"
    af = SM.assets_frame(snap)
    assert {"ticker", "name", "category", "contract_mult", "currency", "equivalent_etf_ucits"} <= set(af.columns)
    (tmp_path / "assets.csv").write_text("ticker,name,category,contract_mult,currency\nAAPL,Apple,Equity,100,USD\n")
    (tmp_path / "assets_etf.csv").write_text("ticker,name\n")
    r = SM.sync_assets(snap, None, tmp_path / "assets_best_am.csv")
    assert r["ok"] and r["new"] == 2                     # MSFT et XOM sont nouveaux pour MIP, AAPL existait
    out = pd.read_csv(tmp_path / "assets_best_am.csv")
    assert "IUIT.L" in set(out["ticker"]) and "XOM" in set(out["ticker"])
    blocks = SM.report_blocks(snap)
    assert any(b[0] == "table" and b[1][0][0] == "Les plus vendus" for b in blocks)
