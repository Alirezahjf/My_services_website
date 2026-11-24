"""The safety of the samples and of the account of the visitor.

The rules that are checked here are the ones that keep the samples in
the hands of those who may use them, and keep the account of the
visitor away from the account of the manager.
"""

import pytest
from app.extensions import db
from app.models import Portfolio, PortfolioLiveLink, Product, Visitor
from app.services.frame_sources import csp_frame_sources, frame_hosts
from app.services.visitor_auth import COOKIE_NAME, SESSION_KEY


class _Link:
    """A small stand-in for a sample, for the sake of the addresses."""

    def __init__(self, url, mode="live", published=True):
        self.url = url
        self.display_mode = mode
        self.is_published = published


# ---------------------------------------------------------------------------
# The addresses that may be drawn inside the page
# ---------------------------------------------------------------------------


def test_only_the_live_samples_give_their_address():
    links = [
        _Link("https://live.example.com/a", "live", True),
        _Link("https://tab.example.com/b", "link", True),
        _Link("https://hidden.example.com/c", "live", False),
    ]
    assert frame_hosts(links) == ["https://live.example.com"]


def test_an_address_that_is_not_of_the_web_is_not_allowed():
    for url in ("javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "not a url", ""):
        assert frame_hosts([_Link(url)]) == []


def test_the_same_address_is_not_written_twice():
    links = [_Link("https://a.example.com/x"), _Link("https://a.example.com/y")]
    assert frame_hosts(links) == ["https://a.example.com"]


def test_the_policy_keeps_its_strictness_when_there_is_no_sample():
    policy = "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
    assert csp_frame_sources(policy, []) == policy


def test_the_policy_gains_only_the_frame_directive():
    policy = "default-src 'self'; object-src 'none'; frame-ancestors 'none'"
    result = csp_frame_sources(policy, ["https://a.example.com"])
    assert "frame-src 'self' https://a.example.com" in result
    assert "default-src 'self'" in result
    assert "object-src 'none'" in result
    assert "frame-ancestors 'none'" in result


def test_the_policy_does_not_get_two_frame_directives():
    policy = "default-src 'self'; frame-src 'none'"
    result = csp_frame_sources(policy, ["https://a.example.com"])
    assert result.count("frame-src") == 1


def test_the_site_allows_the_address_of_its_own_samples(client, app):
    with app.app_context():
        item = Portfolio(title="نمونه‌کار", slug="nm", is_published=True)
        db.session.add(item)
        db.session.flush()
        link = PortfolioLiveLink(portfolio_id=item.id, title="نمونه",
                                 url="https://samples.example.com/live",
                                 display_mode="live", is_published=True)
        db.session.add(link)
        db.session.commit()

    policy = client.get("/").headers.get("Content-Security-Policy", "")
    assert "frame-src" in policy
    assert "https://samples.example.com" in policy


def test_the_site_keeps_its_policy_when_there_is_no_sample(client, app):
    policy = client.get("/").headers.get("Content-Security-Policy", "")
    # The seeded site has no sample, and so the strict policy stays.
    assert "frame-src" not in policy
    assert "default-src 'self'" in policy
    assert "object-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy


# ---------------------------------------------------------------------------
# The account of the visitor
# ---------------------------------------------------------------------------


def test_the_cookie_of_the_visitor_is_of_the_site_and_hides_its_path(client, app):
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    response = client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
        "remember": "y",
    })
    header = response.headers.get("Set-Cookie", "")
    assert COOKIE_NAME in header
    assert "HttpOnly" in header
    assert "SameSite=Lax" in header
    # The path is written down, so that the cookie goes to the whole site.
    assert "Path=/" in header


def test_the_name_of_the_visitor_is_not_the_name_of_the_manager(client, app):
    """The two kinds of sign-in do not use the same name in the session."""
    assert SESSION_KEY == "runup_visitor_id"
    assert SESSION_KEY != "_user_id"


def test_the_sign_out_forgets_the_visitor_of_the_cookie(client, app):
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
        "remember": "y",
    })
    client.post("/account/logout")

    # The cookie is taken away, so that the next visit begins afresh.
    cookies = {cookie.key: cookie.value for cookie in client._cookies.values()}
    assert not cookies.get(COOKIE_NAME)
    body = client.get("/account/", follow_redirects=True).get_data(as_text=True)
    assert "ورود به حساب شما" in body


