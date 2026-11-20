// Every panel action, ported from the body of the old Notebook() so payloads stay the
// same. Saves run in the background; button actions go through useRunner. Each area
// (drafts, cells, kernel, projects, datasets) has its own hook; useNotebookActions joins them.
import { useEffect, useRef, useState } from "react";
import { usePanel } from "@/store";
import { call, useRunner, type Runner } from "@/lib/actions";
import { loadCode } from "@/lib/loadCode";
import type { ActionName, CellProps, CellType, DatasetProps } from "@/types";

export const SAVE_DELAY_MS = 600;

const state = () => usePanel.getState();
const version = () => state().nb?.version ?? 0;

/** Send an action with the current version and merge the reply */
const sendVersioned = async (name: ActionName, extra: Record<string, unknown> = {}) =>
  state().apply(await call(name, { version: version(), ...extra }));

type DraftSaving = ReturnType<typeof useDraftSaving>;

/** Unsaved cell text: kept as a draft on each keystroke, saved after a pause */
function useDraftSaving() {
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const [pendingSaves, setPendingSaves] = useState(0);
  const [savedAt, setSavedAt] = useState(0);

  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  const cancelPendingSave = (cellId: string) => clearTimeout(timers.current[cellId]);

  const dropDraft = (cellId: string, text: string) => {
    const drafts = state().drafts;
    if (drafts[cellId] !== text) return;
    const next = { ...drafts };
    delete next[cellId];
    usePanel.setState({ drafts: next });
  };

  const save = async (cellId: string, text: string) => {
    cancelPendingSave(cellId);
    delete timers.current[cellId];
    setPendingSaves((n) => n + 1);
    const before = (state().nb?.cells || []).find((c) => c.id === cellId);
    try {
      let result = await call("nb_update_cell", { version: version(), cell_id: cellId, source: text });
      // STALE because something else changed (e.g. a run finished): retry once if this
      // cell wasn't edited elsewhere
      if (result && result.error && result.error.code === "STALE") {
        const server = (result.cells || []).find((c) => c.id === cellId);
        if (server && before && server.source === before.source) {
          result = await call("nb_update_cell", { version: result.version, cell_id: cellId, source: text });
        }
      }
      // Never drop a draft while the user is mid-composition in that cell
      if (result && !result.error && state().composing !== cellId) dropDraft(cellId, text);
      state().apply(result);
      return result;
    } catch {
      return null;
    } finally {
      setPendingSaves((n) => Math.max(0, n - 1));
      setSavedAt(Date.now());
    }
  };

  const edit = (cellId: string, text: string) => {
    usePanel.setState({ drafts: { ...state().drafts, [cellId]: text } });
    setSavedAt(0);
    cancelPendingSave(cellId);
    timers.current[cellId] = setTimeout(() => save(cellId, text), SAVE_DELAY_MS);
  };

  const flush = async (cellId: string) => {
    const draft = state().drafts[cellId];
    return draft !== undefined ? save(cellId, draft) : null;
  };

  const flushAll = async () => {
    for (const [cellId, text] of Object.entries(state().drafts)) await save(cellId, text);
  };

  const sourceOf = (cell: CellProps) => state().drafts[cell.id] ?? cell.source;

  const markSaved = () => setSavedAt(Date.now());

  return { pendingSaves, savedAt, save, edit, flush, flushAll, sourceOf, dropDraft, cancelPendingSave, markSaved };
}

