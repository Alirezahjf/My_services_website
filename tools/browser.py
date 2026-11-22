"""Shared browser helpers for local verification (development only, not deployed)."""
import os
import sys

CHROME = os.path.expanduser("~/.cache/ms-playwright/chromium-1255/chrome-linux/chrome")
LIBDIR = os.path.expanduser("~/.cache/ms-playwright/chromium-1255/chrome-linux/lib")

LAUNCH_ARGS = [
    "--no-sandbox",
    "--disable-dev-shm-usage",
    "--disable-gpu",
    "--font-render-hinting=none",
]


def launch(p, host_resolver_rules: str | None = None, ignore_spki: list[str] | None = None, **kwargs):
    """Start Chromium.

    ``host_resolver_rules`` maps a hostname or address to another one, which
    lets a test reach a server bound to loopback under a public address.
    ``ignore_spki`` lists the base64 SHA-256 SPKI fingerprints whose
    certificates the browser accepts even when it does not trust the issuer.
    """
    ensure_lib_path()
    args = list(LAUNCH_ARGS)
    if host_resolver_rules:
        args.append(f"--host-resolver-rules={host_resolver_rules}")
    if ignore_spki:
        args.append("--ignore-certificate-errors-spki-list=" + ",".join(ignore_spki))
    return p.chromium.launch(executable_path=CHROME, args=args, **kwargs)


def ensure_lib_path():
    """Make the bundled Chromium shared libraries visible to the child process."""
    current = os.environ.get("LD_LIBRARY_PATH", "")
    if LIBDIR not in current.split(":"):
        os.environ["LD_LIBRARY_PATH"] = LIBDIR + (":" + current if current else "")


def console_and_errors(page):
    """Attach collectors for console errors, page errors and failed requests."""
    logs = {"console": [], "pageerror": [], "requestfailed": [], "response": []}

    def on_console(msg):
        if msg.type in ("error", "warning"):
            logs["console"].append(f"{msg.type}: {msg.text}")

    def on_pageerror(err):
        logs["pageerror"].append(str(err))

    def on_failed(req):
        logs["requestfailed"].append(f"{req.method} {req.url} :: {req.failure}")

    def on_response(resp):
        if resp.status >= 400:
            logs["response"].append(f"{resp.status} {resp.url}")

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    page.on("requestfailed", on_failed)
    page.on("response", on_response)
    return logs
