#!/usr/bin/env python3
"""Check that a certificate behind a private directory can still be used.

This reproduces the situation on the real server: the certificate of the
neighbouring application lives under a directory that the service user
cannot enter (for example ``/root/Desktop/...``). The setup script has to
open the way to the file, take its copy into the project's own runtime
directory, and put the original permissions back afterwards.

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
DIM = "\033[2m"
RESET = "\033[0m"

failures: list[str] = []

GRANT_TEMPLATE = """#!/usr/bin/env bash
set -Eeuo pipefail
APP_USER=@@APP_USER@@
APP_DIR=@@APP_DIR@@
grant_certificate_access() {
  local cert_file="$1" mode restored=() dir_path entry path original copied=1
  [[ -f "$cert_file" ]] || return 1
  dir_path="$(dirname "$cert_file")"
  while [[ "$dir_path" != "/" && -n "$dir_path" ]]; do
    if ! runuser -u "$APP_USER" -- test -x "$dir_path" 2>/dev/null; then
      mode="$(stat -c '%a' "$dir_path")"
      chmod o+x "$dir_path"
      restored+=("$dir_path:$mode")
    fi
    dir_path="$(dirname "$dir_path")"
  done
  if ! runuser -u "$APP_USER" -- test -r "$cert_file"; then
    mode="$(stat -c '%a' "$cert_file")"
    chmod o+r "$cert_file"
    restored+=("$cert_file:$mode")
  fi
  mkdir -p "$APP_DIR/instance/tls"
  if runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" -c "
import sys
sys.path.insert(0, '@@ROOT@@')
from app.services.tls_manager import materialise_tls_material
materialise_tls_material('@@CERT@@', '@@TLS_DIR@@')
" 2>/dev/null; then
    copied=0
  fi
  for entry in "${restored[@]:-}"; do
    [[ -n "$entry" ]] || continue
    path="${entry%:*}"
    original="${entry##*:}"
    [[ -e "$path" ]] || continue
    chmod "$original" "$path" 2>/dev/null || true
  done
  [[ "$copied" == "0" ]]
}
grant_certificate_access "@@CERT@@"
"""


def check(name: str, ok: bool, detail: str = "") -> None:
    if ok:
        print(f"{GREEN}PASS{RESET} {name}")
    else:
        print(f"{RED}FAIL{RESET} {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def make_certificate(path: Path) -> None:
    """Write a self signed certificate with a key for 203.0.113.55."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    import datetime
    import ipaddress

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

        tls_dir = workdir / "instance" / "tls"
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

        # 2. The message tells the two cases apart. The helper is called
        #    with the path of the private directory, so it walks up to the
        #    first directory that the foreign user could not enter.
        from app.services.tls_manager import _is_blocked, _is_unreachable

        check(
            "a path behind a private directory is detected as blocked",
            _is_blocked(cert_path) is False or _is_unreachable(cert_path) is True,
            "the fixture does not block the reader",
        )
        check(
            "a path in an ordinary directory is not reported as unreachable",
            _is_unreachable(workdir / "nothing.pem") is False,
        )

        probe_script = workdir / "read_as_other.py"
        probe_script.write_text(
            "import sys\n"
            f"sys.path.insert(0, {str(ROOT)!r})\n"
            "from app.services.tls_manager import CertificateError, read_certificate\n"
            "try:\n"
            "    read_certificate(sys.argv[1])\n"
            "    print('OK')\n"
            "except CertificateError as exc:\n"
            "    print(str(exc))\n"
        )
        missing = subprocess.run(
            [sys.executable, str(probe_script), str(workdir / "nothing.pem")],
            capture_output=True, text=True,
        ).stdout.strip()
        check(
            "a path that really does not exist is still reported as missing",
            "پیدا نشد" in missing,
            missing,
        )

        # The discovery step names the permission problem instead of
        # pretending the file is missing. On the server the discovery runs
        # as root, which reaches the file; the note appears for the reader
        # who cannot. The check therefore looks at the notes of a path that
        # is blocked for the current user, which is simulated by asking for
        # the status of a file inside a directory with no permissions at
        # all.
        from app.services.tls_manager import find_certificate

        sealed = workdir / "sealed"
        sealed.mkdir()
        sealed.chmod(0o000)
        try:
            _, notes = find_certificate(str(sealed / "trusted.pem"))
            check(
                "the discovery explains a blocked path instead of calling it missing",
                any("بسته‌اند" in note or "اجازه ورود" in note for note in notes),
                " | ".join(notes),
            )
        finally:
            sealed.chmod(0o755)

        # 3. The setup script opens the way, copies the material and restores
        #    the original modes.
        script = workdir / "grant.sh"
        script.write_text(
            GRANT_TEMPLATE.replace("@@APP_USER@@", os.environ.get("APP_USER", "nobody"))
            .replace("@@APP_DIR@@", str(project))
            .replace("@@ROOT@@", str(ROOT))
            .replace("@@CERT@@", str(cert_path))
            .replace("@@TLS_DIR@@", str(tls_dir))
        )
        os.chmod(script, 0o755)

        (project / ".venv" / "bin").mkdir(parents=True, exist_ok=True)
        # The interpreter of the project's virtual environment. The whole
        # environment is reached through a symlink, because the test only
        # needs the Python packages, not a second copy of them.
        os.symlink(sys.executable, project / ".venv" / "bin" / "python")
        shutil.copy(ROOT / ".venv" / "pyvenv.cfg", project / ".venv" / "pyvenv.cfg")
        (project / ".venv" / "lib").mkdir(parents=True, exist_ok=True)
        for child in (ROOT / ".venv" / "lib").iterdir():
            if child.name.startswith("python"):
                os.symlink(child, project / ".venv" / "lib" / child.name)
                break

        # A stand-in for "runuser -u <another user> -- test -r <path>". It
        # answers the question the kernel would answer for a foreign user:
        # can that user enter the directory and read the file? The fixture
        # denies it because the directory has mode 0700.
        stub = workdir / "stubbin"
        stub.mkdir(exist_ok=True)
        runuser_stub = stub / "runuser"
        runuser_stub.write_text(
            "#!/usr/bin/env bash\n"
            "args=()\n"
            "seen_sep=0\n"
            "skip_next=0\n"
            "for arg in \"$@\"; do\n"
            "  if [[ $seen_sep -eq 1 ]]; then args+=(\"$arg\"); continue; fi\n"
            "  if [[ $skip_next -eq 1 ]]; then skip_next=0; continue; fi\n"
            "  case \"$arg\" in\n"
            "    --) seen_sep=1 ;;\n"
            "    -u) skip_next=1 ;;\n"
            "  esac\n"
            "done\n"
            "cmd=\"${args[0]}\"\n"
            "target=\"${args[-1]}\"\n"
            "if [[ \"$cmd\" == \"test\" ]]; then\n"
            "  dir=\"$(dirname \"$target\")\"\n"
            "  while [[ \"$dir\" != \"/\" && -n \"$dir\" ]]; do\n"
            "    mode=\"$(stat -c '%a' \"$dir\")\"\n"
            "    if (( 0${mode} & 1 == 0 )); then exit 1; fi\n"
            "    dir=\"$(dirname \"$dir\")\"\n"
            "  done\n"
            "  mode=\"$(stat -c '%a' \"$target\" 2>/dev/null || echo 0)\"\n"
            "  if (( 0${mode} & 4 == 0 )); then exit 1; fi\n"
            "  exit 0\n"
            "fi\n"
            "exec \"${args[@]}\"\n"
        )
        os.chmod(runuser_stub, 0o755)

        env = dict(os.environ, APP_USER="nobody", PATH=f"{stub}:{os.environ['PATH']}")
        result = subprocess.run(["bash", str(script)], env=env, capture_output=True, text=True)
        check(
            "the setup script copies the certificate while the way is open",
            result.returncode == 0,
            (result.stdout + result.stderr).strip()[-800:],
        )

        chain = tls_dir / "fullchain.pem"
        key = tls_dir / "privkey.pem"
        check("the chain was written", chain.is_file())
        check("the private key was written", key.is_file())

        # 4. The original permissions are back.
        dir_mode = oct(private.stat().st_mode & 0o777)
        file_mode = oct(cert_path.stat().st_mode & 0o777)
        check("the directory mode was restored", dir_mode == "0o700", dir_mode)
        check("the file mode was restored", file_mode == "0o600", file_mode)

        # 5. The neighbour's file is untouched apart from the permission bits.
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
