"""Compression of the files that the browser asks for.

The sheet of the site, the script and the fonts are sent as they are
without being shortened on the way. A sheet of ninety kilobytes that
the browser has to read is a wait that every visitor pays.

The files that can be shortened are shortened here, before they leave
the server. The work is done once per file and the result is kept, so
the second visitor does not pay for it again.

Only the types that are worth it are shortened. A picture is already
shortened, and a short answer has nothing to gain.
"""

from __future__ import annotations

import gzip
import hashlib
import threading
from pathlib import Path

from flask import current_app, request, send_from_directory

# The types that are worth shortening, with the type that is sent back.
COMPRESSIBLE = {
    "text/css": "text/css",
    "text/javascript": "text/javascript",
    "application/javascript": "text/javascript",
    "application/json": "application/json",
    "image/svg+xml": "image/svg+xml",
    "text/html": "text/html",
    "text/plain": "text/plain",
}

# The types that are never shortened, because they are already short or
# because they are read while they stream.
NOT_COMPRESSIBLE = {
    "image/png", "image/jpeg", "image/gif", "image/webp", "image/avif",
    "video/mp4", "video/webm", "audio/mpeg", "application/zip",
    "application/pdf", "font/woff2", "font/woff", "application/octet-stream",
}

# A file below this size is not worth the work.
MINIMUM_SIZE = 1024

_lock = threading.Lock()
_cache: dict[tuple[str, str], bytes] = {}


def _compressed(path: Path, kind: str) -> bytes:
    """Return the shortened form of a file, and remember it."""
    key = (str(path), kind)
    with _lock:
        found = _cache.get(key)
    if found is not None:
        return found

    raw = path.read_bytes()
    if kind == "gzip":
        result = gzip.compress(raw, 9)
    else:
        result = _brotli(raw)

    with _lock:
        # The cache is small; it holds the files of the site only.
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = result
    return result


def _brotli(raw: bytes) -> bytes:
    """Shorten with brotli, when it is there."""
    try:
        import brotli
    except ImportError:
        return gzip.compress(raw, 9)
    return brotli.compress(raw, quality=9)


def _encoding_for(accept: str) -> str | None:
    """Pick the way of shortening that the browser knows."""
    if "br" in accept:
        return "br"
    if "gzip" in accept:
        return "gzip"
    return None


def compress_static(app):
    """Serve the files of the site in a shorter form.

    The function is used as a view for the files of the site, so that
    only those files are shortened and the answers of the site itself
    are not touched.
    """
    root = Path(app.root_path) / "static"

    def serve(filename: str):
        path = (root / filename).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            return ("not found", 404)

        if not path.is_file():
            return ("not found", 404)

        suffix = path.suffix.lower()
        content_type = {
            ".css": "text/css",
            ".js": "text/javascript",
            ".svg": "image/svg+xml",
            ".json": "application/json",
            ".html": "text/html",
            ".txt": "text/plain",
            ".xml": "application/xml",
            ".woff2": "font/woff2",
            ".woff": "font/woff",
        }.get(suffix, "")

        if content_type in NOT_COMPRESSIBLE or not content_type:
            return send_from_directory(root, filename)

        size = path.stat().st_size
        if size < MINIMUM_SIZE:
            return send_from_directory(root, filename)

        encoding = _encoding_for(request.headers.get("Accept-Encoding", ""))
        if not encoding:
            return send_from_directory(root, filename)

        body = _compressed(path, encoding)
        digest = hashlib.sha256(body).hexdigest()[:16]
        etag = f'"{digest}"'

        if request.headers.get("If-None-Match") == etag:
            response = current_app.response_class(status=304)
        else:
            response = current_app.response_class(body, mimetype=content_type)

        response.headers["Content-Encoding"] = encoding
        response.headers["Content-Length"] = str(len(body))
        response.headers["ETag"] = etag
        response.headers["Vary"] = "Accept-Encoding"
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response

    # The rule keeps the name that the templates use to build the
    # address of a file.
    app.add_url_rule("/static/<path:filename>", "static", serve)


def compress_responses(app):
    """Send the answers of the site in a shorter form too.

    The page of the site holds the part of the sheet that the first
    screen needs, and the browser has to read it before it can draw.
    Shortening the answer makes that reading shorter as well.
    """
    @app.after_request
    def shorten(response):
        if response.direct_passthrough:
            return response
        if response.status_code < 200 or response.status_code >= 300:
            return response

        content_type = (response.headers.get("Content-Type") or "").split(";")[0].strip()
        if content_type not in ("text/html", "application/json", "text/plain"):
            return response
        if response.headers.get("Content-Encoding"):
            return response

        body = response.get_data()
        if len(body) < MINIMUM_SIZE:
            return response

        encoding = _encoding_for(request.headers.get("Accept-Encoding", ""))
        if not encoding:
            return response

        short = _shorten_body(body, encoding)
        response.set_data(short)
        response.headers["Content-Encoding"] = encoding
        response.headers["Content-Length"] = str(len(short))
        response.headers["Vary"] = "Accept-Encoding"
        return response

    return app


def _shorten_body(body: bytes, encoding: str) -> bytes:
    """Shorten a body that is not a file."""
    key = ("body", encoding, hashlib.sha256(body).hexdigest())
    with _lock:
        found = _cache.get(key)
    if found is not None:
        return found

    if encoding == "gzip":
        result = gzip.compress(body, 9)
    else:
        result = _brotli(body)

    with _lock:
        if len(_cache) > 64:
            _cache.clear()
        _cache[key] = result
    return result
