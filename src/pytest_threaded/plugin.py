"""pytest plugin entry point for pytest-threaded."""

# Re-export the cleanup fixture so pytest can discover it
pytest_plugins = []


def pytest_configure(config):
    """Register the pytest-threaded plugin marker."""
    config.addinivalue_line("markers", "concurrent: mark test for concurrent execution")
