"""Readable unit tests for the pure helpers (the golden tests cover end-to-end output)."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import backtest_weight_optimization as bo
import data_config as dc
import data_validator as dv

ROOT = Path(__file__).resolve().parent.parent


def test_splits_do_not_overlap():
    assert dc.DateSplits.validate_no_overlap() is True
    assert dc.DataConfig().get_split_for_purpose("unknown") == dc.DateSplits.get_test_range()


def test_filter_data_by_split_selects_range_and_rejects_unknown():
    df = pd.DataFrame({"d": ["2016-01-01", "2023-02-01", "2025-01-01"], "v": [1, 2, 3]})
    assert dc.filter_data_by_split(df.copy(), "d", "test")["v"].tolist() == [2]
    with pytest.raises(ValueError):
        dc.filter_data_by_split(df.copy(), "d", "bogus")


def test_check_freshness_units():
    now = datetime.now()
    fresh, msg = dc.FreshnessRequirements.check_freshness(now - timedelta(hours=30), {"max_age_hours": 24})
    assert not fresh and "hours" in msg
    assert dc.FreshnessRequirements.check_freshness(now, {})[0] is True


def test_acceptable_difference():
    assert dc.ConsistencyRules.acceptable_difference(100, 101, 2.0)
    assert not dc.ConsistencyRules.acceptable_difference(100, 110, 2.0)


def test_validate_dataframe_reports_missing_column():
    df = pd.DataFrame({"close": [1.0, 2.0]})
    assert any("Missing critical column: open" in e for e in dc.DataValidationRules.validate_dataframe(df))
    with pytest.raises(ValueError):
        dc.DataValidationRules.validate_dataframe(df, raise_on_error=True)


def test_quality_checks_and_score():
    df = pd.DataFrame({"open": [1, 1], "high": [1, 1], "low": [2, 2], "close": [1, 1]})
    errors = dv.check_dataframe_quality(df)
    assert any("high < low" in e for e in errors) and any("duplicate" in e for e in errors)
    assert dv.quality_score(errors) == pytest.approx(1.0 - 0.1 * len(errors))
    assert dv.quality_score([""] * 20) == 0


def test_scan_text_for_leakage_flags_negative_shift():
    issues = dv.scan_text_for_leakage("x.py", "a = 1\nb = df.shift(-1)\n")
    assert [(i.line_number, i.issue_type) for i in issues] == [(2, "future_data")]


def test_evaluate_signals_perfect_predictor():
    returns = pd.Series([-5.0, -4.0, 6.0, 7.0])
    m = bo.evaluate_signals(np.array([0, 0, 1, 1]), returns, "perfect")
    assert (m["precision"], m["recall"], m["f1"]) == (1.0, 1.0, 1.0)
    assert m["return_spread"] == pytest.approx(11.0)


@pytest.mark.xfail(strict=True, reason="known pre-existing bug: ~ on 0/1 ints makes tn negative, so accuracy is wrong")
def test_evaluate_signals_true_negatives_and_accuracy():
    m = bo.evaluate_signals(np.array([0, 0, 1, 1]), pd.Series([-5.0, -4.0, 6.0, 7.0]), "perfect")
    assert m["tn"] == 2 and m["accuracy"] == 1.0


@pytest.mark.parametrize("script, args", [("data_config.py", []),
                                          ("backtest_weight_optimization.py", ["--help"]),
                                          ("backtest_weight_validation.py", ["--help"])])
def test_cli_entry_points_start(script, args, tmp_path):
    # backtest_weight_validation needs the external correlation_analysis module; stub it.
    (tmp_path / "correlation_analysis.py").write_text("PERF = ['cagr']\n")
    env = {"PYTHONPATH": f"{tmp_path}:{ROOT}", "PATH": "/usr/bin:/bin"}
    proc = subprocess.run([sys.executable, str(ROOT / script), *args], capture_output=True, text=True,
                          env=env, cwd=tmp_path, timeout=60)
    assert proc.returncode == 0, proc.stderr
