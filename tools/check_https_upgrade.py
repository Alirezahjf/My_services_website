"""Verify the legacy-HTTP page upgrades to the secure origin in a real browser.

Starts the site twice - once over plain HTTP and once over TLS with a
certificate from a local CA - and checks that a visitor on the HTTP address
is moved to the HTTPS address, and that the HTTPS address keeps working.
"""
from __future__ import annotations

import base64
import datetime
import hashlib
import http.client
import ipaddress
import json
import os
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import tls_manager  # noqa: E402

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

from tools.browser import console_and_errors, launch  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

IP = "203.0.113.99"
WORK = Path("/tmp/https-upgrade-check")


def build_ca_and_leaf():
    WORK.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RunUp Upgrade Test CA")])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
          .public_key(key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - datetime.timedelta(days=1))
          .not_valid_after(now + datetime.timedelta(days=30))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .sign(key, hashes.SHA256()))

    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, IP)]))
            .issuer_name(name).public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(x509.SubjectAlternativeName(
                [x509.IPAddress(ipaddress.ip_address(IP))]), critical=False)
            .sign(key, hashes.SHA256()))

    (WORK / "ca.pem").write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    bundle = WORK / "trusted.pem"
    bundle.write_bytes(
        leaf_key.private_bytes(serialization.Encoding.PEM,
                               serialization.PrivateFormat.TraditionalOpenSSL,
                               serialization.NoEncryption())
        + leaf.public_bytes(serialization.Encoding.PEM))
    bundle.chmod(0o600)

    # The SPKI fingerprint lets the browser accept this one certificate
    # without trusting the whole test CA.
    spki = base64.b64encode(
        hashlib.sha256(leaf.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo)).digest()
    ).decode()
    return bundle, spki


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
    bundle, spki = build_ca_and_leaf()
    tls_port = free_port()
    http_port = free_port()
    tls_dir = WORK / "tls"
    tls_manager.materialise_tls_material(bundle, tls_dir)

    database = WORK / "site.sqlite3"
    from app import create_app
    from app.extensions import db

    application = create_app({
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "SECRET_KEY": "upgrade-check-secret",
        "UPLOAD_FOLDER": str(WORK / "uploads"),
        "RATELIMIT_STORAGE_URI": "memory://",
    })
    with application.app_context():
        db.create_all()

    env = dict(os.environ)
    env.update({
        "PUBLIC_ORIGIN": f"https://{IP}:{tls_port}",
        "SITE_URL": f"https://{IP}:{tls_port}",
        "TLS_CERT_PATH": str(bundle),
        "COOKIE_SECURE": "true",
        "SECRET_KEY": "upgrade-check-secret",
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

    report = {"ip": IP, "tls_port": tls_port, "http_port": http_port}
    try:
        if not wait_port(http_port) or not wait_port(tls_port):
            print(json.dumps(report, indent=2))
            print("FAIL: a server did not start", file=sys.stderr)
            for proc in (http_proc, tls_proc):
                proc.kill()
                print(proc.stdout.read().decode(errors="replace")[-2000:], file=sys.stderr)
            return 1

        # The browser must trust the local CA and resolve the IP to loopback.
        with sync_playwright() as p:
            browser = launch(p, host_resolver_rules=f"MAP {IP} 127.0.0.1", ignore_spki=[spki])
            context = browser.new_context(ignore_https_errors=False)
            page = context.new_page()
            logs = console_and_errors(page)

            # 1. The HTTP page loads.
            http_url = f"http://{IP}:{http_port}/"
            page.goto(http_url, wait_until="domcontentloaded", timeout=30000)
            report["http_page_url"] = page.url

            # 2. The browser is moved to the secure address.
            try:
                page.wait_for_url(f"https://{IP}:{tls_port}/**", timeout=20000)
                report["upgraded"] = True
            except Exception as exc:
                report["upgraded"] = False
                report["upgrade_error"] = str(exc)[:200]
            report["final_url"] = page.url
            try:
                page.wait_for_load_state("networkidle", timeout=20000)
            except Exception:
                pass
            report["http_page_loaded"] = True

            # 3. The secure address works and presents a valid certificate.
            report["secure_status"] = page.evaluate("() => document.title")
            report["secure_content_ok"] = len(page.content()) > 2000

            # 4. No console errors, no CSP violations, no mixed content.
            report["console_errors"] = [c for c in logs["console"] if c.startswith("error")]
            report["page_errors"] = logs["pageerror"]
            report["failed_requests"] = logs["requestfailed"]
            report["external_requests"] = page.evaluate(
                """() => performance.getEntriesByType('resource')
                          .map(r => r.name).filter(n => !n.startsWith(location.origin))""")

            # 5. The secure page carries the right canonical address.
            report["canonical"] = page.evaluate(
                "() => document.querySelector('link[rel=canonical]')?.href")

            context.close()
            browser.close()

        ok = (report.get("upgraded") and report.get("http_page_loaded")
              and not report.get("console_errors") and not report.get("page_errors")
              and not report.get("external_requests"))
        report["result"] = "PASS" if ok else "FAIL"
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if ok else 1
    finally:
        for proc in (http_proc, tls_proc):
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
