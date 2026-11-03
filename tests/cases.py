"""Deterministic characterisation cases shared by the golden generator and the tests.

``tests/golden/baseline.json`` was produced by running :func:`collect_all` against the
ORIGINAL (pre-refactor) modules; the test-suite asserts the refactored modules reproduce it.
Everything is offline and uses temp dirs / synthetic frames.
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import types
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict

import numpy as np
import pandas as pd

VOLATILE_KEYS = {"generated_at", "created_at", "last_modified", "checksums", "timestamp"}


def _scrub(obj: Any, root: str) -> Any:
    """Make an object JSON-safe and independent of timestamps / temp paths."""
    if isinstance(obj, dict):
        return {str(k).replace(root, "<ROOT>"): _scrub(v, root) for k, v in obj.items() if k not in VOLATILE_KEYS}
    if isinstance(obj, (list, tuple, set)):
        items = [_scrub(v, root) for v in obj]
        return sorted(items, key=lambda x: json.dumps(x, sort_keys=True)) if isinstance(obj, set) else items
    if isinstance(obj, str):
        return obj.replace(root, "<ROOT>")
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        return round(float(obj), 10)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, pd.DataFrame):
        return json.loads(obj.to_json(orient="split", date_format="iso"))
    return obj


@contextlib.contextmanager
def _freeze_clock(module):
    """Pin ``module.datetime.now()`` so 'days stale' text matches the recorded baseline."""
    real = module.datetime
    module.datetime = _FrozenDatetime
    try:
        yield
    finally:
        module.datetime = real


def _capture(fn: Callable[[], Any], root: str) -> Dict[str, Any]:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        value = fn()
    out = buf.getvalue().replace(root, "<ROOT>")
    # Per-run wall-clock text in stdout (dates derived from "now") is not comparable.
    out = "\n".join(
        line for line in out.splitlines() if "Date range:" not in line and not line.startswith("Generated:"))
    return {"value": _scrub(value, root), "stdout": out}


def _ohlc_frame(n: int = 40, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    return pd.DataFrame({
        "date": pd.date_range("2023-01-02", periods=n, freq="B"),
        "symbol": ["AAA"] * n,
        "open": close - 0.5, "high": close + 1.0, "low": close - 1.0,
        "close": close, "volume": rng.integers(1000, 5000, n),
    })


def case_data_config() -> Dict[str, Any]:
    import data_config as dc

    cfg = dc.DataConfig()
    df = _ohlc_frame()
    bad = df.copy()
    bad.loc[3, "high"] = bad.loc[3, "low"] - 5
    bad.loc[5:9, "volume"] = np.nan
    bad = bad.drop(columns=["open"])
    split_src = pd.DataFrame({"d": ["2016-05-01", "2022-06-01", "2023-03-01", "2024-07-01"], "v": [1, 2, 3, 4]})
    now = datetime.now()
    return {
        "ranges": [cfg.date_splits.get_train_range(), cfg.date_splits.get_validation_range(),
                   cfg.date_splits.get_test_range()],
        "no_overlap": cfg.date_splits.validate_no_overlap(),
        "markets": dc.DataSourceRegistry.get_all_markets(),
        "src_in": dc.DataSourceRegistry.get_source("IN"),
        "src_us": dc.DataSourceRegistry.get_source("US"),
        "src_none": dc.DataSourceRegistry.get_source("ZZ"),
        "purposes": [cfg.get_split_for_purpose(p) for p in ("backtest", "validation", "training", "x")],
        "validate_clean": cfg.validation.validate_dataframe(df.copy()),
        "validate_bad": cfg.validation.validate_dataframe(bad.copy()),
        "filter": {s: dc.filter_data_by_split(split_src.copy(), "d", s)["v"].tolist()
                   for s in ("train", "validation", "test")},
        "fresh": [cfg.freshness.check_freshness(now - timedelta(minutes=30), cfg.freshness.INTRADAY_SCREENER),
                  cfg.freshness.check_freshness(now - timedelta(hours=10), cfg.freshness.DAILY_SCREENER),
                  cfg.freshness.check_freshness(now - timedelta(days=3, hours=1), cfg.freshness.WEEKLY_ANALYSIS),
                  cfg.freshness.check_freshness(now, {"purpose": "x"})],
        "acceptable": [cfg.consistency.acceptable_difference(*a) for a in
                       [(100, 101, 2.0), (100, 110, 2.0), (0, 0.001, 2.0), (0, 5, 2.0)]],
        "universe": {p: cfg.universe.get_universe(p) for p in ("india_focus", "us_large_cap", "global_all", "nope")},
        "universe_check": dc.validate_universe_consistency(
            dc.Universe.INDIA_FOCUS, pd.DataFrame({"symbol": ["TCS", "INFY"]})),
        "bad_split": _raises(lambda: dc.filter_data_by_split(split_src.copy(), "d", "oops")),
    }


def _raises(fn: Callable[[], Any]) -> str:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 - characterising arbitrary failures
        return f"{type(exc).__name__}: {exc}"
    return "no error"


def _make_data_tree(root: Path) -> None:
    (root / "cache_seed").mkdir(parents=True)
    d1 = _ohlc_frame(60, 1)
    d2 = _ohlc_frame(60, 2)
    d2["close"] = d1["close"] * 1.05
    d1.to_parquet(root / "cache_seed" / "alpha.parquet")
    d2.to_parquet(root / "cache_seed" / "beta.parquet")
    broken = _ohlc_frame(30, 3)
    broken.loc[2, "high"] = broken.loc[2, "low"] - 3
    broken = pd.concat([broken, broken.iloc[:3]])
    broken.to_csv(root / "prices.csv", index=False)
    (root / "scripts").mkdir()
    (root / "scripts" / "bt.py").write_text(
        "import pandas as pd\ndf = pd.read_parquet('alpha')\nx = df.shift(-1)\n"
        "y = df.sample(frac=0.5)\ntrain = all_data\n")


class _FrozenDatetime(datetime):
    """``datetime`` whose ``now()`` is the day the baseline was recorded (staleness is clock-dependent)."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 2, 12, 0, 0)


