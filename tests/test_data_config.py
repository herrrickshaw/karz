"""Tests for data_config.py: splits, validation rules, freshness, consistency."""
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import data_config as dc


def ohlc(closes):
    n = len(closes)
    return pd.DataFrame({
        "date": pd.bdate_range("2023-01-02", periods=n),
        "open": closes, "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes], "close": closes, "volume": [1000] * n,
    })


# ── splits ───────────────────────────────────────────────────────────────────
def test_splits_are_chronological_and_non_overlapping():
    s = dc.DateSplits
    assert s.validate_no_overlap()
    assert s.get_train_range()[1] < s.get_validation_range()[0]
    assert s.get_validation_range()[1] < s.get_test_range()[0]


@pytest.mark.parametrize("purpose,expected", [
    ("training", dc.DateSplits.get_train_range()),
    ("validation", dc.DateSplits.get_validation_range()),
    ("backtest", dc.DateSplits.get_test_range()),
    ("anything-else", dc.DateSplits.get_test_range()),
])
def test_get_split_for_purpose(purpose, expected):
    assert dc.DataConfig().get_split_for_purpose(purpose) == expected


def test_filter_data_by_split_keeps_inclusive_boundaries():
    df = pd.DataFrame({"date": ["2022-12-31", "2023-01-01", "2024-06-30", "2024-07-01"],
                       "x": range(4)})
    out = dc.filter_data_by_split(df, "date", "test")
    assert out["x"].tolist() == [1, 2]


def test_filter_data_by_split_unknown_split_raises():
    with pytest.raises(ValueError):
        dc.filter_data_by_split(pd.DataFrame({"date": []}), "date", "holdout")


# ── registry / universe ──────────────────────────────────────────────────────
def test_registry_lookup():
    assert dc.DataSourceRegistry.get_source("IN")["name"] == "cleaned_long.parquet"
    assert dc.DataSourceRegistry.get_source("US")["symbols"] == 10433
    assert dc.DataSourceRegistry.get_source("XX") is None
    assert dc.DataSourceRegistry.get_all_markets()[0] == "IN"


def test_unknown_universe_preset_falls_back_to_india():
    assert dc.Universe.get_universe("nope") is dc.Universe.INDIA_FOCUS


def test_validate_universe_consistency_flags_under_80pct_coverage():
    u = {"symbols": ["A", "B", "C", "D", "E"]}
    assert dc.validate_universe_consistency(u, pd.DataFrame({"symbol": ["A", "B", "C", "D"]})) == []
    assert dc.validate_universe_consistency(u, pd.DataFrame({"symbol": ["A", "B", "C"]}))


# ── validate_dataframe ───────────────────────────────────────────────────────
def test_clean_frame_has_no_errors():
    assert dc.DataValidationRules.validate_dataframe(ohlc([100.0, 101.0, 102.0])) == []


def test_missing_critical_column_reported_and_can_raise():
    df = ohlc([100.0, 101.0]).drop(columns=["volume"])
    assert "Missing critical column: volume" in dc.DataValidationRules.validate_dataframe(df)
    with pytest.raises(ValueError):
        dc.DataValidationRules.validate_dataframe(df, raise_on_error=True)


def test_null_share_above_5pct_flagged():
    df = ohlc([100.0] * 10)
    df.loc[0, "close"] = np.nan
    errs = dc.DataValidationRules.validate_dataframe(df)
    assert any("Column close has 10.0% nulls" in e for e in errs)


def test_high_below_low_flagged():
    df = ohlc([100.0, 101.0])
    df.loc[1, "high"] = 50.0
    assert "1 rows with high < low" in dc.DataValidationRules.validate_dataframe(df)


def test_daily_move_above_50pct_is_flagged():
    # MAX_DAILY_MOVE_PCT = 50 means 50 %; a +60 % day must be flagged.
    df = ohlc([100.0, 160.0, 161.0])
    errs = dc.DataValidationRules.validate_dataframe(df)
    assert any("extreme daily moves" in e for e in errs)


def test_validate_dataframe_does_not_mutate_the_callers_frame():
    df = ohlc([100.0, 101.0])
    cols = list(df.columns)
    dc.DataValidationRules.validate_dataframe(df)
    assert list(df.columns) == cols


# ── freshness / consistency ──────────────────────────────────────────────────
@pytest.mark.parametrize("req,age,fresh", [
    (dc.FreshnessRequirements.INTRADAY_SCREENER, timedelta(minutes=10), True),
    (dc.FreshnessRequirements.INTRADAY_SCREENER, timedelta(minutes=20), False),
    (dc.FreshnessRequirements.DAILY_SCREENER, timedelta(hours=23), True),
    (dc.FreshnessRequirements.DAILY_SCREENER, timedelta(hours=25), False),
    (dc.FreshnessRequirements.WEEKLY_ANALYSIS, timedelta(days=7), True),
    (dc.FreshnessRequirements.WEEKLY_ANALYSIS, timedelta(days=8), False),
])
def test_check_freshness(req, age, fresh):
    assert dc.FreshnessRequirements.check_freshness(datetime.now() - age, req)[0] is fresh


def test_unknown_freshness_requirement_passes_with_message():
    assert dc.FreshnessRequirements.check_freshness(datetime.now(), {}) == (
        True, "Unknown freshness requirement")


@pytest.mark.parametrize("a,b,tol,ok", [
    (100.0, 102.0, 2.0, True),      # 2/102 = 1.96 %
    (100.0, 103.0, 2.0, False),
    (0.0, 0.005, 2.0, True),        # zero branch: absolute 0.01
    (0.0, 0.02, 2.0, False),
    (-100.0, -101.0, 2.0, True),
])
def test_acceptable_difference(a, b, tol, ok):
    assert dc.ConsistencyRules.acceptable_difference(a, b, tol) is ok
