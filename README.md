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

## Current limitations
- There is no support for class tests, everything is a module level test.