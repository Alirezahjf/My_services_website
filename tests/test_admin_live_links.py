"""The manager's side of the samples.

The manager makes a sample, chooses how it is shown, chooses the
product that goes with it, and says whether a sign-in is needed. The
page of the sample then behaves the way the manager asked.
"""

import pytest
from app.extensions import db
from app.models import Portfolio, PortfolioLiveLink, Product, Visitor


@pytest.fixture()
def portfolio(app):
    with app.app_context():
        item = Portfolio(title="نمونه‌کار آزمون", slug="azmoon-nmak", is_published=True)
        db.session.add(item)
        db.session.commit()
        db.session.refresh(item)
        return item.id


@pytest.fixture()
def product(app):
    with app.app_context():
        item = Product(name="محصول آزمون", slug="azmoon-mahsool",
                       short_description="شرح کوتاه", status="published")
        db.session.add(item)
        db.session.commit()
        db.session.refresh(item)
        return item.id


def test_the_manager_makes_a_sample(admin_client, app, portfolio, product):
    response = admin_client.post("/admin/live-links/new", data={
        "portfolio_id": portfolio,
        "product_id": product,
        "title": "نمونهٔ تازه",
        "url": "https://example.com/demo",
        "summary": "یک نمونهٔ تازه",
        "display_mode": "live",
        "requires_login": "y",
        "is_published": "y",
        "position": 1,
    }, follow_redirects=True)

    assert response.status_code == 200
    with app.app_context():
        link = PortfolioLiveLink.query.one()
        assert link.title == "نمونهٔ تازه"
        assert link.url == "https://example.com/demo"
        assert link.product_id == product
        assert link.portfolio_id == portfolio
        assert link.display_mode == "live"
        assert link.requires_login is True
        assert link.is_published is True


def test_the_manager_chooses_the_link_mode(admin_client, app, portfolio, product):
    admin_client.post("/admin/live-links/new", data={
        "portfolio_id": portfolio,
        "product_id": product,
        "title": "نمونهٔ لینک",
        "url": "https://example.com/elsewhere",
        "display_mode": "link",
        "is_published": "y",
    }, follow_redirects=True)

    with app.app_context():
        link = PortfolioLiveLink.query.one()
        assert link.display_mode == "link"
        assert link.is_live is False


def test_the_manager_may_leave_the_product_empty(admin_client, app, portfolio):
    admin_client.post("/admin/live-links/new", data={
        "portfolio_id": portfolio,
        "product_id": 0,
        "title": "نمونهٔ بی‌محصول",
        "url": "https://example.com/plain",
        "display_mode": "link",
        "is_published": "y",
    }, follow_redirects=True)

    with app.app_context():
        link = PortfolioLiveLink.query.one()
        assert link.product_id is None


def test_a_sample_without_a_url_is_not_saved(admin_client, app, portfolio):
    admin_client.post("/admin/live-links/new", data={
        "portfolio_id": portfolio,
        "title": "نمونهٔ بی‌نشانی",
        "url": "",
        "display_mode": "live",
    }, follow_redirects=True)

    with app.app_context():
        assert PortfolioLiveLink.query.count() == 0


def test_a_sample_with_an_address_that_is_not_of_the_web_is_not_saved(admin_client, app, portfolio):
    admin_client.post("/admin/live-links/new", data={
        "portfolio_id": portfolio,
        "title": "نمونهٔ بد",
        "url": "javascript:alert(1)",
        "display_mode": "live",
    }, follow_redirects=True)

    with app.app_context():
        assert PortfolioLiveLink.query.count() == 0


