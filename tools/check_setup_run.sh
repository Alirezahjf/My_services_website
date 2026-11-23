#!/usr/bin/env bash
# Simulate the production setup on this machine, without root and without
# touching the ports that belong to the other applications.
#
# The script copies the project into a scratch directory, points the setup
# script at it, and stubs out the commands that need root. The result is a
# real Gunicorn process serving the site over TLS with the shared certificate.
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
SANDBOX="${SANDBOX:-/tmp/runup-setup-sim}"
STUB_BIN="$SANDBOX/bin"
TLS_PORT="${TLS_PORT:-9445}"
HTTP_PORT="${HTTP_PORT:-10445}"
CERT_PATH="${CERT_PATH:-}"

log() { printf '\n\033[1;36m[sim]\033[0m %s\n' "$*"; }
die() { printf '\n\033[1;31m[sim] خطا:\033[0m %s\n' "$*" >&2; exit 1; }

command -v runuser >/dev/null 2>&1 && HAVE_RUNUSER=1 || HAVE_RUNUSER=0

log "آماده‌سازی محیط شبیه‌سازی در $SANDBOX"
# Stop anything an earlier run of this simulation left behind. Only processes
# whose command line mentions the sandbox are touched.
for proc_dir in /proc/[0-9]*; do
  pid="${proc_dir#/proc/}"
  cmdline="$(tr '\0' ' ' < "$proc_dir/cmdline" 2>/dev/null || true)"
  [[ "$cmdline" == *"$SANDBOX"* ]] || continue
  kill "$pid" 2>/dev/null || true
done
sleep 2
rm -rf "$SANDBOX"
mkdir -p "$STUB_BIN" "$SANDBOX/project" "$SANDBOX/neighbour/data/tls" "$SANDBOX/systemd"

# A neighbour application with a certificate for the test address.
cp -r "$ROOT/." "$SANDBOX/project/"
rm -rf "$SANDBOX/project/.git" "$SANDBOX/project/.venv"

# The simulation needs a git checkout, because the setup script updates the
# code from the repository before it does anything else.
cd "$SANDBOX/project"
git init -q .
git config user.email "simulation@example.com"
git config user.name "Simulation"
git add -A >/dev/null 2>&1 || true
git commit -qm "simulation snapshot" >/dev/null 2>&1 || true
# A remote that points at the simulation itself, so the update step works.
git remote remove origin >/dev/null 2>&1 || true
git remote add origin "$SANDBOX/project"
cd "$ROOT"

"$ROOT/.venv/bin/python" - "$SANDBOX/neighbour/data/tls/trusted.pem" <<'PY'
import datetime, ipaddress, os, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

path = sys.argv[1]
ip = "203.0.113.55"
now = datetime.datetime.now(datetime.timezone.utc)
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName(
            [x509.IPAddress(ipaddress.ip_address(ip))]), critical=False)
        .sign(key, hashes.SHA256()))
open(path, "w").write(
    key.private_bytes(serialization.Encoding.PEM,
                      serialization.PrivateFormat.TraditionalOpenSSL,
                      serialization.NoEncryption()).decode()
    + cert.public_bytes(serialization.Encoding.PEM).decode())
os.chmod(path, 0o644)
print("neighbour certificate written")
PY

# The environment file of the simulated project.
cat > "$SANDBOX/project/.env" <<ENV
SECRET_KEY=simulation-secret-key-0123456789
FLASK_ENV=production
SITE_URL=http://203.0.113.55:${TLS_PORT}
PUBLIC_ORIGIN=https://203.0.113.55:${TLS_PORT}
HOST=0.0.0.0
PORT=${HTTP_PORT}
HTTPS_PUBLIC_PORT=${TLS_PORT}
HTTP_PUBLIC_PORT=${HTTP_PORT}
MCP_PORT=9944
COOKIE_SECURE=true
ENFORCE_HTTPS=false
TRUST_PROXY_HEADERS=false
DATABASE_URL=sqlite:///${SANDBOX}/project/instance/services.sqlite3
RATELIMIT_STORAGE_URI=memory://
UPLOAD_FOLDER=${SANDBOX}/project/instance/uploads
LOG_LEVEL=INFO
ENV

# Stubs for the commands that need root.
cat > "$STUB_BIN/runuser" <<'STUB'
#!/usr/bin/env bash
# Run the rest of the arguments as the current user.
# Accepts both "runuser -u USER -- cmd" and "runuser USER -- cmd".
args=()
seen_sep=0
skip_next=0
for arg in "$@"; do
  if [[ $seen_sep -eq 1 ]]; then
    args+=("$arg")
    continue
  fi
  if [[ $skip_next -eq 1 ]]; then
    skip_next=0
    continue
  fi
  case "$arg" in
    --) seen_sep=1 ;;
    -u) skip_next=1 ;;
    -*) ;;
    *) ;;
  esac
