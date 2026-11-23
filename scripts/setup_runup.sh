#!/usr/bin/env bash
# One-command setup for the RunUp catalogue: code update, HTTPS and reporting.
#
#   sudo bash scripts/setup_runup.sh
#
# What this script does:
#   1. pull the repository and install Python dependencies into the project venv;
#   2. run the database migrations and the idempotent content seed;
#   3. discover the certificate that the neighbouring application renews and
#      serve it over TLS on the public port;
#   4. keep the legacy HTTP listener working so older links keep opening;
#   5. install a small timer that re-reads the certificate after every renewal.
#
# What this script deliberately does NOT do:
#   * it never installs nginx, apache or Caddy;
#   * it never binds, frees or touches TCP port 80 or 443;
#   * it never enables, resets or flushes the firewall;
#   * it never stops a process it did not start.
#
# The certificate is issued by Let's Encrypt for the server's public IP with
# the short-lived profile. That certificate belongs to the neighbouring
# application; this project only reads it.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/hjf-services}"
APP_USER="${APP_USER:-services}"
BRANCH="${BRANCH:-$(git -C "$APP_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)}"
REPO="${REPO:-https://github.com/Alirezahjf/My_services_website.git}"
PUBLIC_IP="${PUBLIC_IP:-}"
CERT_PATH="${CERT_PATH:-}"
PREFERRED_TLS_PORT="${PREFERRED_TLS_PORT:-9900}"
LEGACY_HTTP_PORT="${LEGACY_HTTP_PORT:-19900}"
WEB_SERVICE="${WEB_SERVICE:-hjf-services}"
TLS_SERVICE="${TLS_SERVICE:-hjf-services-tls}"
MCP_SERVICE="${MCP_SERVICE:-hjf-services-mcp}"

log()  { printf '\n\033[1;36m[RunUp]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[RunUp] هشدار:\033[0m %s\n' "$*" >&2; }
die()  { printf '\n\033[1;31m[RunUp] خطا:\033[0m %s\n' "$*" >&2; exit 1; }

if [[ ${EUID} -ne 0 ]]; then
  die "این دستور باید با sudo یا به‌عنوان root اجرا شود."
fi

# ---------------------------------------------------------------------------
# 0. Safety: never take a port that belongs to another application.
# ---------------------------------------------------------------------------

RESERVED_PORTS=(80 443 8080 8443 9443 9444)

port_listeners() {
  ss -H -ltnp "sport = :$1" 2>/dev/null || true
}

# True when the process holding the port is this project's own Gunicorn.
# The check is based on the command line, so it never confuses a neighbour's
# application with this project and never stops a foreign process.
port_belongs_to_this_project() {
  local port="$1" pids cmdline
  pids="$(port_listeners "$port" | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u)"
  [[ -n "$pids" ]] || return 1
  for pid in $pids; do
    cmdline="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
    [[ "$cmdline" == *gunicorn* && "$cmdline" == *"$APP_DIR"* ]] || return 1
  done
  return 0
}

assert_ports_free() {
  local port
  for port in "$@"; do
    [[ "$port" =~ ^[0-9]{1,5}$ ]] || die "شماره درگاه نامعتبر است: $port"
    (( port > 0 && port < 65536 )) || die "شماره درگاه نامعتبر است: $port"
    for reserved in "${RESERVED_PORTS[@]}"; do
      [[ "$port" != "$reserved" ]] || die "درگاه $port به برنامه دیگری روی این سرور تعلق دارد و قابل استفاده نیست."
    done
  done
}

# ---------------------------------------------------------------------------
# 1. Code and dependencies
# ---------------------------------------------------------------------------

[[ -d "$APP_DIR" ]] || die "پوشه پروژه پیدا نشد: $APP_DIR"
cd "$APP_DIR"

log "دریافت آخرین کد از شاخه ${BRANCH}"
if [[ -d "$APP_DIR/.git" ]]; then
  runuser -u "$APP_USER" -- git -C "$APP_DIR" fetch origin "$BRANCH"
  runuser -u "$APP_USER" -- git -C "$APP_DIR" checkout "$BRANCH"
  runuser -u "$APP_USER" -- git -C "$APP_DIR" reset --hard "origin/$BRANCH"
else
  die "پوشه پروژه مخزن گیت نیست: $APP_DIR"
fi

