"""Background task execution framework using QRunnable and QThreadPool.

Ensures all database queries, network I/O, file exports, and AI calls
execute off the Qt GUI thread to guarantee 60 FPS UI responsiveness.
"""

from __future__ import annotations

import logging
import traceback
from collections.abc import Callable
from typing import Any

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

logger = logging.getLogger(__name__)


class WorkerSignals(QObject):
    """Qt Signals emitted during worker execution.

    Signals:
        started: Emitted when the worker begins execution on the thread pool.
        finished: Emitted when execution completes (regardless of success or failure).
        error: Emitted when an exception occurs; passes (exception, traceback_str).
        result: Emitted when execution succeeds; passes the return value.
        progress: Emitted during task execution to report status (percent, message).
    """

    started = Signal()
    finished = Signal()
    error = Signal(object, str)
    result = Signal(object)
    progress = Signal(int, str)


class Worker(QRunnable):
    """QRunnable wrapper for executing callable functions on a background thread pool."""

    def __init__(
        self,
        fn: Callable[..., Any],
        *args: Any,
        pass_progress: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.pass_progress = pass_progress
        self.signals = WorkerSignals()
        self._is_cancelled = False
        self.setAutoDelete(True)

    def cancel(self) -> None:
        """Mark task as cancelled.

        Note: Worker code can check is_cancelled periodically.
        """
        self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """Return True if cancel was requested."""
        return self._is_cancelled

    def _progress_callback(self, percent: int, message: str = "") -> None:
        """Callback to pass into target function if pass_progress is True."""
        if not self._is_cancelled:
            self.signals.progress.emit(percent, message)

    def run(self) -> None:
        """Execute the target function on the worker thread."""
        if self._is_cancelled:
            self.signals.finished.emit()
            return

        self.signals.started.emit()
        try:
            if self.pass_progress:
                res = self.fn(*self.args, progress_callback=self._progress_callback, **self.kwargs)
            else:
                res = self.fn(*self.args, **self.kwargs)

            if not self._is_cancelled:
                self.signals.result.emit(res)
        except Exception as exc:
            tb = traceback.format_exc()
            fn_name = getattr(self.fn, "__name__", "callable")
            logger.error("Background task error in %s: %s\n%s", fn_name, exc, tb)
            self.signals.error.emit(exc, tb)
        finally:
            self.signals.finished.emit()


class TaskRunner:
    """Manages scheduling and lifecycle of background workers on QThreadPool."""

    def __init__(self, pool: QThreadPool | None = None) -> None:
        self._pool = pool or QThreadPool.globalInstance()
        self._active_workers: set[Worker] = set()

    @property
    def pool(self) -> QThreadPool:
        """Underlying QThreadPool instance."""
        return self._pool

    @property
    def active_task_count(self) -> int:
        """Number of active tasks running in the thread pool."""
        return len(self._active_workers)

    def run_async(
        self,
        fn: Callable[..., Any],
        *args: Any,
        on_result: Callable[[Any], None] | None = None,
        on_error: Callable[[Any, str], None] | None = None,
        on_finished: Callable[[], None] | None = None,
        on_progress: Callable[[int, str], None] | None = None,
        on_started: Callable[[], None] | None = None,
        pass_progress: bool = False,
        **kwargs: Any,
    ) -> Worker:
        """Schedule a task for asynchronous execution on the thread pool."""
        worker = Worker(fn, *args, pass_progress=pass_progress, **kwargs)
        self._active_workers.add(worker)

        if on_started:
            worker.signals.started.connect(on_started)
        if on_result:
            worker.signals.result.connect(on_result)
        if on_error:
            worker.signals.error.connect(on_error)
        if on_progress:
            worker.signals.progress.connect(on_progress)

        def _cleanup() -> None:
            self._active_workers.discard(worker)
            if on_finished:
                on_finished()

        worker.signals.finished.connect(_cleanup)

        self._pool.start(worker)
        return worker

    def wait_for_all(self, timeout_ms: int = 5000) -> bool:
        """Wait up to timeout_ms for all running tasks to complete."""
        return self._pool.waitForDone(timeout_ms)
