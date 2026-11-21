// The top of the Notebook panel: title with save badge, the tabs, the toolbar and the find bar.
import type { KeyboardEvent, RefObject } from "react";
import { AlertCircle, Check, Code2, Database, Eraser, FastForward, Loader2, NotebookPen, RotateCcw, Search, Square, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ProjectPicker } from "@/panel/components/ProjectPicker";
import { isActive } from "@/panel/lib/datasetProgress";
import type { SaveState } from "@/panel/components/notebookHooks";
import type { DatasetProps } from "@/panel/types";

export type PanelTab = "notebook" | "datasets";

const SAVE_TITLES: Record<Exclude<SaveState, "">, string> = { saving: "Saving your edits…", dirty: "Waiting to save", saved: "All changes saved" };
const SAVE_LABELS: Record<Exclude<SaveState, "">, string> = { saving: "Saving…", dirty: "Unsaved", saved: "Saved" };

function SaveBadge({ state }: { state: SaveState }) {
  if (!state) return null;
  return (
    <span className={`rcnb-save ${state}`} aria-live="polite" title={SAVE_TITLES[state]}>
      {state === "saving" ? <Loader2 size={12} className="spin" /> : state === "saved" ? <Check size={12} /> : <AlertCircle size={12} />}
      {SAVE_LABELS[state]}
    </span>
  );
}

export function TitleBar({ name, projectId, onSwitch, onCreate, save }: {
  name: string; projectId: string; save: SaveState;
  onSwitch: (id: string) => Promise<unknown>; onCreate: (name: string) => Promise<unknown>;
}) {
  return (
    <div className="rcnb-titlebar">
      <NotebookPen className="rcnb-titleicon" size={20} />
      <div className="rcnb-titlewrap">
        <div className="rcnb-eyebrow">Project notebook</div>
        <h1 className="rcnb-title">
          <ProjectPicker name={name} current={projectId} onSwitch={onSwitch} onCreate={onCreate} />
        </h1>
      </div>
      <SaveBadge state={save} />
    </div>
  );
}

function datasetCountClass(datasets: DatasetProps[]): string {
  if (datasets.some(isActive)) return " live";
  if (datasets.some((d) => d.status === "failed" || d.status === "missing")) return " warn";
  return "";
}

export function NotebookTabs({ tab, setTab, cellCount, datasets }: {
  tab: PanelTab; setTab: (next: PanelTab) => void; cellCount: number; datasets: DatasetProps[];
}) {
  const onTabKey = (e: KeyboardEvent) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      setTab(tab === "notebook" ? "datasets" : "notebook");
    }
  };
  return (
    <div className="rcnb-tabs" role="tablist" aria-label="Notebook views" onKeyDown={onTabKey}>
      <button role="tab" id="rcnb-tab-notebook" aria-selected={tab === "notebook"} aria-controls="rcnb-view-notebook" className={`rcnb-tab${tab === "notebook" ? " on" : ""}`} onClick={() => setTab("notebook")}>
        <Code2 size={13} />Notebook
        {cellCount > 0 && <span className="rcnb-count">{cellCount}</span>}
      </button>
      <button role="tab" id="rcnb-tab-datasets" aria-selected={tab === "datasets"} aria-controls="rcnb-view-datasets" className={`rcnb-tab${tab === "datasets" ? " on" : ""}`} onClick={() => setTab("datasets")}>
        <Database size={13} />Datasets
        {datasets.length > 0 && <span className={`rcnb-count${datasetCountClass(datasets)}`}>{datasets.length}</span>}
      </button>
    </div>
  );
}

export interface ToolbarActions {
  runAll: () => void;
  interrupt: () => void;
  restart: () => void;
  clearOutputs: () => void;
  toggleFind: () => void;
}

export function NotebookToolbar({ status, colour, isPulsing, isRunningAll, isBusy, canStop, findOpen, actions }: {
  status: string; colour: string; isPulsing: boolean; isRunningAll: boolean; isBusy: boolean; canStop: boolean;
  findOpen: boolean; actions: ToolbarActions;
}) {
  return (
    <div className="rcnb-meta" role="toolbar" aria-label="Notebook actions">
      <span className="rcnb-status" aria-live="polite" title={status}>
        <span className={`rcnb-dot${isPulsing ? " pulse" : ""}`} style={{ background: colour, color: colour }} />
        <span className="rcnb-statustext">{status}</span>
      </span>
      <span className="rcnb-sep" />
      <Button variant="ghost" size="sm" className="rcnb-act primary rcnb-runall" title="Run all code blocks (Ctrl+Shift+Enter)" aria-label="Run all" disabled={isBusy} onClick={actions.runAll}>
        {isRunningAll ? <Loader2 size={13} className="spin" /> : <FastForward size={13} />}
        <span className="rcnb-actlabel">Run all</span>
      </Button>
      <Button variant="ghost" size="sm" className="rcnb-act" title="Stop the running block" aria-label="Stop" disabled={!canStop} onClick={actions.interrupt}>
        <Square size={12} /><span className="rcnb-actlabel">Stop</span>
      </Button>
      <Button variant="ghost" size="sm" className="rcnb-act" title="Restart kernel (clears variables, keeps cells)" aria-label="Restart kernel" disabled={isBusy} onClick={actions.restart}>
        <RotateCcw size={13} /><span className="rcnb-actlabel">Restart</span>
      </Button>
      <Button variant="ghost" size="sm" className="rcnb-act" title="Clear all outputs" aria-label="Clear all outputs" disabled={isBusy} onClick={actions.clearOutputs}>
        <Eraser size={13} /><span className="rcnb-actlabel">Clear</span>
      </Button>
      <Button variant="ghost" size="sm" className={`rcnb-act${findOpen ? " primary" : ""}`} title="Find in cells and outputs" aria-label="Find" aria-expanded={findOpen} onClick={actions.toggleFind}>
        <Search size={13} /><span className="rcnb-actlabel">Find</span>
      </Button>
    </div>
  );
}

export function FindBar({ findRef, find, setFind, hasQuery, shown, total, closeFind, clearFind }: {
  findRef: RefObject<HTMLInputElement>; find: string; setFind: (text: string) => void; hasQuery: boolean;
  shown: number; total: number; closeFind: () => void; clearFind: () => void;
}) {
  return (
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
            closeFind();
            e.currentTarget.blur();
          }
        }}
      />
      {hasQuery && <span className="rcnb-findcount">{shown} of {total}</span>}
      {!!find && (
        <button className="rcnb-mini" title="Clear search" aria-label="Clear search" onClick={clearFind}>
          <X size={12} />
        </button>
      )}
    </label>
  );
}