def test_the_manager_changes_a_sample(admin_client, app, portfolio, product):
    with app.app_context():
        link = PortfolioLiveLink(portfolio_id=portfolio, product_id=product,
                                 title="نمونهٔ کهنه", url="https://example.com/old",
                                 display_mode="live", is_published=True)
        db.session.add(link)
        db.session.commit()
        link_id = link.id

    admin_client.post(f"/admin/live-links/{link_id}/edit", data={
        "portfolio_id": portfolio,
        "product_id": product,
        "title": "نمونهٔ تازه",
        "url": "https://example.com/new",
        "display_mode": "link",
        "is_published": "y",
    }, follow_redirects=True)

    with app.app_context():
        link = db.session.get(PortfolioLiveLink, link_id)
        assert link.title == "نمونهٔ تازه"
        assert link.url == "https://example.com/new"
        assert link.display_mode == "link"


def test_the_manager_takes_a_sample_away(admin_client, app, portfolio):
    with app.app_context():
        link = PortfolioLiveLink(portfolio_id=portfolio, title="نمونه",
                                 url="https://example.com/x", display_mode="live")
        db.session.add(link)
        db.session.commit()
        link_id = link.id

    admin_client.post(f"/admin/live-links/{link_id}/delete", follow_redirects=True)

    with app.app_context():
        assert PortfolioLiveLink.query.count() == 0


def test_the_panel_shows_the_samples_and_the_accounts(admin_client, app, portfolio, product):
    with app.app_context():
        link = PortfolioLiveLink(portfolio_id=portfolio, product_id=product,
                                 title="نمونهٔ پنل", url="https://example.com/x",
                                 display_mode="live", is_published=True)
        visitor = Visitor(email="karim@example.com", display_name="کریم")
        visitor.set_password("a-long-enough-password")
        db.session.add_all([link, visitor])
        db.session.commit()

    response = admin_client.get("/admin/live-links")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "نمونهٔ پنل" in body
    assert "کریم" in body
    assert "karim@example.com" in body


def test_the_panel_is_closed_to_a_visitor(client, portfolio, product):
    """A visitor of the site cannot reach the panel."""
    response = client.get("/admin/live-links", follow_redirects=True)
    body = response.get_data(as_text=True)
    assert "نمونهٔ پنل" not in body
    # The visitor is sent to the page of the sign-in of the manager.
    assert "admin/login" in response.request.path or "ورود" in body


def test_the_sample_appears_on_the_page_of_the_sample_of_work(client, app, portfolio, product):
    with app.app_context():
        link = PortfolioLiveLink(portfolio_id=portfolio, product_id=product,
                                 title="نمونهٔ قابل استفاده", url="https://example.com/demo",
                                 display_mode="live", requires_login=True, is_published=True)
        db.session.add(link)
        db.session.commit()
        slug = db.session.get(Portfolio, portfolio).slug

    body = client.get(f"/portfolio/{slug}").get_data(as_text=True)
    assert "نمونهٔ قابل استفاده" in body
    assert "محصول مرتبط" in body
    assert "محصول آزمون" in body


def test_the_sample_appears_on_the_page_of_the_product(client, app, portfolio, product):
    with app.app_context():
        link = PortfolioLiveLink(portfolio_id=portfolio, product_id=product,
                                 title="نمونهٔ محصول", url="https://example.com/demo",
                                 display_mode="live", requires_login=True, is_published=True)
        db.session.add(link)
        db.session.commit()
        slug = db.session.get(Product, product).slug

    body = client.get(f"/products/{slug}").get_data(as_text=True)
    assert "نمونهٔ محصول" in body
    assert "این محصول را امتحان کنید" in body


def test_a_sample_of_a_work_that_is_not_published_is_not_shown(client, app, portfolio, product):
    with app.app_context():
        item = db.session.get(Portfolio, portfolio)
        item.is_published = False
        db.session.add(item)
        link = PortfolioLiveLink(portfolio_id=portfolio, product_id=product,
                                 title="نمونهٔ پنهان", url="https://example.com/hidden",
                                 display_mode="live", is_published=True)
        db.session.add(link)
        db.session.commit()
        slug = item.slug

    body = client.get(f"/portfolio/{slug}").get_data(as_text=True)
    assert "نمونهٔ پنهان" not in body
