// Notebook panel shim for the right sidebar (plan: docs/plans/done/panel-react-build-plan.md).
// props = NotebookProps from researchchat/workspace/service.py.
//
// Chainlit recompiles and remounts this element on every props push (about once a
// second while a dataset downloads). So this file draws nothing itself: it renders an
// empty placeholder and hands props and callAction to the bundled panel app
// (public/panel → public/build/notebook-panel.js, loaded by public/custom.js). That app
// lives in a root inside Chainlit's side-view container, which a push doesn't replace,
// so it never moves or unmounts on a push: open menus, focus, the cursor and IME
// composition (Vietnamese Telex/VNI) survive.
//
// The wait-and-fallback logic below is a plain-JS copy of connectShim() in
// public/panel/src/shim.ts (tested there); keep the two in step.
import { useEffect, useRef } from "react";

const READY_TIMEOUT_MS = 10000;
const FALLBACK_TEXT = "Panel failed to load. Reload the page to try again.";

export default function Notebook() {
  const slotRef = useRef(null);

  useEffect(() => {
    const slot = slotRef.current;
    let closed = false;
    let api = null;
    const fallback = () => {
      slot.textContent = "";
      const box = document.createElement("div");
      box.className = "rc-panel-fallback";
      box.setAttribute("role", "alert");
      box.textContent = FALLBACK_TEXT;
      slot.appendChild(box);
    };
    const ready = window.__rcPanelReady || (window.__rcPanelReady = new Promise((resolve) => (window.__rcPanelResolve = resolve)));
    const timer = setTimeout(() => !api && !closed && fallback(), READY_TIMEOUT_MS);
    ready.then((a) => {
      if (closed) return;
      try {
        a.setCallAction(callAction);
        a.setProps(props);
        a.attach(slot);
        api = a;
        clearTimeout(timer);
        slot.textContent = "";
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
  }, []);

  useEffect(() => {
    // If Chainlit ever re-renders without a remount, still pass the new props on
    if (window.__rcPanel) {
      window.__rcPanel.setCallAction(callAction);
      window.__rcPanel.setProps(props);
    }
  });

  // An empty marker: the app renders next to it, in the same container
  return <div ref={slotRef} data-rc-panel-slot="" />;
}
