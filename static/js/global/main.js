document.addEventListener('DOMContentLoaded', function () {
  const hamburgerBtn = document.getElementById('hamburgerBtn');
  const drawer = document.getElementById('mobileDrawer');
  const overlay = document.getElementById('drawerOverlay');
  const drawerClose = document.getElementById('drawerClose');
  const accordionButtons = document.querySelectorAll('.drawer-accordion-toggle');

  function openDrawer() {
    if (!drawer || !overlay || !hamburgerBtn) return;

    drawer.classList.add('open');
    overlay.classList.add('open');
    hamburgerBtn.classList.add('active');
    hamburgerBtn.setAttribute('aria-expanded', 'true');
    drawer.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  function closeDrawer() {
    if (!drawer || !overlay || !hamburgerBtn) return;

    drawer.classList.remove('open');
    overlay.classList.remove('open');
    hamburgerBtn.classList.remove('active');
    hamburgerBtn.setAttribute('aria-expanded', 'false');
    drawer.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
  }

  if (hamburgerBtn) {
    hamburgerBtn.addEventListener('click', function (event) {
      event.preventDefault();
      const isOpen = drawer && drawer.classList.contains('open');
      if (isOpen) {
        closeDrawer();
      } else {
        openDrawer();
      }
    });
  }

  if (overlay) {
    overlay.addEventListener('click', closeDrawer);
  }

  if (drawerClose) {
    drawerClose.addEventListener('click', closeDrawer);
  }

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape') {
      closeDrawer();
    }
  });

  accordionButtons.forEach(function (button) {
    button.addEventListener('click', function () {
      const panel = button.closest('.drawer-accordion')?.querySelector('.drawer-accordion-body');
      const isOpen = panel && panel.classList.contains('open');

      document.querySelectorAll('.drawer-accordion-body').forEach(function (item) {
        item.classList.remove('open');
      });
      document.querySelectorAll('.drawer-accordion-toggle').forEach(function (item) {
        item.classList.remove('rotated');
      });

      if (!isOpen && panel) {
        panel.classList.add('open');
        button.classList.add('rotated');
      }
    });
  });

  document.querySelectorAll('.mobile-drawer a').forEach(function (link) {
    link.addEventListener('click', function () {
      closeDrawer();
    });
  });
});