def case_data_validator() -> Dict[str, Any]:
    import data_validator as dv

    with tempfile.TemporaryDirectory() as tmp, _freeze_clock(dv):
        root = Path(tmp)
        _make_data_tree(root)
        validator = dv.DataValidator(base_path=str(root))
        res = _capture(lambda: validator.run_full_validation().to_dict(), str(root))
        res["extract_symbols"] = sorted(dv.DataValidator._extract_symbols(_ohlc_frame(3)))
        res["date_range"] = dv.DataValidator._extract_date_range(_ohlc_frame(3))
        res["date_range_none"] = dv.DataValidator._extract_date_range(pd.DataFrame({"x": [1]}))
        res["kaggle"] = dv.KaggleDataIntegrator.discover_relevant_datasets()
        tracker = dv.DataLineageTracker()
        tracker.track_load("src", "raw", _ohlc_frame(4))
        tracker.track_transform("raw", "clean", "dropna")
        res["lineage"] = _scrub(tracker.get_lineage("clean"), tmp)
        report_path = root / "report.json"
        _capture(lambda: validator.report.save_report(str(report_path)), str(root))
        res["saved_keys"] = sorted(json.loads(report_path.read_text()))
        return res


def case_repo_data_analyzer() -> Dict[str, Any]:
    import repo_data_analyzer as rda

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.py").write_text(
            "import pandas as pd\nfrom sklearn.model_selection import train_test_split\n"
            "df = pd.read_csv('in.csv')\ndf2 = pd.read_parquet('b.parquet')\n"
            "tr, te = train_test_split(df, test_size=0.2)\ndf.to_csv('out.csv')\n"
            "df = df.fillna(0)\n")
        (root / "b.py").write_text(
            "import pandas as pd\nd = pd.read_parquet('x.parquet')\nall_data = d.copy()\n"
            "a = '2020-01-01'\nb = '2021-01-01'\nz = d.head(100)\n")
        (root / "venv_skip.py").write_text("x = 1\n")
        (root / "bad.py").write_text("def (:\n")
        analyzer = rda.RepositoryDataAnalyzer(base_path=str(root))
        res = _capture(lambda: analyzer.analyze_all(), str(root))
        res["value"] = None  # dataclass not JSON; use dict below
        report = analyzer.report
        res["report"] = _scrub(__import__("dataclasses").asdict(report), tmp)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            report.print_report()
        res["printed"] = "\n".join(
            line for line in buf.getvalue().replace(tmp, "<ROOT>").splitlines()
            if not line.startswith("Generated:"))
        out = root / "r.json"
        report.save_report(str(out))
        res["saved_keys"] = sorted(json.loads(out.read_text()))
        v = rda.DataSplitValidator
        frame = pd.DataFrame({"date": pd.date_range("2020-01-01", periods=10), "v": range(10)})
        res["chrono"] = _scrub({k: [str(x) for x in t] for k, t in
                                v.validate_chronological_split(frame, "date").items()}, tmp)
        res["leak"] = [v.check_data_leakage(("2020-01-01", "2020-06-01"), ("2020-07-01", "2020-09-01"),
                                            ("2020-10-01", "2020-12-01")),
                       v.check_data_leakage(("2020-01-01", "2020-08-01"), ("2020-07-01", "2020-09-01"),
                                            ("2020-10-01", "2020-12-01"))]
        return res


def _score_frame(n: int = 60, seed: int = 5) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    cols = ["debt_expansion", "capex_acceleration", "profit_reinvestment", "profitability_quality",
            "sustainability", "timing_alignment", "leverage_health"]
    df = pd.DataFrame({c + "_score": rng.uniform(0, 100, n) for c in cols})
    df["fcf_generation"] = rng.uniform(0, 100, n)
    df["stock_return_12m"] = rng.normal(8, 20, n)
    return df


