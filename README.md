# agent-progress-tracker

Weight-based progress percentage and ETA for multi-step agent runs. Zero dependencies.

## Install

```bash
pip install agent-progress-tracker
```

## Quick start

```python
from agent_progress_tracker import ProgressTracker

tracker = ProgressTracker()
tracker.add_step("fetch",    weight=1)
tracker.add_step("analyse",  weight=3)
tracker.add_step("generate", weight=2)
tracker.add_step("review",   weight=1)

tracker.start("fetch")
tracker.complete("fetch")

snap = tracker.snapshot()
print(f"{snap.percent_complete:.1f}% done")   # 14.3%
print(f"steps: {snap.steps_done}/{snap.steps_total}")  # 1/4
```

## API

### `ProgressTracker`

| Method | Description |
|---|---|
| `add_step(step_id, *, name, weight)` | Register a step |
| `remove_step(step_id)` | Unregister a step |
| `start(step_id)` | Mark step as RUNNING |
| `complete(step_id)` | Mark step as DONE |
| `skip(step_id)` | Mark step as SKIPPED (counts toward completion) |
| `fail(step_id)` | Mark step as FAILED (does not count) |
| `reset()` | Reset all steps to PENDING |
| `snapshot()` | Return a `ProgressSnapshot` |
| `get_step(step_id)` | Look up a step |

### `ProgressSnapshot`

| Attribute | Description |
|---|---|
| `percent_complete` | 0.0–100.0 weighted percentage |
| `steps_done` | DONE + SKIPPED count |
| `steps_total` | All registered steps |
| `steps_failed` | FAILED count |
| `current_step` | First RUNNING step, or `None` |
| `elapsed_ms` | Wall-clock time since tracker creation |
| `eta_ms` | Estimated remaining time (extrapolated from rate), or `None` |
| `is_complete` | `True` when done+failed == total |

## License

MIT