log "نصب وابستگی‌های پایتون در محیط مجازی پروژه"
if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  runuser -u "$APP_USER" -- python3 -m venv "$APP_DIR/.venv"
fi
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

# ---------------------------------------------------------------------------
# 1b. Stylesheet and script
# ---------------------------------------------------------------------------

# The sheet of the site is written by hand and read by hand. The file
# that is served is shortened, so that the browser has less to read
# before the page can be drawn. The source stays in the repository; the
# shortened file is written next to it and is not kept in the
# repository, so the two can never drift apart unnoticed.
log "آماده‌سازی فایل‌های ظاهری"
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/python" "$APP_DIR/tools/build_assets.py"

# ---------------------------------------------------------------------------
# 2. Environment file
# ---------------------------------------------------------------------------

if [[ ! -f "$APP_DIR/.env" ]]; then
  die "فایل .env پیدا نشد؛ این اسکریپت فایل تنظیمات موجود را تغییر نمی‌دهد."
fi

dotenv_value() {
  awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print}' "$APP_DIR/.env" | tail -n 1
}

set_env_value() {
  local key="$1" value="$2" file="$APP_DIR/.env"
  python3 - "$file" "$key" "$value" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
key, value = sys.argv[2], sys.argv[3]
lines = path.read_text().splitlines()
result, found = [], False
for line in lines:
    if line.split("=", 1)[0].strip() == key:
        if not found:
            result.append(f"{key}={value}")
            found = True
    else:
        result.append(line)
if not found:
    result.append(f"{key}={value}")
path.write_text("\n".join(result) + "\n")
PY
}

CURRENT_PORT="$(dotenv_value PORT)"; CURRENT_PORT="${CURRENT_PORT:-9900}"
CURRENT_MCP_PORT="$(dotenv_value MCP_PORT)"; CURRENT_MCP_PORT="${CURRENT_MCP_PORT:-9901}"

if [[ -z "$PUBLIC_IP" ]]; then
  PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
fi
[[ -n "$PUBLIC_IP" ]] || die "نشانی عمومی سرور پیدا نشد؛ آن را با PUBLIC_IP=... بدهید."

# The TLS port must be free before anything is changed.
TLS_PORT="$PREFERRED_TLS_PORT"
# The port that a previous run of this script chose is reused, so that
# repeated updates do not move the public address around. It is only replaced
# when something else has taken the port in the meantime.
RECORDED_TLS_PORT="$(dotenv_value HTTPS_PUBLIC_PORT)"
if [[ -n "$RECORDED_TLS_PORT" && "$RECORDED_TLS_PORT" != "$PREFERRED_TLS_PORT" ]]; then
  if [[ -z "$(port_listeners "$RECORDED_TLS_PORT")" ]] \
     || port_belongs_to_this_project "$RECORDED_TLS_PORT"; then
    TLS_PORT="$RECORDED_TLS_PORT"
    log "درگاه ثبت‌شده قبلی (${TLS_PORT}) دوباره استفاده می‌شود."
  else
    warn "درگاه ثبت‌شده قبلی (${RECORDED_TLS_PORT}) اکنون در اختیار برنامه دیگری است؛ درگاه دیگری انتخاب می‌شود."
  fi
fi
if [[ -n "$(port_listeners "$TLS_PORT")" ]] && ! port_belongs_to_this_project "$TLS_PORT"; then
  warn "درگاه $TLS_PORT اشغال است؛ درگاه جایگزین انتخاب می‌شود."
  TLS_PORT=""
  for candidate in 9445 9943 10444 9446 8445 9950; do
    if [[ -z "$(port_listeners "$candidate")" ]]; then TLS_PORT="$candidate"; break; fi
  done
  [[ -n "$TLS_PORT" ]] || die "هیچ درگاه آزادی برای HTTPS پیدا نشد."
fi
assert_ports_free "$TLS_PORT" "$LEGACY_HTTP_PORT"

log "ثبت تنظیمات HTTPS در .env"
set_env_value HTTPS_PUBLIC_PORT "$TLS_PORT"
set_env_value HTTP_PUBLIC_PORT "$LEGACY_HTTP_PORT"
set_env_value PORT "$LEGACY_HTTP_PORT"
set_env_value SITE_URL "https://${PUBLIC_IP}:${TLS_PORT}"
set_env_value PUBLIC_ORIGIN "https://${PUBLIC_IP}:${TLS_PORT}"
set_env_value COOKIE_SECURE "true"
set_env_value ENFORCE_HTTPS "false"
set_env_value TRUST_PROXY_HEADERS "false"
set_env_value TLS_CERT_PATH "$CERT_PATH"
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
chmod 0640 "$APP_DIR/.env"

