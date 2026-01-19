# pytest-threaded

Run pytest tests concurrently using ThreadPoolExecutor.

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
from pytest_threaded import concurrent_test, concurrent_function_fixture, generate_tests

@pytest.fixture(scope="function")
@concurrent_function_fixture
def my_fixture():
    yield {"value": 42}

@concurrent_test
def my_test(my_fixture):
    print(f"Value: {my_fixture['value']}")

generate_tests(globals())
```

## How it works

The constraint is that pytest runs tests sequentially, and the internals of pytest are not threadsafe.

Hence we arrive at the following constraints:
- Something must run initially to add the tests to the ThreadPoolExecutor
- Something must run later to collect the result/stream the stdout to the console

Additionally on the user experience side we have the following constraints:
- Minimal annotation/extra code in user tests
- The user should be able to run a single test via `pytest path::to::single::test` as well as every test via `pytest`.

To satisify the constraints the example is transformed into the following code:

```python
import pytest
from pytest_threaded import concurrent_test, concurrent_function_fixture, generate_tests

@pytest.fixture(scope="function")
@concurrent_function_fixture
def my_fixture():
    yield {"value": 42}

@concurrent_test
def my_test(my_fixture):
    print(f"Value: {my_fixture['value']}")

#generate_tests(globals())

@pytest.fixture(scope="module")
def dispatch_my_test(my_fixture):
    # dispatch my_test to the executor, capturing output
    pass

def test_all(dispatch_my_test, ...):
    # Wait until executor is complete
    pass

def test_my_test(dispatch_my_test):
    # Stream the output of my_test
    # Wait for it to complete
    # Reraise any exceptions
    pass
```

As tests are run in order of appearance by pytest, if there are multiple tests, `test_all`'s fixtures will dispatch them concurrently.
Then `test_my_test` will serialise the test output.
Additionally when `pytest test_my_test` is run this will also dispatch the fixture.

The dispatch fixtures must be at least module scoped as otherwise the tests cause transitive fixtures to be created twice.

## Current limitations
- There is no support for class tests, everything is a module level test.