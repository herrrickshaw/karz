"""Characterisation tests: refactored modules must reproduce the pre-refactor baseline."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import cases  # noqa: E402

GOLDEN = json.loads((Path(__file__).parent / "golden" / "baseline.json").read_text())


# Parquet file size depends on the installed pyarrow/pandas build, not on this code.
ENV_BOUND_KEYS = {"file_size_mb"}
_FLOAT = re.compile(r"-?\d+\.\d+(?:[eE][-+]?\d+)?")


def _same(a, b):
    """Deep equality; floats (also inside CSV/text strings) compare to 1e-9 relative, since
    last-digit rounding of sums differs between CPU/BLAS builds."""
    if isinstance(a, dict) and isinstance(b, dict):
        a = {k: v for k, v in a.items() if k not in ENV_BOUND_KEYS}
        b = {k: v for k, v in b.items() if k not in ENV_BOUND_KEYS}
        return a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return a == pytest.approx(b, rel=1e-9, abs=1e-12)
    if isinstance(a, str) and isinstance(b, str):
        if a == b:
            return True
        if _FLOAT.sub("#", a) != _FLOAT.sub("#", b):
            return False
        fa, fb = _FLOAT.findall(a), _FLOAT.findall(b)
        return all(float(x) == pytest.approx(float(y), rel=1e-9, abs=1e-12) for x, y in zip(fa, fb))
    return a == b


@pytest.fixture(scope="module")
def current():
    return cases.collect_all()


@pytest.mark.parametrize("module", sorted(GOLDEN))
def test_matches_baseline(current, module):
    assert "CRASH" not in current[module], current[module].get("CRASH")
    assert _same(current[module], GOLDEN[module])
