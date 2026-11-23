"""Legacy-HTTP behaviour and the browser-side check for the secure address.

The plain-HTTP listener exists only so that links shared earlier keep opening.
Redirecting them on the server would break visitors whose device does not
accept the certificate, so the decision is made in the browser instead:

* the page asks the secure origin for a small resource with
  ``mode: 'no-cors'`` and a short timeout;
* when the answer arrives, the browser is sent to the secure address;
* otherwise the visitor stays on the working HTTP page and the check is not
  repeated for a while.

The probe is a same-site request, so it needs no additional CSP permission as
long as the secure origin is the same host. When it is not (a different
hostname), the secure origin has to be allowed in ``connect-src``.
"""
from __future__ import annotations

# How long the browser waits for the secure origin to answer, in milliseconds.
PROBE_TIMEOUT_MS = 2500

# How long the visitor waits before the check is repeated, in milliseconds.
RETRY_DELAY_MS = 10 * 60 * 1000

# The probe resource. It is deliberately tiny and must never be cached.
PROBE_PATH = "/static/https-probe.txt"


def probe_url(secure_origin: str) -> str:
    """The URL the browser uses to test the secure origin."""
    if not secure_origin:
        return ""
    return f"{secure_origin.rstrip('/')}{PROBE_PATH}"


def upgrade_snippet(secure_origin: str) -> str:
    """Deprecated inline variant of the upgrade script.

    The script is served as a static file so that the Content-Security-Policy
    can stay free of inline-script permissions. This helper only remains for
    the tests that describe the intended behaviour.
    """
    target = (secure_origin or "").rstrip("/")
    if not target:
        return ""
    return (
        "(function(){var s=document.currentScript;"
        f"var t=(s.getAttribute('data-secure-origin')||'{target}').replace(/\\/+$/,'');"
        "if(!t)return;var P=t+'/static/https-probe.txt';"
        f"var T={PROBE_TIMEOUT_MS};var R={RETRY_DELAY_MS};"
        "function sc(){try{window.setTimeout(at,R)}catch(e){}}"
        "function at(){if(!window.fetch){sc();return;}"
        "var c=typeof AbortController==='function'?new AbortController():null;"
        "var tm=window.setTimeout(function(){if(c)c.abort()},T);"
        "var o={mode:'no-cors',cache:'no-store',credentials:'omit'};"
        "if(c)o.signal=c.signal;"
        "window.fetch(P,o).then(function(){window.clearTimeout(tm);"
        "window.location.replace(t+window.location.pathname+window.location.search+window.location.hash);"
        "}).catch(function(){window.clearTimeout(tm);sc()})}"
        "at()})();"
    )


def csp_connect_sources(current: str, secure_origin: str) -> str:
    """Add the secure origin to a ``connect-src`` list when it is missing.

    The CSP of the site is intentionally strict and stays that way; only the
    one origin that the probe needs is added. The scheme has to be part of the
    source expression, because a source that carries a port is only matched
    when its scheme matches as well.
    """
    if not secure_origin:
        return current
    origin = secure_origin.rstrip("/")
    if "://" not in origin:
        origin = "https://" + origin
    if origin not in ("https://", "http://"):
        # A source expression with a port must carry its scheme.
        source = origin
    else:
        source = origin

    parts = current.split(";")
    result = []
    for part in parts:
        stripped = part.strip()
        if stripped.startswith("connect-src"):
            values = [v.strip() for v in stripped[len("connect-src"):].split()]
            if source not in values:
                values.append(source)
            result.append("connect-src " + " ".join(values))
        else:
            result.append(part)
    return ";".join(result)
