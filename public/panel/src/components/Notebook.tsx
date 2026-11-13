// The panel (port of the old Notebook() default export). It lives in a React root that
// never unmounts, so local state survives every props push (AC1).
import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { AlertCircle, Check, Code2, Database, Eraser, FastForward, GripVertical, Loader2, NotebookPen, Plus, RotateCcw, Search, SearchX, Square, StickyNote, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BlockMenu, type BlockActions } from "@/components/BlockMenu";
import { CodeCell } from "@/components/CodeCell";
import { DatasetsTab } from "@/components/DatasetsTab";
import { InsertRow } from "@/components/InsertRow";
import { NoteCell } from "@/components/NoteCell";
import { ProjectPicker } from "@/components/ProjectPicker";
import { usePanel } from "@/store";
import { MOVED_EVENT } from "@/overlay";
import { copyText, isActive } from "@/lib/loadCode";
import { useNotebookActions } from "@/lib/notebookActions";
import type { CellProps } from "@/types";

// Status dot colours follow the panel's light/dark tokens
const KERNEL: Record<string, [string, string]> = {
  off: ["hsl(var(--muted-foreground))", "Kernel off · starts on first run"],
  starting: ["hsl(var(--rc-warn))", "Starting kernel…"],
  idle: ["hsl(var(--rc-ok))", "Ready"],
  busy: ["hsl(var(--rc-warn))", "Running…"],
  dead: ["hsl(var(--rc-danger))", "Kernel died"],
  unavailable: ["hsl(var(--rc-danger))", "Docker not running"],
};

interface Drop { id: string; before: boolean }

// The sidebar owns the scroll container (port of findScrollParent)
function scrollParent(el: HTMLElement | null): HTMLElement | null {
  let node = el && el.parentElement;
  while (node) {
    if (/(auto|scroll)/.test(getComputedStyle(node).overflowY)) return node;
    node = node.parentElement;
  }
  return (document.scrollingElement as HTMLElement) || null;
}

function Block({ cell, fresh, menuOpen, setMenu, actions, dragging, drop, onDragStart, onDragOver, onDrop, onDragEnd, children }: {
  cell: CellProps; fresh: boolean; menuOpen: boolean; setMenu: (id: string | null) => void; actions: BlockActions;
  dragging: string | null; drop: Drop | null;
  onDragStart: (e: DragEvent, cell: CellProps) => void; onDragOver: (e: DragEvent, cell: CellProps) => void;
  onDrop: (e: DragEvent, cell: CellProps) => void; onDragEnd: () => void; children: ReactNode;
}) {
  const dropCls = drop && drop.id === cell.id && dragging && dragging !== cell.id ? (drop.before ? " drop-before" : " drop-after") : "";
  return (
    <div
      className={`rcnb-block${fresh ? " rcnb-enter" : ""}${dragging === cell.id ? " dragging" : ""}${dropCls}`}
      data-cell-id={cell.id}
      onDragOver={(e) => onDragOver(e, cell)}
      onDrop={(e) => onDrop(e, cell)}
    >
      <div className={`rcnb-gutter${menuOpen ? " open" : ""}`}>
        <button
          className="rcnb-handle"
          title="Drag to reorder, or click for actions"
          aria-label="Block actions"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          data-rc-toggle={`menu:${cell.id}`}
          draggable
          onDragStart={(e) => onDragStart(e, cell)}
          onDragEnd={onDragEnd}
          onClick={() => setMenu(menuOpen ? null : cell.id)}
        >
          <GripVertical size={16} />
        </button>
      </div>
      <BlockMenu cell={cell} actions={actions} open={menuOpen} setMenu={setMenu} />
      <div className="rcnb-body">{children}</div>
    </div>
  );
}

function Problem({ text, dismiss }: { text: string; dismiss?: () => void }) {
  return (
    <div className="rcnb-callout" role="alert">
      <AlertCircle size={15} />
      <span style={{ flex: 1 }}>{text}</span>
      {dismiss && (
        <button className="rcnb-mini" title="Dismiss" aria-label="Dismiss error" onClick={dismiss}>
          <X size={13} />
        </button>
      )}
    </div>
  );
}

