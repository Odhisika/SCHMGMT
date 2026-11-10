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