/** Running, adding, moving and deleting cells */
function cellActions(runner: Runner, drafts: DraftSaving) {
  const run = async (cell: CellProps) => {
    drafts.cancelPendingSave(cell.id);
    const text = drafts.sourceOf(cell);
    const result = await runner.run("nb_run_cell", { version: version(), cell_id: cell.id, source: text });
    if (result && !result.error) drafts.dropDraft(cell.id, text);
    return result;
  };

  // Run-all should see what is on screen, not the last save; the version is read after
  // the flush, which may have bumped it
  const runAll = () => runner.run("nb_run_all", () => ({ version: version() }), drafts.flushAll);

  const add = async (afterId: string | null, type: CellType) => {
    const result = await call("nb_add_cell", { version: version(), after_id: afterId, type });
    if (result && result.cells && !result.error) {
      const i = afterId ? result.cells.findIndex((c) => c.id === afterId) + 1 : result.cells.length - 1;
      const cell = result.cells[i];
      if (cell) {
        if (type === "markdown") usePanel.setState({ editing: { ...state().editing, [cell.id]: true } });
        else usePanel.setState({ focus: { id: cell.id, start: 0, end: 0 } });
      }
    }
    return state().apply(result);
  };

  const move = async (id: string, direction: "up" | "down") => {
    await drafts.flush(id); // move the text the user sees, not the last saved version
    return sendVersioned("nb_move_cell", { cell_id: id, direction });
  };

  const duplicate = async (id: string) => {
    await drafts.flush(id);
    return sendVersioned("nb_duplicate_cell", { cell_id: id });
  };

  const remove = (id: string) => sendVersioned("nb_delete_cell", { cell_id: id });
  const clearCellOutputs = (id: string) => sendVersioned("nb_clear_cell_outputs", { cell_id: id });
  const reorder = (cellId: string, beforeId: string | null) =>
    runner.run("nb_reorder_cell", { version: version(), cell_id: cellId, before_id: beforeId });

  return { run, runAll, add, move, duplicate, remove, clearCellOutputs, reorder };
}

/** The project's kernel as a whole */
function kernelActions(runner: Runner) {
  const interrupt = () => runner.run("nb_interrupt", { version: version() });
  const restart = () => runner.run("nb_restart", { version: version() });
  const clearOutputs = () => runner.run("nb_clear_outputs", { version: version() });
  return { interrupt, restart, clearOutputs };
}

/** Switching to another project or making a new one; unsaved edits are saved first */
function projectActions(drafts: DraftSaving) {
  const switchProject = async (id: string) => {
    if (!id || id === state().nb?.project.id) return null;
    await drafts.flushAll();
    const result = await call("nb_switch_project", { project_id: id });
    if (result && result.error) state().apply(result);
    return result;
  };

  const createProject = async (name: string) => {
    if (!name || !name.trim()) return null;
    await drafts.flushAll();
    const result = await call("nb_create_project", { name: name.trim() });
    if (result && result.error) state().apply(result);
    return result;
  };

  return { switchProject, createProject };
}

/** The Datasets tab: cancel, delete, and insert load code into the notebook */
function useDatasetActions(drafts: DraftSaving) {
  const [inserting, setInserting] = useState<string | null>(null);

  // Not gated by the runner, like the old act(): cancelling a download must work while a cell runs
  const dsAction = async (name: "ds_cancel" | "ds_delete", id: string) => {
    try {
      return state().apply(await call(name, { dataset_id: id }));
    } catch (e) {
      console.error("[notebook panel]", name, e);
      return null;
    }
  };
  const dsCancel = (id: string) => dsAction("ds_cancel", id);
  const dsDelete = (id: string) => dsAction("ds_delete", id);

  // Dataset -> notebook bridge: a new code cell with the load code
  const insertDatasetCode = async (d: DatasetProps) => {
    if (inserting) return;
    setInserting(d.id);
    try {
      await drafts.flushAll();
      let result = await call("nb_add_cell", { version: version(), after_id: null, type: "code" });
      if (result && result.cells && !result.error) {
        const cell = result.cells[result.cells.length - 1];
        const updated = await call("nb_update_cell", { version: result.version, cell_id: cell.id, source: loadCode(d) });
        if (updated && updated.cells && !updated.error) {
          usePanel.setState({ tab: "notebook", focus: { id: cell.id, start: 0, end: 0 } });
          drafts.markSaved();
        }
        result = updated || result;
      }
      state().apply(result);
    } finally {
      setInserting(null);
    }
  };

  return { inserting, dsCancel, dsDelete, insertDatasetCode };
}

export function useNotebookActions() {
  const runner = useRunner();
  const drafts = useDraftSaving();
  const datasets = useDatasetActions(drafts);
  const { pendingSaves, savedAt, save, edit, flush, flushAll, sourceOf } = drafts;
  return {
    runner, pendingSaves, savedAt, save, edit, flush, flushAll, sourceOf,
    ...cellActions(runner, drafts),
    ...kernelActions(runner),
    ...projectActions(drafts),
    ...datasets,
  };
}
