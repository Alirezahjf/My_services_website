"""The account of the visitor and the samples of the products.

The rules that are checked here are the ones the visitor can see:

* a sample that asks for a sign-in is not given to anybody who has not
  signed in;
* a sample that does not ask for a sign-in is open to all;
* the account of a visitor never disturbs the account of the manager;
* the account of a visitor never touches the account of another
  visitor;
* a password is never written down as it is.
"""

import pytest
from app.extensions import db
from app.models import Portfolio, PortfolioLiveLink, Product, SampleAccess, Visitor
from app.services import visitor_auth


@pytest.fixture()
def portfolio(app):
    """A sample of work that is published."""
    with app.app_context():
        item = Portfolio(
            title="نمونه‌کار آزمون",
            slug="azmoon-nmak",
            summary="خلاصهٔ نمونه‌کار",
            description="توضیح نمونه‌کار",
            is_published=True,
        )
        db.session.add(item)
        db.session.commit()
        db.session.refresh(item)
        return item.id


@pytest.fixture()
def product(app):
    """A product that is published."""
    with app.app_context():
        item = Product(
            name="محصول آزمون",
            slug="azmoon-mahsool",
            short_description="شرح کوتاه",
            status="published",
        )
        db.session.add(item)
        db.session.commit()
        db.session.refresh(item)
        return item.id


@pytest.fixture()
def live_link(app, portfolio, product):
    """A sample that is given only to a visitor who has signed in."""
    with app.app_context():
        link = PortfolioLiveLink(
            portfolio_id=portfolio,
            product_id=product,
            title="نمونهٔ زندهٔ آزمون",
            url="https://example.com/demo",
            summary="یک نمونهٔ زنده",
            display_mode="live",
            requires_login=True,
            is_published=True,
        )
        db.session.add(link)
        db.session.commit()
        db.session.refresh(link)
        return link.id


# ---------------------------------------------------------------------------
# The account of the visitor
# ---------------------------------------------------------------------------


def test_register_creates_the_account_and_signs_the_visitor_in(client):
    response = client.post("/account/register", data={
        "display_name": "زهرا احمدی",
        "email": "Zahra@Example.com",
        "organization": "شرکت نمونه",
        "password": "a-long-enough-password",
        "confirm_password": "a-long-enough-password",
    }, follow_redirects=True)

    assert response.status_code == 200
    with client.application.app_context():
        visitor = Visitor.query.filter_by(email="zahra@example.com").first()
        assert visitor is not None
        assert visitor.display_name == "زهرا احمدی"
        assert visitor.organization == "شرکت نمونه"
        # The password is never written down as it is.
        assert "a-long-enough-password" not in visitor.password_hash
        assert visitor.check_password("a-long-enough-password")
        assert not visitor.check_password("another-password")
        assert visitor.login_count == 1


def test_register_refuses_a_duplicate_address(client, app):
    for _ in range(2):
        client.post("/account/register", data={
            "display_name": "زهرا احمدی",
            "email": "zahra@example.com",
            "password": "a-long-enough-password",
            "confirm_password": "a-long-enough-password",
        }, follow_redirects=True)

    with app.app_context():
        assert Visitor.query.filter_by(email="zahra@example.com").count() == 1


def test_register_refuses_two_different_passwords(client, app):
    client.post("/account/register", data={
        "display_name": "زهرا احمدی",
        "email": "zahra@example.com",
        "password": "a-long-enough-password",
        "confirm_password": "another-password",
    }, follow_redirects=True)

    with app.app_context():
        assert Visitor.query.count() == 0


def test_login_with_the_right_password_signs_the_visitor_in(client, app):
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    response = client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        visitor = Visitor.query.filter_by(email="karim@example.com").first()
        assert visitor.login_count == 1
    # The account of the visitor is shown.
    assert "حساب شما" in response.get_data(as_text=True)


def test_login_with_a_wrong_password_does_not_sign_the_visitor_in(client, app):
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    response = client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "the-wrong-password",
    }, follow_redirects=True)

    assert response.status_code == 200
    assert "نشانی رایانامه یا رمز عبور درست نیست" in response.get_data(as_text=True)


def test_logout_forgets_the_visitor(client, app):
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    }, follow_redirects=True)
    client.post("/account/logout", follow_redirects=True)

    response = client.get("/account/", follow_redirects=True)
    # The visitor is sent to the page of the sign-in.
    assert "ورود به حساب شما" in response.get_data(as_text=True)


# ---------------------------------------------------------------------------
# The samples
# ---------------------------------------------------------------------------


def test_a_sample_that_asks_for_a_sign_in_is_not_given_to_a_stranger(client, live_link):
    response = client.get(f"/samples/{live_link}", follow_redirects=True)

    body = response.get_data(as_text=True)
    assert "ورود به حساب شما" in body
    # The frame of the sample is not shown.
    assert "sample-frame" not in body


def test_the_sign_in_leads_back_to_the_sample(client, live_link):
    response = client.get(f"/samples/{live_link}")
    assert response.status_code == 302
    assert "/account/login" in response.headers["Location"]
    assert f"next=/samples/{live_link}" in response.headers["Location"]


def test_a_sample_that_asks_for_a_sign_in_is_given_after_the_sign_in(client, live_link):
    with client.application.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    })

    response = client.get(f"/samples/{live_link}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "sample-frame" in body
    assert "https://example.com/demo" in body


def test_the_opening_of_a_sample_is_written_down(client, live_link, app):
    with client.application.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()
        visitor_id = visitor.id

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    })
    client.get(f"/samples/{live_link}")

    with app.app_context():
        rows = SampleAccess.query.filter_by(visitor_id=visitor_id).all()
        assert len(rows) == 1
        assert rows[0].live_link_id == live_link
        link = db.session.get(PortfolioLiveLink, live_link)
        assert link.open_count == 1


