// Zustand store: the merged props and the UI state that used to live on
// window.__rcNotebook (plan §4.1). The React root never unmounts now, so this only
// holds state that outside code (the shim) feeds in, or that several parts share.
import { create } from "zustand";
import { newer } from "@/lib/newer";
import type { ActionResult, CallAction, NotebookProps } from "@/types";

export interface Focus { id: string; start: number; end: number }

export interface PanelState {
  nb: NotebookProps | null;
  callAction: CallAction | null;
  tab: "notebook" | "datasets";
  /** cell id -> unsaved text */
  drafts: Record<string, string>;
  /** cell id with an active IME composition (AC10) */
  composing: string | null;
  /** where the cursor should go when a new or inserted cell mounts */
  focus: Focus | null;
  /** note ids open for editing */
  editing: Record<string, boolean>;
  dsOpen: Record<string, boolean>;
  dsFilter: string;
  dsSort: "newest" | "name" | "size";
  setProps: (props: NotebookProps) => void;
  /** Merge an action reply that carries props; returns the reply */
  apply: (result: ActionResult) => ActionResult;
  setCallAction: (fn: CallAction) => void;
  resetForProject: () => void;
}

const PROJECT_STATE = { drafts: {}, composing: null, focus: null, editing: {}, dsOpen: {}, dsFilter: "" } as const;

export const usePanel = create<PanelState>()((set, get) => ({
  nb: null,
  callAction: null,
  tab: "notebook",
  ...PROJECT_STATE,
  dsSort: "newest",

  setProps: (props) => {
    const prev = get().nb;
    if (prev && prev.project.id !== props.project.id) get().resetForProject();
    const next = newer(prev, props);
    if (next !== prev) set({ nb: next });
  },

  apply: (result) => {
    if (result && result.cells) {
      const prev = get().nb;
      let next = newer(prev, result as NotebookProps);
      if (result.error) next = { ...next, error: result.error };
      set({ nb: next });
    }
    return result;
  },

  setCallAction: (fn) => {
    if (get().callAction !== fn) set({ callAction: fn });
  },

  resetForProject: () => set({ ...PROJECT_STATE, drafts: {}, editing: {}, dsOpen: {} }),
}));

/** Test helper: back to a fresh store */
export function resetStore() {
  usePanel.setState({ nb: null, callAction: null, tab: "notebook", ...PROJECT_STATE, drafts: {}, editing: {}, dsOpen: {}, dsSort: "newest" });
}
