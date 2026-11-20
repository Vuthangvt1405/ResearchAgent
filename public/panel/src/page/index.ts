// Page-level extras around Chainlit's own UI, started once when the bundle loads:
// - a top-bar button (and Ctrl+\) that hides or shows the notebook sidebar
// - the Settings button, moved from the chat box to the top bar (same centred window)
// - a search box in the chat box Model picker (OpenRouter has hundreds of models)
// - a Connect / Disconnect button for the Kaggle account in Settings
// - thin, theme-coloured scrollbars (page.css)
// The project picker lives in the Notebook panel itself.
import "./page.css";
import { ensureKaggleButton } from "@/page/kaggleButton";
import { ensureModelSearch } from "@/page/modelSearch";
import { ensureSettingsButton } from "@/page/settingsButton";
import { COLLAPSED_CLASS, TOGGLE_ID, ensureToggle, isCollapsed, isToggleShortcut, readCollapsed, setCollapsed, widenSidebar } from "@/page/sidebarToggle";

const REDRAW_DEBOUNCE_MS = 50;

/** Put every extra back in place; Chainlit redraws the page often */
export function refreshPageExtras(doc: Document) {
  ensureToggle(doc);
  ensureSettingsButton(doc);
  ensureModelSearch(doc);
  ensureKaggleButton(doc);
  widenSidebar(doc);
}

function watchPageChanges(doc: Document): MutationObserver {
  let isQueued = false;
  const observer = new MutationObserver(() => {
    if (isQueued) return;
    isQueued = true;
    // setTimeout, not requestAnimationFrame: rAF doesn't run in background tabs
    setTimeout(() => {
      isQueued = false;
      refreshPageExtras(doc);
    }, REDRAW_DEBOUNCE_MS);
  });
  observer.observe(doc.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["disabled", "aria-checked"],
  });
  return observer;
}

/** Start the extras; returns a stop function (used by tests) */
export function startPageExtras(win: Window = window): () => void {
  const doc = win.document;
  const onKey = (e: KeyboardEvent) => {
    if (isToggleShortcut(e) && doc.getElementById(TOGGLE_ID)) {
      e.preventDefault();
      setCollapsed(doc, !isCollapsed(doc));
    }
  };
  doc.addEventListener("keydown", onKey);
  doc.documentElement.classList.toggle(COLLAPSED_CLASS, readCollapsed(win));
  const observer = watchPageChanges(doc);
  refreshPageExtras(doc);
  return () => {
    observer.disconnect();
    doc.removeEventListener("keydown", onKey);
  };
}
