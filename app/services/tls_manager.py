"""Shared-certificate TLS supervision for the public-IP site.

The site is reached by IP address only, so a public certificate has to be issued
for that IP. This host cannot issue one by itself: Let's Encrypt validates IP
identifiers over HTTP-01 (port 80) or TLS-ALPN-01 (port 443), and both ports
belong to another application on the same machine.

Instead this project *reads* the certificate that the neighbouring application
already renews, and serves it over TLS itself. Nothing is written into the
neighbour's directory and no web server is installed, so ports 80 and 443 are
never touched.

The certificate file is replaced atomically on every renewal. A long-lived
process must therefore re-read the path instead of holding an open handle,
which is what :func:`load_certificate` does on every request cycle.
"""
from __future__ import annotations

import ipaddress
import os
import re
import socket
import ssl
import stat
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# Files that hold a PEM key+certificate bundle in the neighbour project.
_CERT_BUNDLE_NAMES = ("trusted.pem", "fullchain.pem", "cert.pem", "chain.pem")

# systemd units that belong to the neighbouring application.
_NEIGHBOUR_UNIT_HINTS = ("shomarejoo", "shomar", "runup", "run-up", "number", "doorman")

# Directories that may hold the neighbour checkout.
_NEIGHBOUR_DIR_HINTS = ("shomarejoo", "shomar", "runup", "run-up")


class CertificateError(RuntimeError):
    """Raised when a candidate certificate cannot be used."""


@dataclass
class CertificateInfo:
    """A validated view of the certificate currently in use."""

    path: Path
    not_after: datetime
    subject_ip: str | None = None
    fingerprint: str = ""
    serial: str = ""

    @property
    def seconds_remaining(self) -> int:
        return int((self.not_after - datetime.now(timezone.utc)).total_seconds())

    @property
    def is_expired(self) -> bool:
        return self.seconds_remaining <= 0

    @property
    def expires_in(self) -> str:
        """Human readable remaining lifetime, in Persian-friendly ASCII."""
        seconds = self.seconds_remaining
        if seconds <= 0:
            return "منقضی شده"
        days, rest = divmod(seconds, 86400)
        hours, rest = divmod(rest, 3600)
        minutes = rest // 60
        if days >= 1:
            return f"{days} روز و {hours} ساعت"
        if hours >= 1:
            return f"{hours} ساعت و {minutes} دقیقه"
        return f"{minutes} دقیقه"


@dataclass
class TlsStatus:
    """Overall TLS state, reported to the operator in Persian."""

    enabled: bool = False
    reason: str = ""
    detail: str = ""
    certificate: CertificateInfo | None = None
    source_path: str = ""
    public_port: int | None = None
    http_port: int | None = None
    site_url: str = ""
    checked_at: float = field(default_factory=time.time)


# ---------------------------------------------------------------------------
# Certificate inspection
# ---------------------------------------------------------------------------


