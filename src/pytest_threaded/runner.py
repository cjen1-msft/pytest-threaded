"""Core concurrent test runner implementation."""

import pytest
import sys
import threading
import inspect
import queue
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Any


# Thread-local storage
_thread_local = threading.local()

# Save originals before we replace them
_original_stdout = sys.stdout
_original_stderr = sys.stderr


class ThreadLocalStream:
    """
    A file-like object that checks thread-local storage for a redirect.
    If the current thread has set a redirect, write there.
    Otherwise, write to the original stream.
    """
    def __init__(self, original, attr_name):
        self.original = original
        self.attr_name = attr_name
    
    def write(self, text):
        redirect = getattr(_thread_local, self.attr_name, None)
        if redirect is not None:
            redirect.write(text)
        else:
            self.original.write(text)
    
    def flush(self):
        redirect = getattr(_thread_local, self.attr_name, None)
        if redirect is not None:
            redirect.flush()
        else:
            self.original.flush()
    
    def isatty(self):
        return self.original.isatty()
    
    def fileno(self):
        return self.original.fileno()
    
    @property
    def encoding(self):
        return self.original.encoding
    
    @property
    def errors(self):
        return getattr(self.original, 'errors', None)
    
    @property
    def name(self):
        return getattr(self.original, 'name', None)
    
    @property
    def mode(self):
        return getattr(self.original, 'mode', 'w')
    
    def readable(self):
        return False
    
    def writable(self):
        return True
    
    def seekable(self):
        return False


class QueueWriter:
    """A file-like object that writes to a queue."""
    
    def __init__(self, q: queue.Queue, stream_name: str):
        self.queue = q
        self.stream_name = stream_name
    
    def write(self, text: str):
        if text:
            self.queue.put((self.stream_name, text))
    
    def flush(self):
        pass


# Install thread-local streams once at module load
sys.stdout = ThreadLocalStream(_original_stdout, 'stdout_redirect')
sys.stderr = ThreadLocalStream(_original_stderr, 'stderr_redirect')


@dataclass
class _TestResult:
    """Stores the result of a dispatched test."""
    future: Any = None
    output_queue: queue.Queue = field(default_factory=queue.Queue)
    passed: bool = False
    error: Exception = None
    error_tb: Any = None  # Original traceback
    done: threading.Event = field(default_factory=threading.Event)


class ConcurrentTestRunner:
    """Manages concurrent test execution with dispatch/wait pattern."""
    
    _instance = None
    
    def __new__(cls, max_workers=4):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.executor = ThreadPoolExecutor(max_workers=max_workers)
            cls._instance.results: dict[str, _TestResult] = {}
            cls._instance.lock = threading.Lock()
        return cls._instance
    
    def dispatch(self, name: str, func: Callable, *args, **kwargs) -> None:
        """Dispatch a test to run in the executor. Returns immediately."""
        result = _TestResult()
        
        def run_test():
            # Set thread-local redirects (only affects this thread)
            _thread_local.stdout_redirect = QueueWriter(result.output_queue, "stdout")
            _thread_local.stderr_redirect = QueueWriter(result.output_queue, "stderr")
            
            try:
                func(*args, **kwargs)
                result.passed = True
            except Exception as e:
                import sys
                result.error = e
                # Capture original traceback, but skip the run_test wrapper frame
                tb = sys.exc_info()[2]
                if tb is not None:
                    tb = tb.tb_next  # Skip run_test frame to show only test code
                result.error_tb = tb
                result.passed = False
            finally:
                # Clear thread-local redirects
                _thread_local.stdout_redirect = None
                _thread_local.stderr_redirect = None
                result.done.set()
        
        result.future = self.executor.submit(run_test)
        
        with self.lock:
            self.results[name] = result
    
    def wait(self, name: str) -> _TestResult:
        """Wait for a dispatched test, streaming output as it arrives."""
        __tracebackhide__ = True  # Hide this frame from pytest traceback
        with self.lock:
            result = self.results.get(name)
        
        if result is None:
            raise RuntimeError(f"Test '{name}' was not dispatched")
        
        # Print from queue until done and queue is empty
        while not (result.done.is_set() and result.output_queue.empty()):
            try:
                stream_name, text = result.output_queue.get(timeout=0.1)
                if stream_name == "stdout":
                    _original_stdout.write(text)
                    _original_stdout.flush()
                else:
                    _original_stderr.write(text)
                    _original_stderr.flush()
            except queue.Empty:
                continue
        
        # Ensure future is complete
        result.future.result()
        
        # Re-raise with original traceback (shows only the test's stack trace)
        if not result.passed:
            raise result.error.with_traceback(result.error_tb)
        
        return result
    
    def shutdown(self):
        self.executor.shutdown(wait=True)


