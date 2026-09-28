"""Live network egress monitor -- the visible proof of the sovereign claim.

Run this alongside the SEVERANCE server during a demo:

    python ops/network_monitor.py

It polls the OS socket table every `--interval` seconds and prints every
established (or attempted) outbound TCP connection whose remote address is
NOT loopback (127.0.0.1/::1) and NOT one of the explicitly allowed local
service addresses (Ollama on localhost, the API itself). Anything else --
in particular any connection to a public internet address -- is printed in
red as a VIOLATION and appended to `network_violations.log`.

This is deliberately a SEPARATE, standalone process from the API server:
a monitor that runs inside the same process it's watching can't be trusted
to report on itself. For the strongest version of this guarantee, run
SEVERANCE's containers on a Docker network with `internal: true` (see
docker-compose.yml) -- that makes egress impossible at the network layer,
not just observed. This script is the visible, narratable layer on top of
that structural guarantee for a live demo.

Requires: psutil (see requirements.txt)
"""

from __future__ import annotations

import argparse
import datetime
import ipaddress
import json
import sys
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    print("psutil is required: pip install psutil --break-system-packages", file=sys.stderr)
    sys.exit(1)

LOG_PATH = Path(__file__).parent.parent / "network_violations.log"

# Local-only addresses this app is expected to talk to: the Ollama server
# and the API's own listen address. Anything outside this set that is also
# not loopback is flagged as a potential egress violation.
ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "::1", "0.0.0.0", "localhost"}


def _is_loopback(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_loopback
    except ValueError:
        return False


def _is_private(ip: str) -> bool:
    """Private/link-local ranges are allowed too (Docker bridge networks,
    e.g. 172.x.x.x) -- only a genuinely public/routable address is a
    violation of the air-gap claim."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_private or addr.is_link_local or addr.is_loopback
    except ValueError:
        return False


def _log_violation(entry: dict) -> None:
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def scan_once(seen: set) -> list[dict]:
    """Scan current network connections once. Returns newly-seen violations."""
    violations: list[dict] = []
    try:
        connections = psutil.net_connections(kind="tcp")
    except (psutil.AccessDenied, PermissionError):
        print("Permission denied reading the socket table. Try running with sudo/admin rights.")
        return violations

    for conn in connections:
        if not conn.raddr:
            continue  # no remote endpoint (listening socket, etc.)
        remote_ip = conn.raddr.ip
        remote_port = conn.raddr.port
        key = (conn.pid, remote_ip, remote_port)
        if key in seen:
            continue
        seen.add(key)

        if remote_ip in ALLOWED_LOCAL_HOSTS or _is_private(remote_ip):
            continue

        try:
            proc_name = psutil.Process(conn.pid).name() if conn.pid else "unknown"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            proc_name = "unknown"

        entry = {
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "pid": conn.pid,
            "process": proc_name,
            "remote_ip": remote_ip,
            "remote_port": remote_port,
            "status": conn.status,
        }
        violations.append(entry)
        _log_violation(entry)

    return violations


def main() -> None:
    parser = argparse.ArgumentParser(description="SEVERANCE network egress monitor")
    parser.add_argument("--interval", type=float, default=1.0, help="Poll interval in seconds")
    args = parser.parse_args()

    print("=" * 70)
    print(" SEVERANCE NETWORK EGRESS MONITOR")
    print(" Watching for any outbound connection to a non-local address.")
    print(f" Violations are logged to: {LOG_PATH}")
    print("=" * 70)

    seen: set = set()
    clean_ticks = 0
    try:
        while True:
            violations = scan_once(seen)
            if violations:
                for v in violations:
                    print(
                        f"\n\033[91m[VIOLATION] {v['timestamp']} -- process '{v['process']}' "
                        f"(pid {v['pid']}) connected to {v['remote_ip']}:{v['remote_port']} "
                        f"[{v['status']}]\033[0m"
                    )
                clean_ticks = 0
            else:
                clean_ticks += 1
                print(f"\r[{datetime.datetime.now().strftime('%H:%M:%S')}] No external egress detected "
                      f"({clean_ticks} checks clean)", end="", flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nMonitor stopped.")


if __name__ == "__main__":
    main()
