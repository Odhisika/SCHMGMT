"use strict";

/**
 * Global button / form loading states.
 *
 * Used by every portal (admin, teacher, student, super admin) because it is
 * loaded from the shared layouts. It:
 *
 *  - shows a spinner and "processing" feedback on the button that submitted a
 *    form, and blocks double submissions;
 *  - marks buttons/links that start an HTMX request;
 *  - marks download / action links so a click always gives feedback;
 *  - restores the original button if a submission is cancelled or a request
 *    fails;
 *  - exposes `window.AppButtons` so page-specific AJAX handlers can reuse the
 *    same behaviour.
 *
 * Opt out with `data-no-loading` on a form/button. Override the loading label
 * with `data-loading-text="Saving…"`. Opt a custom JS button in with
 * `data-loading`.
 */
(function () {
  var LOADING_CLASS = "app-btn-loading";
  var FLAG = "appLoading";
  var SUBMITTING = "appSubmitting";
  var LOCKED = "appLocked";
  var HIDDEN_FLAG = "data-app-loading-hidden";

  // Remember the last submit control clicked. `SubmitEvent.submitter` is not
  // available in every browser, and this also covers clicks on nested spans.
  var lastSubmitter = null;
  var lastForm = null;

  var ANCHOR_SELECTOR =
    "a.btn, a[class*='btn'], a[role='button'], a.sa-logout, a[data-loading]";
  var CUSTOM_BUTTON_SELECTOR = "button[data-loading]";
  var SKIP_SELECTOR = [
    "[data-no-loading]",
    "[data-bs-toggle]",
    "[data-bs-dismiss]",
    "[data-toggle]",
    "[data-dismiss]",
    "[data-bs-target]",
    "[aria-disabled='true']",
    ".disabled",
    "[disabled]",
  ].join(", ");

  function isVisible(el) {
    if (!el || !el.getClientRects) return false;
    return el.getClientRects().length > 0;
  }

  function cleanText(el) {
    return (el.textContent || "").replace(/\s+/g, " ").trim();
  }

  function makeSpinner() {
    var spinner = document.createElement("span");
    spinner.className = "app-btn-spinner";
    spinner.setAttribute("aria-hidden", "true");
    return spinner;
  }

  function loadingLabel(el) {
    return (
      el.getAttribute("data-loading-text") ||
      el.getAttribute("aria-label") ||
      el.getAttribute("title") ||
      "Processing…"
    );
  }

  function lockSubmitValue(el) {
    if (!el || !el.form || !el.name || el._appHiddenInput) return;

    var hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.name = el.name;
    hidden.value = el.value || "";
    hidden.setAttribute(HIDDEN_FLAG, "1");
    el.form.appendChild(hidden);
    // Keep a reference so reset can remove exactly this node.
    el._appHiddenInput = hidden;
  }

  function unlockSubmitValue(el) {
    if (el && el._appHiddenInput) {
      if (el._appHiddenInput.parentNode) {
        el._appHiddenInput.parentNode.removeChild(el._appHiddenInput);
      }
      el._appHiddenInput = null;
    }
  }

  /**
   * Put a single button/link into its loading state.
   * Returns true when the state was applied.
   */
  function markLoading(el, options) {
    if (!el || el.dataset[FLAG] === "1") return false;

    options = options || {};
    el.dataset[FLAG] = "1";
    el.setAttribute("aria-busy", "true");
    el.classList.add(LOADING_CLASS);

    if (el.tagName === "INPUT") {
      el.dataset.appOriginalValue = el.value;
      el.dataset.appOriginalDisabled = el.disabled ? "1" : "0";
      lockSubmitValue(el);
      el.value = options.text || loadingLabel(el);
      el.disabled = true;
      return true;
    }

    var label = options.text || el.getAttribute("data-loading-text") || cleanText(el);
    if (!label) label = loadingLabel(el);

    el.dataset.appOriginalHtml = el.innerHTML;
    el.dataset.appOriginalMinWidth = el.style.minWidth || "";
    el.dataset.appOriginalDisabled = el.disabled ? "1" : "0";
    el.dataset.appOriginalAriaDisabled =
      el.getAttribute("aria-disabled") || "";

    var width = el.getBoundingClientRect().width;
    if (width) el.style.minWidth = Math.ceil(width) + "px";

    el.innerHTML = "";
    el.appendChild(makeSpinner());
    if (label) el.appendChild(document.createTextNode(label));

    if (el.tagName === "BUTTON") {
      // Only lock name/value when this button is a submit control.
      if ((el.getAttribute("type") || "submit").toLowerCase() === "submit") {
        lockSubmitValue(el);
      }
      el.disabled = true;
    } else {
      el.setAttribute("aria-disabled", "true");
    }

    // Safety net: never leave a button spinning forever if a page-specific
    // handler forgets to reset it (or a response is a download).
    el._appSafetyTimer = window.setTimeout(function () {
      resetLoading(el);
    }, 30000);

    return true;
  }

  /** Restore a single button/link. */
  function resetLoading(el) {
    if (!el || el.dataset[FLAG] !== "1") return;

    if (el._appResetTimer) {
      clearTimeout(el._appResetTimer);
      el._appResetTimer = null;
    }
    if (el._appSafetyTimer) {
      clearTimeout(el._appSafetyTimer);
      el._appSafetyTimer = null;
    }

    if (el.tagName === "INPUT") {
      el.value =
        el.dataset.appOriginalValue !== undefined
          ? el.dataset.appOriginalValue
          : el.value;
      el.disabled = el.dataset.appOriginalDisabled === "1";
    } else {
      if (el.dataset.appOriginalHtml !== undefined) {
        el.innerHTML = el.dataset.appOriginalHtml;
      }
      if (el.dataset.appOriginalMinWidth) {
        el.style.minWidth = el.dataset.appOriginalMinWidth;
      } else {
        el.style.removeProperty("min-width");
      }
      el.disabled = el.dataset.appOriginalDisabled === "1";
      if (el.dataset.appOriginalAriaDisabled) {
        el.setAttribute("aria-disabled", el.dataset.appOriginalAriaDisabled);
      } else {
        el.removeAttribute("aria-disabled");
      }
    }

    unlockSubmitValue(el);
    el.classList.remove(LOADING_CLASS);
    el.removeAttribute("aria-busy");
    delete el.dataset[FLAG];
    delete el.dataset.appOriginalHtml;
    delete el.dataset.appOriginalMinWidth;
    delete el.dataset.appOriginalValue;
    delete el.dataset.appOriginalDisabled;
    delete el.dataset.appOriginalAriaDisabled;
  }

  function findSubmitButton(form) {
    var candidates = [];
    var internal = form.querySelectorAll(
      "button[type='submit'], button:not([type]), input[type='submit'], input[type='image']"
    );
    for (var i = 0; i < internal.length; i += 1) candidates.push(internal[i]);
    if (form.id) {
      var external = document.querySelectorAll(
        "button[form='" + form.id + "'], input[type='submit'][form='" + form.id + "'], input[type='image'][form='" + form.id + "']"
      );
      for (var j = 0; j < external.length; j += 1) candidates.push(external[j]);
    }
    for (var k = 0; k < candidates.length; k += 1) {
      var candidate = candidates[k];
      if (!candidate.disabled && isVisible(candidate)) return candidate;
    }
    return null;
  }

  /** Put an entire form into its loading state. */
  function markFormLoading(form, submitter) {
    if (!form || form.dataset[SUBMITTING] === "1") return false;

    form.dataset[SUBMITTING] = "1";

    if (
      submitter &&
      !submitter.hasAttribute("data-no-loading") &&
      (form.contains(submitter) || submitter.form === form)
    ) {
      markLoading(submitter);
      form._appSubmittingButton = submitter;
    }

    var controls = [];
    var internal = form.querySelectorAll(
      "button[type='submit'], button:not([type]), input[type='submit'], input[type='image']"
    );
    for (var i = 0; i < internal.length; i += 1) controls.push(internal[i]);

    // Buttons outside the form can submit it through the `form="id"` attribute.
    if (form.id) {
      var external = document.querySelectorAll(
        "button[form='" + form.id + "'], input[type='submit'][form='" + form.id + "'], input[type='image'][form='" + form.id + "']"
      );
      for (var j = 0; j < external.length; j += 1) controls.push(external[j]);
    }

    // Lock every other submit control so a second action can't be triggered
    // while the first one is still processing.
    form._appLockedControls = form._appLockedControls || [];
    for (var k = 0; k < controls.length; k += 1) {
      var control = controls[k];
      if (control === submitter) continue;
      if (control.disabled || control.dataset[LOCKED] === "1") continue;
      control.dataset[LOCKED] = "1";
      control.disabled = true;
      form._appLockedControls.push(control);
    }

    // Safety net for submissions that do not navigate (downloads, new tabs).
    form._appSafetyTimer = window.setTimeout(function () {
      resetForm(form);
    }, 30000);

    return true;
  }

  /** Restore a form and everything inside it. */
  function resetForm(form) {
    if (!form) return;

    if (form._appSafetyTimer) {
      clearTimeout(form._appSafetyTimer);
      form._appSafetyTimer = null;
    }

    var locked = form._appLockedControls || [];
    for (var i = 0; i < locked.length; i += 1) {
      locked[i].disabled = false;
      delete locked[i].dataset.appLocked;
    }
    form._appLockedControls = [];

    var loading = form.querySelectorAll("[data-app-loading='1']");
    for (var j = 0; j < loading.length; j += 1) {
      resetLoading(loading[j]);
    }

    // A submit button can live outside the form via the `form="id"` attribute.
    if (form._appSubmittingButton) {
      resetLoading(form._appSubmittingButton);
      form._appSubmittingButton = null;
    }

    delete form.dataset[SUBMITTING];
    delete form.dataset[FLAG];
  }

  /** Restore every button on the page. */
  function resetAll() {
    var loading = document.querySelectorAll("[data-app-loading='1']");
    for (var i = 0; i < loading.length; i += 1) {
      resetLoading(loading[i]);
    }

    var locked = document.querySelectorAll("[data-app-locked='1']");
    for (var j = 0; j < locked.length; j += 1) {
      locked[j].disabled = false;
      delete locked[j].dataset.appLocked;
    }

    var forms = document.querySelectorAll("[data-app-submitting='1']");
    for (var k = 0; k < forms.length; k += 1) {
      delete forms[k].dataset[SUBMITTING];
      delete forms[k].dataset[FLAG];
    }
  }

  function isHtmxForm(form) {
    return !!(
      form.hasAttribute("hx-post") ||
      form.hasAttribute("hx-get") ||
      form.hasAttribute("hx-put") ||
      form.hasAttribute("hx-patch") ||
      form.hasAttribute("hx-delete") ||
      form.closest("[hx-boost='true']")
    );
  }

  function resetForElement(el) {
    if (!el) return;
    if (el.tagName === "FORM") {
      resetForm(el);
    } else if (el.form) {
      resetForm(el.form);
    } else {
      resetLoading(el);
    }
  }

  function shouldMarkClickable(el) {
    if (!el || el.dataset[FLAG] === "1") return false;
    if (el.closest(SKIP_SELECTOR)) return false;
    if (el.tagName === "A") {
      var href = el.getAttribute("href") || "";
      if (!href || href.charAt(0) === "#") return false;
      if (/^(javascript|mailto|tel):/i.test(href)) return false;
      var target = (el.getAttribute("target") || "").toLowerCase();
      if (target && target !== "_self") return false;
      return true;
    }
    return el.tagName === "BUTTON";
  }

  function isDownloadLink(el) {
    if (!el || el.tagName !== "A") return false;
    return (
      el.hasAttribute("download") ||
      /\.(pdf|xlsx?|docx?|csv|zip)([?#]|$)/i.test(el.href || "")
    );
  }

  // ---------------------------------------------------------------------
  // Remember the clicked submit control (fallback for event.submitter).
  // ---------------------------------------------------------------------
  document.addEventListener(
    "click",
    function (event) {
      var target = event.target;
      if (!target || !target.closest) return;
      var control = target.closest(
        "button, input[type='submit'], input[type='image']"
      );
      if (!control) return;
      lastSubmitter = control;
      lastForm = control.form || null;
    },
    true
  );

  // ---------------------------------------------------------------------
  // Form submissions: show progress immediately and block double submits.
  // ---------------------------------------------------------------------
  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!form || form.tagName !== "FORM") return;
      if (form.hasAttribute("data-no-loading")) return;

      if (form.dataset[SUBMITTING] === "1") {
        event.preventDefault();
        event.stopImmediatePropagation();
        return;
      }

      var submitter =
        (event.submitter && event.submitter.form === form
          ? event.submitter
          : null) ||
        (lastForm === form ? lastSubmitter : null) ||
        findSubmitButton(form);

      markFormLoading(form, submitter);

      // A later handler may cancel the submission (custom validation, a
      // confirmation dialog, etc.). In that case undo the loading state,
      // unless htmx is going to perform an AJAX request instead.
      window.setTimeout(function () {
        if (!event.defaultPrevented) return;
        if (isHtmxForm(form)) return;
        resetForm(form);
      }, 0);
    },
    true
  );

  // ---------------------------------------------------------------------
  // Click feedback for action buttons and links.
  // (Submit buttons are intentionally handled by the submit listener above:
  // disabling them during `click` can cancel native form submission.)
  // ---------------------------------------------------------------------
  document.addEventListener(
    "click",
    function (event) {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) {
        return;
      }

      var target = event.target;
      if (!target || !target.closest) return;

      var el = target.closest(ANCHOR_SELECTOR + ", " + CUSTOM_BUTTON_SELECTOR);
      if (!el || !shouldMarkClickable(el)) return;

      if (el.tagName === "BUTTON") {
        var type = (el.getAttribute("type") || "submit").toLowerCase();
        if (type !== "button") return;
      }

      markLoading(el);

      // Downloads don't navigate the page, so clear the spinner afterwards.
      if (isDownloadLink(el)) {
        el._appResetTimer = window.setTimeout(function () {
          resetLoading(el);
        }, 8000);
      }
    },
    true
  );

  // ---------------------------------------------------------------------
  // HTMX requests (used for explicit partial updates such as the
  // notification widget, not for full-page navigation).
  // ---------------------------------------------------------------------
  if (window.htmx || document.body) {
    document.addEventListener("htmx:beforeRequest", function (event) {
      var el = event.detail && event.detail.elt;
      if (!el) return;

      if (el.tagName === "FORM") {
        var submitter =
          (lastForm === el ? lastSubmitter : null) || findSubmitButton(el);
        markFormLoading(el, submitter);
        return;
      }

      if (
        (el.tagName === "A" || el.tagName === "BUTTON") &&
        shouldMarkClickable(el)
      ) {
        markLoading(el);
      }
    });

    document.addEventListener("htmx:afterRequest", function (event) {
      resetForElement(event.detail && event.detail.elt);
    });

    ["htmx:responseError", "htmx:sendError", "htmx:timeout", "htmx:abort", "htmx:validation:failed"].forEach(
      function (name) {
        document.addEventListener(name, function (event) {
          resetForElement(event.detail && event.detail.elt);
        });
      }
    );

    document.addEventListener("htmx:afterSwap", resetAll);
    document.addEventListener("htmx:historyRestore", resetAll);
  }

  // A restored page (Back/Forward cache) should never keep a stale spinner.
  window.addEventListener("pageshow", resetAll);

  // ---------------------------------------------------------------------
  // Public API for page-specific AJAX handlers.
  // ---------------------------------------------------------------------
  window.AppButtons = {
    load: markLoading,
    loadForm: markFormLoading,
    reset: resetLoading,
    resetForm: resetForm,
    resetAll: resetAll,
    isLoading: function (el) {
      return !!(el && el.dataset[FLAG] === "1");
    },
  };
})();
