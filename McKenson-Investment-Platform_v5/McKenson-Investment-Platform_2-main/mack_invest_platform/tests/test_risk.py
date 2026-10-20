import math

import numpy as np
import pandas as pd

from utils import risk_hull as RH


def test_parametric_var_and_es():
    assert abs(RH.var_param(0.01, 0.99, 1) - 2.3263 * 0.01) < 1e-4
    assert abs(RH.var_param(0.01, 0.99, 10) - 2.3263 * 0.01 * math.sqrt(10)) < 1e-4
    assert abs(RH.es_param(0.01, 0.975, 1) - 0.023378) < 1e-4      # ES 97,5 % ≈ VaR 99 % (Bâle)


def test_euler_contributions_sum_to_one():
    cov = pd.DataFrame([[0.04, 0.01], [0.01, 0.09]], index=["A", "B"], columns=["A", "B"])
    c = RH.euler_contributions(pd.Series({"A": 0.6, "B": 0.4}), cov)
    assert abs(c.sum() - 1) < 1e-9


def test_kupiec_validates_correct_model():
    r = pd.Series(np.random.default_rng(0).normal(0, 0.01, 800))
    k = RH.kupiec(r)
    assert k["ok"] and k["p_value"] > 0.01


def test_ewma_reacts_to_shock():
    r = pd.Series([0.001] * 300 + [0.05] * 5)
    assert RH.ewma_vol(r) > r.std()
