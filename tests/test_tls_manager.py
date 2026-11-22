"""Tests for the shared-certificate TLS manager."""
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.services import tls_manager
from app.services.tls_manager import (
    CertificateError,
    CertificateInfo,
    TlsStatus,
    certificate_covers_ip,
    choose_public_port,
    collect_status,
    find_certificate,
    read_certificate,
)


# ---------------------------------------------------------------------------
# Helpers that build a real certificate with a local CA
# ---------------------------------------------------------------------------


def _make_ca(tmp_path: Path) -> tuple[Path, Path]:
    """Create a throwaway CA and return (ca_key, ca_cert) paths."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "RunUp Test CA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path = tmp_path / "ca.key"
    cert_path = tmp_path / "ca.pem"
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, cert_path


def _make_leaf(tmp_path: Path, ca_key: Path, ca_cert: Path, ip: str, days: int = 2,
               common_name: str = "leaf", expired: bool = False) -> tuple[Path, Path]:
    """Issue a leaf certificate for ``ip`` (or a DNS name when ip is empty)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime
    import ipaddress

    ca_key_obj = serialization.load_pem_private_key(ca_key.read_bytes(), password=None)
    ca_cert_obj = x509.load_pem_x509_certificate(ca_cert.read_bytes())

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    if expired:
        not_before = now - datetime.timedelta(days=30)
        not_after = now - datetime.timedelta(days=1)
    else:
        not_before = now - datetime.timedelta(days=1)
        not_after = now + datetime.timedelta(days=days)

    builder = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)]))
        .issuer_name(ca_cert_obj.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
    )
    if ip:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip))]), critical=False)
    else:
        builder = builder.add_extension(
            x509.SubjectAlternativeName([x509.DNSName(f"{common_name}.example")]), critical=False)

    cert = builder.sign(ca_key_obj, hashes.SHA256())
    key_path = tmp_path / f"{common_name}.key"
    crt_path = tmp_path / f"{common_name}.crt"
    key_path.write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ))
    crt_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, crt_path


def _bundle(tmp_path: Path, key: Path, crt: Path, name: str = "trusted.pem") -> Path:
    """Write a combined key+certificate PEM bundle, like the neighbour's."""
    bundle = tmp_path / name
    bundle.write_text(key.read_text() + crt.read_text(), encoding="utf-8")
    bundle.chmod(0o600)
    return bundle


# ---------------------------------------------------------------------------
# Certificate inspection
# ---------------------------------------------------------------------------


