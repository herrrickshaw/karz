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


def _diffs(a, b, path=""):
    """Deep comparison returning human-readable differences; floats (also inside CSV/text strings)
    compare to 1e-9 relative, since last-digit rounding of sums differs between CPU/BLAS builds."""
    if isinstance(a, dict) and isinstance(b, dict):
        a = {k: v for k, v in a.items() if k not in ENV_BOUND_KEYS}
        b = {k: v for k, v in b.items() if k not in ENV_BOUND_KEYS}
        out = [f"{path}: keys differ {sorted(set(a) ^ set(b))}"] if a.keys() != b.keys() else []
        for k in a.keys() & b.keys():
            out += _diffs(a[k], b[k], f"{path}/{k}")
        return out
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} != {len(b)}: {a!r:.120} vs {b!r:.120}"]
        return [d for i, (x, y) in enumerate(zip(a, b)) for d in _diffs(x, y, f"{path}[{i}]")]
    if isinstance(a, float) and isinstance(b, float):
        return [] if a == pytest.approx(b, rel=1e-9, abs=1e-12) else [f"{path}: {a!r} != {b!r}"]
    if isinstance(a, str) and isinstance(b, str):
        if a == b:
            return []
        if _FLOAT.sub("#", a) == _FLOAT.sub("#", b) and all(
                float(x) == pytest.approx(float(y), rel=1e-9, abs=1e-12)
                for x, y in zip(_FLOAT.findall(a), _FLOAT.findall(b))):
            return []
        return [f"{path}: {a!r:.120} != {b!r:.120}"]
    return [] if a == b else [f"{path}: {a!r:.120} != {b!r:.120}"]


@pytest.fixture(scope="module")
def current():
    return cases.collect_all()


@pytest.mark.parametrize("module", sorted(GOLDEN))
def test_matches_baseline(current, module):
    assert "CRASH" not in current[module], current[module].get("CRASH")
    diffs = _diffs(current[module], GOLDEN[module])
    assert not diffs, "\n".join(diffs)
