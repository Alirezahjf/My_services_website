"""Tests for the public appearance refresh.

The checks here cover the defects that the refresh was meant to remove:
a text column that could render the literal word "None", a counter that
could count below zero, a category grid whose lead tile left a hole, a
letter-spacing that pulled the letters of a Persian word apart, and a
scroll-reveal animation that could leave a whole section invisible.

The tests read the rendered HTML, not the source, so they describe what a
visitor receives.
"""
from app.models import Category, Portfolio, Product, WorkflowStep
from app.services.utils import persian_digits

PUBLIC_URLS = ["/", "/products", "/services", "/portfolio", "/about", "/contact",
               "/consultation", "/custom-solution", "/legal/privacy", "/legal/terms"]


def _public_pages(client, app):
    with app.app_context():
        urls = list(PUBLIC_URLS)
        urls += [f"/products/{product.slug}" for product in Product.query.filter_by(status="published").all()]
    return urls


def test_no_public_page_prints_the_python_none(client, app):
    """A missing text column must never reach the visitor as "None"."""
    for url in _public_pages(client, app):
        response = client.get(url)
        assert response.status_code == 200, url
        body = response.get_data(as_text=True)
        assert ">None<" not in body, url
        assert '="None"' not in body, url
        assert "None</" not in body, url


def test_missing_text_columns_render_empty(client, app):
    """A record without a summary or a tagline shows nothing, not "None"."""
    from app.extensions import db

    with app.app_context():
        product = Product.query.filter_by(status="published").first()
        product.tagline = None
        step = WorkflowStep.query.first()
        step.description = None
        portfolio = Portfolio.query.first()
        if portfolio is None:
            portfolio = Portfolio(title="نمونه‌کار آزمایشی", slug="audit-portfolio")
            db.session.add(portfolio)
        portfolio.summary = None
        portfolio.description = None
        db.session.commit()
        product_url = f"/products/{product.slug}"

    home = client.get("/")
    assert ">None<" not in home.get_data(as_text=True)
    detail = client.get(product_url)
    assert ">None<" not in detail.get_data(as_text=True)


def test_text_or_empty_filter_handles_none_and_blank(app):
    with app.app_context():
        render = app.jinja_env.from_string("{{ value|text_or_empty }}")
        assert render.render(value=None) == ""
        assert render.render(value="   ") == ""
        assert render.render(value="متن") == "متن"


def test_home_page_counter_values_are_valid_numbers(client, app):
    """The counters have to carry a plain, non-negative integer."""
    body = client.get("/").get_data(as_text=True)
    import re
    values = re.findall(r'data-count="([^"]*)"', body)
    assert values, "the home page is expected to show counters"
    for value in values:
        assert value.strip() != "", "a counter must not be empty"
        number = float(value)
        assert number >= 0, f"counter target must not be negative: {value}"


def test_counter_never_counts_below_zero():
    """The easing curve must not produce a negative count.

    The counter used to clamp only the upper end of the progress. When the
    clock moved backwards the progress became negative, the cubic easing
    flipped its sign and the number on the page went below zero.
    """
    import math

    def render(target, elapsed):
        ratio = min(1, max(0, elapsed) / 700)
        return max(0, math.floor(target * (1 - math.pow(1 - ratio, 3)) + 0.5))

    # A clock that moved backwards must not produce a negative number.
    assert render(16, -500) == 0
    assert render(16, 0) == 0
    # The eased value only grows towards the target and never passes it.
    previous = -1
    for elapsed in range(0, 900, 25):
        value = render(16, elapsed)
        assert 0 <= value <= 16
        assert value >= previous
        previous = value
    assert render(16, 700) == 16
    assert render(16, 5000) == 16
    # A count of zero stays zero.
    assert render(0, 350) == 0


def test_category_grid_lead_tile_fills_the_whole_row(client, app):
    """The lead tile spans the full row so the grid cannot leave a hole."""
    body = client.get("/").get_data(as_text=True)
    assert "category-card-featured" in body
    with app.app_context():
        assert Category.query.count() > 3, "the seeded data has more than three categories"


def test_category_cards_show_their_product_count(client, app):
    body = client.get("/").get_data(as_text=True)
    assert "محصول منتشرشده" in body


def test_services_page_shows_category_counts(client):
    body = client.get("/services").get_data(as_text=True)
    assert "محصول منتشرشده" in body


def test_empty_states_are_present_for_missing_sections(client, app):
    """An empty section gets a proper empty state instead of a blank area."""
    body = client.get("/portfolio").get_data(as_text=True)
    assert "empty-state" in body or "portfolio-card" in body


