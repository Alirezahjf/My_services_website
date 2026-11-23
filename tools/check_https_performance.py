#!/usr/bin/env python3
"""Measure the old HTTP address against the new secure one.

The two addresses serve the same site. The question is whether the
secure one is slower, and by how much. The measure is done twice: once
with an empty cache and once with a full one, because a visitor who
comes back gets the files from the browser and not from the server.

The pages are opened with a slow processor and a small screen, the way
a phone on a slow line sees them. Several rounds are made and the
middle one is kept, so that a single slow round does not decide.

Usage::

    python tools/check_https_performance.py [rounds]
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

from app.services import tls_manager  # noqa: E402
from tools.browser import console_and_errors, launch  # noqa: E402

WORK = Path("/tmp/runup-https-performance")
IP = "203.0.113.77"

PAGES = ["/", "/products", "/services", "/about", "/contact", "/portfolio",
         "/consultation", "/legal/privacy"]

# The measure of the browser that is used: a slow processor and a
# small screen, which is how a phone on a slow line sees the site.
CPU_THROTTLE = 4
VIEWPORT = {"width": 360, "height": 800}

INIT = """
window.__vitals = { lcp: 0, cls: 0, longTaskMs: 0 };
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) window.__vitals.lcp = e.startTime;
  }).observe({ type: 'largest-contentful-paint', buffered: true });
} catch (e) {}
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (!e.hadRecentInput) window.__vitals.cls += e.value;
    }
  }).observe({ type: 'layout-shift', buffered: true });
} catch (e) {}
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) window.__vitals.longTaskMs += e.duration;
  }).observe({ type: 'longtask', buffered: true });
} catch (e) {}
"""


def build_ca_and_leaf():
    """Make a certificate for the test address and its key."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, IP)])
    now = datetime_now()
    leaf = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + __import__("datetime").timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(__import__("ipaddress").ip_address(IP))]), critical=False)
        .sign(key, hashes.SHA256())
    )
    bundle = leaf.public_bytes(serialization.Encoding.PEM) + key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    spki = base64.b64encode(
        hashlib.sha256(leaf.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo)).digest()
    ).decode()
    return bundle, spki


def datetime_now():
    import datetime
    return datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=5)


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_port(port: int, timeout: float = 40) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.3)
    return False


def measure(page, url: str, client, cache_disabled: bool):
    """Open a page and report what the browser saw."""
    try:
        client.send("Network.setCacheDisabled", {"cacheDisabled": cache_disabled})
    except Exception:
        pass
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_timeout(1500)
    return page.evaluate("""() => {
      const nav = performance.getEntriesByType('navigation')[0] || {};
      const res = performance.getEntriesByType('resource');
      const v = window.__vitals || {};
      const fcp = performance.getEntriesByName('first-contentful-paint')[0];
      return {
        ttfb: nav.responseStart || 0,
        fcp: fcp ? fcp.startTime : 0,
        lcp: v.lcp || 0,
        cls: v.cls || 0,
        longTaskMs: v.longTaskMs || 0,
        transferBytes: res.reduce((a, r) => a + (r.transferSize || 0), 0)
                      + (nav.transferSize || 0),
        requests: res.length + 1,
      };
    }""")


def middle(values):
    return round(statistics.median(values), 1)


