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
  if ('IntersectionObserver' in window && !reducedMotion) {
    const observer = new IntersectionObserver(entries => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.08 });
    revealItems.forEach((item, index) => {
      item.style.transitionDelay = `${(index % 3) * 60}ms`;
      observer.observe(item);
    });
  } else {
    revealItems.forEach(item => item.classList.add('is-visible'));
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
  requestAnimationFrame(() => document.body.classList.add('page-is-ready'));
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
      const el = entry.target, target = Number(el.dataset.count), start = performance.now();
      const tick = now => {
        const ratio = Math.min(1, (now - start) / 700);
        el.textContent = new Intl.NumberFormat('fa-IR').format(Math.round(target * (1 - Math.pow(1 - ratio, 3))));
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
    document.querySelectorAll('.product-card,.service-card,.feature-card').forEach(card => {
      card.addEventListener('pointermove', event => {
        const box = card.getBoundingClientRect();
        card.style.setProperty('--pointer-x', `${event.clientX - box.left}px`);
        card.style.setProperty('--pointer-y', `${event.clientY - box.top}px`);
      });
    });
  }
  document.querySelectorAll('.section-heading,.service-card,.feature-card,.requirement-card,.why-content>ul>li').forEach(el => {
    if (!el.classList.contains('reveal')) el.classList.add('reveal', 'is-visible');
  });
})();
