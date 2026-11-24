"""The sign-in of the visitors, kept apart from the sign-in of the manager.

Flask-Login keeps one name in the session, and the panel uses it. If the
visitors used it too, then a manager who was also a visitor would be
signed out of the panel every time a sample was opened.

So the visitors have their own small system: their own name in the
session, their own cookie, and their own signing key. The two never
touch each other, and the manager's panel is never in reach of a
visitor's account.

The session of a visitor is kept in a cookie of its own, so that the two
kinds of sign-in live side by side in the same browser without one of
them disturbing the other.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app, g, request, session

from app.extensions import db
from app.models import Visitor

# The name under which the visitor is kept in the session of the browser.
SESSION_KEY = "runup_visitor_id"
# The name of the cookie that holds the session of the visitor. The old
# HTTP page and the secure page live side by side in one browser, and a
# cookie that is marked secure is not sent back over the plain
# channel. The name of the cookie therefore follows the name of the
# session cookie of the page, so that the two pages do not tread on
# each other's cookie.
COOKIE_NAME = "runup_visitor"


def cookie_name() -> str:
    """The name of the cookie of the visitor on this page.

    The old HTTP page and the secure page live in one browser, and a
    cookie that is marked secure is not sent back over the plain
    channel. The name of the visitor's cookie therefore follows the
    name of the session cookie of the page: ``session`` becomes
    ``runup_visitor``, and ``runup_session_http`` becomes
    ``runup_visitor_http``. The two pages do not tread on each other's
    cookie.
    """
    session_cookie = current_app.config.get("SESSION_COOKIE_NAME") or "session"
    if session_cookie.startswith("runup_"):
        # The old page: ``runup_session_http`` -> ``runup_visitor_http``.
        return "runup_visitor" + session_cookie[len("runup_session"):]
    if session_cookie == "session":
        return COOKIE_NAME
    return f"{COOKIE_NAME}_{session_cookie}"

# How long a visitor stays signed in.
SESSION_LIFETIME = timedelta(days=30)


# ---------------------------------------------------------------------------
# The token that signs the session
# ---------------------------------------------------------------------------


def _secret() -> bytes:
    """The key that signs the cookie of the visitor."""
    configured = current_app.config.get("VISITOR_COOKIE_SECRET")
    if configured:
        return str(configured).encode("utf-8")
    # Without a separate key the key of the session is used. It is still
    # a different cookie with a different name, so the two cannot be
    # mistaken for one another.
    return current_app.config["SECRET_KEY"].encode("utf-8")


def _sign(payload: str) -> str:
    """The signature of a payload."""
    mac = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{mac}"


def _unsign(token: str) -> str | None:
    """The payload of a token, when the signature holds."""
    if not token or "." not in token:
        return None
    payload, _, signature = token.rpartition(".")
    expected = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return None
    return payload


def _issue(visitor_id: int) -> str:
    """A fresh token for a visitor."""
    expires = datetime.now(timezone.utc) + SESSION_LIFETIME
    payload = f"{visitor_id}|{int(expires.timestamp())}|{secrets.token_urlsafe(16)}"
    return _sign(payload)


def _read(token: str) -> int | None:
    """The visitor that a token belongs to, when it is still good."""
    payload = _unsign(token)
    if not payload:
        return None
    parts = payload.split("|")
    if len(parts) != 3:
        return None
    try:
        visitor_id = int(parts[0])
        expires = int(parts[1])
    except ValueError:
        return None
    if expires < int(datetime.now(timezone.utc).timestamp()):
        return None
    return visitor_id


# ---------------------------------------------------------------------------
# The state of the visitor
# ---------------------------------------------------------------------------


def current_visitor() -> Visitor | None:
    """The visitor of this request, when there is one.

    The visitor is looked for in the session first and in the cookie
    after that, so that the sign-in survives the closing of the tab.
    """
    if "visitor" in g:
        return g.visitor

    visitor = None
    visitor_id = session.get(SESSION_KEY)
    if visitor_id:
        visitor = db.session.get(Visitor, int(visitor_id))

    if visitor is None:
        token = request.cookies.get(cookie_name())
        if token:
            found = _read(token)
            if found:
                visitor = db.session.get(Visitor, found)
                if visitor is not None:
                    session[SESSION_KEY] = visitor.id
                    session.permanent = True

    if visitor is not None and not visitor.is_active:
        visitor = None
        session.pop(SESSION_KEY, None)

    g.visitor = visitor
    return visitor


def is_signed_in() -> bool:
    """True when somebody has signed in."""
    return current_visitor() is not None


def sign_in(visitor: Visitor, remember: bool = False) -> None:
    """Remember that this visitor has signed in.

    The name in the session is enough for the tab that is open now. The
    cookie is for the visitor who comes back later; it is his own and
    does not touch the cookie of the manager.
    """
    session[SESSION_KEY] = visitor.id
    session.permanent = True
    g.visitor = visitor

    if remember:
        # The answer is built by the place that called this, so the
        # cookie is left behind for it to write.
        g.visitor_cookie = _issue(visitor.id)
    else:
        # The visitor does not want to be remembered. Any cookie that
        # was left from an earlier visit is taken away.
        g.visitor_cookie = ""


def sign_out() -> None:
    """Forget the visitor."""
    session.pop(SESSION_KEY, None)
    g.visitor = None
    g.visitor_cookie = ""


def take_pending_cookie() -> str | None:
    """The cookie that is to be written on the answer, when there is one.

    An empty string means that the cookie is to be removed.
    """
    if "visitor_cookie" not in g:
        return None
    value = g.visitor_cookie
    del g.visitor_cookie
    return value


def write_cookie(response):
    """Write the cookie of the visitor on the answer."""
    value = take_pending_cookie()
    if value is None:
        return response
    if value == "":
        response.delete_cookie(cookie_name(), path="/")
        return response
    response.set_cookie(
        cookie_name(), value,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True, samesite="Lax",
        secure=bool(current_app.config.get("SESSION_COOKIE_SECURE")),
        path="/",
    )
    return response
