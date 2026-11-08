#!/usr/bin/env bash
# One-command Ubuntu public-IP test installation for the Arena branch.
# Run: curl -fsSL <this-file-on-raw-github> | sudo bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer with sudo or as root." >&2
  exit 1
fi

REPO="https://github.com/Alirezahjf/My_services_website.git"
BRANCH="arena/5096b461-my-services-website"
APP_DIR="/opt/hjf-services"
APP_USER="services"
ADMIN_USERNAME="admin"
PORT="9900"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 python3-venv python3-pip git curl sqlite3 ufw

if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd --system --group --home-dir /srv/services --create-home --shell /usr/sbin/nologin "${APP_USER}"
fi
mkdir -p "$(dirname "${APP_DIR}")"
chown "${APP_USER}:${APP_USER}" "$(dirname "${APP_DIR}")"

if [[ -d "${APP_DIR}/.git" ]]; then
  runuser -u "${APP_USER}" -- git -C "${APP_DIR}" fetch origin "${BRANCH}"
  runuser -u "${APP_USER}" -- git -C "${APP_DIR}" checkout "${BRANCH}"
  runuser -u "${APP_USER}" -- git -C "${APP_DIR}" reset --hard "origin/${BRANCH}"
else
  runuser -u "${APP_USER}" -- git clone --branch "${BRANCH}" --single-branch "${REPO}" "${APP_DIR}"
fi

cd "${APP_DIR}"
if [[ ! -x .venv/bin/python ]]; then
  runuser -u "${APP_USER}" -- python3 -m venv .venv
fi
runuser -u "${APP_USER}" -- .venv/bin/python -m pip install --upgrade pip
runuser -u "${APP_USER}" -- .venv/bin/pip install -r requirements.txt

FRESH_INSTALL=0
[[ ! -f instance/services.sqlite3 ]] && FRESH_INSTALL=1
mkdir -p instance/uploads backups
if [[ ! -f .env ]]; then
  SECRET_KEY="$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')"
  PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || hostname -I | cut -d' ' -f1)"
  cat > .env <<ENV
SECRET_KEY=${SECRET_KEY}
FLASK_ENV=production
SITE_URL=http://${PUBLIC_IP}:${PORT}
COOKIE_SECURE=false
DATABASE_URL=sqlite:///${APP_DIR}/instance/services.sqlite3
RATELIMIT_STORAGE_URI=memory://
PORT=${PORT}
ENV
fi
chown -R "${APP_USER}:${APP_USER}" .env instance backups
chmod 640 .env
chmod 750 instance instance/uploads

runuser -u "${APP_USER}" -- .venv/bin/flask --app run.py db upgrade
runuser -u "${APP_USER}" -- .venv/bin/flask --app run.py seed-content

CREDENTIAL_FILE="/root/hjf-services-admin.txt"
if [[ ${FRESH_INSTALL} -eq 1 ]]; then
  ADMIN_PASSWORD="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(18))')"
  runuser -u "${APP_USER}" -- .venv/bin/flask --app run.py create-admin \
    --username "${ADMIN_USERNAME}" --password "${ADMIN_PASSWORD}"
  umask 077
  printf 'Username: %s\nPassword: %s\n' "${ADMIN_USERNAME}" "${ADMIN_PASSWORD}" > "${CREDENTIAL_FILE}"
fi

cat > /etc/systemd/system/hjf-services.service <<UNIT
[Unit]
Description=HJF Services Flask test server
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${APP_DIR}/.env
Environment=PATH=${APP_DIR}/.venv/bin
ExecStart=${APP_DIR}/.venv/bin/gunicorn --workers 2 --threads 4 --timeout 60 --bind 0.0.0.0:${PORT} --access-logfile - --error-logfile - "app:create_app()"
Restart=on-failure
RestartSec=5
PrivateTmp=true
NoNewPrivileges=true
ProtectSystem=full
ReadWritePaths=${APP_DIR}/instance ${APP_DIR}/backups

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable hjf-services
systemctl restart hjf-services
ufw allow OpenSSH >/dev/null
ufw allow "${PORT}/tcp" >/dev/null
ufw --force enable >/dev/null

sleep 3
systemctl is-active --quiet hjf-services
curl -fsS --max-time 10 "http://127.0.0.1:${PORT}/" >/dev/null
PUBLIC_IP="$(curl -4 -fsS --max-time 8 https://api.ipify.org || hostname -I | cut -d' ' -f1)"

printf '\nInstallation completed successfully.\n'
printf 'Website: http://%s:%s/\n' "${PUBLIC_IP}" "${PORT}"
printf 'Admin:   http://%s:%s/admin/login\n' "${PUBLIC_IP}" "${PORT}"
if [[ -f ${CREDENTIAL_FILE} ]]; then
  cat "${CREDENTIAL_FILE}"
  printf 'Credentials are also stored in %s (root-only).\n' "${CREDENTIAL_FILE}"
else
  printf 'Existing administrator credentials were left unchanged.\n'
fi
printf 'Service status: systemctl status hjf-services\n'
printf 'Logs: journalctl -u hjf-services -f\n'
printf 'This is an HTTP test setup. Configure HTTPS before production use.\n'
