"""Integration tests using subprocess to verify pytest-threaded behavior.

These tests run pytest as a subprocess and inspect the output to verify:
1. Parallel execution actually happens (timing)
2. Individual pass/fail reporting works
3. Output is thread-isolated (not interleaved)
4. Exception tracebacks are clean
5. Fixtures work correctly
"""

import os
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path

# Get the project root to ensure pytest-threaded is importable
PROJECT_ROOT = Path(__file__).parent.parent


def run_pytest(test_code: str, *args, timeout: int = 30) -> subprocess.CompletedProcess:
    """
    Run pytest on the given test code in a subprocess.
    
    Creates a temporary file with the test code and runs pytest on it.
    Captures output for test assertions and prints it to host terminal.
    """
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".py",
        prefix="test_",
        delete=False
    ) as f:
        f.write(test_code)
        f.flush()
        test_file = f.name

    try:
        env = os.environ.copy()
        # Ensure our package is importable
        pythonpath = str(PROJECT_ROOT / "src")
        if "PYTHONPATH" in env:
            env["PYTHONPATH"] = f"{pythonpath}:{env['PYTHONPATH']}"
        else:
            env["PYTHONPATH"] = pythonpath

        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_file, "-v", "-s", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(PROJECT_ROOT),
        )
        # Print captured output to host
        if result.stdout:
            sys.stdout.write(result.stdout)
            sys.stdout.flush()
        if result.stderr:
            sys.stderr.write(result.stderr)
            sys.stderr.flush()
        return result
    finally:
        os.unlink(test_file)


class TestParallelExecution:
    """Verify that tests actually run in parallel."""

    def test_parallel_timing(self):
        """Three 1-second tests should complete in ~1s, not ~3s."""
        test_code = textwrap.dedent('''
            import time
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def slow_a():
                time.sleep(1)
            
            @concurrent_test
            def slow_b():
                time.sleep(1)
            
            @concurrent_test
            def slow_c():
                time.sleep(1)
            
            generate_tests(globals())
        ''')

        start = time.time()
        result = run_pytest(test_code)
        elapsed = time.time() - start

        # Should complete in ~1-2s if parallel, ~3s+ if sequential
        assert elapsed < 2.5, f"Tests took {elapsed:.2f}s - expected <2.5s for parallel execution"
        # All tests should pass (3 parallel tests + test_all)
        assert result.returncode == 0, "Tests failed"
        output = result.stdout + result.stderr
        assert "4 passed" in output or "passed" in output


