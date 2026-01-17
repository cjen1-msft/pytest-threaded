# pytest-threaded

Run pytest tests in parallel using ThreadPoolExecutor.

## Installation

```bash
pip install pytest-threaded
```

For development:
```bash
pip install -e ".[dev]"
```

## Usage

```python
import pytest
from pytest_threaded import parallel_test, parallel_function_fixture, generate_tests

@pytest.fixture(scope="function")
@parallel_function_fixture
def my_fixture():
    yield {"value": 42}

@parallel_test
def my_test(my_fixture):
    print(f"Value: {my_fixture['value']}")

generate_tests(globals())
```

## Functional Requirements

### Core Requirements
Parallel Execution - Run multiple tests concurrently using ThreadPoolExecutor, reducing total runtime (e.g., 3×2s tests complete in ~2s)

Individual Pass/Fail Reporting - Each test reports its own pass/fail status to pytest, not just a single aggregate result

Streaming Output - Test output (stdout/stderr) streams to the console as tests run, not buffered until completion

Thread-Isolated Output - Each thread's output is captured separately and displayed with the correct test, not interleaved

Pytest Fixture Support - Tests can declare fixtures as parameters, just like normal pytest tests

Single Test Execution - Running pytest test_foo works correctly, dispatching and waiting for just that test

Clean Tracebacks - Failures show the actual test code location, not internal framework code

Fixture Edge Cases
Scenario	Behavior
No fixtures	Test dispatches immediately with no setup
Module+ scoped fixtures	Requested from pytest normally via function signature
Function-scoped fixtures	Must use @parallel_function_fixture for manual lifecycle management
Mixed scopes	Both types work together - pytest fixtures via params, function fixtures via manual invocation
Fixture teardown timing	Teardown occurs after test_all completes (after all waits), not after dispatch
Execution Edge Cases
Scenario	Behavior
Run all tests	test_all triggers all dispatch_<name> fixtures, waits for all
Run single test	test_foo depends on dispatch_foo, which dispatches only that test
Test raises exception	Exception captured, re-raised during wait with original traceback
Test hangs	Future blocks indefinitely (no timeout currently)
Multi-file usage	Test names are module-qualified (module.testname) to avoid collisions
Decorator Order Requirement
Decorators apply bottom-up, so @parallel_function_fixture captures the raw generator before @pytest.fixture wraps it.

