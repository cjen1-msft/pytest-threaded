"""pytest-threaded: Run pytest tests in parallel using ThreadPoolExecutor."""

from pytest_threaded.runner import (
    parallel_test,
    parallel_function_fixture,
    generate_tests,
    ParallelTestRunner,
)

__version__ = "0.1.0"

__all__ = [
    "parallel_test",
    "parallel_function_fixture",
    "generate_tests",
    "ParallelTestRunner",
]