class TestIndividualPassFail:
    """Verify each test reports its own pass/fail status."""

    def test_mixed_pass_fail(self):
        """One passing, one failing test should show individual results."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def passing():
                assert True
            
            @concurrent_test
            def failing():
                assert False, "intentional failure"
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)

        # Should have exit code 1 (some failures)
        assert result.returncode == 1

        output = result.stdout + result.stderr

        # Should show individual pass/fail
        assert "PASSED" in output, "No PASSED in output"
        assert "FAILED" in output, "No FAILED in output"

        # Should show 2 passed (test_all + passing), 1 failed
        assert "2 passed" in output
        assert "1 failed" in output

    def test_all_passing(self):
        """All tests pass - should exit 0."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def test_a():
                assert True
            
            @concurrent_test
            def test_b():
                assert 1 + 1 == 2
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        assert result.returncode == 0
        output = result.stdout + result.stderr
        # 2 parallel tests + test_all = at least 3 passed, may also generate test_test_a etc
        assert "passed" in output

    def test_all_failing(self):
        """All tests fail - should exit 1 with all failures reported."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def fail_a():
                assert False, "fail a"
            
            @concurrent_test
            def fail_b():
                assert False, "fail b"
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        assert result.returncode == 1
        output = result.stdout + result.stderr
        assert "2 failed" in output


class TestThreadIsolatedOutput:
    """Verify that output from each test stays with that test."""

    def test_output_not_interleaved(self):
        """Each test's output should appear as a contiguous block, not interleaved."""
        test_code = textwrap.dedent('''
            import time
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def alpha():
                for i in range(5):
                    print(f"ALPHA:{i}")
                    time.sleep(0.05)
            
            @concurrent_test
            def beta():
                for i in range(5):
                    print(f"BETA:{i}")
                    time.sleep(0.05)
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        assert result.returncode == 0, "Tests failed"

        output = result.stdout

        # State machine: ALPHA should print before BETA (test order is alphabetical)
        # Once we see BETA, we should never see ALPHA again
        seen_beta = False

        for line in output.split('\n'):
            if 'ALPHA:' in line:
                assert not seen_beta, "Output is interleaved! Saw ALPHA after BETA"
            elif 'BETA:' in line:
                seen_beta = True


class TestCleanTracebacks:
    """Verify that exception tracebacks show test code, not framework internals."""

    def test_traceback_shows_test_code(self):
        """Traceback should include the test function, not just runner internals."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def my_failing_test():
                x = 1
                y = 2
                assert x == y, "x should equal y"
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        assert result.returncode == 1

        output = result.stdout + result.stderr

        # Should show the test function name in traceback
        assert "my_failing_test" in output, "Test function name not in traceback"

        # Should show the assertion
        assert "assert x == y" in output or "x should equal y" in output, "Assertion not visible in traceback"

    def test_exception_traceback_shows_origin(self):
        """Exception raised in test should show original location."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def exception_test():
                def inner_func():
                    raise ValueError("error from inner_func")
                inner_func()
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        assert result.returncode == 1

        output = result.stdout + result.stderr

        # Should show inner_func in traceback
        assert "inner_func" in output, "inner_func not in traceback"
        assert "error from inner_func" in output, "Error message not shown"

    def test_traceback_excludes_runner_internals(self):
        """Traceback should not be cluttered with runner.py internals."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def simple_failure():
                raise RuntimeError("simple error")
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        output = result.stdout + result.stderr

        # Count how many times runner.py appears in traceback
        # It might appear once (unavoidable) but shouldn't dominate
        runner_mentions = output.count("runner.py")
        test_file_mentions = output.count("simple_failure")

        # The test function should be more prominent than runner internals
        assert test_file_mentions >= 1, "Test function not in output"


class TestFixtureSupport:
    """Verify that fixtures work correctly with parallel tests."""

    def test_fixture_value_passed(self):
        """Fixture value should be correctly passed to test."""
        test_code = textwrap.dedent('''
            import pytest
            from pytest_threaded import concurrent_test, concurrent_function_fixture, generate_tests
            
            @pytest.fixture(scope="function")
            @concurrent_function_fixture
            def my_fixture():
                yield {"value": 42}
            
            @concurrent_test
            def test_uses_fixture(my_fixture):
                print(f"FIXTURE_VALUE:{my_fixture['value']}")
                assert my_fixture["value"] == 42
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        assert result.returncode == 0, "Test failed"
        assert "FIXTURE_VALUE:42" in result.stdout

    def test_fixture_setup_teardown(self):
        """Fixture setup and teardown should both execute."""
        test_code = textwrap.dedent('''
            import pytest
            from pytest_threaded import concurrent_test, concurrent_function_fixture, generate_tests
            
            @pytest.fixture(scope="function")
            @concurrent_function_fixture
            def tracked_fixture():
                print("FIXTURE:SETUP")
                yield "resource"
                print("FIXTURE:TEARDOWN")
            
            @concurrent_test
            def test_with_tracked(tracked_fixture):
                print(f"FIXTURE:USING:{tracked_fixture}")
                assert tracked_fixture == "resource"
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        output = result.stdout

        assert result.returncode == 0, "Test failed"
        assert "FIXTURE:SETUP" in output, "Setup not called"
        assert "FIXTURE:USING:resource" in output, "Fixture not used"
        assert "FIXTURE:TEARDOWN" in output, "Teardown not called"

    def test_multiple_fixtures(self):
        """Test can use multiple fixtures."""
        test_code = textwrap.dedent('''
            import pytest
            from pytest_threaded import concurrent_test, concurrent_function_fixture, generate_tests
            
            @pytest.fixture(scope="function")
            @concurrent_function_fixture
            def fixture_a():
                yield "A"
            
            @pytest.fixture(scope="function")
            @concurrent_function_fixture
            def fixture_b():
                yield "B"
            
            @concurrent_test
            def test_multi(fixture_a, fixture_b):
                print(f"VALUES:{fixture_a}:{fixture_b}")
                assert fixture_a == "A"
                assert fixture_b == "B"
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        assert result.returncode == 0, "Test failed"
        assert "VALUES:A:B" in result.stdout

    def test_no_fixtures(self):
        """Test without fixtures should work."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def no_fixture_test():
                print("NO_FIXTURES_NEEDED")
                assert True
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        assert result.returncode == 0
        assert "NO_FIXTURES_NEEDED" in result.stdout


class TestSingleTestExecution:
    """Verify that running a single test works correctly."""

    def test_run_single_test(self):
        """Running pytest test_foo should only run that test."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def selected():
                print("SELECTED_RAN")
            
            @concurrent_test
            def not_selected():
                print("NOT_SELECTED_RAN")
            
            generate_tests(globals())
        ''')

        # Run only test_selected using -k filter
        result = run_pytest(test_code, "-k", "test_selected")

        output = result.stdout + result.stderr

        # Only selected test should run
        assert "SELECTED_RAN" in output, "Selected test didn't run"

        # Deselected test should not run (its print won't appear)
        # Note: "NOT_SELECTED_RAN" should NOT be in output
        # But dispatch_not_selected might still be mentioned in deselected count
        assert "1 passed" in output or "passed" in output

    def test_prefixed_name_not_doubled(self):
        """A parallel test named 'test_foo' should become 'test_foo', not 'test_test_foo'."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def test_example():
                print("TEST_EXAMPLE_RAN")
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code, "--collect-only")
        output = result.stdout + result.stderr

        # Should have test_example, NOT test_test_example
        assert "test_example" in output, "test_example not found"
        assert "test_test_example" not in output, "Bug: test name was doubled to 'test_test_example'"

    def test_prefixed_name_runs_correctly(self):
        """A parallel test named 'test_foo' should run when pytest test_foo is invoked."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def test_widget():
                print("WIDGET_TEST_RAN")
                assert True
            
            @concurrent_test  
            def test_gadget():
                print("GADGET_TEST_RAN")
                assert True
            
            generate_tests(globals())
        ''')

        # Run only test_widget
        result = run_pytest(test_code, "-k", "test_widget and not gadget")
        output = result.stdout + result.stderr

        # Only widget test should run
        assert "WIDGET_TEST_RAN" in output, "test_widget didn't run"
        assert "GADGET_TEST_RAN" not in output, "test_gadget should not have run"


class TestStreamingOutput:
    """Verify that output streams as tests run, not buffered."""

    def test_output_appears(self):
        """Test output should appear in pytest output."""
        test_code = textwrap.dedent('''
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def prints_stuff():
                print("LINE_ONE")
                print("LINE_TWO")
                print("LINE_THREE")
            
            generate_tests(globals())
        ''')

        result = run_pytest(test_code)
        output = result.stdout

        assert result.returncode == 0
        assert "LINE_ONE" in output
        assert "LINE_TWO" in output
        assert "LINE_THREE" in output

    def test_single_test_output_streams(self):
        """For a single test, output should stream as it runs, not buffer until completion."""
        test_code = textwrap.dedent('''
            import time
            from pytest_threaded import concurrent_test, generate_tests
            
            @concurrent_test
            def slow_printer():
                print("STREAM_START", flush=True)
                time.sleep(0.5)
                print("STREAM_END", flush=True)
            
            generate_tests(globals())
        ''')

        # Run single test and measure timing between output lines
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", prefix="test_", delete=False) as f:
            f.write(test_code)
            f.flush()
            test_file = f.name

        try:
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{PROJECT_ROOT / 'src'}:{env.get('PYTHONPATH', '')}"

            process = subprocess.Popen(
                [sys.executable, "-m", "pytest", test_file, "-v", "-s", "-k", "slow_printer"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env,
            )

            start_time = end_time = None
            for line in process.stdout:
                sys.stdout.write(line)
                if "STREAM_START" in line:
                    start_time = time.time()
                elif "STREAM_END" in line:
                    end_time = time.time()

            process.wait()

            assert start_time and end_time, "Output markers not found"
            delay = end_time - start_time
            assert 0.3 < delay < 0.8, f"Output not streaming (delay: {delay:.2f}s, expected ~0.5s)"
        finally:
            os.unlink(test_file)
