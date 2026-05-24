"""Tests for agent-progress-tracker."""

from __future__ import annotations

import pytest

from agent_progress_tracker import ProgressTracker, Step, StepStatus

# ---------------------------------------------------------------------------
# StepStatus
# ---------------------------------------------------------------------------


def test_step_status_values():
    assert StepStatus.PENDING.value == "pending"
    assert StepStatus.RUNNING.value == "running"
    assert StepStatus.DONE.value == "done"
    assert StepStatus.SKIPPED.value == "skipped"
    assert StepStatus.FAILED.value == "failed"


def test_step_status_is_str():
    assert isinstance(StepStatus.DONE, str)


# ---------------------------------------------------------------------------
# Step
# ---------------------------------------------------------------------------


def test_step_defaults():
    s = Step(step_id="x", name="X")
    assert s.weight == 1.0
    assert s.status == StepStatus.PENDING
    assert not s.is_complete
    assert s.duration_ms is None


def test_step_is_complete_done():
    s = Step(step_id="x", name="X", status=StepStatus.DONE)
    assert s.is_complete


def test_step_is_complete_skipped():
    s = Step(step_id="x", name="X", status=StepStatus.SKIPPED)
    assert s.is_complete


def test_step_is_not_complete_failed():
    s = Step(step_id="x", name="X", status=StepStatus.FAILED)
    assert not s.is_complete


def test_step_duration_ms():
    s = Step(step_id="x", name="X", started_at=100.0, finished_at=101.5)
    assert s.duration_ms == pytest.approx(1500.0)


def test_step_duration_ms_none_if_not_finished():
    s = Step(step_id="x", name="X", started_at=100.0)
    assert s.duration_ms is None


def test_step_to_dict():
    s = Step(step_id="x", name="X", weight=2.0, status=StepStatus.DONE)
    d = s.to_dict()
    assert d["step_id"] == "x"
    assert d["weight"] == 2.0
    assert d["status"] == "done"


def test_step_repr():
    s = Step(step_id="s1", name="step one")
    r = repr(s)
    assert "s1" in r


# ---------------------------------------------------------------------------
# ProgressTracker — registration
# ---------------------------------------------------------------------------


def test_add_step():
    t = ProgressTracker()
    s = t.add_step("a", name="Step A", weight=2.0)
    assert s.step_id == "a"
    assert s.name == "Step A"
    assert s.weight == 2.0


def test_add_step_default_name():
    t = ProgressTracker()
    s = t.add_step("my-step")
    assert s.name == "my-step"


def test_add_duplicate_raises():
    t = ProgressTracker()
    t.add_step("a")
    with pytest.raises(ValueError, match="already registered"):
        t.add_step("a")


def test_add_step_zero_weight_raises():
    t = ProgressTracker()
    with pytest.raises(ValueError, match="weight"):
        t.add_step("a", weight=0.0)


def test_add_step_negative_weight_raises():
    t = ProgressTracker()
    with pytest.raises(ValueError):
        t.add_step("a", weight=-1.0)


def test_remove_step():
    t = ProgressTracker()
    t.add_step("a")
    t.remove_step("a")
    assert t.get_step("a") is None


def test_remove_missing_step_raises():
    t = ProgressTracker()
    with pytest.raises(KeyError):
        t.remove_step("nonexistent")


def test_steps_order_preserved():
    t = ProgressTracker()
    t.add_step("c")
    t.add_step("a")
    t.add_step("b")
    ids = [s.step_id for s in t.steps]
    assert ids == ["c", "a", "b"]


# ---------------------------------------------------------------------------
# ProgressTracker — transitions
# ---------------------------------------------------------------------------


def test_start_step():
    t = ProgressTracker()
    t.add_step("s")
    step = t.start("s")
    assert step.status == StepStatus.RUNNING
    assert step.started_at is not None


def test_complete_step():
    t = ProgressTracker()
    t.add_step("s")
    t.start("s")
    step = t.complete("s")
    assert step.status == StepStatus.DONE
    assert step.finished_at is not None


def test_complete_without_start_sets_timestamps():
    t = ProgressTracker()
    t.add_step("s")
    step = t.complete("s")
    assert step.status == StepStatus.DONE
    assert step.started_at is not None
    assert step.finished_at is not None


