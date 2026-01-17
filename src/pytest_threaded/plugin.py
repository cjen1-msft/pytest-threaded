"""pytest plugin entry point for pytest-threaded."""

import pytest
from pytest_threaded.runner import cleanup_runner

# Re-export the cleanup fixture so pytest can discover it
pytest_plugins = []


def pytest_configure(config):
    """Register the pytest-threaded plugin marker."""
    config.addinivalue_line(
        "markers", "parallel: mark test for parallel execution"
    )
