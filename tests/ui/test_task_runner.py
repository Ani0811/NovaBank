"""Tests for the asynchronous task runner and background worker framework."""

from __future__ import annotations

import threading
import time
from typing import Any

from PySide6.QtCore import QThreadPool

from novabank.ui.workers.task_runner import TaskRunner, Worker


def sample_computation(x: int, y: int) -> int:
    """Simple computation function."""
    return x + y


def threaded_task() -> int:
    """Task returning the ID of the thread it executed on."""
    return threading.get_ident()


def failing_task() -> None:
    """Task that deliberately raises an exception."""
    raise ValueError("Simulated background calculation failure")


def progressive_task(progress_callback: Any = None) -> str:
    """Task that reports progress increments."""
    if progress_callback:
        progress_callback(25, "Quarter complete")
        progress_callback(50, "Halfway complete")
        progress_callback(100, "Done")
    return "All steps finished"


def test_worker_successful_execution(qtbot) -> None:
    """Verify that a worker executes successfully and emits started, result, and finished signals."""
    worker = Worker(sample_computation, 15, 27)
    pool = QThreadPool()

    with (
        qtbot.waitSignal(worker.signals.started, timeout=2000),
        qtbot.waitSignal(worker.signals.result, timeout=2000) as result_blocker,
        qtbot.waitSignal(worker.signals.finished, timeout=2000),
    ):
        pool.start(worker)

    assert result_blocker.args == [42]
    pool.waitForDone(2000)


def test_worker_runs_on_separate_thread(qtbot) -> None:
    """Verify that tasks actually execute on a worker thread and not the GUI thread."""
    main_thread_id = threading.get_ident()
    worker = Worker(threaded_task)
    pool = QThreadPool()

    with qtbot.waitSignal(worker.signals.result, timeout=2000) as blocker:
        pool.start(worker)

    worker_thread_id = blocker.args[0]
    assert worker_thread_id != main_thread_id
    pool.waitForDone(2000)


def test_worker_exception_handling(qtbot) -> None:
    """Verify that worker catches exceptions and emits error and finished signals without crashing."""
    worker = Worker(failing_task)
    pool = QThreadPool()

    with (
        qtbot.waitSignal(worker.signals.error, timeout=2000) as error_blocker,
        qtbot.waitSignal(worker.signals.finished, timeout=2000),
    ):
        pool.start(worker)

    exc, tb = error_blocker.args
    assert isinstance(exc, ValueError)
    assert "Simulated background calculation failure" in str(exc)
    assert "Traceback" in tb
    pool.waitForDone(2000)


def test_worker_progress_reporting(qtbot) -> None:
    """Verify that worker passes progress callbacks and emits progress signals."""
    worker = Worker(progressive_task, pass_progress=True)
    pool = QThreadPool()

    progress_events: list[tuple[int, str]] = []
    worker.signals.progress.connect(lambda pct, msg: progress_events.append((pct, msg)))

    with (
        qtbot.waitSignal(worker.signals.result, timeout=2000) as res_blocker,
        qtbot.waitSignal(worker.signals.finished, timeout=2000),
    ):
        pool.start(worker)

    assert res_blocker.args == ["All steps finished"]
    assert len(progress_events) == 3
    assert progress_events[0] == (25, "Quarter complete")
    assert progress_events[1] == (50, "Halfway complete")
    assert progress_events[2] == (100, "Done")
    pool.waitForDone(2000)


def test_worker_cancellation_before_execution(qtbot) -> None:
    """Verify that a cancelled worker does not execute fn or emit result, only finished."""
    worker = Worker(sample_computation, 10, 20)
    worker.cancel()
    assert worker.is_cancelled is True

    worker.signals.result.connect(lambda _: setattr(worker, "_test_result_emitted", True))

    pool = QThreadPool()
    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        pool.start(worker)

    assert not hasattr(worker, "_test_result_emitted")
    pool.waitForDone(2000)


def test_task_runner_run_async_callbacks(qtbot) -> None:
    """Verify TaskRunner.run_async wires callbacks cleanly."""
    pool = QThreadPool()
    runner = TaskRunner(pool=pool)
    assert runner.pool is pool

    results: list[int] = []
    finished_called: list[bool] = []
    started_called: list[bool] = []

    worker = runner.run_async(
        sample_computation,
        100,
        250,
        on_started=lambda: started_called.append(True),
        on_result=lambda val: results.append(val),
        on_finished=lambda: finished_called.append(True),
    )

    with qtbot.waitSignal(worker.signals.finished, timeout=2000):
        pass

    assert results == [350]
    assert finished_called == [True]
    assert started_called == [True]
    assert runner.wait_for_all(2000) is True


def test_task_runner_concurrent_execution(qtbot) -> None:
    """Verify TaskRunner manages multiple concurrent background tasks."""
    pool = QThreadPool()
    pool.setMaxThreadCount(4)
    runner = TaskRunner(pool=pool)

    def slow_multiply(val: int) -> int:
        time.sleep(0.05)
        return val * 2

    results: list[int] = []

    def on_result(res: int) -> None:
        results.append(res)

    for i in range(5):
        runner.run_async(slow_multiply, i, on_result=on_result)

    assert runner.wait_for_all(5000) is True
    qtbot.waitUntil(lambda: len(results) == 5, timeout=2000)
    assert sorted(results) == [0, 2, 4, 6, 8]