def test_read_certificate_extracts_ip_and_expiry(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    bundle = _bundle(tmp_path, key, crt)

    info = read_certificate(bundle)

    assert info.subject_ip == "212.237.217.171"
    assert info.not_after > datetime.now(timezone.utc)
    assert info.fingerprint
    assert not info.is_expired
    assert "روز" in info.expires_in or "ساعت" in info.expires_in or "دقیقه" in info.expires_in


def test_read_certificate_detects_expired(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171", expired=True)

    info = read_certificate(crt)

    assert info.is_expired
    assert info.expires_in == "منقضی شده"


def test_read_certificate_rejects_non_certificate_file(tmp_path):
    junk = tmp_path / "junk.pem"
    junk.write_text("not a certificate at all", encoding="utf-8")
    with pytest.raises(CertificateError):
        read_certificate(junk)


def test_read_certificate_reports_missing_file(tmp_path):
    with pytest.raises(CertificateError):
        read_certificate(tmp_path / "absent.pem")


def test_read_certificate_reports_permission_denied(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    bundle = _bundle(tmp_path, key, crt)
    bundle.chmod(0o000)
    try:
        if os.geteuid() == 0:
            pytest.skip("root bypasses file permissions")
        with pytest.raises(CertificateError) as exc:
            read_certificate(bundle)
        assert "اجازه خواندن" in str(exc.value)
    finally:
        bundle.chmod(0o600)


def test_certificate_covers_ip_matches_exactly():
    info = CertificateInfo(path=Path("/tmp/x"), not_after=datetime.now(timezone.utc),
                            subject_ip="212.237.217.171")
    assert certificate_covers_ip(info, "212.237.217.171")
    assert not certificate_covers_ip(info, "212.237.217.172")
    assert not certificate_covers_ip(info, "not-an-ip")


def test_certificate_covers_ip_rejects_domain_only_certificate(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "", common_name="example")
    info = read_certificate(crt)
    assert info.subject_ip is None
    assert not certificate_covers_ip(info, "212.237.217.171")


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def test_find_certificate_uses_explicit_path(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    bundle = _bundle(tmp_path, key, crt)

    found, notes = find_certificate(bundle)

    assert found == bundle
    assert any("مسیر دستی" in n for n in notes)


def test_find_certificate_uses_explicit_directory(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    (tmp_path / "data" / "tls").mkdir(parents=True)
    bundle = _bundle(tmp_path, key, crt, name="trusted.pem")
    bundle.unlink()
    (tmp_path / "data" / "tls" / "trusted.pem").write_text(
        key.read_text() + crt.read_text(), encoding="utf-8")

    found, notes = find_certificate(tmp_path)

    assert found == tmp_path / "data" / "tls" / "trusted.pem"


def test_find_certificate_reports_missing_explicit_path(tmp_path):
    found, notes = find_certificate(tmp_path / "nope.pem")
    assert found is None
    assert any("وجود نداشت" in n for n in notes)


def test_find_certificate_never_writes_into_the_candidate_directory(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    (tmp_path / "data" / "tls").mkdir(parents=True)
    (tmp_path / "data" / "tls" / "trusted.pem").write_text(
        key.read_text() + crt.read_text(), encoding="utf-8")
    before = sorted(p.name for p in (tmp_path / "data" / "tls").iterdir())

    find_certificate(tmp_path)

    after = sorted(p.name for p in (tmp_path / "data" / "tls").iterdir())
    assert before == after


# ---------------------------------------------------------------------------
# Port selection
# ---------------------------------------------------------------------------


def test_choose_public_port_prefers_the_requested_port(monkeypatch):
    monkeypatch.setattr(tls_manager, "port_is_free", lambda port: True)
    assert choose_public_port(9900) == 9900


def test_choose_public_port_never_takes_a_reserved_port(monkeypatch):
    monkeypatch.setattr(tls_manager, "port_is_free", lambda port: True)
    for reserved in (80, 443, 8080, 8443, 9443, 9444):
        with pytest.raises(CertificateError):
            choose_public_port(reserved)


def test_choose_public_port_avoids_reserved_ports_when_falling_back(monkeypatch):
    # 9900 is busy; every other candidate is free.
    def free_except_9900(port):
        return port != 9900
    monkeypatch.setattr(tls_manager, "port_is_free", free_except_9900)
    chosen = choose_public_port(9900)
    assert chosen in (9445, 9943, 10444, 9446, 8445, 9950)
    assert chosen not in (80, 443, 8080, 8443, 9443, 9444)


def test_choose_public_port_skips_busy_fallbacks(monkeypatch):
    free = {9445, 9950}
    monkeypatch.setattr(tls_manager, "port_is_free", lambda port: port in free)
    assert choose_public_port(9900) == 9445


def test_choose_public_port_raises_when_everything_is_taken(monkeypatch):
    monkeypatch.setattr(tls_manager, "port_is_free", lambda port: False)
    with pytest.raises(CertificateError):
        choose_public_port(9900)


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


def test_collect_status_enabled_for_matching_certificate(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    bundle = _bundle(tmp_path, key, crt)

    status = collect_status(
        explicit_cert_path=str(bundle),
        public_port=9900,
        http_port=19900,
        site_url="https://212.237.217.171:9900",
    )

    assert status.enabled is True
    assert status.public_port == 9900
    assert status.certificate is not None
    assert status.certificate.subject_ip == "212.237.217.171"


def test_collect_status_disabled_when_certificate_is_for_another_ip(tmp_path):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "203.0.113.9")
    bundle = _bundle(tmp_path, key, crt)

    status = collect_status(
        explicit_cert_path=str(bundle),
        site_url="https://212.237.217.171:9900",
    )

    assert status.enabled is False
    assert "نشانی این سایت نیست" in status.reason


def test_collect_status_disabled_when_certificate_missing(tmp_path):
    status = collect_status(explicit_cert_path=str(tmp_path / "absent.pem"))
    assert status.enabled is False
    assert status.reason


def test_collect_status_disabled_when_certificate_is_unreadable(tmp_path):
    junk = tmp_path / "junk.pem"
    junk.write_text("nonsense", encoding="utf-8")
    status = collect_status(explicit_cert_path=str(junk))
    assert status.enabled is False
    assert "خوانده نشد" in status.reason


# ---------------------------------------------------------------------------
# Reloader
# ---------------------------------------------------------------------------


class _FakeSignal:
    """Records calls to the reloader's master-process signal helper."""

    def __init__(self, ok: bool = True):
        self.calls = 0
        self.ok = ok

    def __call__(self):
        self.calls += 1
        return self.ok


def test_reloader_signals_master_when_certificate_changes(tmp_path, monkeypatch):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    bundle = _bundle(tmp_path, key, crt)

    fake = _FakeSignal()
    reloader = tls_manager.CertificateReloader(bundle)
    reloader._signal_master = fake  # type: ignore[assignment]
    monkeypatch.setenv("GUNICORN_PID", "4242")

    reloaded, message = reloader.refresh()
    assert reloaded is True
    assert fake.calls == 1
    assert "بارگذاری" in message


def test_reloader_does_not_signal_when_certificate_is_unchanged(tmp_path, monkeypatch):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    bundle = _bundle(tmp_path, key, crt)

    fake = _FakeSignal()
    reloader = tls_manager.CertificateReloader(bundle)
    reloader._signal_master = fake  # type: ignore[assignment]
    monkeypatch.setenv("GUNICORN_PID", "4242")

    reloader.refresh()
    fake.calls = 0
    reloaded, message = reloader.refresh()

    assert reloaded is False
    assert fake.calls == 0
    assert "تغییری نکرده" in message


def test_reloader_reports_failed_signal(tmp_path, monkeypatch):
    ca_key, ca_cert = _make_ca(tmp_path)
    key, crt = _make_leaf(tmp_path, ca_key, ca_cert, "212.237.217.171")
    bundle = _bundle(tmp_path, key, crt)

    fake = _FakeSignal(ok=False)
    reloader = tls_manager.CertificateReloader(bundle)
    reloader._signal_master = fake  # type: ignore[assignment]
    monkeypatch.setenv("GUNICORN_PID", "4242")

    reloaded, message = reloader.refresh()

    assert reloaded is False
    assert "سیگنال" in message


def test_reloader_refuses_expired_certificate(tmp_path, monkeypatch):
    ca_key, ca_cert = _make_ca(tmp_path)
    expired_key, expired_crt = _make_leaf(
        tmp_path, ca_key, ca_cert, "212.237.217.171", expired=True)
    bundle = _bundle(tmp_path, expired_key, expired_crt)

    fake = _FakeSignal()
    reloader = tls_manager.CertificateReloader(bundle)
    reloader._signal_master = fake  # type: ignore[assignment]
    monkeypatch.setenv("GUNICORN_PID", "4242")

    reloaded, message = reloader.refresh()

    assert reloaded is False
    assert fake.calls == 0
    assert "منقضی" in message


def test_reloader_reports_missing_certificate(tmp_path):
    reloader = tls_manager.CertificateReloader(tmp_path / "absent.pem")
    reloaded, message = reloader.refresh()
    assert reloaded is False
    assert "پیدا نشد" in message


def test_read_certificate_names_the_permission_problem(tmp_path, monkeypatch):
    """A file behind a directory the service user cannot enter is not called missing."""
    private = tmp_path / "private"
    private.mkdir()
    bundle = private / "trusted.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n")
    private.chmod(0o700)

    real_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        if self == bundle:
            raise PermissionError(13, "Permission denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)
    with pytest.raises(tls_manager.CertificateError) as excinfo:
        tls_manager.read_certificate(bundle)
    message = str(excinfo.value)
    assert "قابل دسترسی نیست" in message
    assert "پیدا نشد" not in message


def test_find_certificate_explains_a_blocked_path(tmp_path, monkeypatch):
    """The discovery names the permission problem rather than a missing file."""
    private = tmp_path / "private"
    private.mkdir()
    bundle = private / "trusted.pem"
    bundle.write_text("-----BEGIN CERTIFICATE-----\n")

    real_stat = Path.stat

    def fake_stat(self, *args, **kwargs):
        if self == bundle:
            raise PermissionError(13, "Permission denied")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", fake_stat)
    path, notes = tls_manager.find_certificate(str(bundle))
    assert path is None
    assert any("اجازه ورود" in note for note in notes)
