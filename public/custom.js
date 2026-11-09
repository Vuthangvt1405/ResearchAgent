// Project picker inside the chat message box (AC18, plan §4.1, Q1b = b).
// A pill next to the attach and settings buttons, like Claude Code's folder
// picker; it opens a menu above it. Loaded through custom_js in .chainlit/config.toml.
// It has no server access of its own: it asks the Notebook panel to call the
// session-checked nb_* actions, using these window events.
(function () {
  "use strict";

  const EVENT_SWITCH = "rc:switch-project"; // picker -> panel: { project_id }
  const EVENT_CREATE = "rc:create-project"; // picker -> panel: { name }
  const EVENT_PROJECTS = "rc:projects"; // panel -> picker: { projects: [{id, name}], current }
  const EVENT_REQUEST = "rc:projects-request"; // picker -> panel
  const PILL_ID = "rc-project-pill";
  const MENU_ID = "rc-project-menu";

  let state = { projects: [], current: null };

  // Notebook sidebar collapse toggle (top bar, next to the theme button)
  const TOGGLE_ID = "rc-sidebar-toggle";
  const COLLAPSED_CLASS = "rc-nb-collapsed";
  const COLLAPSED_KEY = "rc-notebook-collapsed";

  const ICONS = {
    panelClose: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/><path d="m8 9 3 3-3 3"/>',
    panelOpen: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M15 3v18"/><path d="m10 15-3-3 3-3"/>',
    folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
  };

  function icon(name, size) {
    const span = document.createElement("span");
    span.style.cssText = "display:inline-flex;flex:none";
    // Fixed SVG paths from this file only; no user text goes in here
    span.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
    return span;
  }

  const CSS = `
#${PILL_ID} { display:inline-flex; align-items:center; gap:6px; height:32px; max-width:220px; margin-left:4px; padding:0 10px 0 9px;
  border:1px solid hsl(var(--border)); border-radius:999px; background:transparent; color:hsl(var(--muted-foreground));
  font:500 13px/1 ui-sans-serif,-apple-system,"Segoe UI",sans-serif; cursor:pointer; transition:background .12s,color .12s; }
#${PILL_ID}:hover, #${PILL_ID}[aria-expanded="true"] { background:hsl(var(--accent)); color:hsl(var(--foreground)); }
#${PILL_ID} .rc-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rc-project-menu { position:fixed; z-index:1000; min-width:240px; max-width:320px; max-height:320px; overflow-y:auto; padding:4px;
  border-radius:10px; background:hsl(var(--popover)); color:hsl(var(--popover-foreground)); border:1px solid hsl(var(--border));
  box-shadow:0 8px 28px rgba(0,0,0,.25); font:14px/1.4 ui-sans-serif,-apple-system,"Segoe UI",sans-serif; }
.rc-project-menu .rc-head { padding:6px 10px 4px; font-size:11px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:hsl(var(--muted-foreground)); }
.rc-project-menu button { display:flex; align-items:center; gap:8px; width:100%; padding:7px 10px; border:0; border-radius:6px; background:none; color:inherit; font:inherit; text-align:left; cursor:pointer; }
.rc-project-menu button:hover, .rc-project-menu button:focus-visible { background:hsl(var(--accent)); outline:none; }
.rc-project-menu .rc-label { flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.rc-project-menu .rc-rule { height:1px; margin:4px 0; background:hsl(var(--border)); }
.rc-project-menu .rc-muted { color:hsl(var(--muted-foreground)); }
.rc-project-menu .rc-new { display:flex; gap:6px; padding:4px; }
.rc-project-menu .rc-new input { flex:1; min-width:0; padding:6px 8px; border:1px solid hsl(var(--border)); border-radius:6px; background:transparent; color:inherit; font:inherit; outline:none; }
.rc-project-menu .rc-new input:focus { border-color:hsl(var(--ring)); }
.rc-project-menu .rc-new button { width:auto; padding:6px 10px; background:hsl(var(--primary)); color:hsl(var(--primary-foreground)); justify-content:center; }
.rc-project-menu .rc-new button:hover { background:hsl(var(--primary)); opacity:.9; }
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
/* Project menu: fades and rises in; the pill's arrow turns while it's open */
.rc-project-menu { transform-origin:bottom left; animation:rc-pop .16s cubic-bezier(.2,.9,.3,1.2); }
.rc-project-menu.rc-closing { animation:rc-pop-out .12s ease forwards; }
.rc-project-menu button, .rc-project-menu .rc-new { animation:rc-item .22s ease both; }
.rc-project-menu > :nth-child(2) { animation-delay:.02s } .rc-project-menu > :nth-child(3) { animation-delay:.04s }
.rc-project-menu > :nth-child(4) { animation-delay:.06s } .rc-project-menu > :nth-child(5) { animation-delay:.08s }
.rc-project-menu > :nth-child(n+6) { animation-delay:.1s }
#${PILL_ID} > span:last-child { transition:transform .2s ease; }
#${PILL_ID}[aria-expanded="true"] > span:last-child { transform:rotate(180deg); }
#${PILL_ID}:active { transform:scale(.97); }
#${PILL_ID}.rc-changed .rc-name { animation:rc-swap .3s ease; }
@keyframes rc-pop { from { opacity:0; transform:translateY(6px) scale(.96); } to { opacity:1; transform:none; } }
@keyframes rc-pop-out { to { opacity:0; transform:translateY(4px) scale(.98); } }
@keyframes rc-item { from { opacity:0; transform:translateY(3px); } to { opacity:1; transform:none; } }
@keyframes rc-swap { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
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
  .rc-project-menu, .rc-project-menu *, #${PILL_ID} *, #${TOGGLE_ID} svg { animation:none !important; transition:none !important; }
  html.rc-nb-animating [data-panel], html.rc-nb-animating [data-resize-handle] { transition:none !important; }
}
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

  function currentName() {
    const p = state.projects.find((x) => x.id === state.current);
    return p ? p.name : "Project";
  }

  // ---- the pill ----

  function findToolbar() {
    // Left group of the message box toolbar (attach + settings); null if Chainlit's layout changed
    const settings = document.getElementById("chat-settings-open-modal");
    if (settings && settings.parentElement) return settings.parentElement;
    const upload = document.getElementById("upload-button");
    return upload ? upload.closest("div") : null;
  }

  function renderPill(pill) {
    // A switched project name slides in
    const before = pill.querySelector(".rc-name");
    if (before && before.textContent !== currentName()) {
      pill.classList.remove("rc-changed");
      void pill.offsetWidth; // restart the animation
      pill.classList.add("rc-changed");
    }
    pill.textContent = "";
    const name = document.createElement("span");
    name.className = "rc-name";
    name.textContent = currentName(); // textContent: names are never parsed as HTML
    pill.append(icon("folder", 15), name, icon("chevron", 14));
    pill.title = `Project: ${currentName()} (switch or create)`;
  }

  function ensurePill() {
    const toolbar = findToolbar();
    if (!toolbar) return;
    let pill = document.getElementById(PILL_ID);
    if (pill && pill.parentElement === toolbar) return;
    if (pill) pill.remove();
    pill = document.createElement("button");
    pill.id = PILL_ID;
    pill.type = "button";
    pill.setAttribute("aria-haspopup", "menu");
    pill.setAttribute("aria-expanded", "false");
    pill.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      document.getElementById(MENU_ID) ? closeMenu() : openMenu(pill);
    });
    toolbar.appendChild(pill);
    window.__rcProjectBarMounted = true;
    renderPill(pill);
    if (!state.projects.length) window.dispatchEvent(new CustomEvent(EVENT_REQUEST));
  }

  // ---- the menu ----

  function closeMenu() {
    const menu = document.getElementById(MENU_ID);
    if (menu) {
      // Play the fade-out, then remove; a new id lets a fresh menu open meanwhile
      menu.id = "";
      menu.classList.add("rc-closing");
      menu.style.pointerEvents = "none";
      setTimeout(() => menu.remove(), 130);
    }
    const pill = document.getElementById(PILL_ID);
    if (pill) pill.setAttribute("aria-expanded", "false");
  }

  function item(iconName, text, onPick, muted) {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "menuitem");
    const label = document.createElement("span");
    label.className = "rc-label";
    label.textContent = text;
    const mark = iconName ? icon(iconName, 15) : document.createElement("span");
    mark.style.width = "15px";
    if (muted) b.classList.add("rc-muted");
    b.append(mark, label);
    b.addEventListener("click", () => {
      closeMenu();
      onPick();
    });
    return b;
  }

  function openMenu(pill) {
    closeMenu();
    window.dispatchEvent(new CustomEvent(EVENT_REQUEST)); // refresh the list
    const menu = document.createElement("div");
    menu.id = MENU_ID;
    menu.className = "rc-project-menu";
    menu.setAttribute("role", "menu");
    const head = document.createElement("div");
    head.className = "rc-head";
    head.textContent = "Projects";
    menu.appendChild(head);
    for (const p of state.projects) {
      menu.appendChild(
        item(p.id === state.current ? "check" : null, p.name, () => {
          if (p.id !== state.current) window.dispatchEvent(new CustomEvent(EVENT_SWITCH, { detail: { project_id: p.id } }));
        })
      );
    }
    const rule = document.createElement("div");
    rule.className = "rc-rule";
    menu.appendChild(rule);
    // "New project…" turns into a name field in place (no browser prompt)
    const newItem = item("plus", "New project…", () => {}, true);
    newItem.addEventListener(
      "click",
      (e) => {
        e.stopImmediatePropagation();
        const form = document.createElement("form");
        form.className = "rc-new";
        const input = document.createElement("input");
        input.placeholder = "Project name";
        input.maxLength = 80;
        input.setAttribute("aria-label", "New project name");
        const ok = document.createElement("button");
        ok.type = "submit";
        ok.textContent = "Create";
        form.append(input, ok);
        form.addEventListener("submit", (ev) => {
          ev.preventDefault();
          const name = input.value.trim();
          if (!name) return input.focus();
          closeMenu();
          window.dispatchEvent(new CustomEvent(EVENT_CREATE, { detail: { name } }));
        });
        newItem.after(form);
        newItem.remove();
        input.focus();
      },
      true
    );
    menu.appendChild(newItem);
    document.body.appendChild(menu);

    // Open upwards from the pill, kept inside the window
    const r = pill.getBoundingClientRect();
    const m = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(r.left, window.innerWidth - m.width - 8)) + "px";
    menu.style.top = Math.max(8, r.top - m.height - 6) + "px";
    pill.setAttribute("aria-expanded", "true");
    const first = menu.querySelector("button");
    if (first) first.focus();
  }

  function mount() {
    const style = document.createElement("style");
    style.textContent = CSS;
    document.head.appendChild(style);

    window.addEventListener(EVENT_PROJECTS, (e) => {
      state = { projects: e.detail.projects || [], current: e.detail.current };
      const pill = document.getElementById(PILL_ID);
      if (pill) renderPill(pill);
    });
    document.addEventListener("mousedown", (e) => {
      const menu = document.getElementById(MENU_ID);
      if (menu && !menu.contains(e.target) && e.target.id !== PILL_ID && !e.target.closest("#" + PILL_ID)) closeMenu();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeMenu();
      if ((e.key === "\\" || e.code === "Backslash") && (e.ctrlKey || e.metaKey) && document.getElementById(TOGGLE_ID)) {
        e.preventDefault();
        setCollapsed(!document.documentElement.classList.contains(COLLAPSED_CLASS));
      }
    });
    window.addEventListener("resize", closeMenu);
    document.documentElement.classList.toggle(COLLAPSED_CLASS, readCollapsed());
    // Chainlit redraws the page often; put our buttons back when they disappear
    let queued = false;
    new MutationObserver(() => {
      if (queued) return;
      queued = true;
      // setTimeout, not requestAnimationFrame: rAF doesn't run in background tabs
      setTimeout(() => {
        queued = false;
        ensurePill();
        ensureToggle();
      }, 50);
    }).observe(document.body, { childList: true, subtree: true });
    ensurePill();
    ensureToggle();
  }

  if (document.body) mount();
  else document.addEventListener("DOMContentLoaded", mount);
})();
