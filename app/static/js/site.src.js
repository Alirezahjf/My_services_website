(() => {
  'use strict';
  const menuButton = document.querySelector('[data-menu-toggle]');
  const nav = document.querySelector('[data-nav]');
  if (menuButton && nav) {
    menuButton.addEventListener('click', () => {
      const open = menuButton.getAttribute('aria-expanded') === 'true';
      menuButton.setAttribute('aria-expanded', String(!open));
      nav.classList.toggle('is-open', !open);
    });
    document.addEventListener('click', (event) => {
      if (!nav.contains(event.target) && !menuButton.contains(event.target)) {
        nav.classList.remove('is-open');
        menuButton.setAttribute('aria-expanded', 'false');
      }
    });
  }
  // The header gets a soft edge once the page has moved. It is also
  // given the old class, because the sheet of the site uses it.
  const header = document.querySelector('[data-header]');
  if (header) {
    let headerQueued = false;
    const updateHeader = () => {
      headerQueued = false;
      const moved = window.scrollY > 12;
      header.classList.toggle('is-sticky', window.scrollY > 100);
      header.classList.toggle('is-scrolled', moved);
    };
    window.addEventListener('scroll', () => {
      if (!headerQueued) {
        headerQueued = true;
        requestAnimationFrame(updateHeader);
      }
    }, { passive: true });
    window.addEventListener('resize', updateHeader, { passive: true });
    updateHeader();
  }
  document.querySelectorAll('[data-dismiss]').forEach(button => {
    button.addEventListener('click', () => button.closest('.alert')?.remove());
  });
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const revealItems = document.querySelectorAll('.reveal');
  if (revealItems.length) {
    if ('IntersectionObserver' in window && !reducedMotion) {
      // The elements are visible by default; only when the observer is
      // available they are hidden first and faded in while they scroll
      // into view. Without JavaScript the content stays readable.
      document.documentElement.classList.add('has-reveal');

      // The elements are watched through their closest grid or list, not
      // one by one. A grid of thirteen cards would otherwise need thirteen
      // separate observations and thirteen separate class changes; with
      // the container the whole group is revealed in one step.
      const groups = new Map();
      revealItems.forEach(item => {
        const group = item.parentElement || item;
        if (!groups.has(group)) groups.set(group, []);
        groups.get(group).push(item);
      });

      const observer = new IntersectionObserver(entries => {
        entries.forEach(entry => {
          if (!entry.isIntersecting) return;
          const items = groups.get(entry.target) || [];
          items.forEach((item, index) => {
            item.style.transitionDelay = `${(index % 3) * 60}ms`;
            item.classList.add('is-visible');
          });
          observer.unobserve(entry.target);
        });
      }, { threshold: 0.08, rootMargin: '0px 0px -8% 0px' });
      groups.forEach((items, group) => observer.observe(group));

      // Anything that never entered the viewport - because the page is
      // short, the observer missed it, or the browser restored a scroll
      // position - is revealed after a moment so that no content can stay
      // permanently invisible.
      window.setTimeout(() => {
        revealItems.forEach(item => item.classList.add('is-visible'));
      }, 2500);
    } else {
      revealItems.forEach(item => item.classList.add('is-visible'));
    }
  }
  const dialog = document.querySelector('[data-lightbox-dialog]');
  if (dialog) {
    const image = dialog.querySelector('img');
    const caption = dialog.querySelector('p');
    document.querySelectorAll('[data-lightbox]').forEach(button => {
      button.addEventListener('click', () => {
        image.src = button.dataset.lightbox;
        image.alt = button.dataset.title || 'نمایش تصویر';
        caption.textContent = button.dataset.title || '';
        dialog.showModal();
      });
    });
    dialog.querySelector('[data-lightbox-close]')?.addEventListener('click', () => dialog.close());
    dialog.addEventListener('click', event => {
      if (event.target === dialog) dialog.close();
    });
    dialog.addEventListener('close', () => { image.src = ''; });
  }
  document.querySelectorAll('form[data-loading-form]').forEach(form => {
    form.addEventListener('submit', () => {
      const button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.dataset.originalText = button.textContent;
        button.textContent = 'در حال ارسال…';
      }
    });
  });
})();

