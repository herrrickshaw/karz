"""End-to-end flows for karz: the backtest report/export/data-source loader, the fundamentals composite
validation, repository static analysis and data validation. Synthetic frames only; no parquet engine needed
(pd.read_parquet is patched), no network."""
import json
import sys
import types
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

import backtest_weight_optimization as bwo

# `correlation_analysis` is not part of this repository; another test module installs a blank stub first
sys.modules.setdefault("correlation_analysis", types.ModuleType("correlation_analysis"))
import backtest_weight_validation as bwv  # noqa: E402
import data_validator as dv  # noqa: E402
import repo_data_analyzer as rda  # noqa: E402

ca = bwv.ca
ca.PERF = ["cagr", "return_12m"]


# =============================== backtest_weight_optimization ===============================

def scored_frame(n=20, seed=0):
    rng = np.random.default_rng(seed)
    d = {f"{k}_score": rng.uniform(0, 100, n) for k in bwo.WeightBacktester.BASELINE_WEIGHTS}
    d["stock_return_12m"] = rng.normal(5, 20, n)
    d["company"] = [f"C{i}" for i in range(n)]
    d["symbol"] = [f"S{i}" for i in range(n)]
    d["date"] = pd.date_range("2023-01-02", periods=n)
    d["close"] = 10.0 + np.arange(n)
    return pd.DataFrame(d)


def test_init_prints_validation_warnings_and_split_banner(capsys):
    bt = bwo.WeightBacktester(pd.DataFrame({"stock_return_12m": [1.0, None, None, None]}), use_test_split=True)
    out = capsys.readouterr().out
    assert "Data validation warnings" in out and "TEST [2023-01-01 to 2024-06-30]" in out
    assert len(bt.data) == 4
    capsys.readouterr()
    bwo.WeightBacktester(scored_frame(), lookback_years=2)
    assert "Lookback period: 2 years" in capsys.readouterr().out


def test_generate_report_both_sets_improvement_branches(capsys):
    bt = bwo.WeightBacktester(scored_frame())
    base = dict(n_signals=10, n_outperform=10, tp=5, fp=5, fn=5, tn=5, precision=0.5, recall=0.5, f1=0.5,
                accuracy=0.5, avg_buy_return=1.0, avg_sell_return=0.0, return_spread=1.0)
    for f1, label in ((0.60, "SIGNIFICANT IMPROVEMENT"), (0.52, "MODEST IMPROVEMENT"), (0.45, "NO IMPROVEMENT")):
        capsys.readouterr()
        opt = dict(base, f1=f1, precision=0.6, recall=0.4)
        bt.generate_report({"baseline": base, "optimized": opt})
        out = capsys.readouterr().out
        assert label in out and "BASELINE WEIGHTS" in out and "OPTIMIZED WEIGHTS" in out
    assert "KEEP BASELINE WEIGHTS" in out
    assert "Improved metrics:" in out


def test_generate_report_improved_metric_count_and_equal_marker(capsys):
    bt = bwo.WeightBacktester(scored_frame())
    base = dict(n_signals=1, n_outperform=1, tp=1, fp=0, fn=0, tn=0, precision=0.5, recall=0.5, f1=0.5,
                accuracy=0.5, avg_buy_return=1.0, avg_sell_return=0.0, return_spread=1.0)
    bt.generate_report({"baseline": base, "optimized": dict(base)})
    out = capsys.readouterr().out
    assert "Improved metrics: 0/6" in out and "NO IMPROVEMENT: F1 score decreased by 0.0000" in out
    assert "=" in out


def test_generate_report_single_set(capsys):
    bt = bwo.WeightBacktester(scored_frame())
    m = bt._evaluate_signals(np.array([1, 0] * 10), bt.data["stock_return_12m"], "x")
    bt.generate_report({"baseline": m})
    out = capsys.readouterr().out
    assert "BASELINE WEIGHTS" in out and "OPTIMIZED WEIGHTS" not in out and "IMPROVEMENTS" not in out


