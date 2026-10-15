# utils/technical.py  —  MAM Technical Analysis Engine
"""
RSI, MACD, Bollinger Bands, ATR, Stochastic, VWAP, GARCH (simplified).
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_l = loss.ewm(com=period - 1, min_periods=period).mean()
    rs    = avg_g / avg_l.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_macd(close: pd.Series,
                 fast: int = 12, slow: int = 26, signal: int = 9
                 ) -> tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast   = close.ewm(span=fast, adjust=False).mean()
    ema_slow   = close.ewm(span=slow, adjust=False).mean()
    macd_line  = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram  = macd_line - signal_line
    return macd_line, signal_line, histogram


def compute_bollinger(close: pd.Series,
                      period: int = 20, n_std: float = 2.0
                      ) -> tuple[pd.Series, pd.Series, pd.Series]:
    sma    = close.rolling(period).mean()
    std    = close.rolling(period).std()
    upper  = sma + n_std * std
    lower  = sma - n_std * std
    return upper, sma, lower


def compute_atr(high: pd.Series, low: pd.Series,
                close: pd.Series, period: int = 14) -> pd.Series:
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(com=period - 1, min_periods=period).mean()


def compute_stochastic(high: pd.Series, low: pd.Series,
                       close: pd.Series,
                       k_period: int = 14, d_period: int = 3
                       ) -> tuple[pd.Series, pd.Series]:
    lowest_low   = low.rolling(k_period).min()
    highest_high = high.rolling(k_period).max()
    k = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-12)
    d = k.rolling(d_period).mean()
    return k, d


def compute_vwap(high: pd.Series, low: pd.Series,
                 close: pd.Series, volume: pd.Series) -> pd.Series:
    typical = (high + low + close) / 3
    cum_tp_vol = (typical * volume).cumsum()
    cum_vol    = volume.cumsum()
    return cum_tp_vol / cum_vol.replace(0, np.nan)


def compute_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def compute_sma(close: pd.Series, period: int) -> pd.Series:
    return close.rolling(period).mean()


def garch_vol_estimate(returns: pd.Series,
                       omega: float = 1e-6,
                       alpha: float = 0.10,
                       beta:  float = 0.85) -> pd.Series:
    """
    Simplified GARCH(1,1) conditional variance estimate.
    σ²_t = ω + α·ε²_{t-1} + β·σ²_{t-1}
    """
    r   = returns.dropna().values
    n   = len(r)
    h   = np.zeros(n)
    h[0] = np.var(r)
    for t in range(1, n):
        h[t] = omega + alpha * r[t - 1] ** 2 + beta * h[t - 1]
    vol = pd.Series(np.sqrt(h) * np.sqrt(252),
                    index=returns.dropna().index,
                    name="GARCH_vol")
    return vol


def get_signal(rsi: float, macd_hist: float,
               price: float, bb_upper: float, bb_lower: float) -> tuple[str, str]:
    """Simple composite signal based on RSI + MACD + BB."""
    score = 0
    if rsi < 30:  score += 2
    elif rsi < 45: score += 1
    elif rsi > 70: score -= 2
    elif rsi > 55: score -= 1

    if macd_hist > 0:  score += 1
    elif macd_hist < 0: score -= 1

    if price < bb_lower:  score += 1
    elif price > bb_upper: score -= 1

    if score >= 3:    return "STRONG BUY",  "positive"
    elif score >= 1:  return "BUY",         "positive"
    elif score <= -3: return "STRONG SELL", "negative"
    elif score <= -1: return "SELL",        "negative"
    return "NEUTRAL", "neutral"
