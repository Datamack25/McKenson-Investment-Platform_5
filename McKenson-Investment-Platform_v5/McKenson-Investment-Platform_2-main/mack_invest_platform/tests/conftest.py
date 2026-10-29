"""Tests automatisés MAM (v5.4) — exécutés sans réseau ni base de données.

Lancement local :   cd mack_invest_platform && python -m pytest -q
Sur GitHub :        workflow « MAM — tests automatisés » (à chaque envoi de code).
"""
import os
import sys
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.pop("DATABASE_URL", None)          # jamais de base réelle pendant les tests
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture(scope="session")
def px10():
    """Dix ans de cours synthétiques pour tous les actifs utilisés par la calibration."""
    from utils import advisor as A, calibration as C
    return A._simulated_prices(list(C.history_tickers()), n=2520, seed=3)


@pytest.fixture
def port_basic():
    return {"id": "PT", "name": "Test", "strategy": "Libre", "cash": 60_000.0, "initial_cash": 100_000.0,
            "holdings": {"SPY": {"qty": 50, "avg_price": 500.0}, "TLT": {"qty": 100, "avg_price": 90.0}},
            "trades": [], "options": []}


@pytest.fixture(autouse=True)
def _offline_fx():
    """v5.8 : taux de change fixes pendant les tests (aucun appel réseau)."""
    from utils import fx
    fx.set_rates(fx.FALLBACK)
    yield
    fx.set_rates(None)