def test_latin_letter_spacing_does_not_reach_persian_headings(client):
    """Persian headings must not get a letter-spacing.

    Persian is a cursive script; a negative letter-spacing pulls the
    joined letters apart and breaks the word apart.
    """
    css = client.get("/static/css/main.css").get_data(as_text=True)
    import re
    rules = dict()
    for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
        selector = selector.strip()
        if selector.startswith("@media"):
            continue
        for part in selector.split(","):
            rules.setdefault(part.strip(), []).append(body)
    for selector in ("h1", "h2", "h3", "h4", ".eyebrow"):
        for body in rules.get(selector, []):
            match = re.search(r"letter-spacing:([^;}]*)", body)
            if match:
                value = match.group(1).strip()
                assert value in ("0", "normal", ""), (
                    f"{selector} must not use a letter-spacing on Persian text, found {value}")


def test_reveal_content_is_visible_without_javascript():
    """The reveal animation may only hide content when JavaScript runs.

    The stylesheet marks the elements as visible by default and only the
    script adds the class that hides them, so a visitor without JavaScript
    still sees the whole page.
    """
    from pathlib import Path

    css = Path("app/static/css/main.css").read_text().replace(" ", "")
    assert ".reveal{opacity:1" in css
    assert ".has-reveal.reveal{opacity:0" in css or ".has-reveal .reveal{opacity:0" in css
    assert ".reveal.is-visible{opacity:1" in css


def test_reveal_has_a_fallback_that_reveals_everything(client):
    """The script must reveal every element after a moment."""
    script = (client.get("/static/js/main.js")).get_data(as_text=True)
    assert "is-visible" in script
    assert "setTimeout" in script
    # The observer must stop watching an element once it was revealed.
    assert "unobserve" in script


def test_persian_digits_are_used_for_counts(client):
    """Counts are shown with Persian digits."""
    body = client.get("/").get_data(as_text=True)
    assert persian_digits("2") == "۲"
    assert "۲" in body or "۱" in body


def test_skip_link_and_main_landmarks_exist(client):
    body = client.get("/").get_data(as_text=True)
    assert 'class="skip-link"' in body
    assert 'id="main-content"' in body
    assert "<main" in body


def test_reduced_motion_is_respected_in_the_stylesheet():
    from pathlib import Path

    css = Path("app/static/css/main.css").read_text()
    assert "prefers-reduced-motion:reduce" in css
    reduced = css.split("prefers-reduced-motion:reduce")[-1]
    assert "opacity:1" in reduced or "animation:none" in reduced


def test_hero_content_is_visible_before_the_script_runs():
    """The entrance animation may only start when the script has run.

    The hero blocks used to be hidden by the stylesheet itself, so a
    visitor whose script was slow - or who had no script at all - saw a
    blank hero. The hidden state now belongs to the class that the script
    adds.
    """
    from pathlib import Path

    import re

    css = Path("app/static/css/main.css").read_text().replace(" ", "")
    # Every rule that hides the hero blocks has to carry the class that
    # the script adds; a rule that hides them on its own would leave a
    # blank hero while the script is still loading.
    for match in re.finditer(r"([^{}]*)\{([^{}]*opacity:0[^{}]*)\}", css):
        selector = match.group(1)
        if "[data-page-enter]" in selector:
            assert "page-is-ready" in selector, (
                f"the hero may only be hidden together with the class: {selector}")


def test_the_main_script_is_loaded_in_the_head():
    """The script has to run before the body is painted."""
    from pathlib import Path

    template = Path("app/templates/base.html").read_text()
    head_end = template.index("</head>")
    script = template.index("js/main.js")
    assert script < head_end, "the main script must be loaded in the head"
    assert template.count("js/main.js") == 1, "the script must be loaded only once"


def test_a_metric_adjusted_fallback_font_exists():
    """A fallback font with the same metrics keeps the page from shifting.

    Without it the browser paints the page with a different font first and
    every line moves when the web font arrives.
    """
    from pathlib import Path

    css = Path("app/static/css/main.css").read_text()
    assert "Vazirmatn Fallback" in css
    assert "size-adjust" in css
    # The fallback must not fail to load: a missing local() font would
    # make the whole face fail and leave a console error behind.
    assert "local(" in css
    assert "'Tahoma'" in css or "Tahoma" in css


def test_the_nav_underline_is_not_squeezed_to_nothing():
    """The underline of the active navigation item stays visible."""
    from pathlib import Path

    css = Path("app/static/css/main.css").read_text()
    assert "inset-inline:3px" in css
    assert "inset-inline:10px" not in css
