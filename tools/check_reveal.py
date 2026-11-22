"""Check whether the scroll-reveal animation leaves content invisible.

Elements marked ``.reveal`` start at ``opacity: 0`` and are only made
visible by an IntersectionObserver. If the observer never runs - because
JavaScript failed, the element sits outside the observed area, or the page
is printed - the content stays invisible. This script reports, for every
public page and viewport, how many reveal elements are still hidden and
whether they become visible after scrolling.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from playwright.sync_api import sync_playwright  # noqa: E402

from tools.browser import console_and_errors, launch  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9911"
PAGES = ["/", "/products", "/services", "/portfolio", "/about", "/contact",
         "/consultation", "/custom-solution", "/products/trend-radar"]
VIEWPORTS = [("mobile", 360, 800), ("tablet", 768, 1024), ("desktop", 1280, 900)]

JS = r"""
() => {
  const items = [...document.querySelectorAll('.reveal')];
  const hidden = items.filter(el => {
    const style = getComputedStyle(el);
    return parseFloat(style.opacity) < 0.05 || style.visibility === 'hidden';
  });
  return {
    total: items.length,
    hidden: hidden.length,
    hiddenSample: hidden.slice(0, 5).map(el => el.className),
  };
}
"""


def main():
    report = {"base": BASE, "results": {}}
    with sync_playwright() as pw:
        browser = launch(pw)
        for label, width, height in VIEWPORTS:
            context = browser.new_context(viewport={"width": width, "height": height})
            page = context.new_page()
            logs = console_and_errors(page)
            for path in PAGES:
                key = f"{label}{path}"
                page.goto(BASE + path, wait_until="networkidle")
                before = page.evaluate(JS)
                # Scroll to the bottom so every reveal element is observed.
                page.evaluate("""async () => {
                    const step = window.innerHeight * 0.8;
                    for (let y = 0; y < document.body.scrollHeight; y += step) {
                        window.scrollTo(0, y);
                        await new Promise(r => setTimeout(r, 60));
                    }
                    window.scrollTo(0, document.body.scrollHeight);
                    await new Promise(r => setTimeout(r, 400));
                }""")
                after = page.evaluate(JS)
                report["results"][key] = {"initial": before, "after_scroll": after}
            report.setdefault("logs", {})[label] = logs
            context.close()
        browser.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
