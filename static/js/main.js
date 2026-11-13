"use strict";

// side navigation bar
function toggleSidebar() {
  const sideNav = document.getElementById("side-nav");
  if (sideNav) sideNav.classList.toggle("toggle-active");

  const main = document.getElementById("main");
  if (main) main.classList.toggle("toggle-active");

  const topNavbar = document.getElementById("top-navbar");
  if (topNavbar) topNavbar.classList.toggle("toggle-active");

  const manageWrap = document.querySelector(".manage-wrap");
  if (manageWrap) manageWrap.classList.toggle("toggle-active");

  const toggleBtn = document.getElementById("sidebar-toggle");
  if (toggleBtn) toggleBtn.classList.toggle("toggle-active");
}


// #################################
// popup

var c = 0;
function pop() {
  if (c == 0) {
    document.getElementById("popup-box").style.display = "block";
    c = 1;
  } else {
    document.getElementById("popup-box").style.display = "none";
    c = 0;
  }
}

// const popupMessagesButtons = document.querySelectorAll('popup-btn-messages')

// popupMessagesButtons.forEach(button, () => {
//     button.addEventListener('click', () => {
//         document.getElementById('popup-box-messages').style.display = 'none';
//     })
// })

// const popupMessagesButtom = document.getElementById('popup-btn-messages')
// popupMessagesButtom.addEventListener('click', () => {
//     document.getElementById('popup-box-messages').style.display = 'none';
// })
// ##################################

// Example starter JavaScript for disabling form submissions if there are invalid fields
// Fetch all the forms we want to apply custom Bootstrap validation styles to
var forms = document.getElementsByClassName("needs-validation");

// Loop over them and prevent submission
Array.prototype.filter.call(forms, function (form) {
  form.addEventListener(
    "submit",
    function (event) {
      if (form.checkValidity() === false) {
        event.preventDefault();
        event.stopPropagation();
      }
      form.classList.add("was-validated");
    },
    false
  );
});
// ##################################

// extend and collapse
function showCourses(btn) {
  var btn = $(btn);

  if (collapsed) {
    btn.html('Collapse <i class="fas fa-angle-up"></i>');
    $(".hide").css("max-height", "unset");
    $(".white-shadow").css({ background: "unset", "z-index": "0" });
  } else {
    btn.html('Expand <i class="fas fa-angle-down"></i>');
    $(".hide").css("max-height", "150");
    $(".white-shadow").css({
      background: "linear-gradient(transparent 50%, rgba(255,255,255,.8) 80%)",
      "z-index": "2",
    });
  }
  collapsed = !collapsed;
}

$(document).ready(function () {
  $("#primary-search").focus(function () {
    $("#top-navbar").attr("class", "dim");
    $("#side-nav").css("pointer-events", "none");
    $("#main-content").css("pointer-events", "none");
  });
  $("#primary-search").focusout(function () {
    $("#top-navbar").removeAttr("class");
    $("#side-nav").css("pointer-events", "auto");
    $("#main-content").css("pointer-events", "auto");
  });
});

// Update sidebar active state for HTMX silent refreshes
document.body.addEventListener('htmx:afterOnLoad', function (evt) {
  const path = window.location.pathname;
  const sidebarItems = document.querySelectorAll('#side-nav .main-menu ul li');

  sidebarItems.forEach(item => {
    const link = item.querySelector('a');
    if (!link) return;

    const href = link.getAttribute('href');

    // Match logic similar to sidebar.html template
    if (href === path ||
      (href !== '/' && path.startsWith(href)) ||
      (href === '/result/report-cards/' && path.includes('/result/report-cards/')) ||
      (href.includes('school') && path.includes('school'))) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });
});

