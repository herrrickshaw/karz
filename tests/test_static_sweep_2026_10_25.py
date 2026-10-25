"""Proof tests for the 2026-10-25 static-analysis sweep (karz)."""
import hashlib
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

import data_config as dc
from data_validator import DataValidator as DataIntegrityValidator
from repo_data_analyzer import DataSplitValidator


def test_compute_file_hash_honours_algorithm(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"karz" * 100)
    assert DataIntegrityValidator._compute_file_hash(p, "md5") == hashlib.md5(p.read_bytes()).hexdigest()
    assert DataIntegrityValidator._compute_file_hash(p) == hashlib.sha256(p.read_bytes()).hexdigest()


def test_chronological_split_rejects_ratios_not_summing_to_one():
    df = pd.DataFrame({"d": pd.date_range("2020-01-01", periods=10)})
    with pytest.raises(ValueError):
        DataSplitValidator.validate_chronological_split(df, "d", 0.6, 0.2, 0.4)


def test_chronological_split_still_works_for_valid_ratios():
    df = pd.DataFrame({"d": pd.date_range("2020-01-01", periods=10)})
    s = DataSplitValidator.validate_chronological_split(df, "d", 0.5, 0.3, 0.2)
    assert s["train"][1] == pd.Timestamp("2020-01-05")
    assert s["test"][0] == pd.Timestamp("2020-01-09")


def test_check_freshness_accepts_timezone_aware_timestamp():
    aware = datetime.now(timezone.utc) - timedelta(hours=2)
    fresh, msg = dc.FreshnessRequirements.check_freshness(aware, {"max_age_hours": 1})
    assert fresh is False and "2.0 hours" in msg


def test_validate_no_overlap_raises_even_with_asserts_stripped():
    code = (
        "import data_config as dc\n"
        "dc.DateSplits.TRAIN_END = '2030-01-01'\n"
        "try:\n"
        "    dc.DateSplits.validate_no_overlap()\n"
        "except Exception as e:\n"
        "    print('RAISED', type(e).__name__)\n"
        "else:\n"
        "    print('PASSED_SILENTLY')\n"
    )
    repo_root = str(pathlib.Path(dc.__file__).parent)
    out = subprocess.run([sys.executable, "-O", "-c", code], capture_output=True, text=True,
                         cwd=repo_root, env={**os.environ, "PYTHONPATH": repo_root})
    assert "RAISED" in out.stdout, out.stdout + out.stderr
