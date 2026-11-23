#!/usr/bin/env bash
# Read-only diagnosis of the RunUp site on this server.
#
# It changes nothing: it only reads files, asks the running services and
# looks at the answers. It is safe to run at any time.
#
#   sudo bash tools/diagnose_site.sh
#
set -uo pipefail

APP_DIR="${APP_DIR:-/opt/hjf-services}"
APP_USER="${APP_USER:-services}"

# The names of the units and the ports are taken from the environment of
# the project when they are written there, so that the report always
# speaks about the site that is really running.
read_dotenv() {
  [[ -f "$APP_DIR/.env" ]] || return 0
  awk -F= -v key="$1" '$1 == key {sub(/^[^=]*=/, ""); print}' "$APP_DIR/.env" | tail -n 1
}

WEB_SERVICE="${WEB_SERVICE:-$(read_dotenv RUNUP_WEB_SERVICE)}"
TLS_SERVICE="${TLS_SERVICE:-$(read_dotenv RUNUP_TLS_SERVICE)}"
WEB_SERVICE="${WEB_SERVICE:-hjf-services}"
TLS_SERVICE="${TLS_SERVICE:-hjf-services-tls}"

LEGACY_HTTP_PORT="${LEGACY_HTTP_PORT:-$(read_dotenv HTTP_PUBLIC_PORT)}"
LEGACY_HTTP_PORT="${LEGACY_HTTP_PORT:-19900}"
TLS_PORT="${TLS_PORT:-$(read_dotenv HTTPS_PUBLIC_PORT)}"
TLS_PORT="${TLS_PORT:-9900}"
PUBLIC_IP="${PUBLIC_IP:-$(read_dotenv PUBLIC_IP)}"

hr() { printf '\n=== %s ===\n' "$1"; }

# ---------------------------------------------------------------------------
hr "1. the code on the server"
cd "$APP_DIR" 2>/dev/null || { echo "پوشه پروژه پیدا نشد: $APP_DIR"; exit 1; }
echo "HEAD      : $(git rev-parse HEAD 2>&1)"
echo "branch    : $(git rev-parse --abbrev-ref HEAD 2>&1)"
echo "status    :"; git status --short 2>&1 | head -20
echo "refspec   :"; git config --get-all remote.origin.fetch 2>&1 | sed 's/^/  /'
echo "remote-tracking refs:"; git for-each-ref --format='  %(refname) %(objectname:short)' refs/remotes/origin 2>&1 | head -20

# ---------------------------------------------------------------------------
hr "2. the files of the appearance"
for f in app/static/css/main.css app/static/js/main.js \
         app/static/css/site.src.css app/static/js/site.src.js \
         app/static/css/.asset-version; do
  if [[ -f "$APP_DIR/$f" ]]; then
    printf '  %-30s %8s bytes  sha=%s\n' "$f" "$(stat -c%s "$APP_DIR/$f")" "$(sha256sum "$APP_DIR/$f" | cut -c1-12)"
  else
    printf '  %-30s MISSING\n' "$f"
  fi
done

# ---------------------------------------------------------------------------
hr "3. the units"
for unit in "$WEB_SERVICE" "$TLS_SERVICE"; do
  printf '  %-22s %s\n' "$unit" "$(systemctl is-active "$unit" 2>&1)"
  printf '  %-22s enabled=%s\n' "" "$(systemctl is-enabled "$unit" 2>&1)"
done
echo "  the unit files:"
for unit in "$WEB_SERVICE" "$TLS_SERVICE"; do
  f="/etc/systemd/system/${unit}.service"
  if [[ -f "$f" ]]; then
    echo "    $f"
    grep -E "^(ExecStart|User|WorkingDirectory)" "$f" | sed 's/^/      /'
  else
    echo "    $f  MISSING"
  fi
done

# ---------------------------------------------------------------------------
hr "4. who listens on the ports"
for port in "$LEGACY_HTTP_PORT" "$TLS_PORT"; do
  echo "  port $port:"
  ss -lntp 2>/dev/null | grep -E ":${port}\b" | sed 's/^/    /' || echo "    nothing"
done

# ---------------------------------------------------------------------------
hr "5. the answers of the running services"
printf '  http  127.0.0.1:%-6s -> ' "$LEGACY_HTTP_PORT"
curl -sS -o /dev/null -w '%{http_code} %{size_download} bytes\n' --max-time 10 \
  "http://127.0.0.1:${LEGACY_HTTP_PORT}/" 2>&1 | tr -d '\n' | sed 's/^/ /'; echo
if [[ -n "$PUBLIC_IP" ]]; then
  printf '  https %s:%-6s -> ' "$PUBLIC_IP" "$TLS_PORT"
  curl -sS -o /dev/null -w '%{http_code} %{size_download} bytes\n' --max-time 15 \
    --resolve "${PUBLIC_IP}:${TLS_PORT}:127.0.0.1" \
    "https://${PUBLIC_IP}:${TLS_PORT}/" 2>&1 | tr -d '\n' | sed 's/^/ /'; echo
else
  echo "  (PUBLIC_IP is not known; the secure answer is not asked)"
fi

# ---------------------------------------------------------------------------
hr "6. the stylesheet and the script as the browser gets them"
echo "  the sheet:"
curl -sSI --max-time 10 "http://127.0.0.1:${LEGACY_HTTP_PORT}/static/css/main.css" 2>&1 | sed 's/^/    /' | head -18
echo "  the script:"
curl -sSI --max-time 10 "http://127.0.0.1:${LEGACY_HTTP_PORT}/static/js/main.js" 2>&1 | sed 's/^/    /' | head -18

# ---------------------------------------------------------------------------
hr "7. what the page itself carries"
html="$(curl -sS --max-time 10 "http://127.0.0.1:${LEGACY_HTTP_PORT}/" 2>&1 || true)"
echo "  length of the page: ${#html}"
echo "$html" | grep -o 'href="[^"]*main\.css[^"]*"' | sed 's/^/    /' | head -2
echo "$html" | grep -o 'src="[^"]*main\.js[^"]*"' | sed 's/^/    /' | head -2
echo "$html" | grep -c 'data-page-enter' | sed 's/^/    data-page-enter count: /'

# ---------------------------------------------------------------------------
hr "8. the certificate"
for f in "$APP_DIR/instance/tls/fullchain.pem" "$APP_DIR/instance/tls/privkey.pem" \
         "$APP_DIR/cert.pem" "$APP_DIR/key.pem"; do
  if [[ -f "$f" ]]; then
    printf '  %-46s %8s bytes  owner=%s\n' "$f" "$(stat -c%s "$f")" "$(stat -c%U "$f")"
  else
    printf '  %-46s MISSING\n' "$f"
  fi
done
if [[ -f "$APP_DIR/instance/tls/fullchain.pem" ]]; then
  echo "  what the certificate says:"
  openssl x509 -in "$APP_DIR/instance/tls/fullchain.pem" -noout -subject -issuer -dates -ext subjectAltName 2>&1 | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
hr "9. the recent lines of the units"
for unit in "$WEB_SERVICE" "$TLS_SERVICE"; do
  echo "  $unit:"
  journalctl -u "$unit" -n 20 --no-pager 2>&1 | sed 's/^/    /'
done

echo
echo "پایان تشخیص. هیچ چیز تغییر نکرد."
