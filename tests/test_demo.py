"""Example tests demonstrating pytest-threaded usage."""

import time

import pytest

from pytest_threaded import concurrent_function_fixture, concurrent_test, generate_tests

# =============================================================================
# Define fixtures - use @concurrent_function_fixture for function-scoped fixtures
# =============================================================================

@pytest.fixture(scope="function")  # Function scope now works!
@concurrent_function_fixture          # Register for manual invocation
def shared_resource():
    """A fixture that provides a shared resource."""
    print(f"\n>>> FIXTURE shared_resource: SETUP at {time.time():.2f}")
    resource = {"value": 42}
    yield resource
    print(f"\n>>> FIXTURE shared_resource: TEARDOWN at {time.time():.2f}")


@pytest.fixture(scope="function")  # Function scope now works!
@concurrent_function_fixture          # Register for manual invocation
def another_fixture():
    """Another fixture."""
    print(f"\n>>> FIXTURE another_fixture: SETUP at {time.time():.2f}")
    value = "Hello from fixture!"
    yield value
    print(f"\n>>> FIXTURE another_fixture: TEARDOWN at {time.time():.2f}")


# =============================================================================
# Define tests using the decorator - fixtures work just like normal pytest!
# =============================================================================

@concurrent_test
def foo(shared_resource):
    """Test with one fixture."""
    print("Foo running")
    print(f"Resource value: {shared_resource['value']}")
    time.sleep(2)
    print("Foo done")


@concurrent_test
def bar(shared_resource, another_fixture):
    """Test with multiple fixtures."""
    print("Bar running")
    print(f"Resource value: {shared_resource['value']}")
    print(f"Another fixture: {another_fixture}")
    time.sleep(2)
    print("Bar done")


@concurrent_test
def baz():
    """Test with no fixtures."""
    print("Baz running")
    time.sleep(2)
    print("Baz done")
    raise ValueError("Intentional Failure")


# =============================================================================
# Generate tests - injects _dispatch_all fixture and test_foo, test_bar, etc.
# =============================================================================

generate_tests(globals())
