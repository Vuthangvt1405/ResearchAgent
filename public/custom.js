// Loads the bundled frontend (public/panel → public/build). Loaded through custom_js in
// .chainlit/config.toml. The bundle holds the Notebook panel and the page-level extras
// (sidebar toggle, top-bar Settings button, Model picker search, Kaggle button in
// Settings, scrollbars); see public/panel/src/page. Same-origin only.
(function () {
  "use strict";

  const PANEL_JS = "/public/build/notebook-panel.js";
  const PANEL_CSS = "/public/build/notebook-panel.css";
  // Chainlit serves /public without cache headers, so a browser may reuse an old bundle next to
  // a new custom.js. A per-page-load query always fetches the current build (localhost: cheap).
  const PAGE_LOAD = String(Date.now());
  const LOADED_ATTR = "data-rc-panel";

  // public/elements/Notebook.jsx waits on this promise; the bundle resolves it
  function loadPanel() {
    if (!window.__rcPanelReady) {
      window.__rcPanelReady = new Promise((resolve) => (window.__rcPanelResolve = resolve));
    }
    if (document.querySelector(`script[${LOADED_ATTR}]`)) return;
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = `${PANEL_CSS}?v=${PAGE_LOAD}`;
    document.head.appendChild(css);
    const js = document.createElement("script");
    js.type = "module";
    js.src = `${PANEL_JS}?v=${PAGE_LOAD}`;
    js.setAttribute(LOADED_ATTR, "");
    js.onerror = () => console.error("[notebook panel] could not load " + PANEL_JS);
    document.head.appendChild(js);
  }

  if (document.head) loadPanel();
  else document.addEventListener("DOMContentLoaded", loadPanel);
})();
