# utils/prices.py  —  MAM v5.12 · Cours fiables (correction des faux « +0,0 % »)
"""
Pourquoi ce module ?
--------------------
Les analyses de marché téléchargeaient ensemble des actifs aux calendriers différents (indices US,
pétrole et dollar qui cotent presque 24 h/24, bitcoin qui cote le week-end…). Le tableau commun
contenait donc des lignes où l'indice n'avait PAS coté (aujourd'hui avant l'ouverture de Wall Street,
un week-end, un jour férié) et un `ffill()` recopiait la clôture de la veille dans ces lignes.
Résultat : la « dernière séance » comparait deux fois le même cours → variation de 0,0 %, z-score
nul, « Nasdaq stable », graphiques sectoriels et grandes capitalisations entièrement vides.

Règles appliquées partout :
  * chaque série est lue sur SES propres jours de cotation (`true_closes`) : pas de recopie, et les
    recopies déjà présentes (valeur identique à la veille) sont retirées ;
  * une variation se calcule entre deux clôtures distinctes et complètes (`change`) et renvoie
    NaN — jamais 0 — quand la donnée manque : l'interface affiche alors « donnée indisponible » ;
  * la date de chaque séance utilisée est conservée pour être affichée ;
  * la colonne « Close » est extraite quel que soit le format renvoyé par yfinance (MultiIndex
    Price/Ticker ou Ticker/Price, un seul ticker, « Adj Close » absent avec auto_adjust).
"""
from __future__ import annotations

import time
from datetime import datetime

import numpy as np
import pandas as pd

NAN = float("nan")


# ══════════════════════════════════════════════════════════════════════════════
#  EXTRACTION ROBUSTE
# ══════════════════════════════════════════════════════════════════════════════
def extract_closes(raw: pd.DataFrame | None, tickers: list[str] | tuple) -> pd.DataFrame:
    """Colonnes = tickers, valeurs = clôtures, quel que soit le format renvoyé par yf.download."""
    tickers = list(tickers)
    if raw is None or getattr(raw, "empty", True):
        return pd.DataFrame()
    df = raw
    if isinstance(df.columns, pd.MultiIndex):
        lv0 = set(map(str, df.columns.get_level_values(0)))
        lv1 = set(map(str, df.columns.get_level_values(1)))
        field = next((f for f in ("Close", "Adj Close") if f in lv0), None)
        if field:
            px = df[field]
        else:
            field = next((f for f in ("Close", "Adj Close") if f in lv1), None)
            if not field:
                return pd.DataFrame()
            px = df.xs(field, axis=1, level=1)
    else:
        field = next((f for f in ("Close", "Adj Close") if f in df.columns), None)
        if field:
            px = df[[field]].rename(columns={field: tickers[0] if tickers else field})
        else:   # déjà un tableau de clôtures
            px = df
    if isinstance(px, pd.Series):
        px = px.to_frame(tickers[0] if tickers else "close")
    px = px.apply(pd.to_numeric, errors="coerce")
    if getattr(px.index, "tz", None) is not None:
        px.index = px.index.tz_localize(None)
    px.index = pd.to_datetime(px.index)
    px = px[~px.index.duplicated(keep="last")].sort_index()
    return px.dropna(how="all")


def drop_sparse_rows(px: pd.DataFrame, min_share: float = 0.5) -> pd.DataFrame:
    """Retire les lignes où moins de `min_share` des actifs ont coté (week-end porté par le bitcoin, matinée où
    seuls le pétrole et le dollar cotent…) AVANT un éventuel ffill : sinon ces lignes recopient la veille et
    créent de faux rendements nuls (volatilité et corrélations sous-estimées)."""
    if px is None or px.empty or px.shape[1] < 3:
        return px
    return px[px.notna().mean(axis=1) >= min_share]


