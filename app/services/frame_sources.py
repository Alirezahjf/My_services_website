"""The places from which a sample may be drawn.

The policy of the site is strict, and it stays strict. A sample that is
drawn inside the page comes from another address, and the browser must
be told that this one address is allowed.

Only the addresses that the administrator has really registered are
allowed, and they are written down with their scheme, because a source
expression that carries a port is only matched when its scheme matches
as well. Nothing else of the policy is touched.
"""

from __future__ import annotations

from urllib.parse import urlsplit

# The schemes a sample may come from. The address of the site itself is
# always allowed.
ALLOWED_SCHEMES = ("http", "https")


def frame_hosts(links) -> list[str]:
    """The hosts of the samples that may be drawn inside the page.

    Only the samples that are published are taken, and only the ones
    that are drawn inside the page. A sample that opens in a new tab
    needs no permission at all.
    """
    hosts: list[str] = []
    for link in links or ():
        if not getattr(link, "is_published", False):
            continue
        if getattr(link, "display_mode", "live") != "live":
            continue
        source = _source_expression(link.url)
        if source and source not in hosts:
            hosts.append(source)
    return hosts


def _source_expression(url: str | None) -> str | None:
    """The source expression of one address, when it is one of the
    kinds of address a browser may draw."""
    if not url:
        return None
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return None
    if parts.scheme not in ALLOWED_SCHEMES or not parts.netloc:
        return None
    return f"{parts.scheme}://{parts.netloc}"


def csp_frame_sources(current: str, hosts: list[str]) -> str:
    """Put the hosts of the samples into the ``frame-src`` of the policy.

    The policy of the site has no ``frame-src`` of its own, and so the
    samples would be blocked by ``default-src 'self'``. This adds the
    one directive that is missing, with the hosts that are really used,
    and leaves every other directive as it was.
    """
    if not hosts:
        return current

    source = " ".join(["'self'"] + hosts)
    parts = current.split(";")
    result = []
    placed = False
    for part in parts:
        stripped = part.strip()
        if stripped.startswith("frame-src"):
            if placed:
                continue
            result.append(f" frame-src {source}")
            placed = True
            continue
        result.append(part)
    if not placed:
        result.append(f" frame-src {source}")
    return ";".join(result)