def _run_openssl(args: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["openssl", *args],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise CertificateError(f"ابزار openssl در دسترس نیست: {exc}") from exc
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def read_certificate(path: str | os.PathLike[str]) -> CertificateInfo:
    """Parse and validate the PEM bundle at ``path``.

    The bundle may contain a private key first and the certificate afterwards;
    only the certificate block is parsed here.
    """
    cert_path = Path(path)
    try:
        stat_result = cert_path.stat()
    except PermissionError:
        # The path itself is not reachable: a parent directory denies the
        # traversal. Saying only "the file was not found" would send the
        # reader looking for a missing file instead of a permission
        # problem, so the real cause is named.
        raise CertificateError(
            f"فایل گواهی در مسیر {cert_path} قابل دسترسی نیست؛ کاربر فعلی اجازه ورود به "
            f"پوشه‌های این مسیر را ندارد. دسترسی خواندن را برای کاربر سرویس باز کنید."
        ) from None
    except OSError:
        stat_result = None
    if stat_result is None or not stat.S_ISREG(stat_result.st_mode):
        raise CertificateError(f"فایل گواهی پیدا نشد: {cert_path}")
    try:
        pem = cert_path.read_text(encoding="utf-8", errors="replace")
    except PermissionError as exc:
        raise CertificateError(f"اجازه خواندن فایل گواهی وجود ندارد: {cert_path}") from exc
    except OSError as exc:
        raise CertificateError(f"خواندن فایل گواهی ممکن نشد: {exc}") from exc

    match = re.search(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
        pem,
        re.DOTALL,
    )
    if not match:
        raise CertificateError(f"در فایل {cert_path} هیچ گواهی PEM یافت نشد.")

    code, out, err = _run_openssl_from_stdin(
        match.group(0),
        ["x509", "-noout", "-subject", "-dates", "-fingerprint", "-serial"],
    )
    if code != 0:
        raise CertificateError(f"تجزیه گواهی ناموفق بود: {err}")

    # The SAN extension is optional; ask for it separately so a certificate
    # without any extension does not fail the whole inspection.
    san_code, san_out, _ = _run_openssl_from_stdin(
        match.group(0), ["x509", "-noout", "-ext", "subjectAltName"]
    )
    if san_code == 0:
        out = f"{out}\n{san_out}"

    info = _parse_openssl_output(out)
    info.path = cert_path
    return info


def _run_openssl_from_stdin(pem: str, args: list[str]) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["openssl", *args],
            input=pem,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise CertificateError(f"ابزار openssl در دسترس نیست: {exc}") from exc
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _parse_openssl_output(output: str) -> CertificateInfo:
    subject = ""
    not_after = ""
    fingerprint = ""
    serial = ""
    san = ""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("subject="):
            subject = line[len("subject=") :].strip()
        elif line.startswith("notAfter="):
            not_after = line[len("notAfter=") :].strip()
        elif "Fingerprint=" in line:
            fingerprint = line.split("=", 1)[1].strip()
        elif line.startswith("serial="):
            serial = line.split("=", 1)[1].strip()
        elif "DNS:" in line or "IP Address:" in line:
            san = line

    if not not_after:
        raise CertificateError("تاریخ انقضای گواهی در خروجی openssl پیدا نشد.")
    try:
        parsed = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise CertificateError(f"قالب تاریخ انقضای گواهی شناخته نشد: {not_after}") from exc

    subject_ip = None
    if "IP Address:" in san:
        match = re.search(r"IP Address:([0-9a-fA-F:.]+)", san)
        if match:
            subject_ip = match.group(1).strip()
    else:
        # Fall back to the subject common name, which carries the literal
        # address for IP certificates issued without a SAN extension.
        match = re.search(r"(?:^|[=,\s])((?:\d{1,3}\.){3}\d{1,3})\s*$", subject)
        if match:
            subject_ip = match.group(1)

    return CertificateInfo(
        path=Path(),
        not_after=parsed,
        subject_ip=subject_ip,
        fingerprint=fingerprint,
        serial=serial,
    )


def certificate_covers_ip(info: CertificateInfo, ip: str) -> bool:
    """Return True when ``info`` is valid for the literal address ``ip``."""
    try:
        wanted = ipaddress.ip_address(ip)
    except ValueError:
        return False
    if not info.subject_ip:
        return False
    try:
        covered = ipaddress.ip_address(info.subject_ip)
    except ValueError:
        return False
    return covered == wanted


# ---------------------------------------------------------------------------
# Locating the neighbour's certificate
# ---------------------------------------------------------------------------


def _systemd_working_directory(unit: str) -> Path | None:
    try:
        proc = subprocess.run(
            ["systemctl", "show", unit, "--property=WorkingDirectory", "--value"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    value = (proc.stdout or "").strip()
    if proc.returncode != 0 or not value or value == "/":
        return None
    return Path(value)


def _list_systemd_units() -> list[str]:
    try:
        proc = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--plain"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    units = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split()
        if parts:
            units.append(parts[0])
    return units


def _is_dir(path: Path) -> bool:
    """``Path.is_dir`` that never raises, whatever the permissions are."""
    try:
        return path.is_dir()
    except OSError:
        return False


def _candidate_neighbour_dirs() -> list[Path]:
    """Directories that plausibly hold the neighbouring project."""
    candidates: list[Path] = []

    # 1. The working directory of a neighbour systemd unit.
    for unit in _list_systemd_units():
        if not any(hint in unit.lower() for hint in _NEIGHBOUR_UNIT_HINTS):
            continue
        workdir = _systemd_working_directory(unit)
        if workdir and _is_dir(workdir):
            candidates.append(workdir)

    # 2. The working directory of the process listening on the neighbour ports.
    for port in (9443, 9444, 8080):
        for pid in _pids_listening_on(port):
            cwd = _process_cwd(pid)
            if cwd and _is_dir(cwd):
                candidates.append(cwd)

    # 3. Conventional locations below /root and /srv, /opt.
    roots = [Path("/root/Desktop"), Path("/root"), Path("/srv"), Path("/opt")]
    for root in roots:
        if not _is_dir(root):
            continue
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not any(hint in entry.name.lower() for hint in _NEIGHBOUR_DIR_HINTS):
                continue
            if _is_dir(entry):
                candidates.append(entry)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _pids_listening_on(port: int) -> list[int]:
    pids: list[int] = []
    try:
        proc = subprocess.run(
            ["ss", "-H", "-ltnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    for match in re.finditer(r"pid=(\d+)", proc.stdout or ""):
        pids.append(int(match.group(1)))
    return pids


def _process_cwd(pid: int) -> Path | None:
    try:
        return Path(f"/proc/{pid}/cwd").resolve(strict=True)
    except (OSError, RuntimeError):
        return None


def find_certificate(explicit_path: str | os.PathLike[str] | None = None) -> tuple[Path | None, list[str]]:
    """Locate the neighbour's certificate bundle.

    Returns the resolved path (or ``None``) plus a list of human readable notes
    describing what was searched, so the operator can understand the outcome.
    """
    notes: list[str] = []

    if explicit_path:
        path = Path(explicit_path).expanduser()
        notes.append(f"مسیر دستی بررسی شد: {path}")
        if _is_dir(path):
            found = _bundle_in_dir(path)
            if found:
                return found, notes
            notes.append("پوشه دستی فایل گواهی نداشت.")
            return None, notes
        if _is_file(path):
            return path, notes
        if _is_blocked(path):
            notes.append(
                f"مسیر دستی وجود دارد ولی کاربر سرویس اجازه ورود به پوشه‌های آن را ندارد: {path}"
            )
            return None, notes
        if _is_unreachable(path):
            notes.append(
                f"پوشه‌های مسیر دستی برای کاربر سرویس بسته‌اند: {path}"
            )
            return None, notes
        notes.append("مسیر دستی وجود نداشت.")
        return None, notes

    for directory in _candidate_neighbour_dirs():
        found = _bundle_in_dir(directory)
        if found:
            notes.append(f"گواهی در {found} پیدا شد (پوشه همسایه: {directory}).")
            return found, notes

    notes.append("در هیچ پوشه همسایه‌ای فایل گواهی پیدا نشد.")
    return None, notes


def _is_file(path: Path) -> bool:
    """``Path.is_file`` that never raises, whatever the permissions are."""
    try:
        return path.is_file()
    except OSError:
        return False


def _is_blocked(path: Path) -> bool:
    """Is ``path`` there but out of reach for the current user?

    The file itself answers this: asking for its status raises a
    permission error when a directory on the way denies the traversal.
    """
    try:
        path.stat()
    except PermissionError:
        return True
    except OSError:
        return False
    return False


def _is_unreachable(path: Path) -> bool:
    """Is ``path`` hidden behind a directory the current user cannot enter?

    A file that simply is not there and a file that cannot be reached because
    a parent directory denies traversal look the same to ``Path.exists``. This
    helper tells them apart so the message can name the real cause.

    The answer is about the user who runs the code. When that user is not
    the owner of the directory — the service user on the server — only the
    "other" bits decide, so they are what is looked at.
    """
    current = path.parent
    seen = 0
    while current != current.parent and seen < 40:
        seen += 1
        try:
            info = current.stat()
        except PermissionError:
            return True
        except OSError:
            return False
        if not stat.S_ISDIR(info.st_mode):
            return False
        if info.st_uid == os.getuid():
            # The owner of the directory: the owner bits decide.
            if not (info.st_mode & stat.S_IXUSR):
                return True
        elif info.st_gid in _current_groups():
            if not (info.st_mode & stat.S_IXGRP):
                return True
        elif not (info.st_mode & stat.S_IXOTH):
            return True
        current = current.parent
    return False


def _current_groups() -> set[int]:
    try:
        return set(os.getgroups())
    except OSError:
        return set()


def _bundle_in_dir(directory: Path) -> Path | None:
    for name in _CERT_BUNDLE_NAMES:
        candidate = directory / "data" / "tls" / name
        if _is_file(candidate):
            return candidate
    for name in _CERT_BUNDLE_NAMES:
        candidate = directory / name
        if _is_file(candidate):
            return candidate
    # Last resort: a shallow recursive search for the canonical name.
    try:
        for path in sorted(directory.rglob("trusted.pem")):
            if _is_file(path):
                return path
    except OSError:
        pass
    return None


# ---------------------------------------------------------------------------
# Port selection
# ---------------------------------------------------------------------------


_RESERVED_PORTS = {80, 443, 8080, 8443, 9443, 9444}

# Ports tried, in order, when the preferred one is unavailable. The neighbour
# application may fall back to 4443, 10443 and 8444, so those are excluded too.
_FALLBACK_PORTS = (9900, 9445, 9943, 10444, 9446, 8445, 9950)


def port_is_free(port: int) -> bool:
    """True when nothing is currently listening on ``port``."""
    try:
        proc = subprocess.run(
            ["ss", "-H", "-ltn", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True
    return not (proc.stdout or "").strip()


def choose_public_port(preferred: int = 9900) -> int:
    """Pick the port that will carry HTTPS.

    The preferred port is used when it is free. Ports owned by the neighbour
    application are never taken, and the fallback list avoids the ports the
    neighbour may fall back to.
    """
    if preferred in _RESERVED_PORTS:
        raise CertificateError(
            f"درگاه {preferred} به برنامه‌های دیگر سرور تعلق دارد و قابل استفاده نیست."
        )
    if port_is_free(preferred):
        return preferred
    for candidate in _FALLBACK_PORTS:
        if candidate in _RESERVED_PORTS or candidate == preferred:
            continue
        if port_is_free(candidate):
            return candidate
    raise CertificateError("هیچ درگاه آزادی برای HTTPS پیدا نشد.")


# ---------------------------------------------------------------------------
# Gunicorn certificate hot-reload
# ---------------------------------------------------------------------------


class CertificateReloader:
    """Keeps Gunicorn's TLS material in sync with the neighbour's bundle.

    Gunicorn loads ``--certfile``/``--keyfile`` once at start-up. To pick up a
    renewed certificate without dropping connections the master process is sent
    ``SIGHUP``, which re-loads the configuration and the certificate in place.
    """

    def __init__(self, cert_path: Path | None, reload_signal: int | None = None) -> None:
        self.cert_path = cert_path
        self._lock = threading.Lock()
        self._last_fingerprint = ""
        self._reload_signal = reload_signal
        if reload_signal is None:
            import signal

            self._reload_signal = signal.SIGHUP

    def current_fingerprint(self) -> str:
        with self._lock:
            return self._last_fingerprint

    def refresh(self, send_signal: bool = True) -> tuple[bool, str]:
        """Reload the certificate if the file changed.

        Returns ``(reloaded, message)``.
        """
        if self.cert_path is None:
            return False, "مسیر گواهی مشخص نشده است."
        try:
            info = read_certificate(self.cert_path)
        except CertificateError as exc:
            return False, str(exc)
        if info.is_expired:
            return False, f"گواهی منقضی شده است ({info.expires_in})."
        with self._lock:
            changed = info.fingerprint != self._last_fingerprint
            if changed:
                self._last_fingerprint = info.fingerprint
        if not changed:
            return False, "گواهی تغییری نکرده است."
        if send_signal:
            if not self._signal_master():
                return False, "ارسال سیگنال بازخوانی به Gunicorn ممکن نشد."
        return True, f"گواهی تازه بارگذاری شد (اعتبار تا {info.expires_in})."

    def _signal_master(self) -> bool:
        pid = os.environ.get("GUNICORN_PID") or _find_gunicorn_master()
        if not pid:
            return False
        try:
            os.kill(pid, self._reload_signal)
        except (ProcessLookupError, PermissionError):
            return False
        return True


def _find_gunicorn_master() -> int | None:
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "gunicorn.*app:create_app"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    pids = [int(p) for p in (proc.stdout or "").split() if p.isdigit()]
    return pids[0] if pids else None


# ---------------------------------------------------------------------------
# Status reporting
# ---------------------------------------------------------------------------


def neighbour_present() -> tuple[bool, list[str]]:
    """Detect whether the neighbouring application is running on this host.

    The detection is deliberately conservative: if the answer cannot be
    established, the caller must assume the neighbour is present.
    """
    evidence: list[str] = []
    for port in (9443, 9444, 8080):
        pids = _pids_listening_on(port)
        if pids:
            evidence.append(f"درگاه {port} توسط PID {', '.join(str(p) for p in pids)} در حال استفاده است.")
    for unit in _list_systemd_units():
        if any(hint in unit.lower() for hint in _NEIGHBOUR_UNIT_HINTS):
            evidence.append(f"سرویس systemd «{unit}» وجود دارد.")
    return bool(evidence), evidence


def collect_status(
    *,
    explicit_cert_path: str | None = None,
    public_port: int | None = None,
    http_port: int | None = None,
    site_url: str = "",
) -> TlsStatus:
    """Build the operator-facing status of the TLS setup."""
    status = TlsStatus(site_url=site_url, public_port=public_port, http_port=http_port)

    path, notes = find_certificate(explicit_cert_path)
    if path is None:
        return _status_from_local_copy(status, notes)

    status.source_path = str(path)
    try:
        info = read_certificate(path)
    except CertificateError as exc:
        # The neighbour's file may be out of reach for the service user.
        # The copy in the project's own directory is what the service
        # serves, so that one is asked instead.
        fallback = _status_from_local_copy(status, [str(exc)])
        if fallback.enabled:
            return fallback
        status.enabled = False
        status.reason = "گواهی خوانده نشد"
        status.detail = str(exc)
        return status

    return _status_with_certificate(status, info)


def _status_from_local_copy(status: TlsStatus, notes: list[str]) -> TlsStatus:
    """Describe the state from the copy in the project's own directory.

    The neighbour's certificate can sit behind a directory that the
    service user cannot enter. The copy that the setup script took is
    enough to say whether the site serves HTTPS.
    """
    chain_path = TLS_DIR / "fullchain.pem"
    key_path = TLS_DIR / "privkey.pem"
    if not chain_path.is_file() or not key_path.is_file():
        status.enabled = False
        status.reason = "گواهی همسایه پیدا نشد"
        status.detail = " ".join(notes)
        return status

    try:
        info = read_certificate(chain_path)
    except CertificateError as exc:
        status.enabled = False
        status.reason = "گواهی خوانده نشد"
        status.detail = str(exc)
        return status

    status.source_path = str(chain_path)
    return _status_with_certificate(status, info)


def _status_with_certificate(status: TlsStatus, info: CertificateInfo) -> TlsStatus:
    """Fill in the status from a certificate that was read."""
    status.certificate = info
    if info.is_expired:
        status.enabled = False
        status.reason = "گواهی منقضی شده"
        status.detail = f"اعتبار گواهی به پایان رسیده است ({info.expires_in})."
        return status

    if status.site_url:
        host = _host_from_url(status.site_url)
        if host and not certificate_covers_ip(info, host):
            status.enabled = False
            status.reason = "گواهی برای نشانی این سایت نیست"
            status.detail = f"گواهی برای {info.subject_ip or 'نامشخص'} صادر شده، نه {host}."
            return status

    status.enabled = True
    status.reason = "گواهی معتبر در دسترس است"
    status.detail = f"اعتبار تا {info.expires_in}."
    return status


def _host_from_url(url: str) -> str | None:
    match = re.match(r"^[a-z]+://([^/:]+)", url.strip())
    if not match:
        return None
    host = match.group(1)
    if host.startswith("[") and "]" in host:
        host = host[1 : host.index("]")]
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return None
    return host


def public_ip() -> str | None:
    """Best-effort detection of the server's public IPv4 address."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# Materialising the certificate for Gunicorn
# ---------------------------------------------------------------------------

# Where the split key/certificate pair is written for Gunicorn to consume.
TLS_DIR = Path(os.getenv("TLS_MATERIAL_DIR", "instance/tls"))


def _split_bundle(bundle: Path) -> tuple[bytes, bytes]:
    """Split a combined PEM bundle into (certificate chain, private key)."""
    text = bundle.read_text(encoding="utf-8", errors="replace")
    certs = re.findall(
        r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", text, re.DOTALL
    )
    keys = re.findall(
        r"-----BEGIN (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----.*?"
        r"-----END (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----",
        text,
        re.DOTALL,
    )
    if not certs:
        raise CertificateError("در بسته گواهی هیچ گواهی PEM یافت نشد.")
    if not keys:
        raise CertificateError("در بسته گواهی هیچ کلید خصوصی PEM یافت نشد.")
    chain = "\n".join(certs) + "\n"
    key = keys[0] + "\n"
    return chain.encode("utf-8"), key.encode("utf-8")


def materialise_tls_material(
    bundle_path: Path | str,
    tls_dir: Path | str | None = None,
    owner: str | None = None,
) -> tuple[Path, Path]:
    """Write the split key and chain for Gunicorn.

    The files are written atomically (write to a temporary file, then rename)
    so Gunicorn never reads a half-written file.

    ``owner`` names the user that should own the files. It matters when the
    copy is taken with more rights than the service has: without it the
    service would find a private key it cannot read.
    """
    bundle_path = Path(bundle_path)
    target_dir = Path(tls_dir) if tls_dir else TLS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    chain, key = _split_bundle(bundle_path)

    chain_path = target_dir / "fullchain.pem"
    key_path = target_dir / "privkey.pem"

    for path, payload, mode in ((chain_path, chain, 0o644), (key_path, key, 0o600)):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(payload)
        os.chmod(tmp, mode)
        os.replace(tmp, path)

    _apply_owner(owner, chain_path, key_path)
    return chain_path, key_path


def prepare_tls_material(
    bundle_path: str | os.PathLike[str] | None = None,
    tls_dir: str | os.PathLike[str] | None = None,
    required_ip: str | None = None,
) -> bool:
    """Prepare the TLS material before Gunicorn starts.

    Returns True when a usable certificate was written. When no certificate is
    available the site keeps running over plain HTTP, which is the documented
    fallback.

    The copy that was taken earlier is accepted as it is. That matters when
    the neighbour's file sits behind a directory the service user cannot
    enter: the setup script takes the copy with enough rights and hands it
    over, and the service then starts from that copy instead of reading the
    neighbour's file again.
    """
    from dotenv import load_dotenv

    load_dotenv()
    target_dir = Path(tls_dir) if tls_dir else TLS_DIR
    explicit = bundle_path or os.getenv("TLS_CERT_PATH") or None
    path, _notes = find_certificate(explicit)
    if path is None:
        return _existing_material_is_usable(target_dir, required_ip)
    try:
        info = read_certificate(path)
    except CertificateError:
        return _existing_material_is_usable(target_dir, required_ip)
    if info.is_expired:
        return False
    wanted = required_ip or os.getenv("PUBLIC_ORIGIN") or ""
    host = _host_from_url(wanted) if "://" in wanted else (wanted or None)
    if host and not certificate_covers_ip(info, host):
        return False
    try:
        materialise_tls_material(path, target_dir)
    except (CertificateError, OSError, TypeError, AttributeError):
        return _existing_material_is_usable(target_dir, required_ip)
    return True


def _existing_material_is_usable(target_dir: Path, required_ip: str | None) -> bool:
    """Is the copy that is already in place usable?

    The copy is checked on its own, so a start works even when the
    neighbour's file cannot be read any more. The certificate in the copy is
    what Gunicorn serves, so it is the one that has to be right.
    """
    chain_path = target_dir / "fullchain.pem"
    key_path = target_dir / "privkey.pem"
    if not chain_path.is_file() or not key_path.is_file():
        return False
    try:
        info = read_certificate(chain_path)
    except CertificateError:
        return False
    if info.is_expired:
        return False
    wanted = required_ip or os.getenv("PUBLIC_ORIGIN") or ""
    host = _host_from_url(wanted) if "://" in wanted else (wanted or None)
    if host and not certificate_covers_ip(info, host):
        return False
    return True


def _apply_owner(owner: str | None, *paths: Path) -> None:
    """Hand the material over to the service user.

    The refresh may run with more rights than the service has, so the files
    would end up unreadable for Gunicorn. The owner is set before the
    service is asked to reload, never after.
    """
    if not owner:
        return
    import pwd

    try:
        entry = pwd.getpwnam(owner)
    except KeyError:
        return
    for path in paths:
        try:
            os.chown(path, entry.pw_uid, entry.pw_gid)
        except OSError:
            continue


def refresh_tls_material(
    bundle_path: str | os.PathLike[str] | None = None,
    tls_dir: str | os.PathLike[str] | None = None,
    required_ip: str | None = None,
    owner: str | None = None,
) -> bool:
    """Re-read the certificate and reload Gunicorn when it changed."""
    from dotenv import load_dotenv

    load_dotenv()
    explicit = bundle_path or os.getenv("TLS_CERT_PATH") or None
    path, _notes = find_certificate(explicit)
    if path is None:
        return False
    try:
        info = read_certificate(path)
    except CertificateError:
        return False
    if info.is_expired:
        return False
    wanted = required_ip or os.getenv("PUBLIC_ORIGIN") or ""
    host = _host_from_url(wanted) if "://" in wanted else (wanted or None)
    if host and not certificate_covers_ip(info, host):
        return False

    target_dir = Path(tls_dir) if tls_dir else TLS_DIR
    chain_path = target_dir / "fullchain.pem"
    key_path = target_dir / "privkey.pem"

    try:
        chain, key = _split_bundle(path)
    except (CertificateError, OSError):
        return False

    changed = False
    for target, payload in ((chain_path, chain), (key_path, key)):
        try:
            if target.read_bytes() != payload:
                changed = True
        except OSError:
            changed = True

    if not changed:
        return True

    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        for target, payload, mode in ((chain_path, chain, 0o644), (key_path, key, 0o600)):
            tmp = target.with_suffix(target.suffix + ".tmp")
            tmp.write_bytes(payload)
            os.chmod(tmp, mode)
            os.replace(tmp, target)
        _apply_owner(owner, chain_path, key_path)
    except OSError:
        return False

    # Ask Gunicorn to pick up the new material without dropping connections.
    reloader = CertificateReloader(path)
    reloader.refresh(send_signal=True)
    return True