def test_skip_step():
    t = ProgressTracker()
    t.add_step("s")
    step = t.skip("s")
    assert step.status == StepStatus.SKIPPED
    assert step.is_complete


def test_fail_step():
    t = ProgressTracker()
    t.add_step("s")
    step = t.fail("s")
    assert step.status == StepStatus.FAILED
    assert not step.is_complete


def test_transition_missing_step_raises():
    t = ProgressTracker()
    with pytest.raises(KeyError):
        t.start("nonexistent")


def test_reset_clears_status():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    t.complete("a")
    t.fail("b")
    t.reset()
    for step in t.steps:
        assert step.status == StepStatus.PENDING
        assert step.started_at is None
        assert step.finished_at is None


# ---------------------------------------------------------------------------
# ProgressTracker — snapshot
# ---------------------------------------------------------------------------


def test_snapshot_empty():
    t = ProgressTracker()
    snap = t.snapshot()
    assert snap.percent_complete == 0.0
    assert snap.steps_done == 0
    assert snap.steps_total == 0


def test_snapshot_none_done():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    snap = t.snapshot()
    assert snap.percent_complete == 0.0
    assert snap.steps_done == 0
    assert snap.steps_total == 2


def test_snapshot_all_equal_weight():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    t.add_step("c")
    t.add_step("d")
    t.complete("a")
    t.complete("b")
    snap = t.snapshot()
    assert snap.percent_complete == pytest.approx(50.0)
    assert snap.steps_done == 2


def test_snapshot_unequal_weights():
    t = ProgressTracker()
    t.add_step("small", weight=1.0)
    t.add_step("large", weight=3.0)
    t.complete("small")
    snap = t.snapshot()
    assert snap.percent_complete == pytest.approx(25.0)  # 1/(1+3)


def test_snapshot_skipped_counts():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    t.skip("a")
    snap = t.snapshot()
    assert snap.steps_done == 1
    assert snap.percent_complete == pytest.approx(50.0)


def test_snapshot_failed_does_not_count():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    t.fail("a")
    snap = t.snapshot()
    assert snap.steps_done == 0
    assert snap.steps_failed == 1
    assert snap.percent_complete == 0.0


def test_snapshot_100_when_all_done():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    t.complete("a")
    t.complete("b")
    snap = t.snapshot()
    assert snap.percent_complete == pytest.approx(100.0)


def test_snapshot_current_step():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    t.start("b")
    snap = t.snapshot()
    assert snap.current_step is not None
    assert snap.current_step.step_id == "b"


def test_snapshot_no_current_when_none_running():
    t = ProgressTracker()
    t.add_step("a")
    snap = t.snapshot()
    assert snap.current_step is None


def test_snapshot_eta_none_with_zero_done():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    snap = t.snapshot()
    assert snap.eta_ms is None


def test_snapshot_eta_none_when_all_done():
    t = ProgressTracker()
    t.add_step("a")
    t.complete("a")
    snap = t.snapshot()
    # 100% done — no remaining weight → eta is None
    assert snap.eta_ms is None


def test_snapshot_eta_positive_when_partial():
    calls = [0.0, 1.0, 1.0]  # start, complete("a"), snapshot
    idx = 0

    def fake_clock():
        nonlocal idx
        v = calls[min(idx, len(calls) - 1)]
        idx += 1
        return v

    t = ProgressTracker(clock=fake_clock)
    t.add_step("a", weight=1.0)
    t.add_step("b", weight=1.0)
    t.complete("a")
    snap = t.snapshot()
    assert snap.eta_ms is not None
    assert snap.eta_ms > 0


def test_snapshot_is_complete_all_done():
    t = ProgressTracker()
    t.add_step("a")
    t.complete("a")
    snap = t.snapshot()
    assert snap.is_complete


def test_snapshot_not_complete_with_pending():
    t = ProgressTracker()
    t.add_step("a")
    t.add_step("b")
    t.complete("a")
    snap = t.snapshot()
    assert not snap.is_complete


def test_snapshot_to_dict_keys():
    t = ProgressTracker()
    d = t.snapshot().to_dict()
    assert "percent_complete" in d
    assert "steps_done" in d
    assert "steps_total" in d
    assert "eta_ms" in d
    assert "elapsed_ms" in d


def test_repr():
    t = ProgressTracker()
    t.add_step("a")
    t.complete("a")
    r = repr(t)
    assert "ProgressTracker" in r