def case_backtest_weight_optimization() -> Dict[str, Any]:
    import backtest_weight_optimization as bo

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        df = _score_frame()
        res: Dict[str, Any] = {}
        bt = None

        def build():
            nonlocal bt
            bt = bo.WeightBacktester(df, use_test_split=True)
        res["init"] = _capture(build, tmp)
        scores = bt.calculate_composite_score(df, bt.BASELINE_WEIGHTS)
        res["scores"] = _scrub(scores.tolist(), tmp)
        res["signals"] = _scrub(bt.generate_signals(scores).tolist(), tmp)
        out: Dict[str, Any] = {}
        res["run"] = _capture(lambda: out.update(bt.run_backtest("both")), tmp)
        res["metrics"] = _scrub(out, tmp)
        res["report"] = _capture(lambda: bt.generate_report(out), tmp)
        csv = root / "res.csv"
        res["export"] = _capture(lambda: bt.export_results(out, str(csv)), tmp)
        res["csv"] = csv.read_text()
        for ws in ("baseline", "optimized"):
            o2: Dict[str, Any] = {}
            res["run_" + ws] = _capture(lambda o2=o2, ws=ws: o2.update(bt.run_backtest(ws)), tmp)["stdout"]
            res["keys_" + ws] = sorted(o2)
        # data-source driver
        data = _score_frame(80, 6)
        data["date"] = pd.date_range("2022-06-01", periods=80, freq="10D")
        for c in ("open", "high", "low", "close", "volume"):
            data[c] = 10.0
        pq = root / "d.parquet"
        data.to_parquet(pq)
        res["driver_split"] = _capture(lambda: bo.backtest_from_data_source(str(pq), "IN", True, "both"), tmp)
        res["driver_all"] = _capture(lambda: bo.backtest_from_data_source(str(pq), "IN", False, "baseline"), tmp)
        res["driver_missing"] = _capture(
            lambda: bo.backtest_from_data_source(str(root / "nope.parquet")), tmp)
        return res


def _stub_correlation_analysis() -> types.ModuleType:
    mod = types.ModuleType("correlation_analysis")
    mod.PERF = ["cagr", "return_12m"]

    def analyse(market, target):
        return pd.DataFrame({"metric": ["pe", "roe", "missing_col"], "p_value": [0.01, 0.05, 0.9],
                             "spearman_rho": [-0.5, 0.4, 0.1]})

    def _perf_features(market):
        rng = np.random.default_rng(9)
        return pd.DataFrame({"Symbol": [f"S{i}" for i in range(40)], "cagr": rng.normal(0.1, 0.2, 40)})
    mod.analyse, mod._perf_features = analyse, _perf_features
    return mod


def case_backtest_weight_validation() -> Dict[str, Any]:
    sys.modules["correlation_analysis"] = _stub_correlation_analysis()
    sys.modules.pop("backtest_weight_validation", None)
    import backtest_weight_validation as bv

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rng = np.random.default_rng(10)
        fund = pd.DataFrame({"Symbol": [f"S{i}" for i in range(40)], "pe": rng.normal(20, 5, 40),
                             "roe": rng.normal(0.15, 0.05, 40)})
        fund.to_parquet(root / "US.parquet")
        bv.FUND_DIR = root
        res: Dict[str, Any] = {
            "zscore": _scrub(bv._zscore(pd.Series([1.0, 2.0, 3.0, 4.0])).tolist(), tmp),
            "zscore_const": _scrub(bv._zscore(pd.Series([2.0, 2.0])).tolist(), tmp),
        }
        merged, used, picks = bv.build_composite("US")
        res["composite"] = _scrub({"used": used, "picks": picks, "comp": merged["composite"]}, tmp)
        res["validate"] = _capture(lambda: bv.validate("US", "cagr", 5, False), tmp)
        res["validate_small"] = _capture(lambda: bv.validate("US", "cagr", 50, False), tmp)
        res["proper"] = _capture(lambda: bv.validate_with_proper_split("US", "cagr", 4, True), tmp)
        sys.argv = ["bv", "--market", "US", "--target", "cagr", "--no-split"]
        res["main"] = _capture(bv.main, tmp)
        return res


def collect_all() -> Dict[str, Any]:
    """Run every case; failures are recorded (not raised) so crashes are characterised too."""
    out: Dict[str, Any] = {}
    for name, fn in [("data_config", case_data_config), ("data_validator", case_data_validator),
                     ("repo_data_analyzer", case_repo_data_analyzer),
                     ("backtest_weight_optimization", case_backtest_weight_optimization),
                     ("backtest_weight_validation", case_backtest_weight_validation)]:
        try:
            out[name] = fn()
        except Exception as exc:  # noqa: BLE001
            out[name] = {"CRASH": f"{type(exc).__name__}: {exc}"}
    return json.loads(json.dumps(out, sort_keys=True, default=str))
