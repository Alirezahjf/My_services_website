"""End-to-end tests for the shared-certificate HTTPS setup.

These tests exercise the real code paths: a certificate is issued by a local
CA, a stand-in "neighbour" application listens on the reserved ports, the site
is started with TLS, and the behaviour of the running site is checked.

The certificate is never fetched from the internet; a local CA whose root is
trusted by the test browser is used instead.
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.services import tls_manager
from app.services.https_upgrade import csp_connect_sources, probe_url, upgrade_snippet
from app.services.public_origin import canonical_url, configured_origin, public_url, secure_origin

ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Certificate fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def certificate_authority(tmp_path_factory):
    """A local CA plus a leaf certificate for the test IP."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime
    import ipaddress

    base = tmp_path_factory.mktemp("ca")
    ip = "203.0.113.77"

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RunUp Local Test CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )

    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)]))
        .issuer_name(name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    def write(path, data, mode=0o600):
        path.write_bytes(data)
        path.chmod(mode)
        return path

    ca_key_path = write(base / "ca.key", key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    ca_cert_path = write(base / "ca.pem", ca_cert.public_bytes(serialization.Encoding.PEM), 0o644)
    leaf_key_path = write(base / "leaf.key", leaf_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    leaf_cert_path = write(base / "leaf.pem", leaf.public_bytes(serialization.Encoding.PEM), 0o644)

    bundle = base / "trusted.pem"
    bundle.write_text(
        leaf_key_path.read_text() + leaf_cert_path.read_text(), encoding="utf-8")
    bundle.chmod(0o600)

    return {
        "ip": ip,
        "bundle": bundle,
        "ca_cert": ca_cert_path,
        "ca_key": ca_key_path,
        "leaf_key": leaf_key_path,
        "leaf_cert": leaf_cert_path,
        "base": base,
    }


# ---------------------------------------------------------------------------
# Materialising the certificate for Gunicorn
# ---------------------------------------------------------------------------


def test_materialise_splits_bundle_into_chain_and_key(certificate_authority, tmp_path):
    chain, key = tls_manager.materialise_tls_material(
        certificate_authority["bundle"], tmp_path)

    assert chain.exists() and key.exists()
    assert chain.read_text().count("BEGIN CERTIFICATE") == 1
    assert "PRIVATE KEY" in key.read_text()
    # The private key must never be world readable.
    assert oct(key.stat().st_mode)[-3:] == "600"


def test_materialise_is_atomic_and_leaves_no_partial_file(certificate_authority, tmp_path):
    tls_manager.materialise_tls_material(certificate_authority["bundle"], tmp_path)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_materialise_rejects_a_bundle_without_a_key(certificate_authority, tmp_path):
    broken = tmp_path / "broken.pem"
    broken.write_text(certificate_authority["leaf_cert"].read_text(), encoding="utf-8")
    with pytest.raises(tls_manager.CertificateError):
        tls_manager.materialise_tls_material(broken, tmp_path / "out")


def test_materialise_rejects_a_bundle_without_a_certificate(certificate_authority, tmp_path):
    broken = tmp_path / "broken.pem"
    broken.write_text(certificate_authority["leaf_key"].read_text(), encoding="utf-8")
    with pytest.raises(tls_manager.CertificateError):
        tls_manager.materialise_tls_material(broken, tmp_path / "out")


def test_materialise_accepts_string_paths(certificate_authority, tmp_path):
    """The setup script passes plain strings; they must work."""
    target = tmp_path / "tls"
    chain, key = tls_manager.materialise_tls_material(
        str(certificate_authority["bundle"]), str(target))
    assert chain.exists() and key.exists()


def test_refresh_tls_material_accepts_string_paths(certificate_authority, tmp_path,
                                                    monkeypatch):
    monkeypatch.setenv("PUBLIC_ORIGIN", f"https://{certificate_authority['ip']}:9900")
    target = tmp_path / "tls"
    ok = tls_manager.refresh_tls_material(
        str(certificate_authority["bundle"]), str(target),
        required_ip=certificate_authority["ip"])
    assert ok is True
    assert (target / "fullchain.pem").exists()


def test_prepare_tls_material_writes_files_when_the_certificate_is_valid(
        certificate_authority, tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_ORIGIN", f"https://{certificate_authority['ip']}:9900")
    ok = tls_manager.prepare_tls_material(
        certificate_authority["bundle"], tmp_path, required_ip=certificate_authority["ip"])
    assert ok is True
    assert (tmp_path / "fullchain.pem").exists()
    assert (tmp_path / "privkey.pem").exists()


def test_prepare_tls_material_declines_a_certificate_for_another_ip(
        certificate_authority, tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://198.51.100.5:9900")
    ok = tls_manager.prepare_tls_material(
        certificate_authority["bundle"], tmp_path, required_ip="198.51.100.5")
    assert ok is False
    assert not (tmp_path / "fullchain.pem").exists()


def test_prepare_tls_material_declines_when_the_certificate_is_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("PUBLIC_ORIGIN", "https://203.0.113.77:9900")
    ok = tls_manager.prepare_tls_material(tmp_path / "absent.pem", tmp_path)
    assert ok is False


# ---------------------------------------------------------------------------
# Serving TLS with the shared certificate
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _prepare_database(tmp_path):
    """Create the schema so the site can answer requests."""
    from app import create_app
    from app.extensions import db

    database = tmp_path / "site.sqlite3"
    application = create_app({
        "TESTING": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database}",
        "SECRET_KEY": "integration-test-secret",
        "UPLOAD_FOLDER": str(tmp_path / "uploads"),
        "RATELIMIT_STORAGE_URI": "memory://",
    })
    with application.app_context():
        db.create_all()
    return database


def _serve_tls(certificate_authority, tmp_path, port: int) -> subprocess.Popen:
    """Run Gunicorn with the shared certificate on ``port``."""
    tls_dir = tmp_path / "tls"
    tls_manager.materialise_tls_material(certificate_authority["bundle"], tls_dir)
    database = _prepare_database(tmp_path)
    env = dict(os.environ)
    env["PUBLIC_ORIGIN"] = f"https://{certificate_authority['ip']}:{port}"
    env["SITE_URL"] = f"https://{certificate_authority['ip']}:{port}"
    env["TLS_CERT_PATH"] = str(certificate_authority["bundle"])
    env["COOKIE_SECURE"] = "true"
    env["SECRET_KEY"] = "integration-test-secret"
    env["DATABASE_URL"] = f"sqlite:///{database}"
    env["RATELIMIT_STORAGE_URI"] = "memory://"
    env["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    env["PYTHONPATH"] = str(ROOT)

    proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "--workers", "1", "--threads", "2",
         "--bind", f"127.0.0.1:{port}",
         "--certfile", str(tls_dir / "fullchain.pem"),
         "--keyfile", str(tls_dir / "privkey.pem"),
         "app:create_app()"],
        cwd=str(ROOT), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    # Wait for the listener.
    for _ in range(100):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return proc
        except OSError:
            if proc.poll() is not None:
                out = proc.stdout.read().decode(errors="replace")
                raise RuntimeError(f"gunicorn failed to start:\n{out}")
            time.sleep(0.1)
    proc.kill()
    raise RuntimeError("gunicorn did not start listening in time")


def test_site_serves_a_valid_certificate_for_the_ip(certificate_authority, tmp_path):
    port = _free_port()
    proc = _serve_tls(certificate_authority, tmp_path, port)
    try:
        context = ssl.create_default_context(cafile=str(certificate_authority["ca_cert"]))
        # The certificate carries the IP as its SAN, so the hostname check has
        # to be relaxed to the address itself.
        conn = socket.create_connection(("127.0.0.1", port), timeout=10)
        tls = context.wrap_socket(conn, server_hostname=certificate_authority["ip"])
        peer = tls.getpeercert()
        assert peer is not None, "no peer certificate was presented"
        assert not tls.getpeercert() is None
        tls.close()

        # And the site answers over that connection.
        import http.client

        conn = socket.create_connection(("127.0.0.1", port), timeout=10)
        tls = context.wrap_socket(conn, server_hostname=certificate_authority["ip"])
        client = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=10)
        client.sock = tls
        client.request("GET", "/")
        response = client.getresponse()
        body = response.read()
        assert response.status == 200
        assert b"RunUp" in body or b"HJF" in body or "utf-8".encode() in body
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def test_https_response_uses_the_secure_origin_in_canonical_and_og(
        certificate_authority, tmp_path):
    port = _free_port()
    proc = _serve_tls(certificate_authority, tmp_path, port)
    try:
        import http.client

        context = ssl.create_default_context(cafile=str(certificate_authority["ca_cert"]))
        conn = socket.create_connection(("127.0.0.1", port), timeout=10)
        tls = context.wrap_socket(conn, server_hostname=certificate_authority["ip"])
        client = http.client.HTTPSConnection("127.0.0.1", port, context=context, timeout=10)
        client.sock = tls
        client.request("GET", "/")
        response = client.getresponse()
        body = response.read().decode("utf-8")

        expected = f"https://{certificate_authority['ip']}:{port}"
        assert f'<link rel="canonical" href="{expected}/">' in body
        assert f'<meta property="og:url" content="{expected}/">' in body
        assert "http://" not in body.split('rel="canonical"')[1][:200]
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def test_renewed_certificate_is_picked_up_without_a_restart(certificate_authority, tmp_path):
    """The neighbour replaces the bundle; the site must follow automatically."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime
    import ipaddress

    port = _free_port()
    tls_dir = tmp_path / "tls"
    tls_manager.materialise_tls_material(certificate_authority["bundle"], tls_dir)
    database = _prepare_database(tmp_path)

    env = dict(os.environ)
    env["PUBLIC_ORIGIN"] = f"https://{certificate_authority['ip']}:{port}"
    env["SITE_URL"] = f"https://{certificate_authority['ip']}:{port}"
    env["TLS_CERT_PATH"] = str(certificate_authority["bundle"])
    env["SECRET_KEY"] = "integration-test-secret"
    env["DATABASE_URL"] = f"sqlite:///{database}"
    env["RATELIMIT_STORAGE_URI"] = "memory://"
    env["PYTHONPATH"] = str(ROOT)

    proc = subprocess.Popen(
        [sys.executable, "-m", "gunicorn", "--workers", "1", "--threads", "2",
         "--bind", f"127.0.0.1:{port}",
         "--certfile", str(tls_dir / "fullchain.pem"),
         "--keyfile", str(tls_dir / "privkey.pem"),
         "app:create_app()"],
        cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.1)

        def peer_fingerprint() -> str:
            context = ssl.create_default_context(cafile=str(certificate_authority["ca_cert"]))
            conn = socket.create_connection(("127.0.0.1", port), timeout=10)
            tls = context.wrap_socket(conn, server_hostname=certificate_authority["ip"])
            fingerprint = tls.getpeercert(binary_form=True)
            tls.close()
            return fingerprint.hex()

        before = peer_fingerprint()

        # The neighbour renews: a brand new key and certificate replace the file.
        ca_key = serialization.load_pem_private_key(
            certificate_authority["ca_key"].read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(
            certificate_authority["ca_cert"].read_bytes())
        new_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        new_leaf = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, certificate_authority["ip"])]))
            .issuer_name(ca_cert.subject)
            .public_key(new_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=2))
            .add_extension(
                x509.SubjectAlternativeName(
                    [x509.IPAddress(ipaddress.ip_address(certificate_authority["ip"]))]),
                critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        renewed = tmp_path / "renewed.pem"
        renewed.write_bytes(
            new_key.private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption())
            + new_leaf.public_bytes(serialization.Encoding.PEM))
        renewed.chmod(0o600)
        # Atomic replacement, exactly like the neighbour does it.
        os.replace(renewed, certificate_authority["bundle"])

        # The watcher refreshes the material and signals Gunicorn.
        ok = tls_manager.refresh_tls_material(
            certificate_authority["bundle"], tls_dir,
            required_ip=certificate_authority["ip"])
        assert ok is True

        # Give Gunicorn a moment to reload the certificate.
        deadline = time.time() + 25
        after = before
        while time.time() < deadline:
            try:
                after = peer_fingerprint()
            except OSError:
                after = before
            if after != before:
                break
            time.sleep(0.5)

        assert after != before, "the renewed certificate was not served"
    finally:
        proc.terminate()
        proc.wait(timeout=20)


# ---------------------------------------------------------------------------
# The neighbour's ports are never taken
# ---------------------------------------------------------------------------


def test_setup_never_binds_the_reserved_ports(certificate_authority, tmp_path):
    """The generated systemd unit must not listen on the neighbour's ports."""
    unit = (ROOT / "scripts" / "setup_runup.sh").read_text(encoding="utf-8")
    for reserved in (80, 443, 8080, 8443, 9443, 9444):
        assert f"--bind 0.0.0.0:{reserved}" not in unit
        assert f"--bind=0.0.0.0:{reserved}" not in unit


def test_setup_script_does_not_install_a_web_server_or_reset_the_firewall():
    script = (ROOT / "scripts" / "setup_runup.sh").read_text(encoding="utf-8")
    for forbidden in ("apt-get install nginx", "apt-get install apache", "apt-get install caddy",
                      "ufw reset", "ufw enable", "nft flush ruleset", "iptables -F",
                      "systemctl restart nftables", "pkill python", "killall python"):
        assert forbidden not in script, f"the setup script must not run: {forbidden}"


def test_setup_script_does_not_kill_other_processes():
    script = (ROOT / "scripts" / "setup_runup.sh").read_text(encoding="utf-8")
    for forbidden in ("pkill", "killall", "kill -9"):
        assert forbidden not in script, f"the setup script must not run: {forbidden}"


def test_setup_script_reuses_the_recorded_port():
    """A second update must not move the public address."""
    script = (ROOT / "scripts" / "setup_runup.sh").read_text(encoding="utf-8")
    assert "HTTPS_PUBLIC_PORT" in script
    assert "RECORDED_TLS_PORT" in script
    # The helper that decides whether a port belongs to this project.
    assert "port_belongs_to_this_project" in script


def test_setup_script_uses_two_separate_gunicorn_instances():
    """Gunicorn applies --certfile to every port, so HTTP and TLS need
    separate processes."""
    script = (ROOT / "scripts" / "setup_runup.sh").read_text(encoding="utf-8")
    assert "TLS_SERVICE" in script
    # The plain-HTTP unit must not carry a certificate, and the TLS unit must.
    http_unit = script.split('${WEB_SERVICE}.service" <<UNIT')[1].split("UNIT")[0]
    tls_unit = script.split('${TLS_SERVICE}.service" <<UNIT')[1].split("UNIT")[0]
    assert "--certfile" not in http_unit
    assert "${TLS_ARGS}" in tls_unit
    # The certificate options are built once and only for the TLS unit.
    assert 'TLS_ARGS="--certfile' in script
    # Each unit binds exactly one port.
    assert http_unit.count("--bind") == 1
    assert tls_unit.count("--bind") == 1


def test_setup_script_never_re_enables_the_firewall():
    script = (ROOT / "scripts" / "setup_runup.sh").read_text(encoding="utf-8")
    for forbidden in ("ufw enable", "ufw --force enable", "ufw allow", "firewall-cmd"):
        assert forbidden not in script, f"the setup script must not run: {forbidden}"


# ---------------------------------------------------------------------------
# Public origin and the legacy HTTP upgrade
# ---------------------------------------------------------------------------


def test_public_origin_prefers_public_origin_over_site_url(app):
    app.config["PUBLIC_ORIGIN"] = "https://212.237.217.171:9900"
    app.config["SITE_URL"] = "http://212.237.217.171:9900"
    with app.app_context():
        assert configured_origin() == "https://212.237.217.171:9900"
        assert secure_origin() == "https://212.237.217.171:9900"


def test_public_origin_upgrades_an_http_site_url(app):
    app.config["PUBLIC_ORIGIN"] = ""
    app.config["SITE_URL"] = "http://212.237.217.171:9900"
    with app.app_context():
        assert secure_origin() == "https://212.237.217.171:9900"


def test_public_url_builds_on_the_public_origin(app):
    app.config["PUBLIC_ORIGIN"] = "https://212.237.217.171:9900"
    with app.test_request_context("/"):
        assert public_url("/products") == "https://212.237.217.171:9900/products"


def test_canonical_url_ignores_the_request_scheme(app):
    app.config["PUBLIC_ORIGIN"] = "https://212.237.217.171:9900"
    with app.test_request_context("/products?page=2", base_url="http://212.237.217.171:19900"):
        assert canonical_url() == "https://212.237.217.171:9900/products?page=2"


def test_csp_connect_sources_adds_only_the_probe_origin():
    policy = "default-src 'self'; connect-src 'self'; object-src 'none'"
    updated = csp_connect_sources(policy, "https://212.237.217.171:9900")
    # The source has to carry its scheme, because a source with a port is
    # only matched when the scheme matches too.
    assert "connect-src 'self' https://212.237.217.171:9900" in updated
    assert updated.count("connect-src") == 1
    # Everything else stays untouched.
    assert "default-src 'self'" in updated
    assert "object-src 'none'" in updated
    # The strict policy keeps its other directives.
    assert "script-src" not in updated
    assert "unsafe-inline" not in updated


def test_csp_connect_sources_is_idempotent():
    policy = "default-src 'self'; connect-src 'self'"
    once = csp_connect_sources(policy, "https://212.237.217.171:9900")
    twice = csp_connect_sources(once, "https://212.237.217.171:9900")
    assert once == twice


def test_upgrade_snippet_targets_the_secure_origin():
    snippet = upgrade_snippet("https://212.237.217.171:9900")
    assert "212.237.217.171:9900" in snippet
    assert "location.replace" in snippet
    assert "no-cors" in snippet


def test_upgrade_snippet_is_empty_without_an_origin():
    assert upgrade_snippet("") == ""


def test_probe_url_points_at_the_secure_origin():
    assert probe_url("https://212.237.217.171:9900").startswith("https://212.237.217.171:9900/")


def test_legacy_http_page_offers_the_upgrade_script(client):
    """On plain HTTP the page loads the external upgrade script."""
    app = client.application
    old_origin = app.config.get("PUBLIC_ORIGIN")
    old_secure = app.config.get("SESSION_COOKIE_SECURE")
    app.config["PUBLIC_ORIGIN"] = "https://212.237.217.171:9900"
    app.config["SESSION_COOKIE_SECURE"] = False
    try:
        response = client.get("/", base_url="http://212.237.217.171:19900")
        body = response.data.decode("utf-8")
        assert "js/https-upgrade.js" in body
        assert 'data-secure-origin="https://212.237.217.171:9900"' in body
        # The CSP has to allow the probe origin.
        policy = response.headers["Content-Security-Policy"]
        assert "connect-src" in policy
        assert "212.237.217.171:9900" in policy
        # No inline script may be used, so the strict policy stays valid.
        assert "'unsafe-inline'" not in policy.split("script-src")[1].split(";")[0]
    finally:
        app.config["PUBLIC_ORIGIN"] = old_origin
        app.config["SESSION_COOKIE_SECURE"] = old_secure


def test_https_page_has_no_upgrade_script(client):
    app = client.application
    old_origin = app.config.get("PUBLIC_ORIGIN")
    app.config["PUBLIC_ORIGIN"] = "https://212.237.217.171:9900"
    try:
        response = client.get("/", base_url="https://212.237.217.171:9900")
        body = response.data.decode("utf-8")
        assert "js/https-upgrade.js" not in body
    finally:
        app.config["PUBLIC_ORIGIN"] = old_origin
