// The Notebook panel's behaviour, one hook per concern, so Notebook.tsx only lays out parts.
import { useEffect, useRef, useState, type DragEvent, type RefObject } from "react";
import { MOVED_EVENT } from "@/overlay";
import type { CellProps, NotebookProps } from "@/types";

const SCROLL_SHADOW_AFTER_PX = 4;
const SCROLL_TO_RUNNING_DELAY_MS = 80;
const ENTER_ANIMATION_MS = 400;

// ---- keyboard shortcuts ----

export interface ShortcutActions {
  closeOverlays: () => void;
  saveAll: () => void;
  runAll: () => void;
}

/** Escape, Ctrl+S and Ctrl+Shift+Enter while focus is inside the panel */
export function useNotebookShortcuts(rootRef: RefObject<HTMLElement>, actions: ShortcutActions) {
  // Re-bound on every render on purpose: the handler always sees the latest actions
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const inside = rootRef.current && rootRef.current.contains(document.activeElement);
      if (e.key === "Escape") {
        if (inside) actions.closeOverlays();
        return;
      }
      const mod = e.ctrlKey || e.metaKey;
      if (inside && mod && !e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        actions.saveAll();
      }
      if (inside && mod && e.shiftKey && e.key === "Enter") {
        e.preventDefault();
        actions.runAll();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });
}

// ---- sticky header shadow ----

// The sidebar owns the scroll container (port of findScrollParent)
function scrollParent(el: HTMLElement | null): HTMLElement | null {
  let node = el && el.parentElement;
  while (node) {
    if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node;
    node = node.parentElement;
  }
  return (document.scrollingElement as HTMLElement) || null;
}

/**
 * True once the sidebar that scrolls the panel is scrolled, for the header's shadow.
 * Re-bound when the root moves to a new container (sidebar reopened, phone layout).
 */
export function useStickyHeader(rootRef: RefObject<HTMLElement>): boolean {
  const [isStuck, setIsStuck] = useState(false);
  useEffect(() => {
    let off: (() => void) | null = null;
    const bind = () => {
      off?.();
      const el = scrollParent(rootRef.current);
      if (!el) return;
      const sync = () => setIsStuck(el.scrollTop > SCROLL_SHADOW_AFTER_PX);
      sync();
      el.addEventListener("scroll", sync, { passive: true });
      off = () => el.removeEventListener("scroll", sync);
    };
    bind();
    const host = rootRef.current?.closest("#rc-panel-root");
    host?.addEventListener(MOVED_EVENT, bind);
    return () => {
      off?.();
      host?.removeEventListener(MOVED_EVENT, bind);
    };
  }, []);
  return isStuck;
}

// ---- running cell ----

/** Bring a newly running cell into view, without jumping when it is already visible */
export function useScrollToRunningCell(rootRef: RefObject<HTMLElement>, runningCellId: string | null) {
  const lastRunning = useRef<string | null>(null);
  useEffect(() => {
    if (runningCellId && runningCellId !== lastRunning.current) {
      lastRunning.current = runningCellId;
      const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const t = setTimeout(() => {
        const node = rootRef.current?.querySelector(`[data-cell-id="${CSS.escape(runningCellId)}"]`);
        if (node) node.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
      }, SCROLL_TO_RUNNING_DELAY_MS);
      return () => clearTimeout(t);
    }
    if (!runningCellId) lastRunning.current = null;
    return undefined;
  }, [runningCellId]);
}

// ---- block enter animation ----

/** Blocks animate in only the first time they are drawn for this project */
export function useFreshBlocks(projectId: string | undefined, cells: CellProps[]) {
  const seen = useRef<{ project: string; ids: Set<string>; until: Record<string, number> } | null>(null);
  if (projectId !== undefined && (!seen.current || seen.current.project !== projectId)) {
    seen.current = { project: projectId, ids: new Set(cells.map((c) => c.id)), until: {} };
  }
  return (id: string) => {
    const s = seen.current!;
    if (!s.ids.has(id)) {
      s.ids.add(id);
      s.until[id] = Date.now() + ENTER_ANIMATION_MS;
    }
    return Date.now() < (s.until[id] || 0);
  };
}

