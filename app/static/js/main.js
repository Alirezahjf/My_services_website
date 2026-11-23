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
  const header = document.querySelector('[data-header]');
  if (header && window.innerWidth > 820) {
    const updateHeader = () => header.classList.toggle('is-sticky', window.scrollY > 100);
    window.addEventListener('scroll', updateHeader, { passive: true });
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