def test_evaluate_signals_degenerate_cases(capsys):
    bt = bwo.WeightBacktester(pd.DataFrame({"stock_return_12m": [1.0, 2.0, 3.0, 4.0]}))
    none = bt._evaluate_signals(np.zeros(4), bt.data["stock_return_12m"], "none")
    assert none["precision"] == 0 and none["recall"] == 0 and none["f1"] == 0
    assert none["avg_buy_return"] == 0 or none["avg_buy_return"] != none["avg_buy_return"]
    allbuy = bt._evaluate_signals(np.ones(4), bt.data["stock_return_12m"], "all")
    assert allbuy["recall"] == 1.0 and allbuy["precision"] == 0.5 and allbuy["tn"] == 0


def test_backtest_from_data_source(monkeypatch, tmp_path, capsys):
    df = scored_frame()
    df["date"] = pd.to_datetime(["2022-06-01"] * 5 + ["2023-06-01"] * 15)       # 15 rows inside the TEST split
    monkeypatch.setattr(pd, "read_parquet", lambda p: df.copy())
    res = bwo.backtest_from_data_source("x.parquet", "IN", use_test_split=True, weight_set="both")
    assert set(res) == {"baseline", "optimized"}
    assert res["baseline"]["n_signals"] + 0 <= 15
    res = bwo.backtest_from_data_source("x.parquet", use_test_split=False, weight_set="baseline")
    assert set(res) == {"baseline"}
    assert res["baseline"]["tp"] + res["baseline"]["fp"] + res["baseline"]["fn"] + res["baseline"]["tn"] == 20


def test_backtest_from_data_source_missing_file_and_no_config(monkeypatch):
    def missing(p):
        raise FileNotFoundError(p)
    monkeypatch.setattr(pd, "read_parquet", missing)
    assert bwo.backtest_from_data_source("nope.parquet") == {}
    monkeypatch.setattr(bwo, "HAS_DATA_CONFIG", False)
    assert bwo.backtest_from_data_source("nope.parquet") == {}


def test_backtest_from_data_source_without_date_column_uses_all_rows(monkeypatch):
    df = scored_frame().drop(columns=["date"])
    monkeypatch.setattr(pd, "read_parquet", lambda p: df.copy())
    res = bwo.backtest_from_data_source("x.parquet", use_test_split=True, weight_set="optimized")
    m = res["optimized"]
    assert m["tp"] + m["fp"] + m["fn"] + m["tn"] == 20


@pytest.mark.xfail(strict=True, raises=KeyError,
                   reason="backtest_from_data_source checks for 'date' OR 'Date' but always passes 'date' to "
                          "filter_data_by_split, so a frame with only a 'Date' column raises KeyError "
                          "(backtest_weight_optimization.py:~397)")
def test_backtest_from_data_source_accepts_capitalised_date_column(monkeypatch):
    df = scored_frame().rename(columns={"date": "Date"})
    monkeypatch.setattr(pd, "read_parquet", lambda p: df.copy())
    assert bwo.backtest_from_data_source("x.parquet", use_test_split=True)


def test_export_results_roundtrip_all_columns(tmp_path):
    bt = bwo.WeightBacktester(scored_frame())
    res = bt.run_backtest("both")
    p = tmp_path / "r.csv"
    bt.export_results(res, str(p))
    out = pd.read_csv(p)
    assert list(out["weight_set"]) == ["baseline", "optimized"]
    assert set(out.columns) >= {"true_positives", "false_positives", "f1_score", "return_spread"}
    assert out.loc[0, "f1_score"] == pytest.approx(res["baseline"]["f1"])


# =============================== backtest_weight_validation ===============================

def perf_frame(n=12, start_new=6):
    syms = [f"S{i}" for i in range(n)]
    dates = ["2015-06-01"] * start_new + ["2023-06-01"] * (n - start_new)
    return pd.DataFrame({"Symbol": syms, "date": dates, "cagr": np.arange(n) / 100.0})


def fund_frame(syms, factor=1.0):
    return pd.DataFrame({"Symbol": syms, "roe": [float(i) * factor for i in range(len(syms))],
                         "debt": [float(-i) for i in range(len(syms))], "text": ["x"] * len(syms)})


