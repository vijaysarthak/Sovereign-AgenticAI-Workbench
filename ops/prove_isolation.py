"""Live demo: prove model-generated code runs in a fully isolated sandbox.

Each check sends a hostile script through the SAME function the code agent
uses (agents/sandbox.py's run_python), so this exercises the real path, not
a mock. Run from the host while the stack is up:

    docker compose exec -T api python - < ops/prove_isolation.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, "/app")
from agents.sandbox import run_python  # noqa: E402

GREEN, RED, DIM, BOLD, RESET = "\033[92m", "\033[91m", "\033[2m", "\033[1m", "\033[0m"


def last_line(text: str) -> str:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    return lines[-1][:90] if lines else ""


# Environment variables the api container holds that must never reach a snippet.
SECRET_ENV_NAMES = [k for k in os.environ if k.startswith(("SEVERANCE_", "OLLAMA_", "AGENT_", "SANDBOX_"))]

# (title, attack script, predicate on the result meaning "isolation held")
CHECKS = [
    ("Sandbox runs normal code",
     "print('hello from the sandbox')",
     lambda r: r.exit_code == 0 and "hello" in r.stdout),
    ("No internet access",
     "import socket; socket.create_connection(('8.8.8.8', 53), timeout=3)",
     lambda r: r.exit_code != 0),
    ("Cannot reach the API, Ollama, or any service",
     "import socket; socket.create_connection(('api', 8080), timeout=3)",
     lambda r: r.exit_code != 0),
    ("Only a loopback interface exists",
     "import os; print(os.listdir('/sys/class/net'))",
     lambda r: r.exit_code == 0 and r.stdout.strip() == "['lo']"),
    ("Cannot read app secrets (.env)",
     "print(open('/app/.env').read())",
     lambda r: r.exit_code != 0),
    ("Cannot read the database or corpus",
     "import os; print(os.listdir('/data')); print(os.listdir('/app/corpus'))",
     lambda r: r.exit_code != 0),
    ("Inherits no secrets from the API's environment",
     "import os; print(sorted(os.environ))",
     lambda r: r.exit_code == 0 and not any(k in r.stdout for k in SECRET_ENV_NAMES)),
    ("Runs as unprivileged user (not root)",
     "import os; print(os.getuid())",
     lambda r: r.exit_code == 0 and r.stdout.strip() != "0"),
    ("Zero Linux capabilities",
     "print([l for l in open('/proc/self/status') if l.startswith('CapEff')][0])",
     lambda r: r.exit_code == 0 and r.stdout.split()[-1].strip("0") == ""),
    ("Filesystem is read-only",
     "open('/opt/sandbox/backdoor.py', 'w').write('x')",
     lambda r: r.exit_code != 0),
    ("Infinite loop killed by time limit",
     "while True: pass",
     lambda r: r.timed_out),
    ("Memory bomb blocked",
     "x = bytearray(1024 * 1024 * 1024)",
     lambda r: r.exit_code != 0),
    ("Fork bomb contained",
     "import os; [os.fork() for _ in range(500)]",
     lambda r: r.exit_code != 0),
]


def main() -> None:
    if not os.getenv("SANDBOX_SOCKET"):
        print(f"{RED}SANDBOX_SOCKET is not set: run this inside the api container.{RESET}")
        sys.exit(2)

    print(f"\n{BOLD}SEVERANCE sandbox isolation proof{RESET}")
    print(f"{DIM}Every attack below is executed for real through agents/sandbox.py -> sandbox container{RESET}\n")

    passed = 0
    for i, (title, code, held) in enumerate(CHECKS, 1):
        result = run_python(code, timeout_seconds=2)
        ok = held(result)
        passed += ok
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        evidence = last_line(result.stderr) or last_line(result.stdout) or f"exit={result.exit_code}"
        print(f" {mark}  {i:>2}. {title}")
        print(f"        {DIM}attack: {code.splitlines()[0][:70]}{RESET}")
        print(f"        {DIM}result: {evidence}{RESET}")

    colour = GREEN if passed == len(CHECKS) else RED
    print(f"\n{colour}{BOLD}{passed}/{len(CHECKS)} isolation checks held.{RESET}\n")
    sys.exit(0 if passed == len(CHECKS) else 1)


if __name__ == "__main__":
    main()
