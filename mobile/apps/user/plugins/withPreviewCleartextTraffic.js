"use strict";

const { withAndroidManifest } = require("expo/config-plugins");

/**
 * Preview/development builds may connect to a laptop API over a trusted
 * private Wi-Fi network (private IPv4, port 5000), as validated by the
 * User app's server selector. Production builds must never opt into HTTP.
 *
 * Android blocks cleartext by default for apps targeting API 28+; without
 * this native manifest flag the supported laptop-testing flow cannot work.
 */
module.exports = function withPreviewCleartextTraffic(config, options = {}) {
  if (options.enabled !== true) return config;

  return withAndroidManifest(config, modConfig => {
    const application = modConfig.modResults.manifest.application?.[0];
    if (!application) {
      throw new Error(
        "AFCON360 preview network configuration could not find the Android application manifest element."
      );
    }

    application.$ = application.$ || {};
    application.$["android:usesCleartextTraffic"] = "true";
    return modConfig;
  });
};
