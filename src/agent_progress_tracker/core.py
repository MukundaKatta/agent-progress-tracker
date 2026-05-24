"""Weight-based progress percentage and ETA for multi-step agent runs.

Define the steps up front, then mark them as they complete.  Get a
:class:`ProgressSnapshot` at any point with ``percent_complete``,
``steps_done``, and an optional ``eta_ms`` estimate.

Example::

    from agent_progress_tracker import ProgressTracker

    tracker = ProgressTracker()
    tracker.add_step("fetch",    weight=1)
    tracker.add_step("analyse",  weight=3)
    tracker.add_step("generate", weight=2)
    tracker.add_step("review",   weight=1)

    tracker.start("fetch")
    tracker.complete("fetch")

    snap = tracker.snapshot()
    print(snap.percent_complete)   # 14.3  (1 / 7 total weight)
    print(snap.steps_done)         # 1
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class StepStatus(str, Enum):
    """Lifecycle state of a single step."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    FAILED = "failed"


# Statuses counted as "complete" for weight calculations
_COMPLETE_STATUSES = {StepStatus.DONE, StepStatus.SKIPPED}


@dataclass
class Step:
    """A single tracked step.

    Attributes:
        step_id:     Unique identifier for this step.
        name:        Human-readable label.
        weight:      Relative weight used for percentage calculation.
        status:      Current :class:`StepStatus`.
        started_at:  Unix timestamp when the step started, or ``None``.
        finished_at: Unix timestamp when the step finished, or ``None``.
    """

    step_id: str
    name: str
    weight: float = 1.0
    status: StepStatus = StepStatus.PENDING
    started_at: float | None = None
    finished_at: float | None = None

    @property
    def is_complete(self) -> bool:
        """``True`` when status is DONE or SKIPPED."""
        return self.status in _COMPLETE_STATUSES

    @property
    def duration_ms(self) -> float | None:
        """Wall-clock duration in milliseconds, or ``None`` if not finished."""
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at) * 1000.0

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "step_id": self.step_id,
            "name": self.name,
            "weight": self.weight,
            "status": self.status.value,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
        }

    def __repr__(self) -> str:
        return (
            f"Step(step_id={self.step_id!r},"
            f" status={self.status.value!r},"
            f" weight={self.weight})"
        )


