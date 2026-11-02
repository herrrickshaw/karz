"""Characterisation tests: refactored modules must reproduce the pre-refactor baseline."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

import cases  # noqa: E402

GOLDEN = json.loads((Path(__file__).parent / "golden" / "baseline.json").read_text())


@pytest.fixture(scope="module")
def current():
    return cases.collect_all()


@pytest.mark.parametrize("module", sorted(GOLDEN))
def test_matches_baseline(current, module):
    assert "CRASH" not in current[module], current[module].get("CRASH")
    assert current[module] == GOLDEN[module]