/* Purposeful, resource-light motion and interaction system. No third-party runtime. */
(() => {
  'use strict';
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  document.documentElement.classList.add('motion-ready');
  // The class is added straight away, before the first paint, so that the
  // entrance animation starts from the hidden state instead of the content
  // appearing and then disappearing again.
  document.documentElement.classList.add('page-is-ready');
  const progress = document.querySelector('[data-scroll-progress]');
  const parallax = [...document.querySelectorAll('[data-parallax]')];
  if (progress || (parallax.length && !reduce.matches && window.innerWidth > 820)) {
    let queued = false;
    const update = () => {
      const y = window.scrollY;
      if (progress) {
        const height = Math.max(1, document.documentElement.scrollHeight - window.innerHeight);
        progress.style.transform = `scaleX(${Math.min(1, y / height)})`;
      }
      if (!reduce.matches && window.innerWidth > 820) parallax.forEach(el => {
        const bounds = el.getBoundingClientRect();
        if (bounds.bottom > 0 && bounds.top < window.innerHeight) {
          const offset = Math.max(-18, Math.min(18, -bounds.top * Number(el.dataset.parallax || .03)));
          el.style.setProperty('--parallax-y', `${offset}px`);
        }
      });
      queued = false;
    };
    window.addEventListener('scroll', () => { if (!queued) { queued = true; requestAnimationFrame(update); } }, { passive: true });
    update();
  }
  const counters = document.querySelectorAll('[data-count]');
  if (counters.length && 'IntersectionObserver' in window && !reduce.matches) {
    const counterObserver = new IntersectionObserver(entries => entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const el = entry.target;
      // The target comes from the page and must be a plain, non-negative
      // number. Anything else ("None", "", a negative value) would be
      // rendered as NaN or as a negative count, so it is rejected here and
      // the server-rendered value stays untouched.
      const target = Number(el.dataset.count);
      if (!Number.isFinite(target) || target < 0) {
        el.removeAttribute('data-count');
        counterObserver.unobserve(el);
        return;
      }
      const start = performance.now();
      const tick = now => {
        // The clock can jump backwards, so the progress is clamped to the
        // 0..1 range. Without the clamp a negative progress flips the sign
        // of the easing curve and the counter runs below zero.
        const elapsed = Math.max(0, now - start);
        const ratio = Math.min(1, elapsed / 700);
        const eased = target * (1 - Math.pow(1 - ratio, 3));
        el.textContent = new Intl.NumberFormat('fa-IR').format(Math.max(0, Math.round(eased)));
        if (ratio < 1) requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick); counterObserver.unobserve(el);
    }), { threshold: .4 });
    counters.forEach(el => counterObserver.observe(el));
  }
  const copyText = async (text, button) => {
    try {
      if (navigator.clipboard && window.isSecureContext) await navigator.clipboard.writeText(text);
      else {
        const area = document.createElement('textarea'); area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
        document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove();
      }
      const previous = button.textContent; button.textContent = 'کپی شد ✓'; button.classList.add('is-success');
      setTimeout(() => { button.textContent = previous; button.classList.remove('is-success'); }, 1800);
    } catch (_) { button.textContent = 'کپی نشد'; }
  };
  document.querySelectorAll('[data-copy],[data-copy-target]').forEach(button => button.addEventListener('click', () => {
    const text = button.dataset.copy || document.getElementById(button.dataset.copyTarget)?.textContent;
    if (text) copyText(text.trim(), button);
  }));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      document.querySelector('[data-nav]')?.classList.remove('is-open');
      document.querySelector('[data-menu-toggle]')?.setAttribute('aria-expanded', 'false');
    }
  });
  if (window.matchMedia('(pointer:fine)').matches && !reduce.matches) {
    document.querySelectorAll('[data-spotlight-card],.service-card,.feature-card').forEach(card => {
      let frame = 0, point = null;
      card.addEventListener('pointermove', event => {
        point = { x: event.clientX, y: event.clientY };
        if (frame) return;
        frame = requestAnimationFrame(() => {
          const box = card.getBoundingClientRect();
          if (point) {
            card.style.setProperty('--pointer-x', `${point.x - box.left}px`);
            card.style.setProperty('--pointer-y', `${point.y - box.top}px`);
          }
          frame = 0;
        });
      });
      card.addEventListener('pointerleave', () => {
        point = null;
        card.style.removeProperty('--pointer-x');
        card.style.removeProperty('--pointer-y');
      });
    });
  }
  document.querySelectorAll('.section-heading,.service-card,.feature-card,.requirement-card,.why-content>ul>li').forEach(el => {
    if (!el.classList.contains('reveal')) el.classList.add('reveal', 'is-visible');
  });
})();

