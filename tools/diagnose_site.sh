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
echo "  the processes of this project:"
ps -eo pid,user,etime,args 2>/dev/null | grep -E "gunicorn.*${APP_DIR}" | grep -v grep | sed 's/^/    /' || echo "    none"
echo "  when were the files of the appearance built:"
for f in app/static/css/main.css app/static/js/main.js; do
  [[ -f "$APP_DIR/$f" ]] && echo "    $f : $(date -r "$APP_DIR/$f" '+%Y-%m-%d %H:%M:%S')"
done
echo "  the processes of the neighbour are not touched and are not shown here."

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

# The decisive question: does the running service hand out the files of
# the current update, or the ones of an earlier one? The number on the
# address of the sheet tells which.
echo "  the number on the address of the files of the appearance:"
live_html="$(curl -sS --max-time 10 "http://127.0.0.1:${LEGACY_HTTP_PORT}/" 2>/dev/null || true)"
if [[ -z "$live_html" ]]; then
  live_html="$(curl -sS --max-time 15 --resolve "${PUBLIC_IP}:${TLS_PORT}:127.0.0.1" \
    "https://${PUBLIC_IP}:${TLS_PORT}/" 2>/dev/null || true)"
fi
echo "$live_html" | grep -o 'href="[^"]*main\.css[^"]*"' | sed 's/^/    /' | head -2
echo "$live_html" | grep -o 'src="[^"]*main\.js[^"]*"' | sed 's/^/    /' | head -2
if echo "$live_html" | grep -q 'main\.css?v='; then
  echo "    -> the running service hands out the numbered files: it is up to date."
else
  echo "    -> the running service hands out the OLD files: it must be restarted."
fi

# What a phone sees when it opens the secure address. This is the test
# that matters: a browser that cannot build the path to a trusted root
# shows an empty page and says nothing about it.
echo "  the secure address as a browser meets it:"
if [[ -n "$PUBLIC_IP" ]]; then
  curl -sS -o /dev/null --max-time 15 --resolve "${PUBLIC_IP}:${TLS_PORT}:127.0.0.1" \
    "https://${PUBLIC_IP}:${TLS_PORT}/" 2>&1 | sed 's/^/    /'
  curl -sS -o /dev/null -w '    the certificate is trusted, the page answered %{http_code}\n' \
    --max-time 15 --resolve "${PUBLIC_IP}:${TLS_PORT}:127.0.0.1" \
    "https://${PUBLIC_IP}:${TLS_PORT}/" 2>&1 | sed 's/^/    /'
else
  echo "    (PUBLIC_IP is not known)"
fi

# ---------------------------------------------------------------------------
hr "6. the stylesheet and the script as the browser gets them"
echo "  the sheet:"
curl -sSI --max-time 10 "http://127.0.0.1:${LEGACY_HTTP_PORT}/static/css/main.css" 2>&1 | sed 's/^/    /' | head -18
echo "  the script:"
curl -sSI --max-time 10 "http://127.0.0.1:${LEGACY_HTTP_PORT}/static/js/main.js" 2>&1 | sed 's/^/    /' | head -18

# A phone asks for brotli. The answer must carry the bytes of the name
# it announces. When the server announces brotli but carries gzip, the
# browser cannot read the sheet and the phone shows an empty page.
echo "  the answer a phone gets (it asks for brotli):"
tmp_body="$(mktemp)"
enc="$(curl -sS -o "$tmp_body" -D- --max-time 15 \
  -H "Accept-Encoding: gzip, deflate, br" \
  "http://127.0.0.1:${LEGACY_HTTP_PORT}/static/css/main.css" 2>/dev/null \
  | grep -i '^content-encoding:' | tr -d '\r' | awk '{print $2}')"
echo "    announced: ${enc:-none}"
if [[ -s "$tmp_body" ]]; then
  magic="$(od -An -tx1 -N2 "$tmp_body" | tr -d ' \n')"
  echo "    first bytes: ${magic}"
  case "$enc" in
    br)
      if [[ "$magic" == "1f8b" ]]; then
        echo "    -> WRONG. The answer says brotli but carries gzip."
        echo "       A phone cannot read the sheet and shows an empty page."
      else
        echo "    -> the bytes match the name."
      fi
      ;;
    gzip)
      if [[ "$magic" == "1f8b" ]]; then
        echo "    -> the bytes match the name."
      else
        echo "    -> WRONG. The answer says gzip but carries something else."
      fi
      ;;
    *)
      echo "    -> no shortening was used."
      ;;
  esac
fi
rm -f "$tmp_body"
echo "  can the server shorten with brotli?"
if "$APP_DIR/.venv/bin/python" -c "import brotli" 2>/dev/null; then
  echo "    yes, the package is there."
else
  echo "    NO, the package is missing. The site then answers with gzip,"
  echo "    which is right, as long as it says so."
fi

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

chain_file="$APP_DIR/instance/tls/fullchain.pem"
if [[ -f "$chain_file" ]]; then
  echo "  the leaf certificate:"
  openssl x509 -in "$chain_file" -noout -subject -issuer -dates 2>&1 | sed 's/^/    /'
  openssl x509 -in "$chain_file" -noout -ext subjectAltName 2>&1 | sed 's/^/    /'

  # How many certificates the chain holds. A phone that has never been
  # to this site has no intermediate in its store, so a chain with only
  # the leaf cannot be completed and the page stays empty.
  count="$(grep -c 'BEGIN CERTIFICATE' "$chain_file" 2>/dev/null || echo 0)"
  echo "  the chain holds $count certificate(s)"
  if [[ "$count" -lt 2 ]]; then
    echo "    -> only the leaf is served. A phone that has not seen this"
    echo "       site before may not be able to build the path and will"
    echo "       show an empty page."
  fi

  # The path as the server itself sees it.
  echo "  the path the server can build:"
  openssl verify -untrusted "$chain_file" "$chain_file" 2>&1 | sed 's/^/    /' || true

  # The path as a browser that trusts the system roots sees it.
  echo "  the path a phone would check:"
  openssl s_client -connect "${PUBLIC_IP:-127.0.0.1}:${TLS_PORT}" \
    -servername "${PUBLIC_IP:-127.0.0.1}" -showcerts </dev/null 2>&1 \
    | grep -E "^ *(depth|verify|Verification|subject|issuer)=" | sed 's/^/    /' | head -30 || true
fi

# The source of the certificate: the neighbour's file.
if [[ -n "${TLS_CERT_PATH:-}" && -f "${TLS_CERT_PATH}" ]]; then
  echo "  the neighbour's file that was read (${TLS_CERT_PATH}):"
  echo "    certificates: $(grep -c 'BEGIN CERTIFICATE' "${TLS_CERT_PATH}" 2>/dev/null || echo 0)"
  openssl x509 -in "${TLS_CERT_PATH}" -noout -subject -issuer -dates 2>&1 | sed 's/^/    /'
fi

# ---------------------------------------------------------------------------
hr "9. the recent lines of the units"
for unit in "$WEB_SERVICE" "$TLS_SERVICE"; do
  echo "  $unit:"
  journalctl -u "$unit" -n 20 --no-pager 2>&1 | sed 's/^/    /'
done

echo
echo "پایان تشخیص. هیچ چیز تغییر نکرد."