// ##################################
// Sidebar resize sync
// The sidebar is resizable via the native handle (resize: horizontal).
// The main content, top navbar, bottom action bar and the hamburger toggle
// all offset by the sidebar width, so they read the --sidebar-width CSS
// variable and this keeps it in sync while the handle is dragged.
(function () {
  var STORAGE_KEY = 'schmgmt_sidebar_width';
  var MIN_WIDTH = 230; // must match #side-nav { min-width } in style.min.css
  var MAX_WIDTH = 520; // must match #side-nav { max-width } in style.min.css
  var observer = null;
  var observedSidebar = null;
  var freezeTimer = null;

  function readSavedWidth() {
    try {
      return parseInt(sessionStorage.getItem(STORAGE_KEY), 10);
    } catch (e) {
      return NaN;
    }
  }

  function saveWidth(width) {
    try {
      sessionStorage.setItem(STORAGE_KEY, String(width));
    } catch (e) {
      /* storage unavailable */
    }
  }

  function applyWidth(width) {
    document.documentElement.style.setProperty('--sidebar-width', width + 'px');
  }

  function initSidebarResizeSync() {
    var sidebar = document.getElementById('side-nav');
    if (!sidebar || typeof ResizeObserver === 'undefined') return;

    // A fresh page load loses the inline width written by the native resize
    // handle, so restore the width chosen earlier in this session.
    if (!sidebar.style.width) {
      var saved = readSavedWidth();
      if (saved >= MIN_WIDTH && saved <= MAX_WIDTH) {
        sidebar.style.width = saved + 'px';
      }
    }
    applyWidth(sidebar.offsetWidth);

    // Nothing to do if this exact node is already observed. HTMX swaps and
    // history restores can replace the sidebar node, in which case the new
    // node needs a fresh observer.
    if (observedSidebar === sidebar) return;
    if (observer) observer.disconnect();

    observedSidebar = sidebar;
    observer = new ResizeObserver(function () {
      // Freeze transitions while the handle is being dragged so the layout
      // tracks the pointer directly instead of lagging behind.
      document.documentElement.classList.add('sidebar-resizing');
      applyWidth(sidebar.offsetWidth);
      saveWidth(sidebar.offsetWidth);
      clearTimeout(freezeTimer);
      freezeTimer = setTimeout(function () {
        document.documentElement.classList.remove('sidebar-resizing');
      }, 150);
    });
    observer.observe(sidebar);
  }

  initSidebarResizeSync();
  // Re-attach after HTMX swaps content or restores a history snapshot,
  // which can replace the #side-nav node.
  document.body.addEventListener('htmx:afterSwap', initSidebarResizeSync);
  document.body.addEventListener('htmx:historyRestore', initSidebarResizeSync);
})();

