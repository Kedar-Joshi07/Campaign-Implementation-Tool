const STORAGE_KEY = "campaign-sidebar-layout-v1";
const DEFAULT_WIDTH = 264;
const MIN_WIDTH = 216;
const MAX_WIDTH = 420;
const KEYBOARD_STEP = 16;
const MOBILE_BREAKPOINT = 780;

function clampWidth(width) {
  const viewportMaximum = Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, window.innerWidth * 0.42));
  return Math.round(Math.min(viewportMaximum, Math.max(MIN_WIDTH, width)));
}

function readLayout() {
  try {
    const stored = JSON.parse(window.localStorage.getItem(STORAGE_KEY) || "null");
    return {
      width: Number.isFinite(stored?.width) ? clampWidth(stored.width) : clampWidth(DEFAULT_WIDTH),
      hidden: stored?.hidden === true,
    };
  } catch (_) {
    return { width: clampWidth(DEFAULT_WIDTH), hidden: false };
  }
}

function writeLayout(layout) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
  } catch (_) {
    // Layout controls remain functional when browser storage is unavailable.
  }
}

export function initializeSidebar() {
  const shell = document.querySelector(".app-shell");
  const sidebar = document.querySelector("#primary-sidebar");
  const collapse = document.querySelector("#sidebar-collapse");
  const expand = document.querySelector("#sidebar-expand");
  const handle = document.querySelector("#sidebar-resize-handle");
  if (!shell || !sidebar || !collapse || !expand || !handle) return;

  const layout = readLayout();
  let activePointerId = null;

  function applyWidth(width, { persist = true } = {}) {
    layout.width = clampWidth(width);
    shell.style.setProperty("--sidebar-width", `${layout.width}px`);
    handle.setAttribute("aria-valuenow", String(layout.width));
    handle.setAttribute("aria-valuemax", String(clampWidth(MAX_WIDTH)));
    if (persist) writeLayout(layout);
  }

  function applyVisibility(hidden, { persist = true } = {}) {
    const focusWasInsideSidebar = sidebar.contains(document.activeElement);
    layout.hidden = Boolean(hidden);
    shell.classList.toggle("sidebar-is-hidden", layout.hidden);
    sidebar.setAttribute("aria-hidden", String(layout.hidden));
    sidebar.inert = layout.hidden;
    collapse.setAttribute("aria-expanded", String(!layout.hidden));
    expand.setAttribute("aria-expanded", String(!layout.hidden));
    expand.hidden = !layout.hidden;
    if (persist) writeLayout(layout);
    if (!layout.hidden && document.activeElement === expand) collapse.focus();
    if (layout.hidden && focusWasInsideSidebar) expand.focus();
  }

  function finishResize() {
    if (activePointerId === null) return;
    if (handle.hasPointerCapture(activePointerId)) handle.releasePointerCapture(activePointerId);
    activePointerId = null;
    shell.classList.remove("sidebar-is-resizing");
    document.body.classList.remove("sidebar-is-resizing");
    writeLayout(layout);
  }

  collapse.addEventListener("click", () => applyVisibility(true));
  expand.addEventListener("click", () => applyVisibility(false));

  handle.addEventListener("pointerdown", (event) => {
    if (event.button !== 0 || layout.hidden || window.innerWidth <= MOBILE_BREAKPOINT) return;
    activePointerId = event.pointerId;
    handle.setPointerCapture(activePointerId);
    shell.classList.add("sidebar-is-resizing");
    document.body.classList.add("sidebar-is-resizing");
    event.preventDefault();
  });
  handle.addEventListener("pointermove", (event) => {
    if (event.pointerId !== activePointerId) return;
    const shellLeft = shell.getBoundingClientRect().left;
    applyWidth(event.clientX - shellLeft, { persist: false });
  });
  handle.addEventListener("pointerup", finishResize);
  handle.addEventListener("pointercancel", finishResize);
  handle.addEventListener("lostpointercapture", finishResize);
  handle.addEventListener("keydown", (event) => {
    let nextWidth = null;
    if (event.key === "ArrowLeft") nextWidth = layout.width - KEYBOARD_STEP;
    else if (event.key === "ArrowRight") nextWidth = layout.width + KEYBOARD_STEP;
    else if (event.key === "Home") nextWidth = MIN_WIDTH;
    else if (event.key === "End") nextWidth = MAX_WIDTH;
    if (nextWidth === null) return;
    event.preventDefault();
    applyWidth(nextWidth);
  });

  window.addEventListener("resize", () => applyWidth(layout.width, { persist: false }));
  applyWidth(layout.width, { persist: false });
  applyVisibility(layout.hidden, { persist: false });
}
