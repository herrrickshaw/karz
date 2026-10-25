"""Tests for data_validator.py on a temporary directory (no network, no real data)."""
from datetime import datetime, timedelta

import pandas as pd
import pytest

from data_validator import DataLineageTracker, DataValidator


def write_clean_parquet(base, name="prices", symbols=("AAA",), days=20):
    (base / "cache_seed").mkdir(exist_ok=True)
    end = datetime.now().date()
    rows = []
    for s in symbols:
        for d in pd.bdate_range(end - timedelta(days=days), end):
            rows.append({"symbol": s, "date": d, "open": 10.0, "high": 11.0,
                         "low": 9.0, "close": 10.5, "volume": 100})
    pd.DataFrame(rows).to_parquet(base / "cache_seed" / f"{name}.parquet")


def test_extract_symbols_and_date_range():
    df = pd.DataFrame({"Ticker": ["A", "B", "A"], "Date": ["2024-01-02", "2024-01-05", "2024-01-03"]})
    assert DataValidator._extract_symbols(df) == {"A", "B"}
    assert DataValidator._extract_date_range(df) == ("2024-01-02", "2024-01-05")
    assert DataValidator._extract_date_range(pd.DataFrame({"x": [1]})) == ("unknown", "unknown")


def test_compute_file_hash_matches_hashlib(tmp_path):
    import hashlib
    p = tmp_path / "f.bin"
    p.write_bytes(b"abc")
    assert DataValidator._compute_file_hash(p) == hashlib.sha256(b"abc").hexdigest()


def test_validate_single_source_flags_problems(tmp_path):
    (tmp_path / "cache_seed").mkdir()
    df = pd.DataFrame({"date": pd.to_datetime(["2020-01-01", "2020-01-01"]),
                       "open": [1.0, 1.0], "high": [0.5, 0.5], "low": [1.0, 1.0],
                       "close": [1.0, 1.0], "volume": [1, 1]})
    df.to_parquet(tmp_path / "cache_seed" / "bad.parquet")
    v = DataValidator(str(tmp_path))
    meta = v._scan_parquet_files()[0]
    v._validate_single_source(meta)
    errs = " | ".join(meta.validation_errors)
    assert "duplicate rows" in errs and "high < low" in errs and "stale" in errs
    assert meta.data_quality_score == pytest.approx(0.7)


def test_full_validation_of_one_clean_source_scores_100pct(tmp_path):
    # The four hard-coded Kaggle entries are never downloaded or validated;
    # they must not be averaged in as 0 % quality.
    write_clean_parquet(tmp_path)
    report = DataValidator(str(tmp_path)).run_full_validation()
    validated = [s for s in report.data_sources if s.source_type == "parquet"]
    assert validated[0].data_quality_score == 1.0
    assert report.avg_quality_score == pytest.approx(1.0)


def test_csv_in_data_dir_is_inventoried_once(tmp_path):
    (tmp_path / "data").mkdir()
    pd.DataFrame({"symbol": ["A"], "date": ["2024-01-02"], "close": [1.0]}).to_csv(
        tmp_path / "data" / "x.csv", index=False)
    csvs = DataValidator(str(tmp_path))._scan_csv_files()
    assert [s.source_name for s in csvs] == ["x"]


def test_cross_source_detects_close_discrepancy_over_2pct(tmp_path):
    v = DataValidator(str(tmp_path))
    dates = pd.to_datetime(["2024-01-02", "2024-01-03"])
    v._loaded_data = {
        "a": pd.DataFrame({"symbol": "AAA", "date": dates, "close": [100.0, 100.0]}),
        "b": pd.DataFrame({"symbol": "AAA", "date": dates, "close": [100.0, 103.0]}),
    }
    from data_validator import DataSourceMetadata
    metas = [DataSourceMetadata(n, "parquet", n, "", "", 0, 0, 0, ("", "")) for n in ("a", "b")]
    issues = v._check_cross_source_consistency(metas)
    assert len(issues) == 1 and issues[0].value_2 == 103.0
    assert issues[0].discrepancy_pct == pytest.approx(0.03)


def test_leakage_scan_flags_negative_shift(tmp_path):
    (tmp_path / "s.py").write_text("y = df['c'].shift(-5)\nz = 1\n")
    issues = DataValidator(str(tmp_path))._detect_data_leakage()
    assert [(i.line_number, i.issue_type) for i in issues] == [(1, "future_data")]


def test_lineage_chain():
    t = DataLineageTracker()
    t.track_load("file.parquet", "raw", pd.DataFrame({"a": [1, 2]}))
    t.track_transform("raw", "clean", "dropna")
    chain = t.get_lineage("clean")
    assert [c.get("operation") for c in chain] == ["dropna", None]
    assert chain[1]["records"] == 2


@pytest.mark.xfail(strict=True, reason="Known bug, not fixed: 'Unique Symbols' sums per-source "
                                        "counts, so a symbol present in two sources counts twice")
def test_total_symbols_counts_unique_symbols_across_sources(tmp_path):
    write_clean_parquet(tmp_path, "one", symbols=("AAA",))
    write_clean_parquet(tmp_path, "two", symbols=("AAA",))
    report = DataValidator(str(tmp_path)).run_full_validation()
    assert report.total_symbols == 1
