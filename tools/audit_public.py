"""Audit the rendered public pages for the defects the refresh has to remove.

The audit reads the live DOM instead of the HTML source, so it sees what a
visitor actually gets: literal "None" text, empty category cards, the
featured-card order, and counters that end up below zero.
"""
import json
import sys

sys.path.insert(0, ".")

from playwright.sync_api import sync_playwright  # noqa: E402

from tools.browser import console_and_errors, launch  # noqa: E402

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9911"
PAGES = ["/", "/products", "/services", "/portfolio", "/about", "/contact",
         "/consultation", "/custom-solution"]

JS = r"""
() => {
  const text = document.body.innerText;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const noneNodes = [];
  while (walker.nextNode()) {
    const value = walker.currentNode.nodeValue;
    if (value && value.includes('None')) {
      noneNodes.push({
        text: value.trim().slice(0, 120),
        parent: walker.currentNode.parentElement
          ? walker.currentNode.parentElement.className || walker.currentNode.parentElement.tagName
          : '',
      });
    }
  }
  const attrNone = [];
  document.querySelectorAll('*').forEach(el => {
    for (const attr of el.attributes) {
      if (attr.value === 'None' || attr.value.includes('None')) {
        attrNone.push({ tag: el.tagName, cls: el.className, attr: attr.name, value: attr.value });
      }
    }
  });
  const cards = [...document.querySelectorAll('.category-card')].map(card => ({
    name: (card.querySelector('h3') || {}).textContent || '',
    featured: card.classList.contains('category-card-featured'),
    count: (card.querySelector('.category-content > div span') || {}).textContent || '',
  }));
  const counters = [...document.querySelectorAll('[data-count]')].map(el => ({
    target: el.dataset.count,
    rendered: el.textContent.trim(),
  }));
  const empties = [...document.querySelectorAll('.empty-state, .editorial-empty')].map(el => ({
    cls: el.className,
    heading: (el.querySelector('h2, h3') || {}).textContent || '',
  }));
  return {
    title: document.title,
    noneNodes,
    attrNone,
    cards,
    counters,
    empties,
    hasSkipLink: !!document.querySelector('.skip-link'),
    h1: [...document.querySelectorAll('h1')].map(h => h.textContent.trim()),
  };
}
"""


def main():
    report = {"base": BASE, "pages": {}}
    with sync_playwright() as pw:
        browser = launch(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        logs = console_and_errors(page)
        for path in PAGES:
            url = BASE + path
            response = page.goto(url, wait_until="networkidle")
            data = page.evaluate(JS)
            data["status"] = response.status if response else None
            report["pages"][path] = data
        report["logs"] = logs
        browser.close()
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
