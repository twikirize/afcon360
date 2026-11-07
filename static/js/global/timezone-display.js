/* AFCON360 context-aware display for offset-bearing technical instants.
 * Precedence: business location -> saved user preference -> browser -> UTC.
 * This file formats instants only; it never changes scheduling or API values.
 */
(function (window, document) {
  "use strict";

  var preferenceMeta = document.querySelector('meta[name="afcon360-preferred-timezone"]');
  var preferredTimezone = preferenceMeta ? (preferenceMeta.content || "").trim() : "";

  function validTimezone(name) {
    if (!name || typeof name !== "string") return null;
    try {
      new Intl.DateTimeFormat("en", { timeZone: name }).format(new Date(0));
      return name;
    } catch (error) {
      return null;
    }
  }

  function browserTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || null;
    } catch (error) {
      return null;
    }
  }

  function resolveTimezone(options) {
    options = options || {};
    return validTimezone(options.businessTimezone) ||
      validTimezone(options.preferredTimezone || preferredTimezone) ||
      validTimezone(options.browserTimezone || browserTimezone()) ||
      "UTC";
  }

  function parseInstant(value) {
    if (typeof value !== "string" || !/(?:Z|[+-]\\d{2}:?\\d{2})$/i.test(value)) {
      return null;
    }
    var instant = new Date(value);
    return Number.isNaN(instant.getTime()) ? null : instant;
  }

  function clockLabel(instant, timezone, label) {
    var formatted = new Intl.DateTimeFormat(undefined, {
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
      timeZone: timezone,
      timeZoneName: "short"
    }).format(instant);
    var fallbackLabel = String(timezone).split("/").pop().replace(/_/g, " ");
    return formatted + " (" + (label || fallbackLabel) + ")";
  }

  function formatInstant(value, options) {
    var instant = parseInstant(value);
    if (!instant) return value || "—";
    var zone = resolveTimezone(options);
    return new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: zone
    }).format(instant);
  }

  function formatDualInstant(value, options) {
    var instant = parseInstant(value);
    if (!instant) return value || "—";
    options = options || {};
    var businessZone = validTimezone(options.businessTimezone);
    var viewerZone = resolveTimezone({
      preferredTimezone: options.preferredTimezone,
      browserTimezone: options.browserTimezone
    });
    if (!businessZone) return formatInstant(value, options);
    var business = clockLabel(instant, businessZone, options.businessLabel);
    if (businessZone === viewerZone) return business;
    var viewer = clockLabel(instant, viewerZone, options.viewerLabel);
    return business + " · " + viewer;
  }

  function render(root) {
    root = root || document;
    var elements = [];
    if (root.matches && root.matches("[data-afcon360-instant]")) elements.push(root);
    if (root.querySelectorAll) {
      elements = elements.concat(Array.prototype.slice.call(
        root.querySelectorAll("[data-afcon360-instant]")
      ));
    }
    elements.forEach(function (element) {
      var value = element.getAttribute("data-afcon360-instant") || "";
      var options = {
        businessTimezone: element.getAttribute("data-afcon360-business-timezone"),
        businessLabel: element.getAttribute("data-afcon360-business-label"),
        preferredTimezone: preferredTimezone
      };
      element.textContent = element.getAttribute("data-afcon360-show-viewer-time") === "true"
        ? formatDualInstant(value, options)
        : formatInstant(value, options);
    });
  }

  window.AFCON360Time = {
    resolveTimezone: resolveTimezone,
    formatInstant: formatInstant,
    formatDualInstant: formatDualInstant,
    render: render
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { render(document); });
  } else {
    render(document);
  }
})(window, document);