def download_closes(tickers, period: str = "2y", interval: str = "1d", retries: int = 2) -> tuple[pd.DataFrame, list[str]]:
    """Téléchargement Yahoo avec nouvelles tentatives. Renvoie (clôtures SANS recopie, tickers manquants)."""
    tickers = sorted({str(t) for t in tickers if t})
    if not tickers:
        return pd.DataFrame(), []
    px = pd.DataFrame()
    try:
        import yfinance as yf
    except Exception:
        return pd.DataFrame(), tickers
    for attempt in range(retries + 1):
        try:
            raw = yf.download(tickers, period=period, interval=interval, auto_adjust=True, progress=False,
                              threads=True, group_by="column")
            px = extract_closes(raw, tickers)
        except Exception:
            px = pd.DataFrame()
        missing = [t for t in tickers if t not in px.columns or px[t].dropna().empty]
        if not missing or attempt == retries:
            break
        time.sleep(1.0 + attempt)
        try:   # deuxième passe uniquement sur les manquants (souvent un échec réseau ponctuel)
            raw2 = yf.download(missing, period=period, interval=interval, auto_adjust=True, progress=False,
                               threads=False, group_by="column")
            px2 = extract_closes(raw2, missing)
            if not px2.empty:
                px = px.join(px2[[c for c in px2.columns if c not in px.columns or px[c].dropna().empty]],
                             how="outer", rsuffix="_r") if not px.empty else px2
                px = px[[c for c in px.columns if not str(c).endswith("_r")]]
        except Exception:
            pass
    missing = [t for t in tickers if t not in px.columns or px[t].dropna().empty]
    return px, missing


# ══════════════════════════════════════════════════════════════════════════════
#  SÉRIES PROPRES ET VARIATIONS
# ══════════════════════════════════════════════════════════════════════════════
def true_closes(s: pd.Series | None) -> pd.Series:
    """Clôtures réelles d'UN actif : sans valeur manquante ni recopie (valeur identique à la veille)."""
    if s is None:
        return pd.Series(dtype=float)
    s = pd.to_numeric(s, errors="coerce").dropna()
    if len(s) < 2:
        return s
    return s[s.ne(s.shift())]


def change(s: pd.Series | None, n: int = 1) -> dict:
    """Variation sur `n` séances réelles. ok=False et ret=NaN si la donnée manque (jamais 0 inventé)."""
    c = true_closes(s)
    if len(c) <= n:
        return dict(ok=False, ret=NAN, last=NAN, start=None, end=None, n=n)
    a, b = float(c.iloc[-n - 1]), float(c.iloc[-1])
    return dict(ok=True, ret=b / a - 1 if a else NAN, last=b, start=c.index[-n - 1], end=c.index[-1], n=n)


def change_since(s: pd.Series | None, since) -> dict:
    """Variation depuis une date (ex. 1er janvier pour le « depuis le début de l'année »)."""
    c = true_closes(s)
    if c.empty:
        return dict(ok=False, ret=NAN)
    base = c[c.index < pd.Timestamp(since)]
    if base.empty:
        return dict(ok=False, ret=NAN)
    return dict(ok=True, ret=float(c.iloc[-1] / base.iloc[-1] - 1), start=base.index[-1], end=c.index[-1])


def log_returns(s: pd.Series | None) -> pd.Series:
    return np.log(true_closes(s)).diff().dropna()


_SESSION = {"us": ("America/New_York", 16, 0), "eu": ("Europe/Paris", 17, 35), "jp": ("Asia/Tokyo", 15, 0)}


def session_status(last_date, region: str | None, now: datetime | None = None) -> dict:
    """La dernière « clôture » est-elle une séance terminée ou une séance EN COURS ?
    Yahoo renvoie, pendant la séance, une barre quotidienne du jour avec le DERNIER cours (≈ 15 min de différé)."""
    try:
        from zoneinfo import ZoneInfo
        d = pd.Timestamp(last_date).date()
        tz, hh, mm = _SESSION.get(region or "", (None, None, None))
        if tz is None:   # actifs cotés quasi en continu (or, pétrole, bitcoin) : la barre du jour est toujours partielle
            loc = (now or datetime.now(ZoneInfo("Europe/Paris")))
            loc = loc if loc.tzinfo else loc.replace(tzinfo=ZoneInfo("Europe/Paris"))
            live = d >= loc.date()
            return dict(live=live, label="cours en séance" if live else "clôture", tz="Europe/Paris")
        loc = (now.astimezone(ZoneInfo(tz)) if (now and now.tzinfo) else
               (now.replace(tzinfo=ZoneInfo("Europe/Paris")).astimezone(ZoneInfo(tz)) if now else datetime.now(ZoneInfo(tz))))
        live = d == loc.date() and (loc.hour, loc.minute) < (hh, mm)
        return dict(live=live, label="cours en séance" if live else "clôture", tz=tz,
                    local=loc.strftime("%H:%M"))
    except Exception:
        return dict(live=False, label="clôture")