# ---------------------------------------------------------------------------
# 3. Certificate discovery
# ---------------------------------------------------------------------------

# Prepare the directory in which the material lives.
#
# It belongs to the service user, so the service can read and replace the
# material without any further help. The parent is prepared as well,
# because it may not exist yet or may belong to root from an earlier run.
# The directory also holds the file in which Gunicorn writes its process
# number, so it has to exist even when there is no certificate.
prepare_tls_directory() {
  mkdir -p "$APP_DIR/instance/tls"
  chown "$APP_USER:$APP_USER" "$APP_DIR/instance" 2>/dev/null || true
  chown "$APP_USER:$APP_USER" "$APP_DIR/instance/tls" 2>/dev/null || true
  chmod 0750 "$APP_DIR/instance" "$APP_DIR/instance/tls" 2>/dev/null || true
}

# Take a copy of the neighbour's certificate into the project's own
# runtime directory.
# The certificate usually lives below a home directory that is only
# readable by root, for example /root/Desktop/<neighbour>/data/tls/. The
# service user cannot walk through such a directory, so it can neither
# read the file nor see that it exists. The copy is therefore taken with
# the rights this script runs with, and the service user receives the
# copy, not the neighbour's file.
#
# Nothing inside the neighbour's project is written, moved or deleted:
# the file is only read. The copy lands in the project's own directory
# and is handed to the service user, which is the only party that ever
# reads it.
copy_neighbour_certificate() {
  local cert_file="$1"
  [[ -f "$cert_file" ]] || return 1

  # The directory belongs to the service user, so the service can read
  # and replace the material without any further help. The parent is
  # prepared as well, because it may not exist yet or may belong to
  # root from an earlier run.
  prepare_tls_directory

  if "$APP_DIR/.venv/bin/python" -c "
import sys
sys.path.insert(0, '$APP_DIR')
from app.services.tls_manager import materialise_tls_material
materialise_tls_material('$cert_file', '$APP_DIR/instance/tls', owner='$APP_USER')
" 2>/dev/null; then
    # The chain is world readable, the private key stays with the service
    # user only.
    chmod 0644 "$APP_DIR/instance/tls/fullchain.pem" 2>/dev/null || true
    chmod 0600 "$APP_DIR/instance/tls/privkey.pem" 2>/dev/null || true
    return 0
  fi

  warn "آماده‌سازی فایل گواهی ناموفق بود؛ سایت روی HTTP بالا می‌ماند."
  rm -f "$APP_DIR/instance/tls/fullchain.pem" "$APP_DIR/instance/tls/privkey.pem"
  return 1
}

log "پیدا کردن گواهی همسایه"
CERT_FOUND="$("$APP_DIR/.venv/bin/python" - "$CERT_PATH" "$PUBLIC_IP" <<'PY'
import sys
from app.services.tls_manager import find_certificate_for_ip

explicit, public_ip = sys.argv[1] or None, sys.argv[2]
path, notes = find_certificate_for_ip(explicit, public_ip)
for note in notes:
    print(f"# {note}", file=sys.stderr)
if path is None:
    print("")
    raise SystemExit(0)
print(str(path))
PY
)"

if [[ -z "$CERT_FOUND" ]]; then
  warn "گواهی معتبر برای ${PUBLIC_IP} پیدا نشد؛ سایت روی HTTP بالا می‌ماند و خودش دوباره بررسی می‌کند."
  set_env_value TLS_CERT_PATH "$CERT_PATH"
else
  log "گواهی پیدا شد: $CERT_FOUND"
  set_env_value TLS_CERT_PATH "$CERT_FOUND"
  # The neighbour's file is only read. The copy that Gunicorn serves lives
  # in the project's own runtime directory and belongs to the service user,
  # so the service never needs to reach into the neighbour's project.
  if copy_neighbour_certificate "$CERT_FOUND"; then
    log "فایل‌های گواهی برای Gunicorn آماده شد."
  fi
fi

# ---------------------------------------------------------------------------
# 4. Systemd units
# ---------------------------------------------------------------------------

