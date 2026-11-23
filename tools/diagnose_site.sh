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
WEB_SERVICE="${WEB_SERVICE:-runup-web}"
TLS_SERVICE="${TLS_SERVICE:-runup-tls}"
LEGACY_HTTP_PORT="${LEGACY_HTTP_PORT:-9900}"
TLS_PORT="${TLS_PORT:-9900}"

hr() { printf '\n=== %s ===\n' "$1"; }

hr "1. the code on the server"
cd "$APP_DIR" 2>/dev/null || { echo "پوشه پوشه پروژه پیدا نشد: $APP_DIR"; exit 1; }
echo "HEAD      : $(git rev-parse HEAD 2>&1)"
echo "branch    : $(git rev-parse --abbrev-ref HEAD 2>&1)"
echo "status    :"; git status --short 2>&1 | head -20
echo "refspec   :"; git config --get-all remote.origin.fetch 2>&1 | sed 's/^/  /'
echo "remote-tracking refs:"; git for-each-ref --format='  %(refname) %(objectname:short)' refs/remotes/origin 2>&1 | head -20

hr "2. the built files that the browser receives"
for f in app/static/css/main.css app/static/js/main.js; do
  if [[ -f "$APP_DIR/$f" ]]; then
    printf '  %-28s %8s bytes  sha=%s\n' "$f" "$(stat -c%s "$APP_DIR/$f")" "$(sha256sum "$APP_DIR/$f" | cut -c1-12)"
  else
    printf '  %-28s MISSING\n' "$f"
  fi
done
echo "  the source files:"
for f in app/static/css/site.src.css app/static/js/site.src.js; do
  if [[ -f "$APP_DIR/$f" ]]; then
    printf '  %-28s %8s bytes\n' "$f" "$(stat -c%s "$APP_DIR/$f")"
  else
    printf '  %-28s MISSING\n' "$f"
  fi
done

hr "3. the answers of the running services"
for port in "$LEGACY_HTTP_PORT" "$TLS_PORT"; do
  for scheme in http https; do
    out="$(curl -sS -o /dev/null -w '%{http_code} %{size_download}' --max-time 8 "$scheme://127.0.0.1:${port}/" 2>&1 || true)"
    printf '  %-6s 127.0.0.1:%-5s -> %s\n' "$scheme" "$port" "$out"
  done
done

hr "4. the stylesheet and the script as the browser gets them"
echo "  HTTP head of the stylesheet:"
curl -sSI --max-time 8 "http://127.0.0.1:${LEGACY_HTTP_PORT}/static/css/main.css" 2>&1 | sed 's/^/    /' | head -20
echo "  the script:"
curl -sSI --max-time 8 "http://127.0.0.1:${LEGACY_HTTP_PORT}/static/js/main.js" 2>&1 | sed 's/^/    /' | head -20

hr "5. what the page itself carries"
html="$(curl -sS --max-time 10 "http://127.0.0.1:${LEGACY_HTTP_PORT}/" 2>&1 || true)"
echo "  length of the page: ${#html}"
echo "$html" | grep -o 'class="[^"]*page-is-ready[^"]*"' | head -3
echo "$html" | grep -o 'href="[^"]*main\.css[^"]*"' | head -3
echo "$html" | grep -o 'src="[^"]*main\.js[^"]*"' | head -3
echo "$html" | grep -c 'data-page-enter' | sed 's/^/  data-page-enter count: /'

hr "6. the units"
for unit in "$WEB_SERVICE" "$TLS_SERVICE"; do
  printf '  %-14s %s\n' "$unit" "$(systemctl is-active "$unit" 2>&1)"
done

hr "7. the recent lines of the web unit"
journalctl -u "$WEB_SERVICE" -n 25 --no-pager 2>&1 | sed 's/^/  /'

hr "8. the recent lines of the TLS unit"
journalctl -u "$TLS_SERVICE" -n 15 --no-pager 2>&1 | sed 's/^/  /'

echo
echo "پایان تشخیص. هیچ چیز تغییر نکرد."