def stale(s: pd.Series | None, max_days: int = 5, now: datetime | None = None) -> bool:
    """Vrai si la dernière clôture date de plus de `max_days` jours calendaires."""
    c = true_closes(s)
    if c.empty:
        return True
    return (pd.Timestamp(now or datetime.now()) - c.index[-1]).days > max_days


def fmt_pct(x, digits: int = 1, na: str = "indispo.") -> str:
    """+1,2 % ; « indispo. » au lieu d'un faux 0 %."""
    try:
        if x is None or not np.isfinite(float(x)):
            return na
    except (TypeError, ValueError):
        return na
    return f"{float(x):+.{digits}%}"


def health(px: pd.DataFrame, tickers) -> dict:
    """État des données pour l'interface et l'admin : tickers manquants, dernière date par ticker."""
    rows, missing = [], []
    for t in tickers:
        c = true_closes(px[t]) if (px is not None and t in px) else pd.Series(dtype=float)
        if c.empty:
            missing.append(t)
            rows.append(dict(Ticker=t, Statut="indisponible", **{"Dernière clôture": "—"}))
        else:
            rows.append(dict(Ticker=t, Statut="ok" if not stale(c) else "ancienne",
                             **{"Dernière clôture": c.index[-1].strftime("%d/%m/%Y")}))
    return dict(missing=missing, rows=rows, ok=len(missing) < max(1, len(list(tickers))) * 0.5)


# ══════════════════════════════════════════════════════════════════════════════
#  INTRADAY (1 h / 6 h)
# ══════════════════════════════════════════════════════════════════════════════
def fetch_intraday(tickers=("NQ=F", "^NDX"), period: str = "5d", interval: str = "5m") -> pd.DataFrame:
    """Barres intraday (≈ 15 min de différé chez Yahoo). Index en heure UTC naïve."""
    try:
        import yfinance as yf
        raw = yf.download(list(tickers), period=period, interval=interval, auto_adjust=True, progress=False,
                          threads=True, group_by="column", prepost=True)
        if raw is None or raw.empty:
            return pd.DataFrame()
        idx = raw.index
        if getattr(idx, "tz", None) is not None:
            raw.index = idx.tz_convert("UTC").tz_localize(None)
        return extract_closes(raw, list(tickers))
    except Exception:
        return pd.DataFrame()


def window_stats(s: pd.Series | None, hours: float, now: pd.Timestamp | None = None) -> dict:
    """Variation, volatilité réalisée, plus haut / bas sur les `hours` dernières heures de barres disponibles."""
    c = pd.to_numeric(s, errors="coerce").dropna() if s is not None else pd.Series(dtype=float)
    if len(c) < 3:
        return dict(ok=False, hours=hours)
    end = c.index[-1] if now is None else min(pd.Timestamp(now), c.index[-1])
    w = c[(c.index > end - pd.Timedelta(hours=hours)) & (c.index <= end)]
    base = c[c.index <= end - pd.Timedelta(hours=hours)]
    if len(w) < 2:
        return dict(ok=False, hours=hours)
    ref = float(base.iloc[-1]) if len(base) else float(w.iloc[0])
    r = np.log(w).diff().dropna()
    step_min = max(1.0, float(np.median(np.diff(w.index.values).astype("timedelta64[s]").astype(float))) / 60)
    vol_h = float(r.std() * np.sqrt(60 / step_min)) if len(r) > 2 else NAN
    hi, lo, last = float(w.max()), float(w.min()), float(w.iloc[-1])
    ret = last / ref - 1 if ref else NAN
    trend = "haussière" if ret > 0.002 else "baissière" if ret < -0.002 else "sans direction"
    return dict(ok=True, hours=hours, ret=ret, vol_h=vol_h, hi=hi, lo=lo, last=last, start=w.index[0], end=w.index[-1],
                pos=(last - lo) / (hi - lo) if hi > lo else 0.5, trend=trend, n=len(w))