def main() -> int:
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    WORK.mkdir(parents=True, exist_ok=True)
    bundle, spki = build_ca_and_leaf()
    tls_port = free_port()
    http_port = free_port()
    tls_dir = WORK / "tls"
    tls_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = WORK / "bundle.pem"
    bundle_path.write_bytes(bundle)
    tls_manager.materialise_tls_material(bundle_path, tls_dir)

    database = WORK / "site.sqlite3"

    # The tables are made before the servers start, so that a page can
    # be answered at once.
    from app import create_app
    from app.extensions import db

    application = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "SECRET_KEY": "performance-check-secret",
        "UPLOAD_FOLDER": str(WORK / "uploads"),
        "RATELIMIT_STORAGE_URI": "memory://",
    })
    with application.app_context():
        db.create_all()

    env = dict(os.environ)
    env.update({
        "PUBLIC_ORIGIN": f"https://{IP}:{tls_port}",
        "SITE_URL": f"https://{IP}:{tls_port}",
        "TLS_CERT_PATH": str(bundle_path),
        "COOKIE_SECURE": "false",
        "SECRET_KEY": "performance-check-secret",
        "DATABASE_URL": f"sqlite:///{database}",
        "RATELIMIT_STORAGE_URI": "memory://",
        "UPLOAD_FOLDER": str(WORK / "uploads"),
        "PYTHONPATH": str(ROOT),
    })

    http_proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "--workers", "1", "--threads", "2",
         "--bind", f"127.0.0.1:{http_port}", "app:create_app()"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    tls_proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "--workers", "1", "--threads", "2",
         "--bind", f"127.0.0.1:{tls_port}",
         "--certfile", str(tls_dir / "fullchain.pem"),
         "--keyfile", str(tls_dir / "privkey.pem"), "app:create_app()"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    report = {"ip": IP, "tls_port": tls_port, "http_port": http_port,
              "rounds": rounds}
    try:
        if not wait_port(http_port) or not wait_port(tls_port):
            print(json.dumps(report, indent=2))
            for proc in (http_proc, tls_proc):
                proc.kill()
                print(proc.stdout.read().decode(errors="replace")[-2000:],
                      file=sys.stderr)
            return 1

        results = {}
        with sync_playwright() as p:
            browser = launch(p, host_resolver_rules=f"MAP {IP} 127.0.0.1",
                             ignore_spki=[spki])

            # A visitor who comes back has already shaken hands with the
            # server. The browser keeps the ticket of the session, so
            # the second visit does not pay for the handshake again.
            # This round is called "returning".
            for cache_disabled in (True, False):
                state = "cold" if cache_disabled else "warm"
                for label, port, scheme in (("http", http_port, "http"),
                                           ("https", tls_port, "https")):
                    context = browser.new_context(
                        viewport=VIEWPORT, ignore_https_errors=False)
                    page = context.new_page()
                    page.add_init_script(INIT)
                    client = context.new_cdp_session(page)
                    client.send("Network.enable")
                    client.send("Emulation.setCPUThrottlingRate",
                                {"rate": CPU_THROTTLE})
                    for path in PAGES:
                        url = f"{scheme}://{IP}:{port}{path}"
                        samples = []
                        for _ in range(rounds):
                            try:
                                samples.append(measure(page, url, client,
                                                       cache_disabled))
                            except Exception as exc:  # noqa: BLE001
                                print(f"  {label} {path}: {exc}", file=sys.stderr)
                        if not samples:
                            continue
                        results[f"{state}/{label}{path}"] = {
                            metric: middle([s[metric] for s in samples])
                            for metric in samples[0]
                        }
                    context.close()
            browser.close()

        report["results"] = results
        report["comparison"] = compare(results)

        print(json.dumps(report, indent=2, ensure_ascii=False))
        (WORK / "report.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False))

        return 0
    finally:
        for proc in (http_proc, tls_proc):
            proc.terminate()
        try:
            http_proc.wait(timeout=10)
            tls_proc.wait(timeout=10)
        except Exception:
            http_proc.kill()
            tls_proc.kill()


def compare(results):
    """Say how the secure address stands against the old one."""
    out = {}
    metrics = ["ttfb", "fcp", "lcp", "cls", "longTaskMs", "transferBytes",
               "requests"]
    for path in PAGES:
        for state in ("cold", "warm"):
            old = results.get(f"{state}/http{path}")
            new = results.get(f"{state}/https{path}")
            if not old or not new:
                continue
            row = {}
            for metric in metrics:
                before = old[metric]
                after = new[metric]
                if before:
                    row[metric] = round((after - before) / before * 100, 1)
            out[f"{state}{path}"] = row
    return out


if __name__ == "__main__":
    raise SystemExit(main())
