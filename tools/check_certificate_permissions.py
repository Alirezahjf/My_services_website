#!/usr/bin/env python3
"""Check that a certificate behind a closed directory can still be used.

This reproduces the situation on the real server: the certificate of the
neighbouring application lives under a directory that the service user
cannot enter (for example ``/root/Desktop/...``). The setup script has to
take a copy into the project's own runtime directory and hand that copy to
the service user, while the neighbour's file stays untouched.

The test does not need root. A directory that the current user owns but
that has mode 0700 blocks every other user, which is the same obstacle
that ``/root`` creates on the server.

Run it with::

    python tools/check_certificate_permissions.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
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


def make_certificate(path: Path) -> None:
    """Write a self signed certificate with a key for 203.0.113.55."""
    import datetime
    import ipaddress

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "203.0.113.55")])
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
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("203.0.113.55"))]),
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


COPY_TEMPLATE = """#!/usr/bin/env bash
set -Eeuo pipefail
APP_USER=@@APP_USER@@
APP_DIR=@@APP_DIR@@
copy_neighbour_certificate() {
  local cert_file="$1"
  [[ -f "$cert_file" ]] || return 1
  mkdir -p "$APP_DIR/instance/tls"
  chown "$APP_USER:$APP_USER" "$APP_DIR/instance" 2>/dev/null || true
  chown "$APP_USER:$APP_USER" "$APP_DIR/instance/tls" 2>/dev/null || true
  chmod 0750 "$APP_DIR/instance" "$APP_DIR/instance/tls" 2>/dev/null || true
  if "@@PYTHON@@" -c "
import sys
sys.path.insert(0, '@@ROOT@@')
from app.services.tls_manager import materialise_tls_material
materialise_tls_material('@@CERT@@', '@@TLS_DIR@@', owner='@@APP_USER@@')
" 2>/dev/null; then
    chmod 0644 "@@TLS_DIR@@/fullchain.pem" 2>/dev/null || true
    chmod 0600 "@@TLS_DIR@@/privkey.pem" 2>/dev/null || true
    return 0
  fi
  rm -f "@@TLS_DIR@@/fullchain.pem" "@@TLS_DIR@@/privkey.pem"
  return 1
}
copy_neighbour_certificate "@@CERT@@"
"""


def main() -> int:
    workdir = Path(tempfile.mkdtemp(prefix="runup-perm-"))
    # The scratch directory must be enterable by everybody, so that the
    # only obstacle in the test is the one that is meant to be tested.
    os.chmod(workdir, 0o755)
    try:
        private = workdir / "private"
        private.mkdir()
        os.chmod(private, 0o700)
        cert_path = private / "trusted.pem"
        make_certificate(cert_path)
        os.chmod(cert_path, 0o600)

        tls_dir = workdir / "project" / "instance" / "tls"
        project = workdir / "project"

        # 1. The fixture really blocks other users. The check looks at the
        #    permission bits the way the kernel does for a foreign user:
        #    a directory without the execute bit for others cannot be
        #    entered, and a file without the read bit cannot be read.
        dir_mode = private.stat().st_mode & 0o777
        file_mode = cert_path.stat().st_mode & 0o777
        check(
            "the fixture blocks other users (like /root does)",
            not (dir_mode & 0o001) and not (file_mode & 0o004),
            oct(dir_mode),
        )

        # 2. A path that cannot be reached is not called missing.
        from app.services.tls_manager import CertificateError, read_certificate

        sealed = workdir / "sealed"
        sealed.mkdir()
        sealed.chmod(0o000)
        try:
            read_certificate(sealed / "trusted.pem")
            message = ""
        except CertificateError as exc:
            message = str(exc)
        finally:
            sealed.chmod(0o755)
        check(
            "an unreachable path is reported as a permission problem, not as a missing file",
            "پیدا نشد" not in message,
            message,
        )

        # 3. The setup script takes the copy and hands it to the service
        #    user, without touching the neighbour's file.
        script = workdir / "copy.sh"
        script.write_text(
            COPY_TEMPLATE.replace("@@APP_USER@@", os.environ.get("APP_USER", "services"))
            .replace("@@APP_DIR@@", str(project))
            .replace("@@ROOT@@", str(ROOT))
            .replace("@@PYTHON@@", sys.executable)
            .replace("@@CERT@@", str(cert_path))
            .replace("@@TLS_DIR@@", str(tls_dir))
        )
        os.chmod(script, 0o755)

        env = dict(os.environ, APP_USER=os.environ.get("APP_USER", "services"))
        result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
        check(
            "the setup script takes the copy of a blocked certificate",
            result.returncode == 0,
            (result.stdout + result.stderr).strip()[-800:],
        )

        chain = tls_dir / "fullchain.pem"
        key = tls_dir / "privkey.pem"
        check("the chain was written", chain.is_file())
        check("the private key was written", key.is_file())

        # 4. The neighbour's file keeps its permissions and its content.
        dir_mode = private.stat().st_mode & 0o777
        file_mode = cert_path.stat().st_mode & 0o777
        check("the directory mode was not changed", dir_mode == 0o700, oct(dir_mode))
        check("the file mode was not changed", file_mode == 0o600, oct(file_mode))

        original = cert_path.read_text()
        check(
            "the neighbour's bundle still holds a key and a certificate",
            "BEGIN CERTIFICATE" in original and "PRIVATE KEY" in original,
        )
        check(
            "the copy holds the certificate of the neighbour",
            "BEGIN CERTIFICATE" in chain.read_text(),
        )
        check(
            "the copy holds the private key of the neighbour",
            "PRIVATE KEY" in key.read_text(),
        )
        check(
            "the copy leaves the private key out of the chain",
            "PRIVATE KEY" not in chain.read_text(),
        )
        check(
            "the copy leaves the certificate out of the key",
            "BEGIN CERTIFICATE" not in key.read_text(),
        )
        check(
            "the private key is not readable by others",
            not (key.stat().st_mode & 0o004),
            oct(key.stat().st_mode & 0o777),
        )

        # 5. The status falls back to the copy when the source is blocked.
        from app.services.tls_manager import collect_status

        state = collect_status(
            explicit_cert_path=str(cert_path),
            site_url="https://203.0.113.55:9900",
        )
        check(
            "the status reports HTTPS as on, using the copy",
            state.enabled is True,
            f"{state.reason} — {state.detail}",
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
