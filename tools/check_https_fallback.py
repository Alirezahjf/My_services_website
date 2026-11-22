"""Verify that the legacy HTTP page stays put when the secure origin is down.

This is the fallback the operator asked for: a device that cannot reach or
accept the certificate must keep the working HTTP page instead of being sent
to an error page.
"""
from __future__ import annotations

import datetime
import http.client
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

from tools.browser import console_and_errors, launch  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

IP = "203.0.113.98"
WORK = Path("/tmp/https-fallback-check")


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_port(port, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def main():
    WORK.mkdir(parents=True, exist_ok=True)
    http_port = free_port()
    # A port that nothing listens on: the secure origin is unreachable.
    dead_port = free_port()
    database = WORK / "site.sqlite3"

    application = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "SECRET_KEY": "fallback-check-secret",
        "UPLOAD_FOLDER": str(WORK / "uploads"),
        "RATELIMIT_STORAGE_URI": "memory://",
    })
    with application.app_context():
        db.create_all()

    env = dict(os.environ)
    env.update({
        "PUBLIC_ORIGIN": f"https://{IP}:{dead_port}",
        "SITE_URL": f"https://{IP}:{dead_port}",
        "TLS_CERT_PATH": "",
        "COOKIE_SECURE": "false",
        "SECRET_KEY": "fallback-check-secret",
        "DATABASE_URL": f"sqlite:///{database}",
        "RATELIMIT_STORAGE_URI": "memory://",
        "UPLOAD_FOLDER": str(WORK / "uploads"),
        "PYTHONPATH": str(ROOT),
    })

    proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "--workers", "1", "--threads", "2",
         "--bind", f"127.0.0.1:{http_port}", "app:create_app()"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    report = {"ip": IP, "http_port": http_port, "dead_port": dead_port}
    try:
        if not wait_port(http_port):
            proc.kill()
            print("FAIL: server did not start", file=sys.stderr)
            return 1

        with sync_playwright() as p:
            browser = launch(p, host_resolver_rules=f"MAP {IP} 127.0.0.1")
            context = browser.new_context(ignore_https_errors=False)
            page = context.new_page()
            logs = console_and_errors(page)

            http_url = f"http://{IP}:{http_port}/"
            page.goto(http_url, wait_until="domcontentloaded", timeout=30000)
            report["loaded_url"] = page.url

            # The probe has a 2.5 second timeout; give the page longer than
            # that plus some slack to make sure it does not navigate.
            page.wait_for_timeout(9000)
            report["stayed_on_http"] = page.url.startswith("http://")
            report["final_url"] = page.url
            report["content_present"] = len(page.content()) > 2000
            report["title"] = page.title()

            # The failed probe is expected; it must not be a CSP violation.
            report["csp_violations"] = [
                c for c in logs["console"] if "Content Security Policy" in c
            ]
            report["console_errors"] = [c for c in logs["console"] if c.startswith("error")]
            report["page_errors"] = logs["pageerror"]

            context.close()
            browser.close()

        ok = (report.get("stayed_on_http") and report.get("content_present")
              and not report.get("csp_violations") and not report.get("page_errors"))
        report["result"] = "PASS" if ok else "FAIL"
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if ok else 1
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
