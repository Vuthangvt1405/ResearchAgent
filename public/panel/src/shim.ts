// What the public/elements/Notebook.jsx shim does on each Chainlit mount (AC7).
// Chainlit compiles Notebook.jsx itself and it can't import this bundle, so the shim
// carries a plain-JS copy of connectShim; keep the two in step (a Python test checks
// that the shim still uses the same window names and timeout).
import type { RcPanelApi } from "@/main";
import type { CallAction, NotebookProps } from "@/types";

export const READY_TIMEOUT_MS = 10_000;
export const FALLBACK_TEXT = "Panel failed to load. Reload the page to try again.";

export interface ShimDeps {
  slot: HTMLElement;
  props: NotebookProps;
  callAction: CallAction;
  win?: Window;
}

/** Wait for the bundle, then pass props and attach the slot; returns a cleanup that detaches */
export function connectShim({ slot, props, callAction, win = window }: ShimDeps): () => void {
  let closed = false;
  let api: RcPanelApi | null = null;

  const fallback = () => {
    slot.textContent = "";
    const box = slot.ownerDocument.createElement("div");
    box.className = "rc-panel-fallback";
    box.setAttribute("role", "alert");
    box.textContent = FALLBACK_TEXT;
    slot.appendChild(box);
  };

  const ready = win.__rcPanelReady || (win.__rcPanelReady = new Promise<RcPanelApi>((resolve) => (win.__rcPanelResolve = resolve)));
  const timer = setTimeout(() => !api && !closed && fallback(), READY_TIMEOUT_MS);

  ready.then((a) => {
    if (closed) return;
    try {
      a.setCallAction(callAction);
      a.setProps(props);
      a.attach(slot);
      api = a;
      clearTimeout(timer);
      slot.textContent = ""; // a late bundle replaces the fallback
    } catch (e) {
      console.error("[notebook panel]", e);
      clearTimeout(timer);
      fallback();
    }
  });

  return () => {
    closed = true;
    clearTimeout(timer);
    if (api) api.detach(slot);
  };
}
