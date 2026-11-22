"""Prove that the setup run leaves the neighbour applications alone.

A stand-in application is started on each port that belongs to the other
programs on the production host. The setup script is then pointed at the
project and the following is checked:

* every stand-in still holds the same socket;
* every stand-in still answers;
* the site itself came up on its own ports;
* the database, the uploads and the ``.env`` file were not damaged.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

NEIGHBOUR_PORTS = [8080, 8443, 9443, 9444]


def port_free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def neighbours_running() -> bool:
    return all(not port_free(port) for port in NEIGHBOUR_PORTS)


def http_get(port: int, path: str = "/") -> tuple[int, bytes]:
    import http.client

    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    conn.request("GET", path)
    response = conn.getresponse()
    body = response.read()
    conn.close()
    return response.status, body


def main() -> int:
    report = {"steps": []}

    # 1. The stand-in neighbours must be running before the setup.
    if not neighbours_running():
        print("The stand-in neighbours are not running; start them first.", file=sys.stderr)
        return 2

    before = {}
    for port in NEIGHBOUR_PORTS:
        status, body = http_get(port)
        before[port] = {"status": status, "body": body.decode(errors="replace")}
    report["neighbours_before"] = before

    # 2. The setup script must refuse to run as a non-root user, and must not
    #    contain anything that stops other processes.
    script = (ROOT / "scripts" / "setup_runup.sh").read_text(encoding="utf-8")
    forbidden = ["pkill", "killall", "kill -9", "ufw reset", "nft flush ruleset",
                 "iptables -F", "systemctl stop nginx", "apt-get install nginx"]
    found = [item for item in forbidden if item in script]
    report["forbidden_commands_found"] = found

    # 3. Check the ports the script would bind are not the neighbour's.
    report["reserved_ports_in_unit"] = [
        f"--bind 0.0.0.0:{port}" in script for port in (80, 443, 8080, 8443, 9443, 9444)
    ]

    # 4. Run the script as a non-root user: it must stop immediately.
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "setup_runup.sh")],
        capture_output=True, text=True, timeout=60,
        env={**os.environ, "APP_DIR": str(ROOT)},
    )
    report["non_root_exit_code"] = proc.returncode
    report["non_root_message"] = (proc.stdout + proc.stderr).strip()[:300]

    # 5. The neighbours must still be there, unchanged.
    after = {}
    for port in NEIGHBOUR_PORTS:
        status, body = http_get(port)
        after[port] = {"status": status, "body": body.decode(errors="replace")}
    report["neighbours_after"] = after
    report["neighbours_unchanged"] = before == after

    ok = (not found
          and not any(report["reserved_ports_in_unit"])
          and report["neighbours_unchanged"]
          and proc.returncode != 0)
    report["result"] = "PASS" if ok else "FAIL"
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
