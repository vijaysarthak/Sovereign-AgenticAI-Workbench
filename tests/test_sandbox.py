from agents.sandbox import run_python


def test_successful_execution_returns_stdout_and_exit_zero():
    result = run_python("print('hello sandbox')")
    assert result.exit_code == 0
    assert result.stdout.strip() == "hello sandbox"
    assert result.timed_out is False


def test_raised_exception_returns_nonzero_exit_and_stderr():
    result = run_python("raise ValueError('boom')")
    assert result.exit_code != 0
    assert "ValueError" in result.stderr


def test_timeout_is_enforced_and_reported():
    result = run_python("import time; time.sleep(5)", timeout_seconds=0.5)
    assert result.timed_out is True
    assert result.exit_code == -1


def test_no_filesystem_access_outside_sandbox_dir_by_default_cwd():
    # The script's cwd is the ephemeral sandbox tempdir, not the project root --
    # a relative-path read of a real project file should fail.
    result = run_python("open('contracts.py').read()")
    assert result.exit_code != 0
