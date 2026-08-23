/**
 * Global KYC ribbon controller.
 *
 * - The ribbon is always rendered for authenticated users on user-facing
 *   blueprints (see components/kyc_ribbon.html).
 * - Dismissal is remembered in localStorage keyed by a signature of the
 *   user's current KYC state (tier + fulfillment + missing requirements).
 *   When the state changes (e.g. the user completes a requirement, or is
 *   promoted), the signature changes and the ribbon reappears — so it keeps
 *   reminding until the KYC issues are actually resolved.
 * - Pages can force the ribbon to reappear on a KYC-gated action by either:
 *      dispatchEvent(new CustomEvent('af360:kyc-required'))
 *   or redirecting with `?kyc_gate=1`.
 */
(function () {
  var ribbon = document.getElementById('kycRibbon');
  if (!ribbon) return;

  var KEY = 'af360_kyc_ribbon_seen';

  function signature() {
    return [
      ribbon.dataset.tier,
      ribbon.dataset.fulfillment,
      ribbon.dataset.missing,
      ribbon.dataset.complete
    ].join('|');
  }

  function show() {
    ribbon.style.display = '';
  }

  function hide() {
    ribbon.style.display = 'none';
  }

  function apply() {
    var seen;
    try { seen = localStorage.getItem(KEY); } catch (e) { seen = null; }
    if (seen === signature()) {
      hide();
    } else {
      show();
    }
  }

  var closeBtn = ribbon.querySelector('[data-kyc-dismiss]');
  if (closeBtn) {
    closeBtn.addEventListener('click', function () {
      try { localStorage.setItem(KEY, signature()); } catch (e) { /* ignore */ }
      hide();
    });
  }

  function forceShow() {
    try { localStorage.removeItem(KEY); } catch (e) { /* ignore */ }
    show();
  }

  window.addEventListener('af360:kyc-required', forceShow);
  if (/[?&]kyc_gate=1\b/.test(window.location.search)) {
    forceShow();
  }

  // Expose a small API for other scripts.
  window.AFCON360KycRibbon = { show: forceShow, hide: hide };

  apply();
})();
