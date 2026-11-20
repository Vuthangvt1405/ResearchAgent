// Page-level extras for the Notebook panel. Loaded through custom_js in .chainlit/config.toml.
// - a top-bar button (and Ctrl+\) that hides or shows the notebook sidebar
// - the Settings button, moved from the chat box to the top bar (same centred window)
// - a search box in the chat box Model picker (OpenRouter has hundreds of models)
// - thin, theme-coloured scrollbars
// The project picker lives in the Notebook panel itself (public/elements/Notebook.jsx).
(function () {
  "use strict";

  // Notebook sidebar collapse toggle (top bar, next to the theme button)
  const TOGGLE_ID = "rc-sidebar-toggle";
  const COLLAPSED_CLASS = "rc-nb-collapsed";
  const COLLAPSED_KEY = "rc-notebook-collapsed";

  // Settings button in the top bar. Chainlit's own one stays in the chat box, hidden, and
  // is clicked for us: that keeps its centred window and its own open/confirm handling.
  const SETTINGS_ID = "rc-settings-button";
  const COMPOSER_SETTINGS_ID = "chat-settings-open-modal";

  // Search box for the Model picker. Chainlit's picker is a plain list with no search, so
  // the box is added to its popover and hides the items that don't match.
  const MODEL_POPOVER_ID = "mode-picker-popover-model";
  const MODEL_SEARCH_ID = "rc-model-search";
  const MODEL_EMPTY_ID = "rc-model-search-empty";
  const HIDDEN_ATTR = "data-rc-hidden";

  const ICONS = {
    settings:
      '<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/>',
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
/* Model picker search: an attribute, not a class, so React's re-renders don't undo it */
#${MODEL_POPOVER_ID} [${HIDDEN_ATTR}] { display:none !important; }
#${MODEL_SEARCH_ID} { width:100%; box-sizing:border-box; margin:0 0 4px; padding:6px 8px; border-radius:6px;
  border:1px solid hsl(var(--border)); background:transparent; color:inherit; font-size:13px; outline:none; }
#${MODEL_SEARCH_ID}:focus { border-color:hsl(var(--ring)); }
#${MODEL_EMPTY_ID} { padding:12px 8px; font-size:13px; text-align:center; opacity:.7; }
/* The chat box keeps only what is used while typing; Settings opens from the top bar */
#${COMPOSER_SETTINGS_ID} { display:none !important; }
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

  // ---- Settings button in the top bar ----

  function openSettings() {
    const composerButton = document.getElementById(COMPOSER_SETTINGS_ID);
    if (composerButton && !composerButton.disabled) composerButton.click();
  }

  function ensureSettingsButton() {
    const theme = document.getElementById("theme-toggle");
    const composerButton = document.getElementById(COMPOSER_SETTINGS_ID);
    let btn = document.getElementById(SETTINGS_ID);
    if (!theme || !composerButton) {
      // No chat settings on screen (e.g. before a chat starts): no button
      if (btn) btn.remove();
      return;
    }
    // Sits left of the notebook toggle when there is one, else left of the theme button
    const anchor = document.getElementById(TOGGLE_ID) || theme;
    if (btn && btn.nextElementSibling === anchor) {
      btn.disabled = composerButton.disabled; // greyed while an answer is being written, like Chainlit's
      return;
    }
    if (btn) btn.remove();
    btn = document.createElement("button");
    btn.id = SETTINGS_ID;
    btn.type = "button";
    btn.className = theme.className;
    btn.title = "Settings";
    btn.setAttribute("aria-label", "Settings");
    btn.appendChild(icon("settings", 18));
    btn.disabled = composerButton.disabled;
    btn.addEventListener("click", openSettings);
    anchor.insertAdjacentElement("beforebegin", btn);
  }

  // ---- search box in the Model picker ----

  function modelItems(popover) {
    return Array.from(popover.querySelectorAll("[cmdk-item]"));
  }

  function filterModels(popover, query) {
    const words = query.toLowerCase().split(/\s+/).filter(Boolean);
    let shown = 0;
    for (const item of modelItems(popover)) {
      const text = item.textContent.toLowerCase();
      const matches = words.every((word) => text.includes(word));
      item.toggleAttribute(HIDDEN_ATTR, !matches);
      if (matches) shown += 1;
    }
    let empty = document.getElementById(MODEL_EMPTY_ID);
    if (shown === 0 && !empty) {
      empty = document.createElement("div");
      empty.id = MODEL_EMPTY_ID;
      empty.textContent = "No model matches";
      popover.appendChild(empty);
    } else if (shown > 0 && empty) {
      empty.remove();
    }
  }

  function pickFirstMatch(popover) {
    const first = modelItems(popover).find((item) => !item.hasAttribute(HIDDEN_ATTR));
    if (first) first.click();
  }

  function onSearchKey(e, popover) {
    if (e.key === "Escape") return; // let the picker close as usual
    // The picker's own arrow and Enter keys count hidden items too, so keep them out of here
    e.stopPropagation();
    if (e.key === "Enter") {
      e.preventDefault();
      pickFirstMatch(popover);
    }
  }

  function ensureModelSearch() {
    const popover = document.getElementById(MODEL_POPOVER_ID);
    if (!popover) return;
    const existing = document.getElementById(MODEL_SEARCH_ID);
    if (existing && popover.contains(existing)) {
      filterModels(popover, existing.value); // items re-drawn by Chainlit get the same filter
      return;
    }
    const input = document.createElement("input");
    input.id = MODEL_SEARCH_ID;
    input.type = "search";
    input.placeholder = "Search models…";
    input.setAttribute("aria-label", "Search models");
    input.autocomplete = "off";
    input.addEventListener("input", () => filterModels(popover, input.value));
    input.addEventListener("keydown", (e) => onSearchKey(e, popover));
    popover.insertAdjacentElement("afterbegin", input);
    setTimeout(() => input.focus(), 0);
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
        ensureSettingsButton();
        ensureModelSearch();
        widenSidebar();
      }, 50);
    }).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
    ensureToggle();
    ensureSettingsButton();
    widenSidebar();
  }

  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);
})();
