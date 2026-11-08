(() => {
  'use strict';
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm || 'این عملیات انجام شود؟')) event.preventDefault();
    });
  });
  document.querySelectorAll('button[data-confirm]').forEach(button => {
    button.addEventListener('click', event => {
      if (!window.confirm(button.dataset.confirm || 'این عملیات انجام شود؟')) event.preventDefault();
    });
  });
  const menu = document.querySelector('[data-admin-menu]');
  const sidebar = document.querySelector('[data-admin-sidebar]');
  menu?.addEventListener('click', () => sidebar?.classList.toggle('is-open'));
  document.addEventListener('click', event => {
    if (window.innerWidth <= 900 && sidebar?.classList.contains('is-open') && !sidebar.contains(event.target) && !menu.contains(event.target)) sidebar.classList.remove('is-open');
  });
  const ownerType = document.querySelector('select[name="owner_type"]');
  if (ownerType && document.querySelector('.simple-admin-form')) {
    ownerType.addEventListener('change', () => {
      const url = new URL(window.location.href);
      url.searchParams.set('owner_type', ownerType.value);
      window.location.assign(url.toString());
    });
  }
})();
