/* Legacy-HTTP upgrade helper.
 *
 * The plain-HTTP listener exists only so that links shared earlier keep
 * opening. When the secure address is reachable the visitor is moved there;
 * otherwise the page stays as it is, because the HTTP version is the one that
 * is known to work for that device.
 *
 * The secure origin is injected by the server through a data attribute on the
 * script tag, which keeps the Content-Security-Policy free of inline script
 * permissions.
 */
(function () {
  'use strict';
  var script = document.currentScript || document.querySelector('script[data-https-upgrade]');
  if (!script) return;
  var target = (script.getAttribute('data-secure-origin') || '').replace(/\/+$/, '');
  if (!target) return;

  var PROBE = target + '/static/https-probe.txt';
  var TIMEOUT_MS = 2500;
  var RETRY_MS = 10 * 60 * 1000;
  var STORAGE_KEY = 'runup-https-upgrade';

  function schedule() {
    try {
      window.setTimeout(attempt, RETRY_MS);
    } catch (e) {
      /* no timer available: the visitor simply stays on the HTTP page. */
    }
  }

  function attempt() {
    if (!window.fetch) {
      schedule();
      return;
    }
    var controller = typeof AbortController === 'function' ? new AbortController() : null;
    var timer = window.setTimeout(function () {
      if (controller) controller.abort();
    }, TIMEOUT_MS);
    var options = { mode: 'no-cors', cache: 'no-store', credentials: 'omit' };
    if (controller) options.signal = controller.signal;

    window.fetch(PROBE, options).then(function () {
      window.clearTimeout(timer);
      try {
        window.sessionStorage.setItem(STORAGE_KEY, '1');
      } catch (e) {
        /* storage is optional. */
      }
      window.location.replace(
        target + window.location.pathname + window.location.search + window.location.hash
      );
    }).catch(function () {
      window.clearTimeout(timer);
      schedule();
    });
  }

  try {
    if (window.sessionStorage.getItem(STORAGE_KEY) === '1') {
      schedule();
      return;
    }
  } catch (e) {
    /* storage is optional. */
  }

  // The check starts after the page has painted. The visitor sees the
  // content first and the move to the secure address happens a moment
  // later, so the probe never delays the first paint of the page.
  var start = function () { attempt(); };
  if (window.requestIdleCallback) {
    window.requestIdleCallback(start, { timeout: 1500 });
  } else if (document.readyState === 'complete') {
    window.setTimeout(start, 0);
  } else {
    window.addEventListener('load', function () { window.setTimeout(start, 0); });
  }
})();
