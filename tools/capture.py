#!/usr/bin/env python3
"""Take screenshots of the public pages, for visual comparison.

Usage::

    python tools/capture.py <output-directory> [base-url]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from tools.browser import launch  # noqa: E402

PAGES = [
    ("home", "/"),
    ("products", "/products"),
    ("services", "/services"),
    ("portfolio", "/portfolio"),
    ("about", "/about"),
    ("contact", "/contact"),
]

VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900},
    "mobile": {"width": 390, "height": 844},
}


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/shots")
    base = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:9911"
    out.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = launch(p)
        for view, size in VIEWPORTS.items():
            context = browser.new_context(
                viewport=size, device_scale_factor=1, locale="fa-IR")
            page = context.new_page()
            for name, path in PAGES:
                url = base + path
                try:
                    page.goto(url, wait_until="networkidle", timeout=30000)
                except Exception as exc:  # noqa: BLE001
                    print(f"  {name}: {exc}")
                    continue
                page.wait_for_timeout(2600)
                page.screenshot(path=str(out / f"{name}-{view}.png"), full_page=False)

                # The entrance animation runs when a block comes into
                # view, so the page is walked down before the full page
                # picture is taken. Otherwise the shot shows blocks that
                # are still waiting for their turn.
                height = page.evaluate("document.body.scrollHeight")
                step = 700
                for y in range(0, height, step):
                    page.evaluate(f"window.scrollTo(0,{y})")
                    page.wait_for_timeout(90)
                page.evaluate("window.scrollTo(0,0)")
                page.wait_for_timeout(900)

                page.screenshot(path=str(out / f"{name}-{view}-full.png"), full_page=True)
                print(f"  {name}-{view} saved")
            context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
