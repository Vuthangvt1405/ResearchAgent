// Whether the notebook panel is open (the panel is then the page's focus) and the Ctrl+\ shortcut.
// Only this choice is stored in the browser.
export const NOTEBOOK_OPEN_KEY = "sillytherin.notebookOpen";
const CLOSED = "closed";

export function isNotebookOpen(storage: Storage): boolean {
  try {
    return storage.getItem(NOTEBOOK_OPEN_KEY) !== CLOSED;
  } catch {
    return true; // a browser that refuses storage still gets the default
  }
}

export function rememberNotebookOpen(storage: Storage, isOpen: boolean): void {
  try {
    storage.setItem(NOTEBOOK_OPEN_KEY, isOpen ? "open" : CLOSED);
  } catch {
    // not remembered: the choice still applies to this page
  }
}

export function isToggleShortcut(event: KeyboardEvent): boolean {
  const hasCommandKey = event.ctrlKey || event.metaKey;
  // the physical key too: on some layouts "\\" needs AltGr, which changes event.key
  const isBackslash = event.key === "\\" || event.code === "Backslash";
  return hasCommandKey && !event.altKey && !event.shiftKey && isBackslash;
}

// ---- the chat's width while the notebook is open (the panel takes the rest)
export const CHAT_WIDTH_KEY = "sillytherin.chatWidth";
export const DEFAULT_CHAT_WIDTH = 400;
export const MIN_CHAT_WIDTH = 320;
export const MIN_PANEL_WIDTH = 360;
export const CHAT_WIDTH_STEP = 24; // one arrow-key press on the divider

/** A width both sides can live with: the chat at least MIN_CHAT_WIDTH, the panel at least MIN_PANEL_WIDTH */
export function clampChatWidth(width: number, rowWidth: number): number {
  const widest = Math.max(MIN_CHAT_WIDTH, rowWidth - MIN_PANEL_WIDTH);
  return Math.round(Math.min(Math.max(width, MIN_CHAT_WIDTH), widest));
}

export function readChatWidth(storage: Storage): number {
  try {
    const stored = Number.parseInt(storage.getItem(CHAT_WIDTH_KEY) ?? "", 10);
    return Number.isFinite(stored) ? stored : DEFAULT_CHAT_WIDTH;
  } catch {
    return DEFAULT_CHAT_WIDTH;
  }
}

export function rememberChatWidth(storage: Storage, width: number): void {
  try {
    storage.setItem(CHAT_WIDTH_KEY, String(width));
  } catch {
    // not remembered: the width still applies to this page
  }
}