// ---- drag and drop ----

export interface Drop { id: string; before: boolean }

export function useDragReorder(cells: CellProps[], reorder: (cellId: string, beforeId: string | null) => Promise<unknown>) {
  const [drag, setDrag] = useState<string | null>(null);
  const [drop, setDrop] = useState<Drop | null>(null);

  const startDrag = (e: DragEvent, cell: CellProps) => {
    setDrag(cell.id);
    setDrop(null);
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", cell.id); } catch { /* older browsers */ }
    }
  };
  const overBlock = (e: DragEvent, cell: CellProps) => {
    if (!drag || drag === cell.id) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const before = e.clientY < rect.top + rect.height / 2;
    if (!drop || drop.id !== cell.id || drop.before !== before) setDrop({ id: cell.id, before });
  };
  const endDrag = () => {
    setDrag(null);
    setDrop(null);
  };
  const dropOn = async (e: DragEvent, cell: CellProps) => {
    e.preventDefault();
    e.stopPropagation();
    const dragId = drag;
    const where = drop;
    endDrag();
    if (!dragId || dragId === cell.id) return;
    let beforeId: string | null = cell.id;
    if (where && where.id === cell.id && !where.before) {
      const i = cells.findIndex((c) => c.id === cell.id);
      beforeId = cells[i + 1] ? cells[i + 1].id : null;
    }
    await reorder(dragId, beforeId);
  };

  return { drag, drop, startDrag, overBlock, endDrag, dropOn };
}

// ---- find ----

export function useCellFind(cells: CellProps[], sourceOf: (cell: CellProps) => string) {
  const findRef = useRef<HTMLInputElement>(null);
  const [find, setFind] = useState("");
  const [findOpen, setFindOpen] = useState(false);

  const q = find.trim().toLowerCase();
  const focusedCell = (document.activeElement as HTMLElement | null)?.getAttribute?.("data-cell-src");
  const matches = (cell: CellProps) => !q
    || sourceOf(cell).toLowerCase().includes(q)
    || (cell.outputs || []).some((o) => (o.text || "").toLowerCase().includes(q));
  // The cell being typed in stays visible even when the edit makes it stop matching
  const visible = cells.filter((cell) => matches(cell) || (q && focusedCell === cell.id));
  const matchIds = new Set(q ? visible.map((c) => c.id) : []);

  const toggleFind = () => {
    const next = !findOpen;
    setFindOpen(next);
    if (!next) setFind("");
    else setTimeout(() => findRef.current?.focus(), 0);
  };
  const closeFind = () => {
    setFind("");
    setFindOpen(false);
  };
  const clearFind = () => {
    setFind("");
    findRef.current?.focus();
  };

  return { findRef, find, setFind, findOpen, q, visible, matchIds, toggleFind, closeFind, clearFind };
}

// ---- problem line and save badge ----

/** The one problem shown above the cells: the last action's error first, then the server's, then the kernel's */
export function problemText(runnerError: string | null, nb: NotebookProps): string | null {
  if (runnerError) return runnerError;
  if (nb.error) return nb.error.message;
  if (nb.kernel === "dead") return "The kernel died (maybe out of memory). Press Restart.";
  if (nb.kernel === "unavailable") return "Docker isn't running: start Docker Desktop, then press Restart.";
  return null;
}

export type SaveState = "saving" | "dirty" | "saved" | "";

export function saveState(pendingSaves: number, draftCount: number, savedAt: number): SaveState {
  if (pendingSaves) return "saving";
  if (draftCount) return "dirty";
  if (savedAt) return "saved";
  return "";
}
