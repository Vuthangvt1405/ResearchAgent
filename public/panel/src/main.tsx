// Bundle entry: creates the persistent root once and exposes window.__rcPanel for the
// Notebook.jsx shim (plan §4.2). Loaded same-origin by public/custom.js.
import { createRoot, type Root } from "react-dom/client";
import { App } from "@/components/App";
import { createOverlay } from "@/overlay";
import { usePanel } from "@/store";
import type { CallAction, NotebookProps } from "@/types";
import "./styles.css";

export interface RcPanelApi {
  attach(slot: HTMLElement): void;
  detach(slot: HTMLElement): void;
  setProps(props: NotebookProps): void;
  setCallAction(fn: CallAction): void;
}

declare global {
  interface Window {
    __rcPanel?: RcPanelApi;
    __rcPanelReady?: Promise<RcPanelApi>;
    __rcPanelResolve?: (api: RcPanelApi) => void;
    /** Chainlit's copilot shadow root; its shadcn portals render there when set */
    cl_shadowRootElement?: HTMLElement;
  }
}

let reactRoot: Root | null = null;

/** Create the root and the API exactly once; later calls return the same API */
export function bootstrap(win: Window = window): RcPanelApi {
  if (win.__rcPanel) return win.__rcPanel;
  const overlay = createOverlay(win.document);
  reactRoot = createRoot(overlay.root);
  reactRoot.render(<App />);
  const api: RcPanelApi = {
    attach: (slot) => overlay.attach(slot),
    detach: (slot) => overlay.detach(slot),
    setProps: (props) => usePanel.getState().setProps(props),
    setCallAction: (fn) => usePanel.getState().setCallAction(fn),
  };
  win.__rcPanel = api;
  // custom.js usually created the promise before this module loaded
  if (win.__rcPanelResolve) win.__rcPanelResolve(api);
  else win.__rcPanelReady = Promise.resolve(api);
  return api;
}

/** Tests only: unmount the root and forget the API, so the next test starts clean */
export function teardown(win: Window = window) {
  reactRoot?.unmount();
  reactRoot = null;
  delete win.__rcPanel;
  delete win.__rcPanelReady;
  delete win.__rcPanelResolve;
}

if (import.meta.env.MODE !== "test") bootstrap();
