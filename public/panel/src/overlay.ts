// The persistent root and where it lives (plan §4.1, D3 revised by D9).
//
// Chainlit remounts the sidebar element on every props push, but only the element
// itself: its container (#side-view-content, inside the sidebar on desktop or the
// sheet dialog on phones) stays the same DOM node. So #rc-panel-root lives inside that
// container and is moved only when Chainlit makes a new container (sidebar opened, or a
// switch between desktop and phone layout), never on a push. A focused textarea and
// its IME composition (Vietnamese Telex/VNI) are therefore never moved mid-typing.

export const HIDE_GRACE_MS = 300;
const ROOT_ID = "rc-panel-root";
const CONTAINER = "#side-view-content";
/** Fired on the root after it moved into a new container */
export const MOVED_EVENT = "rc-panel-moved";

export interface Overlay {
  /** Register the element's placeholder; the root moves into its container if needed */
  attach(slot: HTMLElement): void;
  /** Forget a placeholder; hide after HIDE_GRACE_MS if no other one appears */
  detach(slot: HTMLElement): void;
  /** The root the React app renders into */
  readonly root: HTMLElement;
}

/** The stable box around the placeholder: Chainlit's side view, else the slot's parent */
export function containerOf(slot: HTMLElement): HTMLElement | null {
  return slot.closest<HTMLElement>(CONTAINER) || slot.parentElement;
}

export function createOverlay(doc: Document = document): Overlay {
  let root = doc.getElementById(ROOT_ID);
  if (!root) {
    root = doc.createElement("div");
    root.id = ROOT_ID;
    root.hidden = true;
  }
  const el = root;
  const slots: HTMLElement[] = []; // most recent last
  let hideTimer: ReturnType<typeof setTimeout> | null = null;

  const current = () => {
    for (let i = slots.length - 1; i >= 0; i--) if (slots[i].isConnected) return slots[i];
    return null;
  };

  function place(slot: HTMLElement) {
    const box = containerOf(slot);
    // Move only when the container changed: a push keeps the same one
    if (box && el.parentNode !== box) {
      box.appendChild(el);
      el.dispatchEvent(new Event(MOVED_EVENT));
    }
    el.hidden = false;
  }

  return {
    root: el,
    attach(slot) {
      const i = slots.indexOf(slot);
      if (i !== -1) slots.splice(i, 1);
      slots.push(slot);
      if (hideTimer) {
        clearTimeout(hideTimer);
        hideTimer = null;
      }
      place(slot);
    },
    detach(slot) {
      const i = slots.indexOf(slot);
      if (i === -1) return; // detach before attach: nothing to do
      slots.splice(i, 1);
      if (current()) return;
      // The next placeholder normally arrives in the same tick; hide only if none does
      if (hideTimer) clearTimeout(hideTimer);
      hideTimer = setTimeout(() => {
        hideTimer = null;
        if (!current()) el.hidden = true;
      }, HIDE_GRACE_MS);
    },
  };
}