# Global runner
_runner = ConcurrentTestRunner(max_workers=4)

# Registry for concurrent tests
_concurrent_tests: dict[str, tuple[Callable, list[str]]] = {}

# Registry for concurrent function fixtures (stores raw generator functions)
_concurrent_function_fixtures: dict[str, Callable] = {}


def concurrent_function_fixture(func: Callable) -> Callable:
    """
    Decorator that registers a function-scoped fixture for use with concurrent tests.
    
    This allows function-scoped fixtures to work with concurrent tests by
    manually managing their lifecycle outside of pytest's scope rules.
    
    Usage:
        @pytest.fixture(scope="function")  # Function scope works!
        @concurrent_function_fixture          # Must be BELOW @pytest.fixture
        def my_fixture():
            print("setup")
            yield {"value": 42}
            print("teardown")
    
    The fixture can still be used normally by non-concurrent pytest tests.
    """
    _concurrent_function_fixtures[func.__name__] = func
    return func


def concurrent_test(func: Callable) -> Callable:
    """
    Decorator that registers a function as a concurrent test.
    The actual dispatch/wait test methods are generated automatically.
    
    Supports pytest fixtures - just add them as function parameters:
    
        @concurrent_test
        def my_test(tmp_path, my_fixture):
            # tmp_path and my_fixture will be resolved by pytest
            # and passed to the function
            pass
    """
    name = func.__name__
    # Get the fixture names from the function signature
    sig = inspect.signature(func)
    fixture_names = list(sig.parameters.keys())
    _concurrent_tests[name] = (func, fixture_names)
    return func


def make_dispatch_test(name: str, func: Callable, fixture_names: list[str]):
    """Create a dispatch test method that resolves fixtures and dispatches."""
    
    # Build the function signature dynamically to request fixtures
    if fixture_names:
        # Create a dispatch function that takes fixtures as parameters
        params = ", ".join(fixture_names)
        func_args = ", ".join(f"{f}={f}" for f in fixture_names)
        
        # Use exec to create a function with the right signature
        # This is necessary for pytest to detect fixture parameters
        code = f"""
def test_dispatch(self, {params}):
    _runner.dispatch(name, func, {func_args})
"""
        local_vars = {"_runner": _runner, "name": name, "func": func}
        exec(code, local_vars)
        test_dispatch = local_vars["test_dispatch"]
    else:
        def test_dispatch(self):
            _runner.dispatch(name, func)
    
    test_dispatch.__name__ = f"test_dispatch_{name}"
    test_dispatch.__qualname__ = f"TestDispatch.test_dispatch_{name}"
    return test_dispatch