/* ==========================================================================
   The movement of the pages.

   This part was written as its own file while the pages were being
   rebuilt. It is joined to the script of the site here, so the browser
   fetches one file instead of two.
   ========================================================================== */

/* ==========================================================================
   RunUp — the motion layer.

   Everything here is written for the DOM that the server renders. There
   is no framework, no runtime is fetched, and the whole file is a few
   kilobytes.

   Two rules shape this file:

   * Nothing that carries content is hidden unless the visitor asked for
     movement. Without JavaScript, or with less movement requested, the
     page is a plain, complete page.
   * Only transform and opacity are animated. Nothing that would make the
     browser lay the page out again.
   ========================================================================== */

(() => {
  'use strict';

  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(pointer: fine)');

  const isCalm = () => motionQuery.matches;
  const canHover = () => finePointer.matches && !isCalm();

  /* ------------------------------------------------------------------
     Splitting a heading into lines.

     The heading is wrapped in a line per row of text. Each line holds
     the text in a span that slides up from behind the mask when the
     heading comes into view. The split is measured after the fonts have
     loaded, so the lines are where the reader will actually see them.
     ------------------------------------------------------------------ */

  function splitHeading(element) {
    if (element.dataset.split === 'done') return;
    element.dataset.split = 'done';

    const text = element.textContent.trim();
    if (!text) return;

    // The line boxes of the browser are the truth about where the text
    // breaks. The heading is measured as it is rendered, and the words
    // are then grouped by the line they sit on.
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    let node = walker.nextNode();
    while (node) {
      if (node.textContent.trim()) textNodes.push(node);
      node = walker.nextNode();
    }

    if (!textNodes.length) return;

    const range = document.createRange();
    const words = [];

    textNodes.forEach((textNode) => {
      const parts = textNode.textContent.split(/(\s+)/);
      let offset = 0;
      parts.forEach((part) => {
        if (part.trim()) {
          range.setStart(textNode, offset);
          range.setEnd(textNode, offset + part.length);
          const rect = range.getBoundingClientRect();
          words.push({ word: part, top: Math.round(rect.top), left: rect.left });
        }
        offset += part.length;
      });
    });

    // The words are grouped by their vertical position. Two words are on
    // the same line when their boxes start at the same height.
    const lines = [];
    words.forEach((item) => {
      let line = lines.find((entry) => Math.abs(entry.top - item.top) < 4);
      if (!line) {
        line = { top: item.top, items: [] };
        lines.push(line);
      }
      line.items.push(item);
    });

    // The lines are then put back in the order the reader expects, which
    // for Persian is right to left.
    lines.sort((a, b) => a.top - b.top);
    const texts = lines.map((line) => {
      line.items.sort((a, b) => b.left - a.left);
      return line.items.map((item) => item.word).join(' ');
    });

    if (texts.length < 2) {
      // A heading that already fits on one line stays one line.
      element.dataset.split = 'single';
      return;
    }

    element.textContent = '';
    texts.forEach((line) => {
      const mask = document.createElement('span');
      mask.className = 'reveal-line';
      const inner = document.createElement('span');
      inner.textContent = line;
      mask.appendChild(inner);
      element.appendChild(mask);
    });
  }

  function splitHeadings() {
    const headings = document.querySelectorAll('[data-split]');
    if (!headings.length) return;

    // The mark of "arrived" goes on the heading and on every line of
    // it. The line is what the sheet watches for, so that each line
    // can rise from behind its mask on its own turn.
    const arrive = (heading) => {
      heading.classList.add('is-in');
      heading.querySelectorAll('.reveal-line').forEach((line) => {
        line.classList.add('is-in');
      });
    };

    if (isCalm()) {
      headings.forEach(arrive);
      return;
    }

    headings.forEach(splitHeading);

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        arrive(entry.target);
        observer.unobserve(entry.target);
      });
    }, { threshold: 0.2, rootMargin: '0px 0px -6% 0px' });

    headings.forEach((heading) => observer.observe(heading));
  }

  /* ------------------------------------------------------------------
     The light that follows the pointer.

     The position is written into two custom properties, so the browser
     only repaints. The cards themselves do not move, which keeps the
     grid stable.
     ------------------------------------------------------------------ */

  function attachPointerLight() {
    if (!canHover()) return;
    const cards = document.querySelectorAll('[data-lit]');
    if (!cards.length) return;

    cards.forEach((card) => {
      let frame = 0;
      let point = null;

      card.addEventListener('pointermove', (event) => {
        point = { x: event.clientX, y: event.clientY };
        if (frame) return;
        frame = requestAnimationFrame(() => {
          if (point) {
            const box = card.getBoundingClientRect();
            card.style.setProperty('--px', `${point.x - box.left}px`);
            card.style.setProperty('--py', `${point.y - box.top}px`);
          }
          frame = 0;
        });
      });

      card.addEventListener('pointerleave', () => {
        point = null;
        card.style.removeProperty('--px');
        card.style.removeProperty('--py');
      });
    });
  }

  /* ------------------------------------------------------------------
     The hairline that fills while a section passes the reading line.

     One observer for the whole page; every section reports how far it
     has come. The value is written into a custom property, so the
     browser only has to paint a thin line.
     ------------------------------------------------------------------ */

  function attachSectionProgress() {
    const sections = document.querySelectorAll('[data-section-progress]');
    if (!sections.length || isCalm()) return;

    const line = window.innerHeight * 0.35;
    let queued = false;

    const update = () => {
      queued = false;
      sections.forEach((section) => {
        const box = section.getBoundingClientRect();
        if (box.bottom < 0 || box.top > window.innerHeight) return;
        // How much of the section has passed the reading line.
        const seen = (line - box.top) / Math.max(1, box.height);
        const ratio = Math.max(0, Math.min(1, seen));
        section.style.setProperty('--section-progress', ratio.toFixed(3));
      });
    };

    window.addEventListener('scroll', () => {
      if (!queued) {
        queued = true;
        requestAnimationFrame(update);
      }
    }, { passive: true });

    window.addEventListener('resize', update, { passive: true });
    update();
  }

  /* ------------------------------------------------------------------
     The counter.

     A number that counts up when it comes into view. The target is
     checked before it is used: a value that is not a plain, finite and
     non-negative number is refused, so the text that the server wrote
     stays on the page.
     ------------------------------------------------------------------ */

  function attachCounters() {
    const counters = document.querySelectorAll('[data-count]');
    if (!counters.length || !('IntersectionObserver' in window) || isCalm()) return;

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        const element = entry.target;

        const target = Number(element.dataset.count);
        if (!Number.isFinite(target) || target < 0) {
          element.removeAttribute('data-count');
          observer.unobserve(element);
          return;
        }

        const start = performance.now();
        const duration = 900;
        const formatter = new Intl.NumberFormat('fa-IR');

        const tick = (now) => {
          const elapsed = Math.max(0, now - start);
          const ratio = Math.min(1, elapsed / duration);
          // A ratio that stays inside 0..1 keeps the easing curve from
          // turning over when the clock jumps backwards.
          const eased = 1 - Math.pow(1 - ratio, 4);
          element.textContent = formatter.format(Math.max(0, Math.round(target * eased)));
          if (ratio < 1) requestAnimationFrame(tick);
          else element.textContent = formatter.format(target);
        };

        requestAnimationFrame(tick);
        observer.unobserve(element);
      });
    }, { threshold: .35 });

    counters.forEach((element) => observer.observe(element));
  }

  /* ------------------------------------------------------------------
     The number that rolls in the product cards.

     The count of a category is written by the server. This only adds
     the small movement when the card comes into view.
     ------------------------------------------------------------------ */

  function attachEntrance() {
    const groups = document.querySelectorAll('[data-stagger]');
    if (!groups.length) return;

    // The delay of each child is written before the group is shown, so
    // the whole group starts moving in the same frame.
    groups.forEach((group) => {
      Array.from(group.children).forEach((child, index) => {
        child.style.setProperty('--stagger', `${Math.min(index, 9) * 55}ms`);
      });
    });

    if (isCalm()) {
      groups.forEach((group) => group.classList.add('is-in'));
      return;
    }

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add('is-in');
        observer.unobserve(entry.target);
      });
    }, { threshold: 0, rootMargin: '0px 0px -3% 0px' });

    groups.forEach((group) => observer.observe(group));
  }

  /* ------------------------------------------------------------------
     The tilt of a card.

     A small turn towards the pointer, never more than a few degrees.
     The card is a link, so the movement is a hint and never carries
     meaning on its own.
     ------------------------------------------------------------------ */

  function attachTilt() {
    if (!canHover()) return;
    const cards = document.querySelectorAll('[data-tilt]');
    if (!cards.length) return;

    const MAX = 4.5;

    cards.forEach((card) => {
      let frame = 0;
      let point = null;

      card.addEventListener('pointermove', (event) => {
        point = { x: event.clientX, y: event.clientY };
        if (frame) return;
        frame = requestAnimationFrame(() => {
          if (!point) return;
          const box = card.getBoundingClientRect();
          const x = (point.x - box.left) / box.width - .5;
          const y = (point.y - box.top) / box.height - .5;
          card.style.setProperty('--tilt-x', `${(-y * MAX).toFixed(2)}deg`);
          card.style.setProperty('--tilt-y', `${(x * MAX).toFixed(2)}deg`);
          frame = 0;
        });
      });

      card.addEventListener('pointerleave', () => {
        point = null;
        card.style.setProperty('--tilt-x', '0deg');
        card.style.setProperty('--tilt-y', '0deg');
      });
    });
  }

  /* ------------------------------------------------------------------
     The link that is about to be followed.

     A short fade hides the moment of change. It is kept short, it is
     cancelled when the visitor changes their mind, and it is skipped
     entirely when less movement was asked for.
     ------------------------------------------------------------------ */

  function attachPageLeave() {
    if (isCalm()) return;
    const main = document.querySelector('#main-content');
    if (!main) return;

    let leaving = false;

    document.addEventListener('click', (event) => {
      if (leaving) return;

      const link = event.target.closest('a[href]');
      if (!link) return;

      const url = new URL(link.href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.hash) return;
      if (link.target === '_blank') return;
      if (link.hasAttribute('download')) return;
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (event.defaultPrevented) return;

      leaving = true;
      main.classList.add('is-leaving');

      // The page is given a moment to fade out. If the browser does not
      // go on, the link is followed anyway.
      window.setTimeout(() => {
        window.location.href = url.href;
      }, 190);
      event.preventDefault();
    });

    window.addEventListener('pageshow', () => {
      leaving = false;
      main.classList.remove('is-leaving');
    });
  }

  /* ------------------------------------------------------------------
     Start.
     ------------------------------------------------------------------ */

  function start() {
    document.documentElement.classList.add('motion-ready');
    splitHeadings();
    attachPointerLight();
    attachSectionProgress();
    attachCounters();
    attachEntrance();
    attachTilt();
    attachPageLeave();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }

  // The lines are measured again when the font arrives, because the
  // width of a Persian word is not known before the real face is there.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(() => {
      document.querySelectorAll('[data-split]').forEach((heading) => {
        if (heading.dataset.split === 'done') return;
        splitHeading(heading);
      });
    });
  }
})();