export function Notebook() {
  const nb = usePanel((s) => s.nb);
  const tab = usePanel((s) => s.tab);
  const drafts = usePanel((s) => s.drafts);
  const a = useNotebookActions();
  const rootRef = useRef<HTMLDivElement>(null);
  const findRef = useRef<HTMLInputElement>(null);
  const [menu, setMenu] = useState<string | null>(null);
  const [find, setFind] = useState("");
  const [findOpen, setFindOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const [drop, setDrop] = useState<Drop | null>(null);
  const [hideError, setHideError] = useState<string | null>(null);
  const [headStuck, setHeadStuck] = useState(false);
  const seen = useRef<{ project: string; ids: Set<string>; until: Record<string, number> } | null>(null);
  const lastRunning = useRef<string | null>(null);

  // A new project starts unfiltered with no menu open, as the old switchProject did (AC6)
  const projectKey = nb?.project.id;
  useEffect(() => {
    setMenu(null);
    setFind("");
    setFindOpen(false);
    setDrag(null);
    setDrop(null);
  }, [projectKey]);

  // Keyboard shortcuts while focus is inside the panel
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const inside = rootRef.current && rootRef.current.contains(document.activeElement);
      if (e.key === "Escape") {
        if (inside) {
          setMenu(null);
          setFind("");
          setFindOpen(false);
        }
        return;
      }
      const mod = e.ctrlKey || e.metaKey;
      if (inside && mod && !e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        a.flushAll();
      }
      if (inside && mod && e.shiftKey && e.key === "Enter") {
        e.preventDefault();
        a.runAll();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  // The sticky header gets a shadow once the sidebar that scrolls the panel is scrolled.
  // Re-bound when the root moves to a new container (sidebar reopened, phone layout).
  useEffect(() => {
    let off: (() => void) | null = null;
    const bind = () => {
      off?.();
      const el = scrollParent(rootRef.current);
      if (!el) return;
      const sync = () => setHeadStuck(el.scrollTop > 4);
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

  // Bring a newly running cell into view, without jumping when it is already visible
  const running = nb?.running_cell_id ?? null;
  useEffect(() => {
    if (running && running !== lastRunning.current) {
      lastRunning.current = running;
      const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const t = setTimeout(() => {
        const node = rootRef.current?.querySelector(`[data-cell-id="${CSS.escape(running)}"]`);
        if (node) node.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
      }, 80);
      return () => clearTimeout(t);
    }
    if (!running) lastRunning.current = null;
    return undefined;
  }, [running]);

  if (!nb) return null;

  const projectId = nb.project.id;
  const datasets = nb.datasets || [];
  const kernel = nb.kernel;
  const busy = kernel === "busy" || !!nb.running_cell_id;
  const [colour, status] = (busy ? KERNEL.busy : KERNEL[kernel]) || KERNEL.off;
  const sourceOf = (cell: CellProps) => drafts[cell.id] ?? cell.source;

  // Blocks animate in only the first time they are drawn for this project
  if (!seen.current || seen.current.project !== projectId) seen.current = { project: projectId, ids: new Set(nb.cells.map((c) => c.id)), until: {} };
  const isFresh = (id: string) => {
    const s = seen.current!;
    if (!s.ids.has(id)) {
      s.ids.add(id);
      s.until[id] = Date.now() + 400;
    }
    return Date.now() < (s.until[id] || 0);
  };

  const copyCell = async (cell: CellProps) => {
    const key = `cell:${cell.id}`;
    if (!(await copyText(sourceOf(cell)))) return;
    setCopied(key);
    setTimeout(() => setCopied((c) => (c === key ? null : c)), 1500);
  };

  const actions: BlockActions = {
    add: a.add,
    duplicate: a.duplicate,
    copy: copyCell,
    clearOutputs: a.clearCellOutputs,
    move: a.move,
    remove: a.remove,
  };

  // ---- drag and drop ----
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
      const i = nb.cells.findIndex((c) => c.id === cell.id);
      beforeId = nb.cells[i + 1] ? nb.cells[i + 1].id : null;
    }
    await a.reorder(dragId, beforeId);
  };

  // ---- find ----
  const q = find.trim().toLowerCase();
  const focusedCell = (document.activeElement as HTMLElement | null)?.getAttribute?.("data-cell-src");
  const matches = (cell: CellProps) => !q
    || sourceOf(cell).toLowerCase().includes(q)
    || (cell.outputs || []).some((o) => (o.text || "").toLowerCase().includes(q));
  const visible = nb.cells.filter((cell) => matches(cell) || (q && focusedCell === cell.id));
  const matchIds = new Set(q ? visible.map((c) => c.id) : []);
  const toggleFind = () => {
    const next = !findOpen;
    setFindOpen(next);
    if (!next) setFind("");
    else setTimeout(() => findRef.current?.focus(), 0);
  };

  // ---- problems ----
  const problem = a.runner.error
    ? a.runner.error
    : nb.error
      ? nb.error.message
      : kernel === "dead"
        ? "The kernel died (maybe out of memory). Press Restart."
        : kernel === "unavailable"
          ? "Docker isn't running: start Docker Desktop, then press Restart."
          : null;
  const errorKey = `${projectId}:${nb.version}`;
  const showProblem = problem && (a.runner.error || !nb.error || hideError !== errorKey);
  const dismiss = a.runner.error ? a.runner.clearError : nb.error ? () => setHideError(errorKey) : undefined;

  const draftCount = Object.keys(drafts).length;
  const saveState = a.pendingSaves ? "saving" : draftCount ? "dirty" : a.savedAt ? "saved" : "";
  const setTab = (next: "notebook" | "datasets") => next !== tab && usePanel.setState({ tab: next });
  const onTabKey = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      setTab(tab === "notebook" ? "datasets" : "notebook");
    }
  };
  const isBusy = !!a.runner.busy;

  return (
    <div className="rcnb" ref={rootRef}>
      <div className="rcnb-page">
        <div className="rcnb-titlebar">
          <NotebookPen className="rcnb-titleicon" size={20} />
          <div className="rcnb-titlewrap">
            <div className="rcnb-eyebrow">Project notebook</div>
            <h1 className="rcnb-title">
              <ProjectPicker name={nb.project.name} current={projectId} onSwitch={a.switchProject} onCreate={a.createProject} />
            </h1>
          </div>
          {saveState && (
            <span className={`rcnb-save ${saveState}`} aria-live="polite" title={saveState === "saving" ? "Saving your edits…" : saveState === "dirty" ? "Waiting to save" : "All changes saved"}>
              {saveState === "saving" ? <Loader2 size={12} className="spin" /> : saveState === "saved" ? <Check size={12} /> : <AlertCircle size={12} />}
              {saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved" : "Unsaved"}
            </span>
          )}
        </div>

        <div className={`rcnb-head${headStuck ? " stuck" : ""}`}>
          <div className="rcnb-tabs" role="tablist" aria-label="Notebook views" onKeyDown={onTabKey}>
            <button role="tab" id="rcnb-tab-notebook" aria-selected={tab === "notebook"} aria-controls="rcnb-view-notebook" className={`rcnb-tab${tab === "notebook" ? " on" : ""}`} onClick={() => setTab("notebook")}>
              <Code2 size={13} />Notebook
              {nb.cells.length > 0 && <span className="rcnb-count">{nb.cells.length}</span>}
            </button>
            <button role="tab" id="rcnb-tab-datasets" aria-selected={tab === "datasets"} aria-controls="rcnb-view-datasets" className={`rcnb-tab${tab === "datasets" ? " on" : ""}`} onClick={() => setTab("datasets")}>
              <Database size={13} />Datasets
              {datasets.length > 0 && <span className={`rcnb-count${datasets.some(isActive) ? " live" : datasets.some((d) => d.status === "failed" || d.status === "missing") ? " warn" : ""}`}>{datasets.length}</span>}
            </button>
          </div>

          {tab === "notebook" && (
            <div className="rcnb-meta" role="toolbar" aria-label="Notebook actions">
              <span className="rcnb-status" aria-live="polite" title={status}>
                <span className={`rcnb-dot${busy || kernel === "starting" ? " pulse" : ""}`} style={{ background: colour, color: colour }} />
                <span className="rcnb-statustext">{status}</span>
              </span>
              <span className="rcnb-sep" />
              <Button variant="ghost" size="sm" className="rcnb-act primary rcnb-runall" title="Run all code blocks (Ctrl+Shift+Enter)" aria-label="Run all" disabled={isBusy} onClick={a.runAll}>
                {a.runner.busy === "nb_run_all" ? <Loader2 size={13} className="spin" /> : <FastForward size={13} />}
                <span className="rcnb-actlabel">Run all</span>
              </Button>
              <Button variant="ghost" size="sm" className="rcnb-act" title="Stop the running block" aria-label="Stop" disabled={!busy} onClick={a.interrupt}>
                <Square size={12} /><span className="rcnb-actlabel">Stop</span>
              </Button>
              <Button variant="ghost" size="sm" className="rcnb-act" title="Restart kernel (clears variables, keeps cells)" aria-label="Restart kernel" disabled={isBusy} onClick={a.restart}>
                <RotateCcw size={13} /><span className="rcnb-actlabel">Restart</span>
              </Button>
              <Button variant="ghost" size="sm" className="rcnb-act" title="Clear all outputs" aria-label="Clear all outputs" disabled={isBusy} onClick={a.clearOutputs}>
                <Eraser size={13} /><span className="rcnb-actlabel">Clear</span>
              </Button>
              <Button variant="ghost" size="sm" className={`rcnb-act${findOpen ? " primary" : ""}`} title="Find in cells and outputs" aria-label="Find" aria-expanded={findOpen} onClick={toggleFind}>
                <Search size={13} /><span className="rcnb-actlabel">Find</span>
              </Button>
            </div>
          )}

          {tab === "notebook" && findOpen && (
            <label className="rcnb-findbar">
              <Search size={13} />
              <input
                ref={findRef}
                value={find}
                placeholder="Find in cells and outputs"
                aria-label="Find in notebook"
                onChange={(e) => setFind(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    setFind("");
                    setFindOpen(false);
                    e.currentTarget.blur();
                  }
                }}
              />
              {q && <span className="rcnb-findcount">{visible.length} of {nb.cells.length}</span>}
              {!!find && (
                <button className="rcnb-mini" title="Clear search" aria-label="Clear search" onClick={() => { setFind(""); findRef.current?.focus(); }}>
                  <X size={12} />
                </button>
              )}
            </label>
          )}
        </div>

        {tab === "datasets" ? (
          <div role="tabpanel" id="rcnb-view-datasets" aria-labelledby="rcnb-tab-datasets">
            {showProblem && <Problem text={problem} dismiss={dismiss} />}
            <DatasetsTab datasets={datasets} inserting={a.inserting} onCancel={a.dsCancel} onDelete={a.dsDelete} onInsert={a.insertDatasetCode} />
          </div>
        ) : (
          <div role="tabpanel" id="rcnb-view-notebook" aria-labelledby="rcnb-tab-notebook">
            {showProblem && <Problem text={problem} dismiss={dismiss} />}

            {!nb.cells.length && !q && (
              <div className="rcnb-empty">
                <NotebookPen size={24} />
                <h3>Start your notebook</h3>
                <div>Run Python in this project's own kernel, and keep notes beside it.</div>
                <div className="rcnb-add">
                  <Button variant="ghost" size="sm" className="rcnb-act primary" onClick={() => a.add(null, "code")}><Plus size={14} />Code block</Button>
                  <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => a.add(null, "markdown")}><StickyNote size={14} />Note</Button>
                </div>
              </div>
            )}

            {visible.map((cell) => (
              <div key={cell.id}>
                <Block
                  cell={cell}
                  fresh={isFresh(cell.id)}
                  menuOpen={menu === cell.id}
                  setMenu={setMenu}
                  actions={actions}
                  dragging={drag}
                  drop={drop}
                  onDragStart={startDrag}
                  onDragOver={overBlock}
                  onDrop={dropOn}
                  onDragEnd={endDrag}
                >
                  {cell.type === "markdown" ? (
                    <NoteCell id={cell.id} source={sourceOf(cell)} match={matchIds.has(cell.id)} onChange={(t) => a.edit(cell.id, t)} onSave={() => a.flush(cell.id)} />
                  ) : (
                    <CodeCell
                      cell={cell}
                      source={sourceOf(cell)}
                      running={cell.id === nb.running_cell_id}
                      match={matchIds.has(cell.id)}
                      canRun={kernel !== "unavailable" && !isBusy}
                      copied={copied === `cell:${cell.id}`}
                      onChange={(t) => a.edit(cell.id, t)}
                      onRun={() => a.run(cell)}
                      onCopy={() => copyCell(cell)}
                      onMenu={() => setMenu(menu === cell.id ? null : cell.id)}
                      onMove={(dir) => a.move(cell.id, dir)}
                    />
                  )}
                </Block>
                {!q && <InsertRow afterId={cell.id} onAdd={a.add} />}
              </div>
            ))}

            {q && !visible.length && (
              <div className="rcnb-findempty">
                <SearchX size={18} style={{ opacity: 0.6 }} />
                <div style={{ marginTop: 6 }}>No cell matches “{find}”.</div>
                <Button variant="ghost" size="sm" className="rcnb-act" style={{ marginTop: 6 }} onClick={() => { setFind(""); findRef.current?.focus(); }}>Clear search</Button>
              </div>
            )}

            {!q && (
              <div className="rcnb-add">
                <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => a.add(null, "code")}><Plus size={14} />Code</Button>
                <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => a.add(null, "markdown")}><Plus size={14} />Note</Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
