#!/usr/bin/env python3
"""Check that the certificate of this project is never taken for the neighbour's.

On the real server the project lives in ``/opt/hjf-services`` and carries
its own units, whose names start with ``runup-``. The discovery used to
recognise those units as the neighbour's, which pointed it at this
project, where a test certificate for ``127.0.0.1`` was found. That
certificate never covers the public address, and because the search
stopped there, the site stayed on plain HTTP.

The check builds that situation and asks for the certificate of the
neighbour.

Run it with::

    python tools/check_certificate_discovery.py
"""

from __future__ import annotations

import datetime
import ipaddress
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"{GREEN}PASS{RESET} {name}")
    else:
        print(f"{RED}FAIL{RESET} {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def write_certificate(path: Path, ip: str) -> None:
    """Write a self signed certificate with a key for ``ip``."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=90))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip))]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        + cert.public_bytes(serialization.Encoding.PEM)
    )


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="runup-discovery-"))
    os.chmod(workdir, 0o755)
    try:
        # The neighbour, with the certificate that fits the public address.
        neighbour = workdir / "shomarejoo_web"
        neighbour_cert = neighbour / "data" / "tls" / "trusted.pem"
        write_certificate(neighbour_cert, "203.0.113.55")

        # This project, with a test certificate that fits nothing.
        project = workdir / "hjf-services"
        own_cert = project / "cert.pem"
        write_certificate(own_cert, "127.0.0.1")

        from app.services import tls_manager

        # Pretend the project lives where it lives on the server.
        tls_manager.PROJECT_ROOT = project

        check(
            "the project's own unit is not taken for a neighbour's unit",
            tls_manager._is_own_unit("runup-web.service") is True
            and tls_manager._is_own_unit("runup-tls.service") is True,
        )
        check(
            "the neighbour's unit is still recognised",
            tls_manager._is_own_unit("shomarejoo-web.service") is False,
        )
        check(
            "the project's own directory is not a candidate",
            tls_manager._is_own_directory(project) is True,
        )
        check(
            "the neighbour's directory is still a candidate",
            tls_manager._is_own_directory(neighbour) is False,
        )

        # The explicit path inside the project is ignored.
        found, notes = tls_manager.find_certificate(str(own_cert))
        check(
            "a certificate inside this project is not taken for the neighbour's",
            found != own_cert,
            " | ".join(notes),
        )

        # The search does not stop at a certificate that fits another
        # address: it looks on.
        original_dirs = tls_manager._candidate_neighbour_dirs
        tls_manager._candidate_neighbour_dirs = lambda: [project, neighbour]
        try:
            found, notes = tls_manager.find_certificate_for_ip(
                None, "203.0.113.55")
        finally:
            tls_manager._candidate_neighbour_dirs = original_dirs
        check(
            "the search skips a certificate for another address and goes on",
            found == neighbour_cert,
            " | ".join(notes),
        )

        # And when nothing fits, it says so instead of picking the wrong one.
        original_dirs = tls_manager._candidate_neighbour_dirs
        tls_manager._candidate_neighbour_dirs = lambda: [project]
        try:
            found, notes = tls_manager.find_certificate_for_ip(
                None, "203.0.113.55")
        finally:
            tls_manager._candidate_neighbour_dirs = original_dirs
        check(
            "no certificate for another address is returned",
            found is None,
            " | ".join(notes),
        )
        check(
            "the reason is written down for the operator",
            any("203.0.113.55" in note for note in notes),
            " | ".join(notes),
        )

    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print()
    if failures:
        print(f"{RED}{len(failures)} check(s) failed{RESET}")
        return 1
    print(f"{GREEN}all checks passed{RESET}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
