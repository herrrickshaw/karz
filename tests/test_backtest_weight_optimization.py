"""Tests for WeightBacktester scoring, signals and confusion-matrix metrics."""
import numpy as np
import pandas as pd
import pytest

from backtest_weight_optimization import WeightBacktester


@pytest.fixture
def bt():
    df = pd.DataFrame({"stock_return_12m": [5.0, 1.0, 2.0, 6.0]})
    return WeightBacktester(df)


def test_both_weight_sets_sum_to_100():
    assert sum(WeightBacktester.BASELINE_WEIGHTS.values()) == 100
    assert sum(WeightBacktester.OPTIMIZED_WEIGHTS.values()) == 100


def test_composite_prefers_suffixed_column_and_falls_back_to_bare_name(bt):
    df = pd.DataFrame({"debt_expansion_score": [1.0, 2.0], "capex_acceleration": [10.0, 0.0]})
    s = bt.calculate_composite_score(df, {"debt_expansion": 50, "capex_acceleration": 50,
                                          "missing": 100})
    assert s.tolist() == pytest.approx([5.5, 1.0])


def test_signals_buy_strictly_above_percentile(bt):
    assert bt.generate_signals(np.array([1.0, 2.0, 3.0, 4.0]), 50).tolist() == [0, 0, 1, 1]
    assert bt.generate_signals(np.array([2.0, 2.0, 2.0]), 50).tolist() == [0, 0, 0]


def test_perfect_signals_give_perfect_confusion_matrix(bt):
    # median return 3.5 -> outperformers are rows 0 and 3
    m = bt._evaluate_signals(np.array([1, 0, 0, 1]), bt.data["stock_return_12m"], "x")
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (2, 0, 0, 2)
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["f1"] == 1.0
    assert m["accuracy"] == 1.0


def test_inverted_signals(bt):
    m = bt._evaluate_signals(np.array([0, 1, 1, 0]), bt.data["stock_return_12m"], "x")
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (0, 2, 2, 0)
    assert m["accuracy"] == 0.0 and m["f1"] == 0


def test_return_spread(bt):
    m = bt._evaluate_signals(np.array([1, 0, 0, 1]), bt.data["stock_return_12m"], "x")
    assert m["avg_buy_return"] == pytest.approx(5.5)
    assert m["avg_sell_return"] == pytest.approx(1.5)
    assert m["return_spread"] == pytest.approx(4.0)


def test_run_backtest_both_sets(bt):
    df = pd.DataFrame({
        "fcf_generation_score": [4.0, 1.0, 2.0, 3.0],
        "debt_expansion_score": [1.0, 4.0, 3.0, 2.0],
        "stock_return_12m": [10.0, -5.0, 0.0, 8.0],
    })
    res = WeightBacktester(df).run_backtest("both")
    assert set(res) == {"baseline", "optimized"}
    # optimized weights fcf (22) above debt (10): picks rows 0 and 3, the two winners
    assert res["optimized"]["precision"] == 1.0
    assert res["baseline"]["precision"] == 0.0


def test_export_results_csv(bt, tmp_path):
    m = bt._evaluate_signals(np.array([1, 0, 0, 1]), bt.data["stock_return_12m"], "x")
    p = tmp_path / "r.csv"
    bt.export_results({"baseline": m}, str(p))
    out = pd.read_csv(p)
    assert out.loc[0, "weight_set"] == "baseline" and out.loc[0, "true_negatives"] == 2
