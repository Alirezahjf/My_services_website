"""Measure page performance + capture screenshots for a running site.

Usage: python tools/measure.py <base_url> <label> [outdir]
Dev-only helper; not part of the deployed application.
"""
import json
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tools.browser import launch, console_and_errors  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

PAGES = [
    ("home", "/"),
    ("products", "/products"),
    ("product_detail", "/products/trend-radar"),
    ("services", "/services"),
    ("portfolio", "/portfolio"),
    ("about", "/about"),
    ("contact", "/contact"),
    ("consultation", "/consultation"),
    ("legal_privacy", "/legal/privacy"),
    ("notfound", "/this-page-does-not-exist"),
]

VIEWPORTS = [("mobile", 360, 800), ("tablet", 768, 1024), ("desktop", 1280, 900), ("wide", 1920, 1080)]

# 4x CPU throttle approximates a mid-range mobile device.
CPU_THROTTLE = 4


def collect_metrics(page, url):
    client = page.context.new_cdp_session(page)
    try:
        client.send("Network.enable")
        client.send("Network.setCacheDisabled", {"cacheDisabled": True})
    except Exception:
        pass
    client.send("Emulation.setCPUThrottlingRate", {"rate": CPU_THROTTLE})
    # Install observers before navigation so LCP/CLS are captured from the start.
    page.add_init_script(
        """
        window.__vitals = { lcp: 0, cls: 0, longTaskMs: 0, shifts: [] };
        try {
          new PerformanceObserver((list) => {
            for (const e of list.getEntries()) {
              window.__vitals.lcp = e.startTime;
              const el = e.element;
              if (el) window.__vitals.lcpElement = el.tagName + '.' + (el.className || '').toString().split(' ')[0];
            }
          }).observe({ type: 'largest-contentful-paint', buffered: true });
        } catch (e) {}
        try {
          new PerformanceObserver((list) => {
            for (const e of list.getEntries()) {
              if (!e.hadRecentInput) {
                window.__vitals.cls += e.value;
                window.__vitals.shifts.push({v: e.value, t: e.startTime,
                  n: (e.sources || []).map(s => (s.node && s.node.nodeName) || '').join(',')});
              }
            }
          }).observe({ type: 'layout-shift', buffered: true });
        } catch (e) {}
        try {
          new PerformanceObserver((list) => {
            for (const e of list.getEntries()) window.__vitals.longTaskMs += e.duration;
          }).observe({ type: 'longtask', buffered: true });
        } catch (e) {}
      """
    )
    t0 = time.perf_counter()
    response = page.goto(url, wait_until="load", timeout=60000)
    load_ms = (time.perf_counter() - t0) * 1000
    page.wait_for_timeout(1500)
    try:
        client.send("Emulation.setCPUThrottlingRate", {"rate": 1})
    except Exception:
        pass
    data = page.evaluate(
        """() => {
        const nav = performance.getEntriesByType('navigation')[0] || {};
        const paints = Object.fromEntries(performance.getEntriesByType('paint').map(p => [p.name, p.startTime]));
        const res = performance.getEntriesByType('resource');
        const v = window.__vitals || {};
        return {
          ttfb: nav.responseStart || 0,
          domContentLoaded: nav.domContentLoadedEventEnd || 0,
          loadEvent: nav.loadEventEnd || 0,
          lcp: v.lcp || paints['largest-contentful-paint'] || 0,
          lcpElement: v.lcpElement || '',
          fcp: paints['first-contentful-paint'] || 0,
          cls: v.cls || 0,
          shifts: v.shifts || [],
          longTaskMs: v.longTaskMs || 0,
          transferBytes: res.reduce((a, r) => a + (r.transferSize || 0), 0) + (nav.transferSize || 0),
          encodedBytes: res.reduce((a, r) => a + (r.encodedBodySize || 0), 0) + (nav.encodedBodySize || 0),
          requests: res.length + 1,
          externalRequests: res.filter(r => !r.name.startsWith(location.origin)).map(r => r.name),
        };
      }"""
    )
    data["status"] = response.status if response else 0
    data["wallClockMs"] = load_ms
    data["htmlBytes"] = len(response.body()) if response else 0
    try:
        client.detach()
    except Exception:
        pass
    return data


def run(base_url, label, outdir):
    os.makedirs(outdir, exist_ok=True)
    results = {}
    errors = {}
    with sync_playwright() as p:
        browser = launch(p)
        for vp_name, w, h in VIEWPORTS:
            for name, path in PAGES:
                key = f"{name}@{vp_name}"
                ctx = browser.new_context(
                    viewport={"width": w, "height": h},
                    device_scale_factor=1,
                    locale="fa-IR",
                    ignore_https_errors=False,
                )
                page = ctx.new_page()
                logs = console_and_errors(page)
                url = base_url.rstrip("/") + path
                try:
                    m = collect_metrics(page, url)
                except Exception as exc:
                    m = {"error": str(exc)}
                results[key] = m
                if logs["console"] or logs["pageerror"] or logs["requestfailed"] or logs["response"]:
                    errors[key] = logs
                # screenshot for the visual before/after comparison
                shot = os.path.join(outdir, f"{label}-{name}-{vp_name}.png")
                try:
                    page.screenshot(path=shot, full_page=(vp_name == "desktop"))
                except Exception:
                    pass
                ctx.close()
        browser.close()
    out = {"label": label, "base_url": base_url, "results": results, "errors": errors}
    with open(os.path.join(outdir, f"{label}-metrics.json"), "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    return out


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:9900"
    label = sys.argv[2] if len(sys.argv) > 2 else "run"
    outdir = sys.argv[3] if len(sys.argv) > 3 else "/tmp/perf"
    out = run(base, label, outdir)
    rows = []
    for k, v in out["results"].items():
        if v.get("error"):
            rows.append((k, "ERROR", v["error"][:60]))
            continue
        rows.append(
            (
                k,
                f"LCP={v.get('lcp', 0):.0f}",
                f"CLS={v.get('cls', 0):.3f}",
                f"TTFB={v.get('ttfb', 0):.0f}",
                f"longTask={v.get('longTaskMs', 0):.0f}",
                f"bytes={v.get('transferBytes', 0)}",
                f"req={v.get('requests', 0)}",
                f"ext={len(v.get('externalRequests', []))}",
            )
        )
    for r in rows:
        print(" | ".join(str(x) for x in r))
    print("\nERRORS:", json.dumps(out["errors"], ensure_ascii=False)[:3000])
