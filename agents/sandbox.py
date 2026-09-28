"""Deterministic, isolated Python code execution sandbox.

NON-NEGOTIABLE DESIGN PRINCIPLES (same discipline as harness/verify.py):
1. Zero model calls in this module. The model proposes code; THIS module
   disposes of it by actually running it and reporting exactly what happened.
2. Model-proposed code never runs in the SEVERANCE server process. Two modes:
   * Container isolation (Docker deployment): when SANDBOX_SOCKET is set,
     code is sent to the separate `sandbox` container (sandbox/server.py).
     That container has no network interface, a read-only root filesystem,
     a non-root user, no Linux capabilities, pid/memory/CPU caps, and no
     access to the corpus, database, or secrets. See docker-compose.yml.
   * Process isolation (local development): when SANDBOX_SOCKET is unset,
     code runs in a fresh subprocess with a stripped environment, timeout,
     and (POSIX-only) memory limits. This does NOT block network or host
     file access.
3. Never trust the child's own claims -- stdout/stderr/exit_code come from
   the OS, not from the code's self-reported output.
4. Fails closed: if SANDBOX_SOCKET is set but the sandbox is unreachable,
   the result is a failure. It never silently falls back to local execution,
   which would quietly drop the container isolation guarantee.
"""

from __future__ import annotations

import json
import os
import socket

from contracts import CodeExecutionResult
from sandbox.executor import MAX_CAPTURED_CHARS, execute

DEFAULT_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_TIMEOUT_SECONDS", "8"))
DEFAULT_MEMORY_MB = int(os.getenv("SANDBOX_MEMORY_MB", "256"))

__all__ = ["run_python", "MAX_CAPTURED_CHARS"]


def _run_remote(socket_path: str, code: str, timeout_seconds: float, memory_mb: int) -> dict:
    request = {"code": code, "timeout_seconds": timeout_seconds, "memory_mb": memory_mb}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        # Leave headroom for queueing behind another snippet plus startup.
        sock.settimeout(timeout_seconds * 2 + 10)
        sock.connect(socket_path)
        sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
        with sock.makefile("r", encoding="utf-8") as reader:
            line = reader.readline()
    if not line:
        raise RuntimeError("sandbox closed the connection without a result")
    return json.loads(line)


def run_python(
    code: str,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    memory_mb: int = DEFAULT_MEMORY_MB,
) -> CodeExecutionResult:
    """Execute `code` as a standalone Python script in isolation.

    Never raises: any failure to execute is reported as exit_code=-1 with the
    error text in stderr, so callers (harness/code_runner.py) treat it
    uniformly as a failed attempt and retry or abstain.
    """
    socket_path = os.getenv("SANDBOX_SOCKET")
    if not socket_path:
        return CodeExecutionResult(**execute(code, timeout_seconds, memory_mb))
    try:
        return CodeExecutionResult(**_run_remote(socket_path, code, timeout_seconds, memory_mb))
    except Exception as exc:  # noqa: BLE001 - fail closed, never fall back to local execution
        return CodeExecutionResult(
            stdout="",
            stderr=f"Isolated sandbox unavailable ({exc}); code was not executed.",
            exit_code=-1,
            timed_out=False,
            duration_seconds=0.0,
        )