done
exec "${args[@]}"
STUB
cat > "$STUB_BIN/systemctl" <<'STUB'
#!/usr/bin/env bash
# In the simulation "systemctl restart <unit>" runs the unit's ExecStartPre
# lines and then starts the ExecStart line as a background process; every
# other call succeeds.
#
# The ExecStartPre lines are run for real. A command that is not valid —
# a shell operator inside "python -c", for example — must fail here the
# way it would fail on the server.
#
# The environment of the unit is applied to the commands it runs, the way
# systemd applies it. The helper commands of this stub keep their own
# path, because the unit narrows it to the virtual environment.
action="${1:-}"
shift || true
if [[ "$action" == "restart" || "$action" == "start" ]]; then
  for unit in "$@"; do
    unit="${unit//.service/}"
    file="${SYSTEMD_DIR:-/etc/systemd/system}/${unit}.service"
    [[ -f "$file" ]] || continue
    stub_path="$PATH"
    # The unit uses shell variables; expand them in this shell.
    ( set -a; [[ -f "$APP_DIR/.env" ]] && . "$APP_DIR/.env"; set +a
      cd "$APP_DIR"
      unit_env=()
      while read -r env_line; do
        env_line="${env_line#Environment=}"
        [[ -n "$env_line" ]] || continue
        env_name="${env_line%%=*}"
        env_value="${env_line#*=}"
        [[ -n "$env_name" ]] || continue
        unit_env+=("$env_name=$env_value")
      done < <(grep '^Environment=' "$file")
      while read -r pre_line; do
        pre_line="${pre_line#ExecStartPre=}"
        [[ -n "$pre_line" ]] || continue
        if ! env "${unit_env[@]}" PATH="$stub_path" \
             bash -c "$pre_line" >>"$SANDBOX/${unit}.pre.log" 2>&1; then
          echo "ExecStartPre failed for ${unit}: $pre_line" >&2
          cat "$SANDBOX/${unit}.pre.log" >&2
          exit 1
        fi
      done < <(grep '^ExecStartPre=' "$file")
      exec_line="$(grep -m1 '^ExecStart=' "$file" | sed 's/^ExecStart=//')"
      [[ -n "$exec_line" ]] || continue
      nohup env "${unit_env[@]}" PATH="$stub_path" \
        bash -c "$exec_line" >"$SANDBOX/${unit}.log" 2>&1 &
      echo $! > "$SANDBOX/${unit}.pid" )
  done
