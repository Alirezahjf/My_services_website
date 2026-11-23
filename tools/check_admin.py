#!/usr/bin/env python3
"""Check that the panel of the manager still works.

The script builds its own database, so the data of the site is not
touched. It signs in and walks through every page of the panel, and it
reports the console errors and the failed requests of each page.

Usage::

    python tools/check_admin.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# The database of the check is a temporary one, so the data of the site
# is never written to. The address can be given on the command line, so
# the script and the server can share the same file.
_DB = os.environ.get("ADMIN_CHECK_DATABASE")
if not _DB:
    _TMP = tempfile.mkdtemp(prefix="runup-admin-check-")
    _DB = f"{_TMP}/check.sqlite3"
os.environ["DATABASE_URL"] = f"sqlite:///{_DB}"
os.environ["SECRET_KEY"] = "admin-check-secret-key-not-used-anywhere-else"

from playwright.sync_api import sync_playwright  # noqa: E402

from app import create_app  # noqa: E402
from app.models import AdminUser, Category, Product  # noqa: E402
from tools.browser import launch  # noqa: E402

PAGES = [
    "/admin/",
    "/admin/products",
    "/admin/categories",
    "/admin/features",
    "/admin/integrations",
    "/admin/portfolios",
    "/admin/media",
    "/admin/pages",
    "/admin/menus",
    "/admin/content",
    "/admin/services",
    "/admin/faqs",
    "/admin/leads",
    "/admin/agents",
    "/admin/agent-activity",
    "/admin/repositories",
    "/admin/settings",
    "/admin/workflow",
    "/admin/activity",
]

USERNAME = "check-admin"
PASSWORD = "check-admin-password-1234"


def main() -> int:
    app = create_app()
    with app.app_context():
        from app.extensions import db
        db.create_all()
        user = AdminUser(username=USERNAME, is_superadmin=True)
        user.set_password(PASSWORD)
        db.session.add(user)
        # One category and one product, so the pages have something to
        # show and the counters are not zero.
        category = Category(name="دستهٔ آزمایشی", slug="check-category",
                            icon="brain", is_visible=True, position=0)
        db.session.add(category)
        db.session.flush()
        product = Product(name="محصول آزمایشی", slug="check-product",
                          category_id=category.id, status="published",
                          commercial_status="concept", tagline="برچسب آزمایشی",
                          short_description="توضیح کوتاه آزمایشی")
        db.session.add(product)
        db.session.commit()

    failures = 0

    with sync_playwright() as p:
        browser = launch(p)
        context = browser.new_context(viewport={"width": 1440, "height": 900},
                                      locale="fa-IR")
        page = context.new_page()
        console: list[str] = []
        errors: list[str] = []
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        base = "http://127.0.0.1:9912"
        page.goto(base + "/admin/login", wait_until="networkidle")
        page.fill("input[name=username]", USERNAME)
        page.fill("input[name=password]", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_load_state("networkidle")

        if "/admin/login" in page.url and "/admin/" not in page.url:
            print("FAIL — the sign in did not go through")
            return 1
        print("signed in")

        for path in PAGES:
            console.clear()
            errors.clear()
            response = page.goto(base + path, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(400)
            status = response.status if response else 0
            notes = [n for n in console + errors if "favicon" not in n]
            if status != 200 or notes:
                failures += 1
                print(f"  {path}: {status}")
                for note in notes[:4]:
                    print(f"      - {note[:180]}")
            else:
                print(f"  {path}: {status}")

        context.close()
        browser.close()

    print("PASS — the panel answers on every page" if failures == 0
          else f"FAIL — {failures} pages need a look")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
