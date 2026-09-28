"""Sandbox execution server -- runs inside the isolated `sandbox` container.

Listens on a Unix domain socket (on a volume shared only with `api`) rather
than TCP, so the container can run with `network_mode: none`: it has no
network interface at all, not even to other SEVERANCE services.

Protocol: one JSON object per line in each direction.
  request:  {"code": str, "timeout_seconds": float, "memory_mb": int}
            or {"ping": true}
  response: {"stdout", "stderr", "exit_code", "timed_out", "duration_seconds"}
            or {"ok": true}
"""

from __future__ import annotations

import json
import os
import socketserver
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from executor import execute  # noqa: E402

SOCKET_PATH = os.getenv("SANDBOX_SOCKET", "/run/sandbox/sandbox.sock")
MAX_CODE_BYTES = 256 * 1024
# Hard ceilings: the caller may ask for less, never for more.
MAX_TIMEOUT_SECONDS = float(os.getenv("SANDBOX_MAX_TIMEOUT_SECONDS", "30"))
MAX_MEMORY_MB = int(os.getenv("SANDBOX_MAX_MEMORY_MB", "512"))
# Snippets share one uid, so run them one at a time: no snippet can observe
# or signal another one mid-flight.
_slots = threading.BoundedSemaphore(int(os.getenv("SANDBOX_CONCURRENCY", "1")))


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        line = self.rfile.readline(MAX_CODE_BYTES + 4096)
        try:
            request = json.loads(line)
            if request.get("ping"):
                response = {"ok": True}
            else:
                code = request["code"]
                if not isinstance(code, str) or len(code.encode("utf-8")) > MAX_CODE_BYTES:
                    raise ValueError("code missing or too large")
                timeout = min(float(request.get("timeout_seconds", 8)), MAX_TIMEOUT_SECONDS)
                memory = min(int(request.get("memory_mb", 256)), MAX_MEMORY_MB)
                with _slots:
                    response = execute(code, timeout, memory)
        except Exception as exc:  # noqa: BLE001 - fail closed
            response = {
                "stdout": "", "stderr": f"Sandbox rejected request: {exc}",
                "exit_code": -1, "timed_out": False, "duration_seconds": 0.0,
            }
        self.wfile.write((json.dumps(response) + "\n").encode("utf-8"))


class Server(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main() -> None:
    try:
        os.unlink(SOCKET_PATH)
    except FileNotFoundError:
        pass
    with Server(SOCKET_PATH, Handler) as server:
        os.chmod(SOCKET_PATH, 0o666)
        print(f"[sandbox] listening on {SOCKET_PATH}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