log "نوشتن سرویس‌های systemd"
# Two separate Gunicorn instances are used on purpose. Gunicorn applies
# --certfile to every port it binds, so a single process cannot serve plain
# HTTP on one port and TLS on another. The plain-HTTP instance keeps the old
# links working; the TLS instance carries the certificate.
#
# TLS_PORT keeps its value in every case: it is the port that was chosen
# for HTTPS and is written to .env. Whether the TLS service is actually
# started is a separate question, and it is kept in TLS_ENABLED. Clearing
# TLS_PORT would break the address that was just published.
TLS_ARGS=""
TLS_ENABLED=1
if [[ -s "$APP_DIR/instance/tls/fullchain.pem" && -s "$APP_DIR/instance/tls/privkey.pem" ]]; then
  TLS_ARGS="--certfile ${APP_DIR}/instance/tls/fullchain.pem --keyfile ${APP_DIR}/instance/tls/privkey.pem"
  log "سرویس با TLS روی درگاه ${TLS_PORT} بالا می‌آید."
else
  warn "مدرک گواهی آماده نیست؛ سایت فقط روی HTTP درگاه ${LEGACY_HTTP_PORT} بالا می‌ماند."
  TLS_ENABLED=0
fi

# The units are rewritten on every update. A unit that is failing would
# otherwise keep restarting itself in a loop while its new content is
# being written, so the services of this project are stopped first. Only
# the units of this project are touched.
log "متوقف کردن سرویس‌های این پروژه پیش از نوشتن واحدها"
for unit in "$TLS_SERVICE" "$WEB_SERVICE" "$MCP_SERVICE"; do
  systemctl stop "$unit" >/dev/null 2>&1 || true
done

# The directory of the material has to exist even when there is no
# certificate: Gunicorn writes its process number into it.
prepare_tls_directory
# A process number left over from an earlier run would point at a
# process that no longer exists.
rm -f "$APP_DIR/instance/tls/gunicorn.pid"

cat > "/etc/systemd/system/${WEB_SERVICE}.service" <<UNIT
[Unit]
Description=RunUp catalogue (Gunicorn, plain HTTP for the legacy links)
After=network.target
# A unit that keeps failing must not restart itself for hours. Five
# tries are enough to see the problem; the update script starts it again.
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PATH=${APP_DIR}/.venv/bin
ExecStart=${APP_DIR}/.venv/bin/gunicorn --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:${LEGACY_HTTP_PORT} --access-logfile - --error-logfile - "app:create_app()"
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=${APP_DIR}/instance ${APP_DIR}/backups

[Install]
WantedBy=multi-user.target
UNIT

if [[ "$TLS_ENABLED" == "1" ]]; then
cat > "/etc/systemd/system/${TLS_SERVICE}.service" <<UNIT
[Unit]
Description=RunUp catalogue (Gunicorn over TLS)
After=network.target ${WEB_SERVICE}.service
# A unit that keeps failing must not restart itself for hours. Five
# tries are enough to see the problem; the update script starts it again.
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PATH=${APP_DIR}/.venv/bin
ExecStartPre=${APP_DIR}/.venv/bin/python -c "import sys; sys.path.insert(0, '${APP_DIR}'); from app.services.tls_manager import prepare_tls_material; prepare_tls_material() or print('no TLS material yet; the site starts on plain HTTP')"
ExecStart=${APP_DIR}/.venv/bin/gunicorn --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:${TLS_PORT} ${TLS_ARGS} --pid ${APP_DIR}/instance/tls/gunicorn.pid --access-logfile - --error-logfile - "app:create_app()"
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=${APP_DIR}/instance ${APP_DIR}/backups

[Install]
WantedBy=multi-user.target
UNIT
fi

cat > "/etc/systemd/system/${MCP_SERVICE}.service" <<UNIT
[Unit]
Description=RunUp official MCP Streamable HTTP server
After=network.target ${WEB_SERVICE}.service
# A unit that keeps failing must not restart itself for hours. Five
# tries are enough to see the problem; the update script starts it again.
StartLimitIntervalSec=120
StartLimitBurst=5

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PATH=${APP_DIR}/.venv/bin
Environment=MCP_PORT=${CURRENT_MCP_PORT}
ExecStart=${APP_DIR}/.venv/bin/uvicorn mcp_server:asgi_app --host 0.0.0.0 --port ${CURRENT_MCP_PORT} --proxy-headers
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=${APP_DIR}/instance

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
if [[ "$TLS_ENABLED" == "1" ]]; then
  systemctl enable "$WEB_SERVICE" "$TLS_SERVICE" "$MCP_SERVICE" >/dev/null 2>&1 || true