@pytest.fixture
def stub_ca(monkeypatch):
    perf = perf_frame()
    monkeypatch.setattr(ca, "_perf_features", lambda market: perf.copy(), raising=False)
    corr = pd.DataFrame({"metric": ["roe", "debt", "absent"], "spearman_rho": [0.8, -0.5, 0.3],
                         "p_value": [0.01, 0.05, 0.5]})
    monkeypatch.setattr(ca, "analyse", lambda market, target: corr, raising=False)
    monkeypatch.setattr(pd, "read_parquet", lambda p: fund_frame(list(perf["Symbol"])))
    return perf


def test_build_composite_sign_aligns_and_skips_missing_columns(stub_ca):
    merged, used, picks = bwv.build_composite("US", "cagr")
    assert used == ["roe", "debt"]                              # p<=0.10 picks; 'absent' (p=0.5) excluded
    assert list(picks["metric"]) == ["roe", "debt"]
    z = bwv._zscore
    expected = 1 * z(merged["roe"]) + (-1) * z(merged["debt"])
    assert merged["composite"].tolist() == pytest.approx(expected.tolist())


def test_build_composite_falls_back_to_strongest_when_none_significant(stub_ca, monkeypatch):
    corr = pd.DataFrame({"metric": ["roe", "debt"], "spearman_rho": [0.1, -0.1], "p_value": [0.5, 0.6]})
    monkeypatch.setattr(ca, "analyse", lambda m, t: corr)
    merged, used, picks = bwv.build_composite("US", "cagr", top_k=1)
    assert used == ["roe"] and len(picks) == 1
    monkeypatch.setattr(ca, "analyse", lambda m, t: corr.iloc[0:0])
    assert bwv.build_composite("US")[0] is None


def test_p_value_boundary_is_inclusive(stub_ca, monkeypatch):
    corr = pd.DataFrame({"metric": ["roe", "debt"], "spearman_rho": [0.1, -0.1], "p_value": [0.10, 0.1001]})
    monkeypatch.setattr(ca, "analyse", lambda m, t: corr)
    assert bwv.build_composite("US")[1] == ["roe"]


def test_validate_all_data_quintiles(stub_ca, capsys):
    r = bwv.validate("US", "cagr", q=3, use_test_split=False)
    assert r["n"] == 12 and r["used_test_split"] is False and r["metrics_used"] == ["roe", "debt"]
    assert list(r["table"].columns) == ["mean", "median", "count"] and list(r["table"]["count"]) == [4, 4, 4]
    assert r["spread_top_minus_bottom"] == pytest.approx(r["table"].loc[3, "mean"] - r["table"].loc[1, "mean"])
    assert r["spread_top_minus_bottom"] > 0                              # composite rises with cagr by construction


def test_validate_no_overlap_and_too_few(stub_ca, monkeypatch):
    monkeypatch.setattr(ca, "analyse", lambda m, t: pd.DataFrame())
    assert bwv.validate("US")["error"] == "no fundamentals/perf overlap"
    monkeypatch.setattr(ca, "analyse", lambda m, t: pd.DataFrame(
        {"metric": ["roe"], "spearman_rho": [1.0], "p_value": [0.01]}))
    assert "too few names (12) for 7-tiles" in bwv.validate("US", q=7)["error"]
    assert "too few names" in bwv.validate("US", q=7)["error"]


def test_validate_prints_data_validation_warnings(stub_ca, capsys):
    bwv.validate("US", "cagr", q=3)
    assert "Data validation warnings" in capsys.readouterr().out         # frame lacks the critical columns


def test_validate_test_split_without_date_column(stub_ca, monkeypatch, capsys):
    monkeypatch.setattr(ca, "_perf_features", lambda m: perf_frame().drop(columns="date"))
    r = bwv.validate("US", "cagr", q=3, use_test_split=True)
    assert "No date column in performance data" in capsys.readouterr().out
    assert r["n"] == 12 and r["used_test_split"] is True


def test_validate_test_split_keeps_only_test_period_rows(stub_ca, capsys):
    r = bwv.validate("US", "cagr", q=2, use_test_split=True)
    assert r["n"] == 6 and "Applied TEST split: 6 records" in capsys.readouterr().out


