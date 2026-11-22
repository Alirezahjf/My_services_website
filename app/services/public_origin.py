"""The single source of truth for the site's public origin.

Every absolute URL the site emits (canonical link, Open Graph tags, sitemap
entries, JSON-LD) has to use the secure address, even when the request that
triggered the rendering arrived over plain HTTP. The address is therefore
never taken from the request but read from the configuration.
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit, urlunsplit

from flask import current_app, has_app_context, request


def configured_origin() -> str:
    """The public origin of the site, without a trailing slash.

    Priority: ``PUBLIC_ORIGIN`` > ``SITE_URL`` > the scheme/host of the
    current request. An empty result means the origin is not known yet.
    """
    if has_app_context():
        origin = (current_app.config.get("PUBLIC_ORIGIN") or "").strip()
        if origin:
            return origin.rstrip("/")
        site_url = (current_app.config.get("SITE_URL") or "").strip()
        if site_url:
            return site_url.rstrip("/")
    origin = (os.getenv("PUBLIC_ORIGIN") or "").strip()
    if origin:
        return origin.rstrip("/")
    return (os.getenv("SITE_URL") or "").strip().rstrip("/")


def secure_origin() -> str | None:
    """The public origin, guaranteed to use ``https`` when it is known."""
    origin = configured_origin()
    if not origin:
        return None
    parts = urlsplit(origin)
    if parts.scheme == "https":
        return origin
    return urlunsplit(("https", parts.netloc, parts.path.rstrip("/"), parts.query, parts.fragment))


def public_url(path: str = "", endpoint: str | None = None, **values) -> str:
    """Build an absolute URL on the public origin.

    ``path`` is a site-relative path such as ``/products``. When ``endpoint``
    is given, the URL is built from the Flask endpoint instead.
    """
    origin = configured_origin()
    if endpoint:
        from flask import url_for

        relative = url_for(endpoint, **values)
    else:
        relative = path or "/"
    if not relative.startswith("/"):
        relative = "/" + relative
    if not origin:
        # Fall back to the request host while the origin is not configured.
        return request.url_root.rstrip("/") + relative if has_app_context() else relative
    return origin.rstrip("/") + relative


def canonical_url() -> str:
    """The canonical address of the current page on the public origin."""
    path = request.path
    query = request.query_string.decode("utf-8", "replace")
    return public_url(path) + (f"?{query}" if query else "")


def request_is_legacy_http() -> bool:
    """True when the current request arrived over plain HTTP.

    The legacy HTTP listener only exists so that old links keep working. It
    must never be treated as the canonical address of the site.
    """
    if not has_app_context():
        return False
    if request.scheme == "https":
        return False
    # When a trusted proxy header is present, ``request.scheme`` already
    # reflects the original scheme.
    return True


def legacy_http_base() -> str | None:
    """The origin of the plain-HTTP listener, when one is configured."""
    if not has_app_context():
        return None
    port = current_app.config.get("HTTP_PUBLIC_PORT")
    if not port:
        return None
    origin = configured_origin()
    if origin:
        parts = urlsplit(origin)
        return urlunsplit(("http", parts.netloc.split(":")[0], f":{port}", "", ""))
    return None
