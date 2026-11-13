// Page-level extras for the Notebook panel. Loaded through custom_js in .chainlit/config.toml.
// - a top-bar button (and Ctrl+\) that hides or shows the notebook sidebar
// - thin, theme-coloured scrollbars
// The project picker lives in the Notebook panel itself (public/elements/Notebook.jsx).
(function () {
  "use strict";

  // Notebook sidebar collapse toggle (top bar, next to the theme button)
  const TOGGLE_ID = "rc-sidebar-toggle";
  const COLLAPSED_CLASS = "rc-nb-collapsed";
  const COLLAPSED_KEY = "rc-notebook-collapsed";

  const ICONS = {
    panelClose: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/><path d="m8 9 3 3-3 3"/>',
    panelOpen: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/><path d="m10 15-3-3 3-3"/>',
  };

  function icon(name, size) {
    const span = document.createElement("span");
    span.style.cssText = "display:inline-flex;flex:none";
    // Fixed SVG paths from this file only; no user text goes in here
    span.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
    return span;
  }

  const CSS = `
/* Collapsed: the sidebar panel shrinks to nothing and the chat takes the space.
   The panel library sets flex inline, so !important wins over it. */
html.${COLLAPSED_CLASS} [data-panel]:has(#side-view-content) { flex:0.001 1 0px !important; opacity:0; pointer-events:none; }
/* (0.001, not 0: browsers don't animate flex-grow to or from exactly 0) */
html.${COLLAPSED_CLASS} [data-resize-handle]:has(+ [data-panel] #side-view-content) { opacity:0; pointer-events:none; width:0 !important; }
/* Animate only while toggling, so dragging the divider stays instant */
html.rc-nb-animating [data-panel] { transition:flex-grow .32s cubic-bezier(.32,.72,0,1), opacity .22s ease; }
html.rc-nb-animating [data-resize-handle] { transition:opacity .2s ease; }
#${TOGGLE_ID} svg { transition:transform .32s cubic-bezier(.32,.72,0,1); }
#${TOGGLE_ID}:active svg { transform:scale(.88); }
/* ---- scrollbars: thin, rounded, theme-coloured, no arrow buttons ----
   Chromium/Safari use ::-webkit-scrollbar; Firefox uses the standard properties.
   (In Chromium, setting scrollbar-color would switch the webkit styles off.) */
::-webkit-scrollbar { width:10px; height:10px; }
::-webkit-scrollbar-track, ::-webkit-scrollbar-corner { background:transparent; }
::-webkit-scrollbar-button { display:none; width:0; height:0; }
::-webkit-scrollbar-thumb { background-color:hsl(var(--muted-foreground) / .28); border:3px solid transparent; border-radius:999px; background-clip:padding-box; min-height:32px; }
::-webkit-scrollbar-thumb:hover { background-color:hsl(var(--muted-foreground) / .5); border-width:2px; }
::-webkit-scrollbar-thumb:active { background-color:hsl(var(--muted-foreground) / .65); border-width:2px; }
/* Notebook: sideways bars on code and outputs are thinner and only show on hover */
.rcnb-src::-webkit-scrollbar, .rcnb-pre::-webkit-scrollbar, .rcnb-img::-webkit-scrollbar, .rcnb-note::-webkit-scrollbar { height:8px; }
.rcnb-src::-webkit-scrollbar-thumb, .rcnb-pre::-webkit-scrollbar-thumb, .rcnb-img::-webkit-scrollbar-thumb, .rcnb-note::-webkit-scrollbar-thumb { background-color:transparent; border-width:2px; }
.rcnb-code:hover .rcnb-src::-webkit-scrollbar-thumb, .rcnb-pre:hover::-webkit-scrollbar-thumb,
.rcnb-img:hover::-webkit-scrollbar-thumb, .rcnb-note:hover::-webkit-scrollbar-thumb { background-color:hsl(var(--muted-foreground) / .3); }
.rcnb-code:hover .rcnb-src::-webkit-scrollbar-thumb:hover, .rcnb-pre:hover::-webkit-scrollbar-thumb:hover,
.rcnb-img:hover::-webkit-scrollbar-thumb:hover { background-color:hsl(var(--muted-foreground) / .55); }
@supports not selector(::-webkit-scrollbar) {
  * { scrollbar-width:thin; scrollbar-color:hsl(var(--muted-foreground) / .35) transparent; }
}
@media (prefers-reduced-motion: reduce) {
  #${TOGGLE_ID} svg { animation:none !important; transition:none !important; }
  html.rc-nb-animating [data-panel], html.rc-nb-animating [data-resize-handle] { transition:none !important; }
}
/* The notebook uses the sidebar's full width: Chainlit's 24px side padding is halved */
#side-view-content:has(#rc-panel-root) { padding-left:12px !important; padding-right:12px !important; }
/* Chainlit's own back arrow closes the panel for good; the top-bar toggle replaces it */
#side-view-title > button { display:none !important; }
`;

  // ---- sidebar collapse ----

  function readCollapsed() {
    try {
      return localStorage.getItem(COLLAPSED_KEY) === "1";
    } catch (e) {
      return false;
    }
  }

  let animTimer = null;

  function setCollapsed(on) {
    const root = document.documentElement;
    root.classList.add("rc-nb-animating");
    clearTimeout(animTimer);
    animTimer = setTimeout(() => root.classList.remove("rc-nb-animating"), 400);
    root.classList.toggle(COLLAPSED_CLASS, on);
    try {
      localStorage.setItem(COLLAPSED_KEY, on ? "1" : "0");
    } catch (e) {
      /* private window: just don't remember */
    }
    renderToggle();
  }

  function renderToggle() {
    const btn = document.getElementById(TOGGLE_ID);
    if (!btn) return;
    const collapsed = document.documentElement.classList.contains(COLLAPSED_CLASS);
    btn.textContent = "";
    btn.appendChild(icon(collapsed ? "panelOpen" : "panelClose", 18));
    const label = (collapsed ? "Show notebook" : "Hide notebook") + " (Ctrl+\\)";
    btn.title = label;
    btn.setAttribute("aria-label", label);
    btn.setAttribute("aria-pressed", String(!collapsed));
  }

  // Open the sidebar as wide as Chainlit allows (the chat keeps its 40% minimum). Done
  // once per divider, i.e. each time the sidebar opens; a later drag by the user is kept.
  // The Home key is the resize library's own "shrink the left panel to its minimum".
  const widened = new WeakSet();

  function widenSidebar() {
    const handle = document.querySelector("[data-resize-handle]:has(+ [data-panel] #side-view-content)");
    if (!handle || widened.has(handle)) return;
    widened.add(handle);
    if (document.documentElement.classList.contains(COLLAPSED_CLASS)) return;
    handle.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
  }

  function ensureToggle() {
    const theme = document.getElementById("theme-toggle");
    const hasSidebar = !!document.getElementById("side-view-content");
    let btn = document.getElementById(TOGGLE_ID);
    if (!theme || !hasSidebar) {
      // No notebook panel on screen (e.g. before a chat starts): no toggle
      if (btn) btn.remove();
      return;
    }
    if (btn && btn.nextElementSibling === theme) return;
    if (btn) btn.remove();
    btn = document.createElement("button");
    btn.id = TOGGLE_ID;
    btn.type = "button";
    btn.className = theme.className; // same look as Chainlit's own top-bar buttons
    btn.addEventListener("click", () => setCollapsed(!document.documentElement.classList.contains(COLLAPSED_CLASS)));
    theme.insertAdjacentElement("beforebegin", btn);
    renderToggle();
  }

  // ---- notebook panel bundle (plan: docs/plans/done/panel-react-build-plan.md) ----
  // The panel is a bundled React app (public/panel → public/build). Load it once per
  // page, same-origin only (SEC3). public/elements/Notebook.jsx waits on this promise.
  const PANEL_JS = "/public/build/notebook-panel.js";
  const PANEL_CSS = "/public/build/notebook-panel.css";

  function loadPanel() {
    if (!window.__rcPanelReady) {
      window.__rcPanelReady = new Promise((resolve) => (window.__rcPanelResolve = resolve));
    }
    if (document.querySelector(`script[src="${PANEL_JS}"]`)) return;
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = PANEL_CSS;
    document.head.appendChild(css);
    const js = document.createElement("script");
    js.type = "module";
    js.src = PANEL_JS;
    js.onerror = () => console.error("[notebook panel] could not load " + PANEL_JS);
    document.head.appendChild(js);
  }

  function mount() {
    loadPanel();
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);

    document.addEventListener("keydown", (e) => {
      if ((e.key === "\\" || e.code === "Backslash") && (e.ctrlKey || e.metaKey) && document.getElementById(TOGGLE_ID)) {
        e.preventDefault();
        setCollapsed(!document.documentElement.classList.contains(COLLAPSED_CLASS));
      }
    });
    document.documentElement.classList.toggle(COLLAPSED_CLASS, readCollapsed());
    // Chainlit redraws the page often; put the toggle back when it disappears
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      // setTimeout, not requestAnimationFrame: rAF doesn't run in background tabs
      setTimeout(() => {
        queued = false;
        ensureToggle();
        widenSidebar();
      }, 50);
    }).observe(document.body, { childList: true, subtree: true });
    ensureToggle();
    widenSidebar();
  }

  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);
})();
