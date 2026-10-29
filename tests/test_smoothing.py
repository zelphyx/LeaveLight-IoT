"""Test smoothing sekunder sesuai FR-04 dan TC-05 spec LeaveLight."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "laptop"))
from smoothing import LuxSmoother


def test_smoother_initial_state():
    smoother = LuxSmoother(window=3)
    assert smoother.current() is None


def test_smoother_moving_average():
    smoother = LuxSmoother(window=3)
    assert smoother.add(100.0) == 100.0
    assert smoother.add(110.0) == 105.0
    assert smoother.add(120.0) == 110.0
    # Window moves: removes 100, adds 150 -> (110 + 120 + 150) / 3 = 126.666...
    assert pytest.approx(smoother.add(150.0), 0.01) == 126.67


def test_smoother_ignores_none_and_invalid():
    smoother = LuxSmoother(window=3)
    smoother.add(100.0)
    smoother.add(110.0)
    assert smoother.add(None) == 105.0
    assert smoother.add("invalid") == 105.0
    assert smoother.add(True) == 105.0  # boolean skipped


def test_smoother_reset():
    smoother = LuxSmoother(window=3)
    smoother.add(100.0)
    smoother.reset()
    assert smoother.current() is None