def test_the_rate_of_the_sign_in_is_limited(app, tmp_path):
    """A flood of attempts at the sign-in is turned away."""
    from app import create_app
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": True,
        "RATELIMIT_STORAGE_URI": "memory://",
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/limit.sqlite3",
        "UPLOAD_FOLDER": tmp_path / "up",
        "SECRET_KEY": "test",
    })
    with application.app_context():
        db.create_all()
    client = application.test_client()
    statuses = [client.post("/account/login", data={
        "email": "nobody@example.com", "password": "wrong",
    }).status_code for _ in range(10)]
    assert 429 in statuses


def test_the_address_of_the_visitor_is_not_written_down(client, app):
    """Only a hash of the address is kept, the same way the leads are."""
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()
        visitor_id = visitor.id

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    })

    with app.app_context():
        row = db.session.get(Visitor, visitor_id)
        assert row.last_login_ip_hash
        assert len(row.last_login_ip_hash) == 64
        assert "127.0.0.1" not in row.last_login_ip_hash


# ---------------------------------------------------------------------------
# The forms of the visitor
# ---------------------------------------------------------------------------


def test_the_forms_of_the_visitor_are_protected_by_a_token(app, tmp_path):
    """Without a token the forms of the visitor are turned away."""
    from app import create_app
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": True,
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/csrf.sqlite3",
        "UPLOAD_FOLDER": tmp_path / "up",
        "SECRET_KEY": "test",
    })
    with application.app_context():
        db.create_all()
    client = application.test_client()

    for path, data in (
        ("/account/register", {
            "display_name": "زهرا", "email": "zahra@example.com",
            "password": "a-long-enough-password", "confirm_password": "a-long-enough-password",
        }),
        ("/account/login", {"email": "zahra@example.com", "password": "a-long-enough-password"}),
        ("/account/logout", {}),
    ):
        response = client.post(path, data=data)
        assert response.status_code == 400, path

    with application.app_context():
        assert Visitor.query.count() == 0


def test_the_logout_of_the_visitor_needs_a_post(client, app):
    """The visitor cannot be thrown out by a link."""
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    })
    body = client.get("/account/").get_data(as_text=True)
    assert "کریم" in body

    # A plain address must not throw the visitor out.
    response = client.get("/account/logout")
    assert response.status_code in (404, 405)
    body = client.get("/account/").get_data(as_text=True)
    assert "کریم" in body
    assert "ورود به حساب شما" not in body


# ---------------------------------------------------------------------------
# The two pages live side by side
# ---------------------------------------------------------------------------


def test_the_visitor_cookie_of_the_old_page_has_a_name_of_its_own(app, tmp_path):
    """The old HTTP page and the secure page live in one browser.

    A cookie that is marked secure is not sent back over the plain
    channel, and so the old page needs a cookie of its own. The name of
    the visitor's cookie follows the name of the session cookie of the
    page.
    """
    from app import create_app
    from app.services.visitor_auth import cookie_name

    secure_app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/secure.sqlite3",
        "UPLOAD_FOLDER": tmp_path / "up",
        "SECRET_KEY": "test",
        "SESSION_COOKIE_NAME": "session",
    })
    old_app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/old.sqlite3",
        "UPLOAD_FOLDER": tmp_path / "up",
        "SECRET_KEY": "test",
        "SESSION_COOKIE_NAME": "runup_session_http",
    })

    with secure_app.app_context():
        secure_name = cookie_name()
    with old_app.app_context():
        old_name = cookie_name()

    assert secure_name != old_name
    assert "visitor" in secure_name
    assert "visitor" in old_name


def test_the_cookie_of_the_visitor_is_written_with_the_name_of_the_page(client, app):
    """The name of the cookie that goes out is the name of the page."""
    from app.services.visitor_auth import cookie_name

    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()
        expected = cookie_name()

    response = client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
        "remember": "y",
    })
    assert expected in response.headers.get("Set-Cookie", "")
