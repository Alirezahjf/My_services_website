#!/usr/bin/env bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/backups/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$DEST"
if [[ -f "$ROOT/instance/services.sqlite3" ]]; then
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$ROOT/instance/services.sqlite3" ".backup '$DEST/services.sqlite3'"
  else
    cp "$ROOT/instance/services.sqlite3" "$DEST/services.sqlite3"
  fi
fi
if [[ -d "$ROOT/instance/uploads" ]]; then cp -a "$ROOT/instance/uploads" "$DEST/uploads"; fi
{
  echo "date=$(date -Is)"
  echo "source=$ROOT"
  echo "database=SQLite backup (use pg_dump separately for PostgreSQL)"
  echo "secrets=.env intentionally excluded"
} > "$DEST/MANIFEST.txt"
chmod -R go-rwx "$DEST"
echo "Backup created: $DEST"