fi
exit 0
STUB
cat > "$STUB_BIN/chown" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
cat > "$STUB_BIN/chmod" <<'STUB'
#!/usr/bin/env bash
exit 0
STUB
chmod +x "$STUB_BIN"/*

# The systemd unit names are relative to SYSTEMD_DIR.
# The setup script insists on running as root; the simulation overrides that.
cp "$ROOT/scripts/setup_runup.sh" "$SANDBOX/setup_runup.sh"
python3 - "$SANDBOX/setup_runup.sh" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text()
text = text.replace(
    'if [[ ${EUID} -ne 0 ]]; then\n  die "این دستور باید با sudo یا به‌عنوان root اجرا شود."\nfi',
    'if [[ ${EUID} -ne 0 && "${RUNUP_SIMULATE:-0}" != "1" ]]; then\n  die "این دستور باید با sudo یا به‌عنوان root اجرا شود."\nfi')
# The systemd units are written to /etc; the simulation writes them locally.
text = text.replace('"/etc/systemd/system/${WEB_SERVICE}.service"',
                    '"${SYSTEMD_DIR:-/etc/systemd/system}/${WEB_SERVICE}.service"')
text = text.replace('"/etc/systemd/system/${MCP_SERVICE}.service"',
                    '"${SYSTEMD_DIR:-/etc/systemd/system}/${MCP_SERVICE}.service"')
text = text.replace('"/etc/systemd/system/${TLS_SERVICE}.service"',
                    '"${SYSTEMD_DIR:-/etc/systemd/system}/${TLS_SERVICE}.service"')
text = text.replace('"/etc/systemd/system/runup-cert-refresh.service"',
                    '"${SYSTEMD_DIR:-/etc/systemd/system}/runup-cert-refresh.service"')
text = text.replace('"/etc/systemd/system/runup-cert-refresh.timer"',
                    '"${SYSTEMD_DIR:-/etc/systemd/system}/runup-cert-refresh.timer"')
path.write_text(text)
print("setup script patched for simulation")
PY

log "اجرای اسکریپت راه‌اندازی"
export PATH="$STUB_BIN:$PATH"
export SANDBOX="$SANDBOX"
export RUNUP_SIMULATE=1
export APP_DIR="$SANDBOX/project"
export APP_USER="$(id -un)"
export BRANCH=""
export SYSTEMD_DIR="$SANDBOX/systemd"
export CERT_PATH="$SANDBOX/neighbour/data/tls/trusted.pem"
export PUBLIC_IP="203.0.113.55"
export PREFERRED_TLS_PORT="$TLS_PORT"
export LEGACY_HTTP_PORT="$HTTP_PORT"
export TLS_SERVICE="runup-tls-sim"
export MCP_SERVICE="runup-mcp-sim"
export WEB_SERVICE="runup-web-sim"
export REPO="$ROOT"

# The update is run twice in a row, the way the operator does it.
for run in 1 2; do
  log "اجرای ${run} از اسکریپت راه‌اندازی"
  bash "$SANDBOX/setup_runup.sh" 2>&1 | tail -30 || die "اسکریپت راه‌اندازی در اجرای ${run} شکست خورد."
done

log "بررسی نتیجه"
CHOSEN_TLS_PORT="$(sed -n 's/^HTTPS_PUBLIC_PORT=//p' "$SANDBOX/project/.env" | tail -n1)"
CHOSEN_HTTP_PORT="$(sed -n 's/^HTTP_PUBLIC_PORT=//p' "$SANDBOX/project/.env" | tail -n1)"
log "درگاه‌های انتخاب‌شده: TLS=$CHOSEN_TLS_PORT HTTP=$CHOSEN_HTTP_PORT"

[[ -s "$SANDBOX/project/instance/tls/fullchain.pem" ]] || die "زنجیره گواهی ساخته نشد."
[[ -s "$SANDBOX/project/instance/tls/privkey.pem" ]] || die "کلید خصوصی ساخته نشد."
grep -q "^TLS_CERT_PATH=" "$SANDBOX/project/.env" || die "مسیر گواهی در .env ثبت نشد."
grep -q "^PUBLIC_ORIGIN=https://203.0.113.55:${CHOSEN_TLS_PORT}$" "$SANDBOX/project/.env" || die "نشانی امن در .env ثبت نشد."

# The TLS instance carries the certificate and listens on the TLS port.
grep -q -- "--certfile" "$SANDBOX/systemd/${TLS_SERVICE}.service" || die "Gunicorn با گواهی راه‌اندازی نشد."
grep -q -- "--bind 0.0.0.0:${CHOSEN_TLS_PORT}" "$SANDBOX/systemd/${TLS_SERVICE}.service" || die "درگاه TLS در سرویس نیست."

# The plain-HTTP instance must not carry a certificate: Gunicorn would then
# speak TLS on that port too.
grep -q -- "--certfile" "$SANDBOX/systemd/${WEB_SERVICE}.service" && die "سرویس HTTP نباید گواهی داشته باشد."
grep -q -- "--bind 0.0.0.0:${CHOSEN_HTTP_PORT}" "$SANDBOX/systemd/${WEB_SERVICE}.service" || die "درگاه HTTP در سرویس نیست."

# No unit may take a port that belongs to another application.
for port in 80 443 8080 8443 9443 9444; do
  for unit_file in "$SANDBOX/systemd"/*.service; do
    if grep -q -- "--bind 0.0.0.0:${port}" "$unit_file"; then
      die "سرویس درگاه $port همسایه را گرفته است."
    fi
  done
done

# Both instances must actually answer.
HTTP_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 "http://127.0.0.1:${CHOSEN_HTTP_PORT}/" || echo 000)"
[[ "$HTTP_CODE" == "200" ]] || die "پاسخ HTTP روی درگاه ${CHOSEN_HTTP_PORT} برابر ${HTTP_CODE} بود."
TLS_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 --insecure "https://127.0.0.1:${CHOSEN_TLS_PORT}/" || echo 000)"
[[ "$TLS_CODE" == "200" ]] || die "پاسخ HTTPS روی درگاه ${CHOSEN_TLS_PORT} برابر ${TLS_CODE} بود."

# The certificate the site serves must be the one of the neighbour.
SERVED="$(echo | openssl s_client -connect "127.0.0.1:${CHOSEN_TLS_PORT}" -servername 203.0.113.55 2>/dev/null | openssl x509 -noout -fingerprint 2>/dev/null || true)"
EXPECTED="$(openssl x509 -in "$SANDBOX/neighbour/data/tls/trusted.pem" -noout -fingerprint 2>/dev/null || true)"
[[ -n "$SERVED" && "$SERVED" == "$EXPECTED" ]] || die "گواهی ارائه‌شده با گواهی همسایه یکی نیست."

# ---------------------------------------------------------------------------
# The same run with a neighbour whose certificate sits behind a closed
# directory, the way it does on the real server under /root.
# ---------------------------------------------------------------------------
log "اجرای دوباره با گواهی همسایه پشت پوشه بسته"
CLOSED="$SANDBOX/closed"
mkdir -p "$CLOSED/data/tls"
cp "$SANDBOX/neighbour/data/tls/trusted.pem" "$CLOSED/data/tls/trusted.pem"
chmod 0700 "$CLOSED"
chmod 0600 "$CLOSED/data/tls/trusted.pem"

rm -rf "$SANDBOX/project/instance/tls"
export CERT_PATH="$CLOSED/data/tls/trusted.pem"
bash "$SANDBOX/setup_runup.sh" 2>&1 | tail -30 || die "اسکریپت راه‌اندازی با گواهی بسته شکست خورد."

[[ -s "$SANDBOX/project/instance/tls/fullchain.pem" ]] || die "زنجیره گواهی بسته ساخته نشد."
[[ -s "$SANDBOX/project/instance/tls/privkey.pem" ]] || die "کلید خصوصی گواهی بسته ساخته نشد."

# The setup script must not change anything in the neighbour's project.
# The only chmod calls it makes belong to the project's own directories.
grep -nE "chmod .*\\\$\{?CERT|chmod .*neighbour|chmod .*cert_file" "$SANDBOX/setup_runup.sh" \
  && die "اسکریپت مجوز فایل همسایه را تغییر می‌دهد."
# Every chmod in the script must point at the project's own directory.
while read -r chmod_line; do
  case "$chmod_line" in
    *'instance/tls'*|*'instance"'*|*'backups'*|*'.env'*) ;;
    *) die "اسکریپت مجوز جای دیگری را تغییر می‌دهد: $chmod_line" ;;
  esac
done < <(grep -E "^\s*chmod " "$SANDBOX/setup_runup.sh")

# And the site still serves HTTPS with that certificate.
CLOSED_CODE="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 --insecure "https://127.0.0.1:${CHOSEN_TLS_PORT}/" || echo 000)"
[[ "$CLOSED_CODE" == "200" ]] || die "پاسخ HTTPS با گواهی بسته برابر ${CLOSED_CODE} بود."

CLOSED_SERVED="$(echo | openssl s_client -connect "127.0.0.1:${CHOSEN_TLS_PORT}" -servername 203.0.113.55 2>/dev/null | openssl x509 -noout -fingerprint 2>/dev/null || true)"
[[ -n "$CLOSED_SERVED" && "$CLOSED_SERVED" == "$EXPECTED" ]] || die "گواهی ارائه‌شده با گواهی بسته همسایه یکی نیست."

# ---------------------------------------------------------------------------
# The same run with a certificate for another address lying inside this
# project, the way it happened on the real server.
# ---------------------------------------------------------------------------
log "اجرای دوباره با گواهی نادرست داخل پروژه خودمان"
"$ROOT/.venv/bin/python" - "$SANDBOX/project/cert.pem" <<'PY'
import datetime, ipaddress, sys
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

path = sys.argv[1]
ip = "127.0.0.1"
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, ip)])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip))]), critical=False)
        .sign(key, hashes.SHA256()))
with open(path, "wb") as handle:
    handle.write(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption()))
    handle.write(cert.public_bytes(serialization.Encoding.PEM))
print("foreign certificate written")
PY

rm -rf "$SANDBOX/project/instance/tls"
# The neighbour is found the way the server finds it: through its own
# project. The certificate that lies inside this project must not win.
export CERT_PATH="$SANDBOX/neighbour/data/tls/trusted.pem"
bash "$SANDBOX/setup_runup.sh" 2>&1 | tail -30 || die "اسکریپت راه‌اندازی با گواهی نادرست شکست خورد."

[[ -s "$SANDBOX/project/instance/tls/fullchain.pem" ]] || die "زنجیره گواهی همسایه ساخته نشد."
FOREIGN_SERVED="$(echo | openssl s_client -connect "127.0.0.1:${CHOSEN_TLS_PORT}" -servername 203.0.113.55 2>/dev/null | openssl x509 -noout -fingerprint 2>/dev/null || true)"
[[ -n "$FOREIGN_SERVED" && "$FOREIGN_SERVED" == "$EXPECTED" ]] \
  || die "گواهی نادرست داخل پروژه به‌جای گواهی همسایه ارائه شد."

log "همه بررسی‌ها موفق بود."
