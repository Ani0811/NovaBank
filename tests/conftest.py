"""Global pytest fixtures and teardown handlers for NovaBank test suite."""

import pytest
from PySide6.QtCore import QThreadPool


@pytest.fixture(autouse=True)
def cleanup_qt_thread_pool():
    """Wait for all background worker threads to terminate before tearing down test fixtures."""
    yield
    pool = QThreadPool.globalInstance()
    if pool is not None:
        pool.waitForDone(2000)