// ##################################
// Custom confirmation dialog and toast notifications.
// Replaces the browser's native confirm()/alert() prompts with the app's
// own Bootstrap-styled modal so every action looks consistent.
(function () {
  var modalEl = document.getElementById("appConfirmModal");
  if (!modalEl || typeof bootstrap === "undefined") return;

  var modal = new bootstrap.Modal(modalEl);
  var iconWrap = document.getElementById("appConfirmIcon");
  var iconEl = iconWrap ? iconWrap.querySelector("i") : null;
  var titleEl = document.getElementById("appConfirmTitle");
  var messageEl = document.getElementById("appConfirmMessage");
  var okBtn = document.getElementById("appConfirmOk");
  var cancelBtn = document.getElementById("appConfirmCancel");

  var activeResolve = null;
  var activeSettled = true;

  function settle(result) {
    if (activeSettled) return;
    activeSettled = true;
    var resolve = activeResolve;
    activeResolve = null;
    if (resolve) resolve(result);
  }

  function variantStyles(variant) {
    switch (variant) {
      case "danger":
        return { wrap: "is-danger", button: "btn-danger", icon: "fa-triangle-exclamation" };
      case "warning":
        return { wrap: "is-warning", button: "btn-warning", icon: "fa-exclamation-circle" };
      case "success":
        return { wrap: "is-success", button: "btn-success", icon: "fa-check-circle" };
      default:
        return { wrap: "is-primary", button: "btn-primary", icon: "fa-circle-question" };
    }
  }

  function resolveIcon(icon, fallback) {
    if (!icon) return fallback;
    return icon.indexOf("fa-") === 0 ? icon : "fa-" + icon;
  }

  window.appConfirm = function (options) {
    if (typeof options === "string") options = { message: options };
    options = options || {};

    if (activeResolve) settle(false);

    var styles = variantStyles(options.variant);
    if (iconWrap) iconWrap.className = "app-confirm-icon mx-auto mb-3 " + styles.wrap;
    if (iconEl) iconEl.className = "fas " + resolveIcon(options.icon, styles.icon);
    if (titleEl) titleEl.textContent = options.title || "Please confirm";
    if (messageEl) messageEl.textContent = options.message || "Are you sure you want to continue?";
    if (okBtn) {
      okBtn.textContent = options.okText || "Confirm";
      okBtn.className = "btn " + styles.button + " px-4";
    }
    if (cancelBtn) cancelBtn.textContent = options.cancelText || "Cancel";

    return new Promise(function (resolve) {
      activeResolve = resolve;
      activeSettled = false;
      modal.show();
    });
  };

  if (okBtn) {
    okBtn.addEventListener("click", function () {
      settle(true);
      modal.hide();
    });
  }

  modalEl.addEventListener("hidden.bs.modal", function () {
    settle(false);
  });

  function confirmOptionsFromData(element) {
    return {
      message: element.getAttribute("data-confirm"),
      title: element.getAttribute("data-confirm-title"),
      okText: element.getAttribute("data-confirm-ok"),
      cancelText: element.getAttribute("data-confirm-cancel"),
      variant: element.getAttribute("data-confirm-variant"),
      icon: element.getAttribute("data-confirm-icon"),
    };
  }

  // Declarative links and buttons: <a data-confirm="..."> or
  // <button data-confirm="..." data-confirm-variant="danger">.
  document.addEventListener(
    "click",
    function (event) {
      var trigger = event.target.closest("[data-confirm]");
      if (!trigger) return;

      // Forms are handled by the submit listener below. Without this guard a
      // click on a submit button would be treated as a click on the form,
      // preventing the submission and re-clicking the form (which never submits).
      if (trigger.tagName === "FORM") return;

      if (trigger.getAttribute("data-confirm-bypass") === "true") {
        trigger.removeAttribute("data-confirm-bypass");
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();

      window.appConfirm(confirmOptionsFromData(trigger)).then(function (confirmed) {
        if (!confirmed) return;
        trigger.setAttribute("data-confirm-bypass", "true");
        trigger.click();
      });
    },
    true
  );

  // Declarative forms: <form method="post" data-confirm="...">.
  document.addEventListener(
    "submit",
    function (event) {
      var form = event.target;
      if (!form || form.tagName !== "FORM" || !form.hasAttribute("data-confirm")) return;

      if (form.getAttribute("data-confirm-bypass") === "true") {
        form.removeAttribute("data-confirm-bypass");
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();

      window.appConfirm(confirmOptionsFromData(form)).then(function (confirmed) {
        if (!confirmed) return;
        form.setAttribute("data-confirm-bypass", "true");
        if (typeof form.requestSubmit === "function") {
          form.requestSubmit();
        } else {
          form.submit();
        }
      });
    },
    true
  );

  window.appNotify = function (message, variant, title) {
    var container = document.getElementById("appToastContainer");
    if (!container || typeof bootstrap === "undefined") {
      if (message) console.info(message);
      return;
    }

    variant = variant || "success";
    var icons = {
      success: "fa-circle-check",
      danger: "fa-circle-exclamation",
      warning: "fa-triangle-exclamation",
      info: "fa-circle-info",
    };

    var toastEl = document.createElement("div");
    toastEl.className = "toast align-items-center border-0 app-toast text-bg-" + variant;
    toastEl.setAttribute("role", "alert");
    toastEl.setAttribute("aria-live", "assertive");
    toastEl.setAttribute("aria-atomic", "true");

    var wrapper = document.createElement("div");
    wrapper.className = "d-flex";

    var body = document.createElement("div");
    body.className = "toast-body d-flex align-items-start gap-2";

    var icon = document.createElement("i");
    icon.className = "fas " + (icons[variant] || icons.info) + " mt-1";
    body.appendChild(icon);

    var copy = document.createElement("div");
    if (title) {
      var heading = document.createElement("div");
      heading.className = "fw-semibold";
      heading.textContent = title;
      copy.appendChild(heading);
    }
    var text = document.createElement("div");
    text.textContent = message;
    copy.appendChild(text);
    body.appendChild(copy);

    var close = document.createElement("button");
    close.type = "button";
    close.className = "btn-close btn-close-white me-2 m-auto";
    close.setAttribute("data-bs-dismiss", "toast");
    close.setAttribute("aria-label", "Close");

    wrapper.appendChild(body);
    wrapper.appendChild(close);
    toastEl.appendChild(wrapper);
    container.appendChild(toastEl);

    toastEl.addEventListener("hidden.bs.toast", function () {
      toastEl.remove();
    });

    new bootstrap.Toast(toastEl, { delay: 4500 }).show();
  };
})();

// Keep the notification panel inside the viewport on narrow screens. Bootstrap
// uses static dropdown positioning for this widget; here we align the panel to
// the viewport edge and place it just below the bell after it opens.
document.addEventListener("shown.bs.dropdown", function (event) {
  var widget = event.target && event.target.closest
    ? event.target.closest(".notification-widget")
    : null;
  if (!widget) return;
  if (window.innerWidth > 575.98) return;

  var bell = widget.querySelector(".notification-bell");
  var menu = widget.querySelector(".notification-dropdown");
  if (!bell || !menu) return;

  var bellRect = bell.getBoundingClientRect();
  var top = Math.min(bellRect.bottom + 8, Math.max(8, window.innerHeight - 180));
  menu.style.top = top + "px";
  menu.style.right = "8px";
  menu.style.left = "auto";
  menu.style.width = Math.min(370, window.innerWidth - 16) + "px";
  menu.style.maxHeight = Math.max(150, window.innerHeight - top - 8) + "px";
});

document.addEventListener("hidden.bs.dropdown", function (event) {
  var widget = event.target && event.target.closest
    ? event.target.closest(".notification-widget")
    : null;
  if (!widget) return;
  var menu = widget.querySelector(".notification-dropdown");
  if (!menu) return;
  menu.style.removeProperty("top");
  menu.style.removeProperty("right");
  menu.style.removeProperty("left");
  menu.style.removeProperty("width");
  menu.style.removeProperty("max-height");
});
