/**
 * AFCON360 KYC Draft — status page hook.
 *
 * Loaded on the KYC status page. If the user just completed a successful KYC
 * submission (flagged by kyc-draft.js during submit), the now-unneeded client
 * draft is discarded so unsubmitted PII is not retained in the browser.
 */
(function () {
  'use strict';
  if (window.KycDraft && typeof window.KycDraft.resolvePendingOnLoad === 'function') {
    window.KycDraft.resolvePendingOnLoad();
  }
})();