def test_the_counter_of_a_sample_counts_the_people_and_not_the_visits(client, live_link, app):
    """A visitor who refreshes the page does not make the sample look
    busier than it is."""
    with client.application.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    })
    client.get(f"/samples/{live_link}")
    client.get(f"/samples/{live_link}")
    client.get(f"/samples/{live_link}")

    with app.app_context():
        # The counter counts the visitor once.
        link = db.session.get(PortfolioLiveLink, live_link)
        assert link.open_count == 1
        # But every opening is in the record.
        assert SampleAccess.query.count() == 3


def test_a_second_visitor_is_counted_on_their_own(client, live_link, app):
    with client.application.app_context():
        for name in ("first@example.com", "second@example.com"):
            visitor = Visitor(email=name, display_name="بازدیدکننده")
            visitor.set_password("a-long-enough-password")
            db.session.add(visitor)
        db.session.commit()

    for name in ("first@example.com", "second@example.com"):
        client.post("/account/logout")
        client.post("/account/login", data={
            "email": name,
            "password": "a-long-enough-password",
        })
        client.get(f"/samples/{live_link}")

    with app.app_context():
        link = db.session.get(PortfolioLiveLink, live_link)
        assert link.open_count == 2


def test_a_sample_that_is_open_is_given_to_anybody(client, app, portfolio, product):
    with app.app_context():
        link = PortfolioLiveLink(
            portfolio_id=portfolio,
            product_id=product,
            title="نمونهٔ آزاد",
            url="https://example.com/open",
            display_mode="link",
            requires_login=False,
            is_published=True,
        )
        db.session.add(link)
        db.session.commit()
        link_id = link.id

    response = client.get(f"/samples/{link_id}")
    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "https://example.com/open" in body
    # A sample that does not ask for a sign-in writes nothing down.
    with app.app_context():
        assert SampleAccess.query.count() == 0


def test_a_sample_that_is_not_published_is_not_there(client, app, portfolio, product):
    with app.app_context():
        link = PortfolioLiveLink(
            portfolio_id=portfolio,
            product_id=product,
            title="نمونهٔ پیش‌نویس",
            url="https://example.com/draft",
            display_mode="live",
            requires_login=False,
            is_published=False,
        )
        db.session.add(link)
        db.session.commit()
        link_id = link.id

    assert client.get(f"/samples/{link_id}").status_code == 404


def test_the_page_of_the_sample_names_the_product_that_goes_with_it(client, app, live_link, product):
    with client.application.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    })
    response = client.get(f"/samples/{live_link}")
    body = response.get_data(as_text=True)
    assert "محصول مرتبط" in body
    assert "محصول آزمون" in body


def test_a_sample_of_a_link_mode_opens_in_a_new_tab(client, app, portfolio, product):
    with app.app_context():
        link = PortfolioLiveLink(
            portfolio_id=portfolio,
            product_id=product,
            title="نمونهٔ لینک",
            url="https://example.com/elsewhere",
            display_mode="link",
            requires_login=False,
            is_published=True,
        )
        db.session.add(link)
        db.session.commit()
        link_id = link.id

    body = client.get(f"/samples/{link_id}").get_data(as_text=True)
    assert 'target="_blank"' in body
    assert "sample-frame" not in body


# ---------------------------------------------------------------------------
# The two accounts never mix
# ---------------------------------------------------------------------------


def test_the_account_of_a_visitor_does_not_disturb_the_manager(client, app, live_link):
    """The manager signs in at the panel, the visitor at the account.

    Both of them use the same browser, and neither of them may throw the
    other out.
    """
    client.post("/admin/login", data={
        "username": "admin",
        "password": "a-very-secure-test-password",
    }, follow_redirects=True)

    with client.application.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
    })

    # The manager is still in the panel.
    response = client.get("/admin/portfolios", follow_redirects=True)
    assert response.status_code == 200
    assert "مدیر آزمون" in response.get_data(as_text=True)

    # And the visitor is still the visitor.
    body = client.get(f"/samples/{live_link}").get_data(as_text=True)
    assert "sample-frame" in body


def test_the_account_of_a_visitor_does_not_disturb_another_visitor(client, app):
    """Two visitors in two browsers, each with their own account."""
    with app.app_context():
        first = Visitor(email="first@example.com", display_name="نخست")
        first.set_password("a-long-enough-password")
        second = Visitor(email="second@example.com", display_name="دوم")
        second.set_password("a-long-enough-password")
        db.session.add_all([first, second])
        db.session.commit()

    client.post("/account/login", data={
        "email": "first@example.com",
        "password": "a-long-enough-password",
    })
    body = client.get("/account/").get_data(as_text=True)
    assert "نخست" in body
    assert "دوم" not in body


def test_the_cookie_of_the_visitor_has_a_name_of_its_own(client, app):
    """The cookie of the visitor is not the cookie of the manager."""
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()

    client.post("/account/login", data={
        "email": "karim@example.com",
        "password": "a-long-enough-password",
        "remember": "y",
    }, follow_redirects=True)

    names = {cookie.key for cookie in client._cookies.values()}
    assert "runup_visitor" in names
    # The cookie of the session itself is a different one.
    assert "session" in names


def test_a_tampered_cookie_is_not_honoured(client, app):
    """A cookie that was changed by hand gives no access."""
    with app.app_context():
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add(visitor)
        db.session.commit()
        visitor_id = visitor.id

    client.set_cookie("runup_visitor", f"{visitor_id}.0000000000.deadbeef", domain="localhost")
    body = client.get("/account/").get_data(as_text=True)
    assert "حساب شما" not in body