else
  systemctl enable "$WEB_SERVICE" "$MCP_SERVICE" >/dev/null 2>&1 || true
fi

# ---------------------------------------------------------------------------
# 5. Certificate watcher timer
# ---------------------------------------------------------------------------

log "نصب تایمر تمدید گواهی"
cat > "/etc/systemd/system/runup-cert-refresh.service" <<SERVICE
[Unit]
Description=Re-read the neighbouring certificate for the RunUp site
After=network.target

[Service]
Type=oneshot
# The timer runs as root because the neighbouring certificate often lives
# below a directory that only root may enter. It only reads that file; the
# copy it writes goes into the project's own runtime directory and is handed
# to the service user. Nothing inside the neighbour's project is changed.
User=root
Group=root
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PATH=${APP_DIR}/.venv/bin
ExecStartPre=/bin/sh -c 'mkdir -p ${APP_DIR}/instance/tls && chown ${APP_USER}:${APP_USER} ${APP_DIR}/instance/tls'
ExecStart=${APP_DIR}/.venv/bin/python -c "import sys; sys.path.insert(0, '${APP_DIR}'); from app.services.tls_manager import refresh_tls_material; ok = refresh_tls_material(owner='${APP_USER}'); sys.exit(0 if ok else 1)"
ExecStartPost=/bin/sh -c 'chown ${APP_USER}:${APP_USER} ${APP_DIR}/instance/tls/* 2>/dev/null || true'

[Install]
WantedBy=multi-user.target
SERVICE

cat > "/etc/systemd/system/runup-cert-refresh.timer" <<TIMER
[Unit]
Description=Check the neighbouring certificate every few minutes

[Timer]
OnBootSec=2min
OnUnitActiveSec=5min
Persistent=true

[Install]
WantedBy=timers.target
TIMER

systemctl daemon-reload
systemctl enable --now runup-cert-refresh.timer >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# 6. Database and content
# ---------------------------------------------------------------------------

log "به‌روزرسانی پایگاه داده و داده‌های اولیه"
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/flask" --app run.py db upgrade
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/flask" --app run.py seed-content

# ---------------------------------------------------------------------------
# 7. Start and verify
# ---------------------------------------------------------------------------

log "راه‌اندازی مجدد سرویس‌ها"
if [[ "$TLS_ENABLED" == "1" ]]; then
  systemctl restart "$WEB_SERVICE" "$TLS_SERVICE" "$MCP_SERVICE"
else
  systemctl restart "$WEB_SERVICE" "$MCP_SERVICE"
fi

sleep 4
systemctl is-active --quiet "$WEB_SERVICE" || { journalctl -u "$WEB_SERVICE" -n 40 --no-pager >&2 || true; die "سرویس سایت بالا نیامد."; }
if [[ "$TLS_ENABLED" == "1" ]]; then
  systemctl is-active --quiet "$TLS_SERVICE" || { journalctl -u "$TLS_SERVICE" -n 40 --no-pager >&2 || true; die "سرویس HTTPS بالا نیامد."; }
fi

HTTP_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:${LEGACY_HTTP_PORT}/" || true)"
[[ "$HTTP_STATUS" == "200" ]] || die "پاسخ HTTP روی درگاه ${LEGACY_HTTP_PORT} برابر ${HTTP_STATUS:-بدون پاسخ} بود."

HTTPS_STATUS="بدون گواهی"
if [[ -n "$CERT_FOUND" ]]; then
  HTTPS_STATUS="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 \
      --resolve "${PUBLIC_IP}:${TLS_PORT}:127.0.0.1" \
      "https://${PUBLIC_IP}:${TLS_PORT}/" || true)"
  [[ "$HTTPS_STATUS" == "200" ]] || warn "پاسخ HTTPS برابر ${HTTPS_STATUS:-بدون پاسخ} بود؛ گواهی را بررسی کنید."
fi

# ---------------------------------------------------------------------------
# 8. Report
# ---------------------------------------------------------------------------

echo
runuser -u "$APP_USER" -- "$APP_DIR/.venv/bin/flask" --app run.py status || true
echo
log "پایان. دستور وضعیت: sudo -u ${APP_USER} ${APP_DIR}/.venv/bin/flask --app run.py status"
