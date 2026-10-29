# utils/earnings.py  —  MAM v5.6 · Calendrier des publications de résultats
"""
Les publications de résultats trimestriels font bouger un titre bien plus que la
moyenne. Pendant ces périodes, un gérant passe en mode plus tactique : il vérifie
sa thèse, l'exposition de la ligne et le scénario qu'il attend.

* next_earnings(tickers)   → prochaine date de publication connue par ligne (Yahoo Finance)
* earnings_window(...)     → lignes dont la publication tombe dans les N prochains jours
* in_earnings_period(...)  → la ligne est-elle en « période de résultats » (±3 jours) ?

Seules les actions publient des résultats : ETF, devises, futures et crypto-actifs
sont ignorés. Si Yahoo Finance ne répond pas, la date est simplement absente.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

PERIOD_DAYS = 3          # « période de résultats » : 3 jours avant et après la publication


def _is_equity(ticker: str) -> bool:
    try:
        from utils.line_risk import needs_sheet
        return needs_sheet(ticker)
    except Exception:
        t = ticker.upper()
        return not (t.endswith(("=F", "=X", "-USD", "-EUR")) or t.startswith("^"))


def _fetch_one(ticker: str) -> date | None:
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        cal = getattr(tk, "calendar", None)
        cands = []
        if isinstance(cal, dict):
            v = cal.get("Earnings Date")
            cands = list(v) if isinstance(v, (list, tuple)) else ([v] if v is not None else [])
        elif isinstance(cal, pd.DataFrame) and not cal.empty:
            try:
                cands = list(cal.loc["Earnings Date"].values)
            except Exception:
                cands = []
        today = date.today()
        dates = []
        for c in cands:
            try:
                d = pd.Timestamp(c).date()
                if d >= today - timedelta(days=PERIOD_DAYS):
                    dates.append(d)
            except Exception:
                continue
        if not dates:
            try:
                ed = tk.get_earnings_dates(limit=8)
                if ed is not None and len(ed):
                    for ix in ed.index:
                        d = pd.Timestamp(ix).date()
                        if d >= today - timedelta(days=PERIOD_DAYS):
                            dates.append(d)
            except Exception:
                pass
        return min(dates) if dates else None
    except Exception:
        return None


def _cached_fetch():
    try:
        import streamlit as st

        @st.cache_data(ttl=6 * 3600, show_spinner=False)
        def _f(tickers: tuple) -> dict:
            return {t: _fetch_one(t) for t in tickers}
        return _f
    except Exception:
        return lambda tickers: {t: _fetch_one(t) for t in tickers}


def next_earnings(tickers, fetch=None) -> dict[str, date | None]:
    """{ticker: prochaine date de publication} pour les actions de la liste."""
    eq = tuple(sorted({t for t in tickers if t and _is_equity(t)}))
    if not eq:
        return {}
    fetch = fetch or _cached_fetch()
    try:
        return dict(fetch(eq))
    except Exception:
        return {}


def earnings_window(dates: dict[str, date | None], days: int = 30, today: date | None = None) -> pd.DataFrame:
    """Publications prévues dans les `days` prochains jours (ou il y a moins de 3 jours)."""
    today = today or date.today()
    rows = []
    for t, d in (dates or {}).items():
        if d is None:
            continue
        delta = (d - today).days
        if -PERIOD_DAYS <= delta <= days:
            rows.append(dict(ticker=t, date=d, jours=delta,
                             periode=abs(delta) <= PERIOD_DAYS,
                             libelle=("aujourd'hui" if delta == 0 else
                                      f"dans {delta} jour(s)" if delta > 0 else f"il y a {-delta} jour(s)")))
    df = pd.DataFrame(rows)
    return df.sort_values("date").reset_index(drop=True) if not df.empty else df


def in_earnings_period(ticker: str, dates: dict[str, date | None], today: date | None = None) -> date | None:
    d = (dates or {}).get(ticker)
    if d is None:
        return None
    return d if abs((d - (today or date.today())).days) <= PERIOD_DAYS else None


def earnings_sentences(df: pd.DataFrame, weights: dict[str, float] | None = None) -> list[str]:
    """Phrases simples pour les rapports et la revue du comité."""
    out = []
    if df is None or df.empty:
        return out
    for _, r in df.iterrows():
        w = (weights or {}).get(r["ticker"])
        ws = f" ({w:.0%} du portefeuille)" if w else ""
        out.append(f"{r['ticker']}{ws} publie ses résultats {r['libelle']} ({r['date']:%d/%m}) : "
                   + ("le cours peut bouger fortement, vérifiez que votre raison d'investir tient toujours."
                      if r["periode"] else "préparez votre scénario avant la publication."))
    return out


def stamp() -> str:
    return datetime.now().strftime("%d/%m/%Y")
