#!/usr/bin/env python3
"""Check the public pages for layout problems.

The script looks for three things on every page and every size:

* content that reaches outside the width of the page,
* blocks that are much taller than they are wide because a flex base
  was used as a height,
* content that stays invisible although it carries text.

Usage::

    python tools/check_layout.py [base-url]
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from tools.browser import launch  # noqa: E402

PAGES = [
    "/",
    "/products",
    "/services",
    "/portfolio",
    "/about",
    "/contact",
    "/consultation",
    "/custom-solution",
]

SIZES = [
    ("desktop", 1440, 900),
    ("tablet", 820, 1100),
    ("mobile", 390, 844),
]


def main() -> int:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9911"
    problems = 0

    with sync_playwright() as p:
        browser = launch(p)
        for label, width, height in SIZES:
            context = browser.new_context(viewport={"width": width, "height": height},
                                          locale="fa-IR")
            page = context.new_page()
            for path in PAGES:
                page.goto(base + path, wait_until="networkidle", timeout=30000)
                page.wait_for_timeout(700)

                # The page is walked down so that every block has had its
                # turn before the page is measured.
                total = page.evaluate("document.body.scrollHeight")
                for y in range(0, total, 800):
                    page.evaluate(f"window.scrollTo(0,{y})")
                    page.wait_for_timeout(40)
                page.wait_for_timeout(500)

                report = page.evaluate("""() => {
                    const doc = document.documentElement;
                    const overflow = doc.scrollWidth - doc.clientWidth;
                    const wide = [];
                    const tall = [];
                    const hidden = [];
                    const limit = doc.clientWidth;

                    // A block that is cut off by one of its parents does
                    // not make the page wider.
                    const clipped = (el) => {
                        let node = el.parentElement;
                        while (node && node !== document.body) {
                            const cs = getComputedStyle(node);
                            if (cs.overflowX !== 'visible') return true;
                            node = node.parentElement;
                        }
                        return false;
                    };

                    document.querySelectorAll('body *').forEach((el) => {
                        const box = el.getBoundingClientRect();
                        if (box.width === 0 && box.height === 0) return;
                        const cs = getComputedStyle(el);

                        // The parts of a drawing are not the page.
                        if (el.closest('svg')) return;
                        // The answer of a closed question is meant to be
                        // out of sight until the question is opened.
                        if (el.closest('details:not([open])')) return;
                        if (el.closest('[hidden]')) return;
                        // The lights and the moving row are wider than
                        // the page on purpose; the section that holds
                        // them hides the rest.
                        if (el.classList.contains('hero-glow')) return;
                        if (el.closest('.kinetic-strip')) return;
                        if (el.classList.contains('hero-noise')) return;

                        // Something reaches outside the page. A block that
                        // is cut off by one of its parents does not push
                        // the page sideways, so it is not a problem.
                        if (box.right > limit + 2 || box.left < -2) {
                            if (cs.position !== 'fixed' && !clipped(el)) {
                                wide.push(el.tagName + '.' + (el.className || '') +
                                          ' [' + Math.round(box.left) + '..' +
                                          Math.round(box.right) + ']');
                            }
                        }

                        // A block that is far taller than it is wide.
                        if (box.height > 320 && box.width > 0 &&
                            box.height > box.width * 3.5 &&
                            el.children.length === 0) {
                            tall.push(el.tagName + '.' + (el.className || '') +
                                      ' ' + Math.round(box.width) + 'x' +
                                      Math.round(box.height));
                        }

                        // Text that cannot be seen.
                        if (parseFloat(cs.opacity) < 0.05 &&
                            cs.visibility !== 'hidden' &&
                            box.height > 0 && el.textContent.trim().length > 3) {
                            hidden.push(el.tagName + '.' + (el.className || ''));
                        }
                    });

                    return {
                        overflow,
                        wide: wide.slice(0, 4),
                        tall: tall.slice(0, 4),
                        hidden: hidden.slice(0, 6),
                    };
                }""")

                issues = []
                if report["overflow"] > 2:
                    issues.append(f"page is {report['overflow']}px wider than the screen")
                if report["wide"]:
                    issues.append(f"outside: {report['wide']}")
                if report["tall"]:
                    issues.append(f"too tall: {report['tall']}")
                if report["hidden"]:
                    issues.append(f"hidden: {report['hidden']}")

                if issues:
                    problems += 1
                    print(f"  {label} {path}")
                    for issue in issues:
                        print(f"      - {issue}")

            context.close()
        browser.close()

    print("PASS — no layout problem found" if problems == 0
          else f"FAIL — {problems} page/size combinations need a look")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
