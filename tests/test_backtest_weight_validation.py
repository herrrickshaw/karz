"""Tests for backtest_weight_validation.py pure helpers.

The module imports `correlation_analysis`, which is NOT in this repository, so a
stub is installed before import; only the self-contained helpers are tested.
"""
import sys
import types

import pandas as pd
import pytest

sys.modules.setdefault("correlation_analysis", types.ModuleType("correlation_analysis"))
import backtest_weight_validation as bwv  # noqa: E402


def test_zscore_standardises():
    z = bwv._zscore(pd.Series([1.0, 2.0, 3.0]))
    assert z.tolist() == pytest.approx([-1.0, 0.0, 1.0])


def test_zscore_constant_series_is_zero_not_nan():
    assert bwv._zscore(pd.Series([5.0, 5.0, 5.0])).tolist() == [0.0, 0.0, 0.0]


def test_validate_quintile_spread(monkeypatch):
    merged = pd.DataFrame({"composite": range(10), "cagr": [float(i) for i in range(10)]})
    monkeypatch.setattr(bwv, "build_composite", lambda m, t: (merged.copy(), ["x"], None))
    monkeypatch.setattr(bwv, "HAS_DATA_CONFIG", False)
    r = bwv.validate("US", "cagr", q=5)
    # Q5 = {8, 9} mean 8.5; Q1 = {0, 1} mean 0.5
    assert r["spread_top_minus_bottom"] == pytest.approx(8.0)
    assert r["n"] == 10


def test_validate_too_few_names(monkeypatch):
    merged = pd.DataFrame({"composite": [1.0, 2.0], "cagr": [1.0, 2.0]})
    monkeypatch.setattr(bwv, "build_composite", lambda m, t: (merged, [], None))
    assert "too few names" in bwv.validate("US", "cagr", q=5)["error"]
