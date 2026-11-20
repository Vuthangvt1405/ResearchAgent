// The panel (port of the old Notebook() default export). It lives in a React root that
// never unmounts, so local state survives every props push. Behaviour lives in
// notebookHooks.ts and the header parts in NotebookHeader.tsx; this file lays them out.
import { useEffect, useRef, useState, type DragEvent, type ReactNode } from "react";
import { AlertCircle, GripVertical, NotebookPen, Plus, SearchX, StickyNote, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BlockMenu, type BlockActions } from "@/components/BlockMenu";
import { CellToolbar } from "@/components/CellToolbar";
import { CodeCell } from "@/components/CodeCell";
import { DatasetsTab } from "@/components/DatasetsTab";
import { InsertRow } from "@/components/InsertRow";
import { NoteCell } from "@/components/NoteCell";
import { FindBar, NotebookTabs, NotebookToolbar, TitleBar, type PanelTab } from "@/components/NotebookHeader";
import {
  problemText, saveState, useCellFind, useDragReorder, useFreshBlocks, useNotebookShortcuts,
  useScrollToRunningCell, useStickyHeader, type Drop,
} from "@/components/notebookHooks";
import { usePanel } from "@/store";
import { copyText } from "@/lib/clipboard";
import { useNotebookActions } from "@/lib/notebookActions";
import type { CellProps } from "@/types";

const COPIED_FEEDBACK_MS = 1500;

// Status dot colours follow the panel's light/dark tokens
const KERNEL: Record<string, [string, string]> = {
  off: ["hsl(var(--muted-foreground))", "Kernel off · starts on first run"],
  starting: ["hsl(var(--rc-warn))", "Starting kernel…"],
  idle: ["hsl(var(--rc-ok))", "Ready"],
  busy: ["hsl(var(--rc-warn))", "Running…"],
  dead: ["hsl(var(--rc-danger))", "Kernel died"],
  unavailable: ["hsl(var(--rc-danger))", "Docker not running"],
};

function Block({ cell, fresh, menuOpen, setMenu, actions, copied, dragging, drop, onDragStart, onDragOver, onDrop, onDragEnd, children }: {
  cell: CellProps; fresh: boolean; menuOpen: boolean; setMenu: (id: string | null) => void; actions: BlockActions; copied: boolean;
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
      <div className="rcnb-body">
        <CellToolbar cell={cell} actions={actions} copied={copied} isMenuOpen={menuOpen} setMenu={setMenu} />
        {children}
      </div>
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
  const [menu, setMenu] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [hideError, setHideError] = useState<string | null>(null);

  const cells = nb?.cells ?? [];
  const sourceOf = (cell: CellProps) => drafts[cell.id] ?? cell.source;
  const finder = useCellFind(cells, sourceOf);
  const dragger = useDragReorder(cells, a.reorder);
  const isFresh = useFreshBlocks(nb?.project.id, cells);
  const headStuck = useStickyHeader(rootRef);
  useScrollToRunningCell(rootRef, nb?.running_cell_id ?? null);
  useNotebookShortcuts(rootRef, {
    closeOverlays: () => {
      setMenu(null);
      finder.closeFind();
    },
    saveAll: a.flushAll,
    runAll: a.runAll,
  });

  // A new project starts unfiltered with no menu open, as the old switchProject did
  const projectKey = nb?.project.id;
  useEffect(() => {
    setMenu(null);
    finder.closeFind();
    dragger.endDrag();
  }, [projectKey]);

  if (!nb) return null;

  const projectId = nb.project.id;
  const datasets = nb.datasets || [];
  const kernel = nb.kernel;
  const busy = kernel === "busy" || !!nb.running_cell_id;
  const [colour, status] = (busy ? KERNEL.busy : KERNEL[kernel]) || KERNEL.off;
  const { q, visible, matchIds } = finder;

  const copyCell = async (cell: CellProps) => {
    const key = `cell:${cell.id}`;
    if (!(await copyText(sourceOf(cell)))) return;
    setCopied(key);
    setTimeout(() => setCopied((c) => (c === key ? null : c)), COPIED_FEEDBACK_MS);
  };

  const actions: BlockActions = {
    add: a.add,
    duplicate: a.duplicate,
    copy: copyCell,
    clearOutputs: a.clearCellOutputs,
    move: a.move,
    remove: a.remove,
  };

  // ---- problems ----
  const problem = problemText(a.runner.error, nb);
  const errorKey = `${projectId}:${nb.version}`;
  const showProblem = problem && (a.runner.error || !nb.error || hideError !== errorKey);
  const dismiss = a.runner.error ? a.runner.clearError : nb.error ? () => setHideError(errorKey) : undefined;

  const save = saveState(a.pendingSaves, Object.keys(drafts).length, a.savedAt);
  const setTab = (next: PanelTab) => next !== tab && usePanel.setState({ tab: next });
  const isBusy = !!a.runner.busy;

  return (
    <div className="rcnb" ref={rootRef}>
      <div className="rcnb-page">
        <TitleBar name={nb.project.name} projectId={projectId} onSwitch={a.switchProject} onCreate={a.createProject} save={save} />

        <div className={`rcnb-head${headStuck ? " stuck" : ""}`}>
          <NotebookTabs tab={tab} setTab={setTab} cellCount={nb.cells.length} datasets={datasets} />

          {tab === "notebook" && (
            <NotebookToolbar
              status={status}
              colour={colour}
              isPulsing={busy || kernel === "starting"}
              isRunningAll={a.runner.busy === "nb_run_all"}
              isBusy={isBusy}
              canStop={busy}
              findOpen={finder.findOpen}
              actions={{ runAll: a.runAll, interrupt: a.interrupt, restart: a.restart, clearOutputs: a.clearOutputs, toggleFind: finder.toggleFind }}
            />
          )}

          {tab === "notebook" && finder.findOpen && (
            <FindBar
              findRef={finder.findRef}
              find={finder.find}
              setFind={finder.setFind}
              hasQuery={!!q}
              shown={visible.length}
              total={nb.cells.length}
              closeFind={finder.closeFind}
              clearFind={finder.clearFind}
            />
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
                  copied={copied === `cell:${cell.id}`}
                  dragging={dragger.drag}
                  drop={dragger.drop}
                  onDragStart={dragger.startDrag}
                  onDragOver={dragger.overBlock}
                  onDrop={dragger.dropOn}
                  onDragEnd={dragger.endDrag}
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
                      onChange={(t) => a.edit(cell.id, t)}
                      onRun={() => a.run(cell)}
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
                <div style={{ marginTop: 6 }}>No cell matches “{finder.find}”.</div>
                <Button variant="ghost" size="sm" className="rcnb-act" style={{ marginTop: 6 }} onClick={finder.clearFind}>Clear search</Button>
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