def make_dispatch_fixture(name: str, func: Callable, fixture_names: list[str]):
    """Create a module-scoped dispatch fixture that manually invokes fixtures and dispatches.
    
    For fixtures decorated with @concurrent_fixture, we manually invoke the generator
    to bypass pytest's scope checking. This allows function-scoped fixtures to work
    with module-scoped dispatch fixtures.
    """
    
    if fixture_names:
        # Build code that manually invokes concurrent function fixtures
        # and passes their values to the test function
        setup_lines = []
        cleanup_lines = []
        func_args_parts = []
        pytest_fixture_names = []
        
        for fname in fixture_names:
            if fname in _concurrent_function_fixtures:
                # Manually invoke the fixture generator
                setup_lines.append(
                    f"    _gen_{fname} = _concurrent_function_fixtures['{fname}']()\n"
                    f"    {fname} = next(_gen_{fname})"
                )
                cleanup_lines.append(
                    f"    try:\n"
                    f"        next(_gen_{fname})\n"
                    f"    except StopIteration:\n"
                    f"        pass"
                )
            else:
                # Request from pytest normally (must be module+ scoped)
                pytest_fixture_names.append(fname)
            func_args_parts.append(f"{fname}={fname}")
        
        params = ", ".join(pytest_fixture_names)
        func_args = ", ".join(func_args_parts)
        setup_code = "\n".join(setup_lines) if setup_lines else "    pass  # no manual fixture setup"
        cleanup_code = "\n".join(cleanup_lines) if cleanup_lines else "    pass  # no manual fixture cleanup"
        
        code = f"""
@pytest.fixture(scope="module")
def dispatch_{name}({params}):
{setup_code}
    _runner.dispatch('{name}', func, {func_args})
    yield '{name}'
{cleanup_code}
"""
        local_vars = {
            "_runner": _runner, 
            "func": func, 
            "pytest": pytest,
            "_concurrent_function_fixtures": _concurrent_function_fixtures,
        }
        exec(code, local_vars)
        dispatch_fixture = local_vars[f"dispatch_{name}"]
    else:
        @pytest.fixture(scope="module")
        def dispatch_fixture():
            _runner.dispatch(name, func)
            yield name
        dispatch_fixture.__name__ = f"dispatch_{name}"
    
    return dispatch_fixture


def make_wait_func(name: str):
    """Create a wait test function that depends on the dispatch fixture."""
    
    # Avoid doubling the test_ prefix if name already starts with test_
    test_name = name if name.startswith("test_") else f"test_{name}"
    
    code = f"""
def {test_name}(dispatch_{name}):
    __tracebackhide__ = True
    _runner.wait(name)
"""
    local_vars = {"_runner": _runner, "name": name}
    exec(code, local_vars)
    test_func = local_vars[test_name]
    return test_func


def generate_tests(module_globals: dict) -> None:
    """
    Generate test functions and inject them into the module namespace.
    Call this at the end of your test file after all @concurrent_test functions.
    
    Args:
        module_globals: Pass globals() from your test module
    
    This injects:
        - dispatch_<name>: Session-scoped fixture that dispatches the test
        - test_all: Test that triggers all dispatch fixtures (ensures concurrency)
        - test_<name>: Waits for and streams the result of each test
    
    NOTE: Fixtures used by @concurrent_test functions should be session or module
    scoped to ensure they stay alive during test execution.
    """
    if not _concurrent_tests:
        return
    
    # Add cleanup fixture
    if "_cleanup_parallel_runner" not in module_globals:
        @pytest.fixture(scope="session", autouse=True)
        def _cleanup_parallel_runner():
            """Cleanup fixture to shutdown the executor after all tests."""
            yield
            _runner.shutdown()
        module_globals["_cleanup_parallel_runner"] = _cleanup_parallel_runner
    
    # Add dispatch fixtures
    dispatch_fixture_names = []
    for name, (func, fixture_names) in _concurrent_tests.items():
        fixture_name = f"dispatch_{name}"
        dispatch_fixture_names.append(fixture_name)
        module_globals[fixture_name] = make_dispatch_fixture(name, func, fixture_names)
    
    # Add test_all that depends on all dispatch fixtures (triggers concurrent dispatch)
    params = ", ".join(dispatch_fixture_names)
    code = f"""
def test_all({params}):
    '''Triggers all dispatch fixtures to start concurrent execution.'''
    pass
"""
    exec(code, {})
    module_globals["test_all"] = eval(f"lambda {params}: None")
    module_globals["test_all"].__name__ = "test_all"
    
    # Add wait tests
    for name in _concurrent_tests:
        # Avoid doubling the test_ prefix
        test_name = name if name.startswith("test_") else f"test_{name}"
        module_globals[test_name] = make_wait_func(name)


# Keep module-level fixture as fallback for imports
@pytest.fixture(scope="session", autouse=True)
def cleanup_runner():
    """Cleanup fixture to shutdown the executor after all tests."""
    yield
    _runner.shutdown()