@pytest.mark.xfail(strict=True,
                   reason="validate() selects TEST rows with merged.index.isin(perf_test.index), but `merged` "
                          "is the inner-merge result with a fresh RangeIndex while perf_test keeps perf's "
                          "labels: if any symbol lacks fundamentals the positions shift and the wrong rows "
                          "are kept (backtest_weight_validation.py:~84)")
def test_validate_test_split_is_label_aligned_after_merge(stub_ca, monkeypatch):
    perf = perf_frame()
    monkeypatch.setattr(pd, "read_parquet", lambda p: fund_frame(list(perf["Symbol"][1:])))   # S0 has no fundamentals
    r = bwv.validate("US", "cagr", q=2, use_test_split=True)
    assert r["n"] == 6                                                    # S6..S11 are the TEST-period names


@pytest.mark.xfail(strict=True, raises=KeyError,
                   reason="validate() tests for 'date' OR 'Date' but always filters on 'date' "
                          "(backtest_weight_validation.py:~80): a 'Date'-only frame raises KeyError")
def test_validate_accepts_capitalised_date_column(stub_ca, monkeypatch):
    monkeypatch.setattr(ca, "_perf_features", lambda m: perf_frame().rename(columns={"date": "Date"}))
    assert bwv.validate("US", "cagr", q=2, use_test_split=True)["n"] > 0


def test_validate_with_proper_split_banner(stub_ca, capsys):
    r = bwv.validate_with_proper_split("US", "cagr", 3, use_test_split=False)
    out = capsys.readouterr().out
    assert "FUNDAMENTALS COMPOSITE VALIDATION" in out and "not recommended" in out and r["n"] == 12
    bwv.validate_with_proper_split("US", "cagr", 2)
    assert "Using TEST split: 2023-01-01 to 2024-06-30" in capsys.readouterr().out


