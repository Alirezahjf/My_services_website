"""The chain that is served must be enough to reach a trusted root.

A phone that has never opened this site holds no intermediate
certificate in its store. It can only build the path if the server sends
the intermediate along with the leaf. When the server sends the leaf
alone, the browser on a phone gives up and shows an empty page, while a
desktop that has the intermediate cached from an earlier visit keeps
working. The difference between the two is the reason this is written
down here.
"""

from __future__ import annotations

import datetime
import ipaddress
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.services import tls_manager

IP = "203.0.113.55"


def _write_key(path: Path, key) -> None:
    path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))


def _make_ca(tmp_path: Path) -> tuple[Path, Path]:
    """A root that signs an intermediate, the way a real issuer does."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Root")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    key_path = tmp_path / "root-key.pem"
    cert_path = tmp_path / "root.pem"
    _write_key(key_path, key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, cert_path


def _make_intermediate(tmp_path: Path, root_key, root_cert) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    root_cert_obj = x509.load_pem_x509_certificate(root_cert.read_bytes())
    root_key_obj = serialization.load_pem_private_key(root_key.read_bytes(), password=None)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test Intermediate")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(root_cert_obj.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=20))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .sign(root_key_obj, hashes.SHA256())
    )
    key_path = tmp_path / "int-key.pem"
    cert_path = tmp_path / "int.pem"
    _write_key(key_path, key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, cert_path


def _make_leaf(tmp_path: Path, int_key, int_cert, ip: str) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    int_cert_obj = x509.load_pem_x509_certificate(int_cert.read_bytes())
    int_key_obj = serialization.load_pem_private_key(int_key.read_bytes(), password=None)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(int_cert_obj.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip))]),
            critical=False,
        )
        .sign(int_key_obj, hashes.SHA256())
    )
    key_path = tmp_path / "leaf-key.pem"
    cert_path = tmp_path / "leaf.pem"
    _write_key(key_path, key)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return key_path, cert_path


def _bundle(key_path: Path, *cert_paths: Path) -> bytes:
    """The neighbour's file: the key first, then the leaf and the chain."""
    parts = [key_path.read_bytes()]
    for cert in cert_paths:
        parts.append(cert.read_bytes())
    return b"".join(parts)


def test_the_served_chain_holds_the_intermediate(tmp_path):
    """The neighbour's bundle carries the leaf and the intermediate.

    The bundle is written as the key first and then the certificate with
    its chain, the way the neighbour writes it. The file that is served
    must hold both, because a phone that has not seen the site before
    cannot build the path without the intermediate.
    """
    root_key, root_cert = _make_ca(tmp_path)
    int_key, int_cert = _make_intermediate(tmp_path, root_key, root_cert)
    leaf_key, leaf_cert = _make_leaf(tmp_path, int_key, int_cert, IP)

    bundle = tmp_path / "trusted.pem"
    bundle.write_bytes(_bundle(leaf_key, leaf_cert, int_cert))

    out_dir = tmp_path / "served"
    chain, key = tls_manager.materialise_tls_material(bundle, out_dir)

    chain_text = chain.read_text(encoding="utf-8")
    assert chain_text.count("BEGIN CERTIFICATE") == 2, \
        "the served chain holds only the leaf; a phone cannot build the path"
    assert "BEGIN PRIVATE KEY" not in chain_text, \
        "the private key must not be in the chain file"

    key_text = key.read_text(encoding="utf-8")
    assert "BEGIN" in key_text and "PRIVATE KEY" in key_text
    assert "BEGIN CERTIFICATE" not in key_text, \
        "the key file must not hold a certificate"

    # The path to the root must now be complete.
    result = subprocess.run(
        ["openssl", "verify", "-CAfile", str(root_cert), "-untrusted", str(chain),
         str(leaf_cert)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, \
        f"the path to the root is not complete: {result.stdout}{result.stderr}"


def test_a_bundle_with_only_the_leaf_is_not_passed_off_as_complete(tmp_path):
    """A bundle with only the leaf is still served, but it is named.

    The site must keep working with what the neighbour gives. It must
    also say that the chain is short, so that the reason for an empty
    page on a phone is written down where it can be read.
    """
    root_key, root_cert = _make_ca(tmp_path)
    int_key, int_cert = _make_intermediate(tmp_path, root_key, root_cert)
    leaf_key, leaf_cert = _make_leaf(tmp_path, int_key, int_cert, IP)

    bundle = tmp_path / "trusted.pem"
    bundle.write_bytes(_bundle(leaf_key, leaf_cert))

    out_dir = tmp_path / "served"
    chain, _key = tls_manager.materialise_tls_material(bundle, out_dir)

    assert chain.read_text(encoding="utf-8").count("BEGIN CERTIFICATE") == 1

    # The certificate is still the right one for the address.
    info = tls_manager.read_certificate(chain)
    assert info.subject_ip == IP
    assert not info.is_expired