@dataclass
class ProgressSnapshot:
    """A point-in-time snapshot of overall progress.

    Attributes:
        percent_complete: 0.0–100.0 based on weights of completed steps.
        steps_done:       Number of steps in DONE or SKIPPED state.
        steps_total:      Total number of registered steps.
        steps_failed:     Number of steps in FAILED state.
        current_step:     The first RUNNING step, or ``None``.
        elapsed_ms:       Wall-clock time since the tracker was created.
        eta_ms:           Estimated remaining time in ms, or ``None`` if
                          no steps have completed yet.
    """

    percent_complete: float
    steps_done: int
    steps_total: int
    steps_failed: int
    current_step: Step | None
    elapsed_ms: float
    eta_ms: float | None

    @property
    def is_complete(self) -> bool:
        """``True`` when all steps are done/skipped or failed (nothing pending)."""
        return self.steps_done + self.steps_failed == self.steps_total

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict."""
        return {
            "percent_complete": self.percent_complete,
            "steps_done": self.steps_done,
            "steps_total": self.steps_total,
            "steps_failed": self.steps_failed,
            "current_step": self.current_step.to_dict() if self.current_step else None,
            "elapsed_ms": self.elapsed_ms,
            "eta_ms": self.eta_ms,
            "is_complete": self.is_complete,
        }

    def __repr__(self) -> str:
        return (
            f"ProgressSnapshot(percent={self.percent_complete:.1f}%,"
            f" done={self.steps_done}/{self.steps_total})"
        )


class ProgressTracker:
    """Track progress through a sequence of weighted steps.

    Args:
        clock: Optional callable returning the current time in seconds.
               Defaults to :func:`time.monotonic`.
    """

    def __init__(self, *, clock: Any = None) -> None:
        self._clock = clock if clock is not None else time.monotonic
        self._start: float = self._clock()
        self._steps: dict[str, Step] = {}
        self._order: list[str] = []  # insertion order

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def add_step(
        self,
        step_id: str,
        *,
        name: str = "",
        weight: float = 1.0,
    ) -> Step:
        """Register a new step.

        Args:
            step_id: Unique step identifier.
            name:    Human-readable label (defaults to *step_id*).
            weight:  Relative weight (positive float).

        Raises:
            ValueError: If *step_id* is already registered, or *weight* <= 0.

        Returns:
            The created :class:`Step`.
        """
        if step_id in self._steps:
            raise ValueError(f"Step {step_id!r} is already registered")
        if weight <= 0:
            raise ValueError(f"weight must be > 0, got {weight}")
        step = Step(step_id=step_id, name=name or step_id, weight=weight)
        self._steps[step_id] = step
        self._order.append(step_id)
        return step

    def remove_step(self, step_id: str) -> None:
        """Remove a registered step.

        Raises:
            KeyError: If *step_id* is not registered.
        """
        if step_id not in self._steps:
            raise KeyError(f"Step {step_id!r} not found")
        del self._steps[step_id]
        self._order.remove(step_id)

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def start(self, step_id: str) -> Step:
        """Mark step as RUNNING.

        Raises:
            KeyError: If *step_id* is not registered.
        """
        step = self._get(step_id)
        step.status = StepStatus.RUNNING
        step.started_at = self._clock()
        return step

    def complete(self, step_id: str) -> Step:
        """Mark step as DONE.

        Raises:
            KeyError: If *step_id* is not registered.
        """
        step = self._get(step_id)
        step.status = StepStatus.DONE
        if step.started_at is None:
            step.started_at = step.finished_at = self._clock()
        else:
            step.finished_at = self._clock()
        return step

    def skip(self, step_id: str) -> Step:
        """Mark step as SKIPPED (counts towards completion).

        Raises:
            KeyError: If *step_id* is not registered.
        """
        step = self._get(step_id)
        step.status = StepStatus.SKIPPED
        step.finished_at = self._clock()
        return step

    def fail(self, step_id: str) -> Step:
        """Mark step as FAILED (does not count towards completion).

        Raises:
            KeyError: If *step_id* is not registered.
        """
        step = self._get(step_id)
        step.status = StepStatus.FAILED
        step.finished_at = self._clock()
        return step

    def reset(self) -> None:
        """Reset all steps to PENDING and restart the timer."""
        self._start = self._clock()
        for step in self._steps.values():
            step.status = StepStatus.PENDING
            step.started_at = None
            step.finished_at = None

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_step(self, step_id: str) -> Step | None:
        """Return the :class:`Step` for *step_id*, or ``None``."""
        return self._steps.get(step_id)

    @property
    def steps(self) -> list[Step]:
        """All steps in registration order."""
        return [self._steps[sid] for sid in self._order]

    def snapshot(self) -> ProgressSnapshot:
        """Return a :class:`ProgressSnapshot` of the current state."""
        now = self._clock()
        elapsed_ms = (now - self._start) * 1000.0

        all_steps = [self._steps[sid] for sid in self._order]
        total_weight = sum(s.weight for s in all_steps)
        done_weight = sum(s.weight for s in all_steps if s.status in _COMPLETE_STATUSES)

        percent = (done_weight / total_weight * 100.0) if total_weight > 0 else 0.0

        steps_done = sum(1 for s in all_steps if s.status in _COMPLETE_STATUSES)
        steps_failed = sum(1 for s in all_steps if s.status == StepStatus.FAILED)

        current = next((s for s in all_steps if s.status == StepStatus.RUNNING), None)

        # ETA: extrapolate from elapsed/done-weight
        eta_ms: float | None = None
        if done_weight > 0 and done_weight < total_weight:
            rate = elapsed_ms / done_weight  # ms per unit weight
            remaining_weight = total_weight - done_weight
            eta_ms = rate * remaining_weight

        return ProgressSnapshot(
            percent_complete=round(percent, 2),
            steps_done=steps_done,
            steps_total=len(all_steps),
            steps_failed=steps_failed,
            current_step=current,
            elapsed_ms=elapsed_ms,
            eta_ms=eta_ms,
        )

    def __repr__(self) -> str:
        snap = self.snapshot()
        return (
            f"ProgressTracker(steps={len(self._steps)},"
            f" done={snap.steps_done},"
            f" percent={snap.percent_complete:.1f}%)"
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, step_id: str) -> Step:
        if step_id not in self._steps:
            raise KeyError(f"Step {step_id!r} not found")
        return self._steps[step_id]
