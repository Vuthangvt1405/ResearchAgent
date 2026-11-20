// A top-bar button (and Ctrl+\) that hides or shows the notebook sidebar.
import { createIcon } from "@/page/icons";
import { SIDEBAR_CONTENT_ID, THEME_BUTTON_ID } from "@/page/chainlitPage";

export const TOGGLE_ID = "rc-sidebar-toggle";
export const COLLAPSED_CLASS = "rc-nb-collapsed";
const ANIMATING_CLASS = "rc-nb-animating";
const COLLAPSED_KEY = "rc-notebook-collapsed";
const ANIMATION_MS = 400;

export function readCollapsed(win: Window): boolean {
  try {
    return win.localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function rememberCollapsed(win: Window, isCollapsed: boolean) {
  try {
    win.localStorage.setItem(COLLAPSED_KEY, isCollapsed ? "1" : "0");
  } catch {
    /* private window: just don't remember */
  }
}

export function isCollapsed(doc: Document): boolean {
  return doc.documentElement.classList.contains(COLLAPSED_CLASS);
}

let animationTimer: ReturnType<typeof setTimeout> | undefined;

export function setCollapsed(doc: Document, collapsed: boolean) {
  const root = doc.documentElement;
  root.classList.add(ANIMATING_CLASS);
  clearTimeout(animationTimer);
  animationTimer = setTimeout(() => root.classList.remove(ANIMATING_CLASS), ANIMATION_MS);
  root.classList.toggle(COLLAPSED_CLASS, collapsed);
  if (doc.defaultView) rememberCollapsed(doc.defaultView, collapsed);
  renderToggle(doc);
}

function renderToggle(doc: Document) {
  const button = doc.getElementById(TOGGLE_ID);
  if (!button) return;
  const collapsed = isCollapsed(doc);
  button.textContent = "";
  button.appendChild(createIcon(doc, collapsed ? "panelOpen" : "panelClose", 18));
  const label = (collapsed ? "Show notebook" : "Hide notebook") + " (Ctrl+\\)";
  button.title = label;
  button.setAttribute("aria-label", label);
  button.setAttribute("aria-pressed", String(!collapsed));
}

/** Put the toggle left of the theme button while a sidebar is on screen; remove it otherwise */
export function ensureToggle(doc: Document) {
  const theme = doc.getElementById(THEME_BUTTON_ID);
  const hasSidebar = !!doc.getElementById(SIDEBAR_CONTENT_ID);
  let button = doc.getElementById(TOGGLE_ID);
  if (!theme || !hasSidebar) {
    // No notebook panel on screen (e.g. before a chat starts): no toggle
    button?.remove();
    return;
  }
  if (button && button.nextElementSibling === theme) return;
  button?.remove();
  button = doc.createElement("button");
  button.id = TOGGLE_ID;
  (button as HTMLButtonElement).type = "button";
  button.className = theme.className; // same look as Chainlit's own top-bar buttons
  button.addEventListener("click", () => setCollapsed(doc, !isCollapsed(doc)));
  theme.insertAdjacentElement("beforebegin", button);
  renderToggle(doc);
}

export function isToggleShortcut(e: KeyboardEvent): boolean {
  return (e.key === "\\" || e.code === "Backslash") && (e.ctrlKey || e.metaKey);
}

// Open the sidebar as wide as Chainlit allows (the chat keeps its 40% minimum). Done
// once per divider, i.e. each time the sidebar opens; a later drag by the user is kept.
// The Home key is the resize library's own "shrink the left panel to its minimum".
const widenedHandles = new WeakSet<Element>();

export function widenSidebar(doc: Document) {
  const handle = doc.querySelector(`[data-resize-handle]:has(+ [data-panel] #${SIDEBAR_CONTENT_ID})`);
  if (!handle || widenedHandles.has(handle)) return;
  widenedHandles.add(handle);
  if (isCollapsed(doc)) return;
  handle.dispatchEvent(new KeyboardEvent("keydown", { key: "Home", bubbles: true }));
}
