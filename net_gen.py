import pytest
import time
from parallel_runner import parallel_test, parallel_function_fixture, generate_tests


# =============================================================================
# Define fixtures - use @parallel_fixture for function-scoped fixtures
# =============================================================================

@pytest.fixture(scope="function")  # Function scope now works!
@parallel_function_fixture          # Register for manual invocation
def shared_resource():
    """A fixture that provides a shared resource."""
    print(f"\n>>> FIXTURE shared_resource: SETUP at {time.time():.2f}")
    resource = {"value": 42}
    yield resource
    print(f"\n>>> FIXTURE shared_resource: TEARDOWN at {time.time():.2f}")


@pytest.fixture(scope="function")  # Function scope now works!
@parallel_function_fixture          # Register for manual invocation
def another_fixture():
    """Another fixture."""
    print(f"\n>>> FIXTURE another_fixture: SETUP at {time.time():.2f}")
    value = "Hello from fixture!"
    yield value
    print(f"\n>>> FIXTURE another_fixture: TEARDOWN at {time.time():.2f}")


# =============================================================================
# Define tests using the decorator - fixtures work just like normal pytest!
# =============================================================================

@parallel_test
def foo(shared_resource):
    """Test with one fixture."""
    print("Foo running")
    print(f"Resource value: {shared_resource['value']}")
    time.sleep(2)
    print("Foo done")


@parallel_test
def bar(shared_resource, another_fixture):
    """Test with multiple fixtures."""
    print("Bar running")
    print(f"Resource value: {shared_resource['value']}")
    print(f"Another fixture: {another_fixture}")
    time.sleep(2)
    print("Bar done")


@parallel_test
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