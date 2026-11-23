"""Start stand-in applications on the ports the real server uses.

The script binds simple HTTP servers on the ports that belong to the other
applications on the production host. After a setup run the same processes must
still hold the same sockets, which proves that the update did not disturb
them.

Usage: python tools/fake_neighbours.py [--ports 80,443,8080,8443,9443,9444]
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = json.dumps({"port": self.server.server_address[1], "pid": os.getpid()}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def start(ports: list[int]) -> list[_Server]:
    servers = []
    for port in ports:
        try:
            server = _Server(("0.0.0.0", port), _Handler)
        except OSError as exc:
            print(f"cannot bind port {port}: {exc}", file=sys.stderr)
            for running in servers:
                running.shutdown()
            raise
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server)
    return servers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ports", default="8080,8443,9443,9444")
    parser.add_argument("--seconds", type=int, default=0,
                        help="Run for a limited number of seconds (0 = forever).")
    parser.add_argument("--report", default="", help="Write a JSON report to this path.")
    args = parser.parse_args()

    ports = [int(p) for p in args.ports.split(",") if p.strip()]
    servers = start(ports)

    report = {
        "pids": [os.getpid()],
        "ports": {str(s.server_address[1]): s.socket.getsockname() for s in servers},
        "started_at": time.time(),
    }
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)

    print("listening on " + ", ".join(str(p) for p in ports), flush=True)

    stop = threading.Event()

    def _handle(_signum, _frame):
        stop.set()

    signal.signal(signal.SIGTERM, _handle)
    signal.signal(signal.SIGINT, _handle)

    if args.seconds:
        stop.wait(args.seconds)
    else:
        stop.wait()
    for server in servers:
        server.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
