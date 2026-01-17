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

## Current limitations
- There is no support for class tests, everything is a module level test.