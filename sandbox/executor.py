"""Raw Python snippet execution -- standard library ONLY.

Shared by two callers so the execution rules exist in exactly one place:
  * agents/sandbox.py, in-process fallback for local development, and
  * sandbox/server.py, inside the locked-down `sandbox` container.

Zero model calls, zero project imports (no contracts, no pydantic): the
sandbox image contains this directory and nothing else.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MAX_CAPTURED_CHARS = 4000


def _limit_resources(memory_mb: int):
    """preexec_fn capping child memory and disabling core dumps (POSIX only)."""
    try:
        import resource
    except ImportError:
        return None

    mem_bytes = memory_mb * 1024 * 1024

    def _apply() -> None:
        for limit, value in (
            (resource.RLIMIT_AS, mem_bytes),
            (resource.RLIMIT_CORE, 0),
            (resource.RLIMIT_FSIZE, 16 * 1024 * 1024),
        ):
            try:
                resource.setrlimit(limit, (value, value))
            except (ValueError, OSError):
                pass

    return _apply


def _kill_group(proc: subprocess.Popen) -> None:
    """Kill the snippet and anything it spawned, not just the direct child."""
    if sys.platform == "win32":
        proc.kill()
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def execute(code: str, timeout_seconds: float, memory_mb: int) -> dict:
    """Run `code` as a standalone script in a fresh subprocess.

    Returns a plain dict with the CodeExecutionResult fields. Never raises:
    a failure to launch is reported as exit_code=-1 (fail closed).
    """
    start = time.monotonic()

    def _result(stdout: str, stderr: str, exit_code: int, timed_out: bool) -> dict:
        return {
            "stdout": (stdout or "")[:MAX_CAPTURED_CHARS],
            "stderr": (stderr or "")[:MAX_CAPTURED_CHARS],
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_seconds": round(time.monotonic() - start, 3),
        }

    try:
        with tempfile.TemporaryDirectory(prefix="severance_sandbox_") as tmpdir:
            script_path = Path(tmpdir) / "snippet.py"
            script_path.write_text(code, encoding="utf-8")

            posix = sys.platform != "win32"
            proc = subprocess.Popen(
                [sys.executable, "-I", "-S", str(script_path)],
                cwd=tmpdir,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=_limit_resources(memory_mb) if posix else None,
                start_new_session=posix,
                env={"PATH": "/usr/bin:/bin"},  # stripped env: no inherited secrets/config
            )
            try:
                stdout, stderr = proc.communicate(timeout=timeout_seconds)
                return _result(stdout, stderr, proc.returncode, False)
            except subprocess.TimeoutExpired:
                _kill_group(proc)
                stdout, _ = proc.communicate()
                return _result(
                    stdout,
                    f"Execution exceeded the {timeout_seconds}s sandbox time limit and was terminated.",
                    -1,
                    True,
                )
            finally:
                # Reap any background children the snippet left behind.
                _kill_group(proc)
    except Exception as exc:  # noqa: BLE001 - fail closed
        return _result("", f"Sandbox failed to execute code: {exc}", -1, False)
