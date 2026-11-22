"""Compare two running servers page by page, interleaved.

Measuring the two versions one after the other is unreliable on a shared
machine: the numbers move by several percent between two identical runs.
This script therefore alternates between the two servers for every single
measurement, so that a slow moment on the machine affects both versions
equally. The result is the paired difference, which is what matters.

Usage: python tools/compare_performance.py <before_url> <after_url> [runs]
"""
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.sync_api import sync_playwright  # noqa: E402

from tools.browser import console_and_errors, launch  # noqa: E402

PAGES = ["/", "/products", "/products/trend-radar", "/services", "/portfolio",
         "/about", "/contact", "/consultation", "/legal/privacy"]
VIEWPORTS = [("mobile", 360, 800), ("tablet", 768, 1024), ("desktop", 1280, 900)]
CPU_THROTTLE = 4

INIT = """
window.__vitals = { lcp: 0, cls: 0, longTaskMs: 0 };
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) window.__vitals.lcp = e.startTime;
  }).observe({ type: 'largest-contentful-paint', buffered: true });
} catch (e) {}
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (!e.hadRecentInput) window.__vitals.cls += e.value;
    }
  }).observe({ type: 'layout-shift', buffered: true });
} catch (e) {}
try {
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) window.__vitals.longTaskMs += e.duration;
  }).observe({ type: 'longtask', buffered: true });
} catch (e) {}
"""


def measure(page, url, client):
    try:
        client.send("Network.setCacheDisabled", {"cacheDisabled": True})
    except Exception:
        pass
    page.goto(url, wait_until="load", timeout=60000)
    page.wait_for_timeout(1500)
    return page.evaluate("""() => {
      const nav = performance.getEntriesByType('navigation')[0] || {};
      const res = performance.getEntriesByType('resource');
      const v = window.__vitals || {};
      return {
        ttfb: nav.responseStart || 0,
        lcp: v.lcp || 0,
        cls: v.cls || 0,
        longTaskMs: v.longTaskMs || 0,
        transferBytes: res.reduce((a, r) => a + (r.transferSize || 0), 0) + (nav.transferSize || 0),
        requests: res.length + 1,
        external: res.filter(r => !r.name.startsWith(location.origin)).length,
      };
    }""")


def main():
    before_url = sys.argv[1].rstrip("/")
    after_url = sys.argv[2].rstrip("/")
    runs = int(sys.argv[3]) if len(sys.argv) > 3 else 5
    samples = {}
    with sync_playwright() as pw:
        browser = launch(pw)
        for vp, w, h in VIEWPORTS:
            context = browser.new_context(viewport={"width": w, "height": h},
                                          device_scale_factor=1, locale="fa-IR")
            page = context.new_page()
            page.add_init_script(INIT)
            client = page.context.new_cdp_session(page)
            try:
                client.send("Emulation.setCPUThrottlingRate", {"rate": CPU_THROTTLE})
            except Exception:
                pass
            for path in PAGES:
                key = f"{path}@{vp}"
                samples[key] = {"before": [], "after": []}
                for _ in range(runs):
                    # Interleaved: the two versions alternate, so a slow
                    # moment on the machine hits both of them.
                    samples[key]["before"].append(measure(page, before_url + path, client))
                    samples[key]["after"].append(measure(page, after_url + path, client))
            context.close()
        browser.close()

    metrics = ["lcp", "cls", "ttfb", "longTaskMs", "transferBytes", "requests"]
    summary = {}
    print(f"{'page@viewport':28} {'metric':14} {'before':>10} {'after':>10} {'delta':>9}  verdict")
    print("-" * 92)
    for metric in metrics:
        deltas = []
        for key, data in samples.items():
            b = statistics.median([s[metric] for s in data["before"]])
            a = statistics.median([s[metric] for s in data["after"]])
            if b:
                deltas.append((a - b) / b)
            summary.setdefault(metric, {"before": [], "after": [], "deltas": []})
            summary[metric]["before"].append(b)
            summary[metric]["after"].append(a)
            if b:
                summary[metric]["deltas"].append((a - b) / b)
        print()
    for metric in metrics:
        info = summary[metric]
        mb = statistics.median(info["before"])
        ma = statistics.median(info["after"])
        deltas = info["deltas"]
        if not deltas:
            print(f"{'ALL PAGES':28} {metric:14} {mb:>10.4g} {ma:>10.4g} {'n/a':>9}")
            continue
        mean = statistics.mean(deltas) * 100
        median = statistics.median(deltas) * 100
        better = sum(1 for d in deltas if d < -0.05)
        worse = sum(1 for d in deltas if d > 0.05)
        print(f"{'ALL PAGES (median)':28} {metric:14} {mb:>10.4g} {ma:>10.4g} "
              f"{median:>+8.1f}%  better={better} worse={worse} (mean {mean:+.1f}%)")

    out = {"before_url": before_url, "after_url": after_url, "runs": runs,
           "samples": samples, "summary": summary}
    with open("/tmp/perf/compare.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("\nwritten to /tmp/perf/compare.json")


if __name__ == "__main__":
    main()