def test_main_prints_table_and_signal_text(stub_ca, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bwv", "--market", "US", "--target", "cagr", "--quantiles", "3", "--no-split"])
    assert bwv.main() == 0
    out = capsys.readouterr().out
    assert "n=12" in out and "metrics: roe, debt" in out and "Evaluated on all available data" in out
    assert "signal separates winners" in out and "Q3−Q1 spread (cagr): +" in out


def test_main_error_path_and_test_split_message(stub_ca, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["bwv", "--quantiles", "3"])
    assert bwv.main() == 0
    assert "Evaluated on TEST split" in capsys.readouterr().out
    monkeypatch.setattr(ca, "analyse", lambda m, t: pd.DataFrame())
    assert bwv.main() == 0
    assert "no fundamentals/perf overlap" in capsys.readouterr().out


def test_main_negative_spread_message(stub_ca, monkeypatch, capsys):
    monkeypatch.setattr(ca, "analyse", lambda m, t: pd.DataFrame(
        {"metric": ["roe"], "spearman_rho": [-1.0], "p_value": [0.01]}))
    monkeypatch.setattr(sys, "argv", ["bwv", "--quantiles", "3", "--no-split"])
    bwv.main()
    assert "no/negative separation" in capsys.readouterr().out


# =============================== repo_data_analyzer ===============================

REPO = {
    "a_all.py": "import pandas as pd\ndf = pd.read_parquet('prices.parquet')\nfull_data = df\n"
                "df.to_csv('out.csv')\n",
    "b_split.py": "from sklearn.model_selection import train_test_split\nimport pandas as pd\n"
                  "df = pd.read_csv('a.csv')\nd2 = pd.read_csv('b.csv')\n"
                  "tr, te = train_test_split(df, test_size=0.2, random_state=1)\nassert len(tr)\n",
    "c_sample.py": "import pandas as pd\nx = pd.read_csv('q.csv', nrows=500)\nassert x is not None\n"
                   "bt_start = '2020-01-01'\nbt_end = '2021-01-01'\n",
}


@pytest.fixture
def repo(tmp_path):
    for n, src in REPO.items():
        (tmp_path / n).write_text(src)
    (tmp_path / "broken.py").write_text("def (:\n")
    return tmp_path


def test_analyze_all_builds_the_report(repo, capsys):
    rep = rda.RepositoryDataAnalyzer(str(repo)).analyze_all()
    names = [a.script_name for a in rep.scripts_analyzed]
    assert names == ["a_all.py", "b_split.py", "c_sample.py"]                 # broken.py is skipped (SyntaxError)
    assert rep.total_scripts == 3
    a, b, c = rep.scripts_analyzed
    assert a.uses_all_data and a.trains_on_test_data and a.issues and not a.has_train_test_split
    assert b.has_train_test_split and b.split_method == "random" and not b.trains_on_test_data
    assert any("2 data sources" in w for w in b.warnings) is False             # 'assert' present -> no consistency warn
    assert c.uses_samples and c.sample_size == 500 and not c.is_exhaustive and c.backtest_dates == ("2020-01-01", "2021-01-01")
    assert any("no explicit train/test split" in w for w in c.warnings)
    assert rep.scripts_with_issues == 1 and rep.scripts_missing_train_val_split == 1
    assert rep.scripts_training_on_test == 1
    assert rep.exhaustive_vs_sample_breakdown == {"exhaustive_testing": 2, "sample_testing": 1}
    assert rep.data_dependency_graph["a_all.py"] == ["prices.parquet"]
    assert rep.source_to_users == {"out.csv": ["a_all.py"]}
    assert any(r.startswith("🔴 CRITICAL: 1 scripts") for r in rep.recommendations)
    assert rep.recommendations[-1].startswith("📌 Create a data_config.py")


def test_report_save_and_print(repo, tmp_path, capsys):
    rep = rda.RepositoryDataAnalyzer(str(repo)).analyze_all()
    capsys.readouterr()
    out = tmp_path / "rep.json"
    rep.save_report(str(out))
    data = json.loads(out.read_text())
    assert data["total_scripts"] == 3 and len(data["scripts_analyzed"]) == 3
    rep.print_report()
    text = capsys.readouterr().out
    assert "REPOSITORY DATA USAGE ANALYSIS REPORT" in text


def test_pattern_heuristics_boundaries(tmp_path):
    def an(src):
        p = tmp_path / "t.py"
        p.write_text(src)
        return rda.RepositoryDataAnalyzer(str(tmp_path))._analyze_script(p)

    assert an("x = 1\n").is_exhaustive
    s = an("df.head(10)\n")
    assert s.uses_samples and s.sample_size == 10 and not s.is_exhaustive
    assert an("df.sample(n=5)\nnrows = 3\n").uses_samples
    t = an("df.loc[:split_point]\n")
    assert t.split_method == "chronological"
    tr = an("scale(df)\nnormalize(df)\ndf.fillna(0)\ndf.dropna()  # nan\n")
    assert tr.data_transformations == ["scaling", "normalization", "null_imputation", "null_removal"]
    assert "drop" not in an("x = 1\n").data_transformations
    assert an("a = '2020-01-01'\n").backtest_dates is None                   # needs two dates
    dup = an("import pandas as pd\na = pd.read_csv('1.csv')\nb = pd.read_csv('2.csv')\n")
    assert any("2 data sources" in w for w in dup.warnings)
    assert not any("data sources" in w for w in an("a = pd.read_csv('1.csv')\nb = pd.read_csv('2.csv')\n"
                                                   "assert a is not None\n").warnings)
    assert not any("data sources" in w for w in an("a = pd.read_csv('1.csv')\nb = pd.read_csv('2.csv')\n"
                                                   "# compare them\n").warnings)
    assert an("shuffle(x)\n").uses_samples
    assert an("train_test_split(a, b)\n").split_method == "random"
    assert an("x = df.copy()\n").trains_on_test_data                         # .copy() alone trips the heuristic


def test_recommendations_variants():
    a = rda.ScriptAnalysis("p", "n.py", loaded_data_sources=["a", "b"], data_transformations=[])
    recs = rda.RepositoryDataAnalyzer(".")._generate_recommendations([a], 0, 0)
    assert len(recs) == 3 and "transformations" in recs[0] and "Multiple scripts use multiple" in recs[1]
    s = rda.ScriptAnalysis("p", "s.py", uses_samples=True)
    recs = rda.RepositoryDataAnalyzer(".")._generate_recommendations([s], 2, 0)
    assert recs[0].startswith("⚠️  2 scripts lack") and "Examples: s.py" in recs[1]


def test_get_func_name_and_string_arg():
    import ast
    c = ast.parse("a.b.read_csv(x)\nfoo(1)\nf()()").body
    assert rda.RepositoryDataAnalyzer._get_func_name(c[0].value.func) == "read_csv"
    assert rda.RepositoryDataAnalyzer._get_func_name(c[1].value.func) == "foo"
    assert rda.RepositoryDataAnalyzer._get_func_name(c[2].value.func) is None
    assert rda.RepositoryDataAnalyzer._extract_string_arg(ast.parse("1").body[0].value) is None


def test_analyze_script_unreadable_returns_none(tmp_path):
    assert rda.RepositoryDataAnalyzer(str(tmp_path))._analyze_script(tmp_path / "missing.py") is None


# =============================== data_validator ===============================

def write_csv(base, name, rows):
    (base / "data").mkdir(exist_ok=True)
    pd.DataFrame(rows).to_csv(base / "data" / f"{name}.csv", index=False)


def test_report_save_and_summary(tmp_path, capsys):
    rep = dv.DataValidator(str(tmp_path)).run_full_validation()
    capsys.readouterr()
    rep.print_summary()
    assert "DATA VALIDATION REPORT SUMMARY" in capsys.readouterr().out
    out = tmp_path / "r.json"
    rep.save_report(str(out))
    assert json.loads(out.read_text())["total_sources"] == rep.total_sources
    assert "Report saved to" in capsys.readouterr().out
    assert rep.to_dict()["summary"] == rep.summary


def test_scan_csv_dedupes_overlapping_patterns_and_skips_unreadable(tmp_path):
    write_csv(tmp_path, "prices", {"symbol": ["A"], "date": ["2024-01-01"], "close": [1.0]})
    (tmp_path / "data" / "empty.csv").write_text("")
    v = dv.DataValidator(str(tmp_path))
    srcs = v._scan_csv_files()
    assert [s.source_name for s in srcs] == ["prices"]
    assert srcs[0].source_type == "csv" and srcs[0].symbols_count == 1 and srcs[0].record_count == 1


def test_scan_parquet_skips_unreadable_files(tmp_path, monkeypatch, capsys):
    (tmp_path / "cache_seed").mkdir()
    (tmp_path / "cache_seed" / "bad.parquet").write_bytes(b"not parquet")
    assert dv.DataValidator(str(tmp_path))._scan_parquet_files() == []
    assert "Error reading bad.parquet" in capsys.readouterr().out


def test_validate_single_source_checks(tmp_path, capsys):
    now = datetime.now().date()
    gappy = [now - timedelta(days=10 * i) for i in range(14)][::-1]
    write_csv(tmp_path, "q", {"symbol": ["A"] * 14, "date": [str(d) for d in gappy],
                              "open": ["x"] * 14, "high": [2.0] * 14, "low": [1.0] * 14, "close": [1.5] * 14,
                              "volume": [1] * 14, "nulls": [None] * 14})
    v = dv.DataValidator(str(tmp_path))
    meta = v._scan_csv_files()[0]
    v._validate_single_source(meta)
    errs = " | ".join(meta.validation_errors)
    assert "High nulls in ['nulls']" in errs and "Column 'open' should be numeric" in errs
    assert "Many date gaps detected (13 gaps > 5 days)" in errs
    assert "stale" not in errs
    assert meta.data_quality_score == pytest.approx(0.7)


def test_validate_single_source_staleness_boundary_and_capitalised_date(tmp_path):
    now = datetime.now().date()
    for name, days, stale in (("fresh30", 30, False), ("stale31", 31, True)):
        write_csv(tmp_path, name, {"Date": [str(now - timedelta(days=days))], "close": [1.0]})
    v = dv.DataValidator(str(tmp_path))
    metas = {m.source_name: m for m in v._scan_csv_files()}
    for name, stale in (("fresh30", False), ("stale31", True)):
        v._validate_single_source(metas[name])
        assert any("stale" in e for e in metas[name].validation_errors) is stale


def test_validate_single_source_unknown_type_and_failure(tmp_path, capsys):
    meta = dv.DataSourceMetadata(source_name="k", source_type="kaggle", path="x", created_at="", last_modified="",
                                 file_size_mb=0, record_count=0, symbols_count=0, date_range=("a", "b"),
                                 columns=[])
    dv.DataValidator(str(tmp_path))._validate_single_source(meta)
    assert meta.validation_errors == []
    meta.source_type = "csv"
    meta.path = str(tmp_path / "gone.csv")
    dv.DataValidator(str(tmp_path))._validate_single_source(meta)
    assert meta.data_quality_score == 0.0 and meta.validation_errors[0].startswith("Failed to validate")


def test_cross_source_discrepancy_threshold(tmp_path):
    base = datetime.now().date()
    rows = lambda close: {"symbol": ["A"] * 3, "date": [str(base - timedelta(days=i)) for i in range(3)],
                          "close": [close] * 3}
    write_csv(tmp_path, "one", rows(100.0))
    write_csv(tmp_path, "two", rows(103.0))                      # 3% apart: flagged
    write_csv(tmp_path, "three", rows(101.9))                    # 1.9% apart from one: not flagged
    v = dv.DataValidator(str(tmp_path))
    metas = v._scan_csv_files()
    for m in metas:
        v._validate_single_source(m)
    issues = v._check_cross_source_consistency(metas)
    pairs = {(i.source_1, i.source_2) for i in issues}
    assert ("one", "two") in pairs or ("two", "one") in pairs
    assert not any({i.source_1, i.source_2} == {"one", "three"} for i in issues)
    assert all(i.field == "close" and i.discrepancy_pct > 0.02 for i in issues)
    assert len({i.date for i in issues if {i.source_1, i.source_2} == {"one", "two"}}) == 3


def test_detect_leakage_and_repo_mapping(tmp_path):
    (tmp_path / "s.py").write_text("x = df.shift(-1)\ntrain = all_data\nuses prices\nsplit random_state = None\n")
    (tmp_path / "t.py").write_text("print('prices')\n")
    v = dv.DataValidator(str(tmp_path))
    issues = v._detect_data_leakage()
    kinds = sorted({(i.issue_type, i.line_number) for i in issues})
    assert ("future_data", 1) in kinds and ("test_in_train", 2) in kinds and ("unfair_split", 4) in kinds
    assert all(i.severity == "low" for i in issues)
    meta = dv.DataSourceMetadata("prices", "csv", "p", "", "", 0, 0, 0, ("a", "b"), [])
    m = v._map_repos_to_data([meta])
    assert set(m) == {str(tmp_path / "s.py"), str(tmp_path / "t.py")}


def test_full_validation_summary_counts(tmp_path, capsys):
    now = datetime.now().date()
    write_csv(tmp_path, "good", {"symbol": ["A"], "date": [str(now)], "close": [1.0]})
    (tmp_path / "s.py").write_text("x = df.shift(-2)\n# good\n")
    rep = dv.DataValidator(str(tmp_path)).run_full_validation()
    assert rep.total_sources >= 1 and rep.avg_quality_score == pytest.approx(1.0)
    assert "Future-looking operations: 1" in rep.summary
    assert any("s.py" in k for k in rep.repo_data_mapping) or rep.repo_data_mapping == {}


def test_kaggle_integrator_and_lineage():
    ds = dv.KaggleDataIntegrator.discover_relevant_datasets(markets=["US"], categories=["x"])
    assert len(ds) == 3 and all({"title", "url", "records"} <= set(d) for d in ds)
    t = dv.DataLineageTracker()
    df = pd.DataFrame({"a": [1, 2]})
    t.track_load("file.csv", "raw", df)
    t.track_transform("raw", "clean", "dropna")
    t.track_transform("never_loaded", "orphan", "x")
    chain = t.get_lineage("clean")
    assert [c.get("operation", c.get("source")) for c in chain] == ["dropna", "file.csv"]
    assert chain[1]["records"] == 2 and chain[1]["columns"] == ["a"]
    assert t.get_lineage("unknown") == []
