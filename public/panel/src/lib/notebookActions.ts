// Every panel action, ported from the body of the old Notebook() so payloads stay the
// same (AC4). Saves run in the background; button actions go through useRunner (AC8).
import { useEffect, useRef, useState } from "react";
import { usePanel } from "@/store";
import { call, useRunner } from "@/lib/actions";
import { loadCode } from "@/lib/loadCode";
import type { CellProps, CellType, DatasetProps } from "@/types";

export const SAVE_DELAY_MS = 600;

const state = () => usePanel.getState();
const version = () => state().nb?.version ?? 0;

export function useNotebookActions() {
  const runner = useRunner();
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const [pendingSaves, setPendingSaves] = useState(0);
  const [savedAt, setSavedAt] = useState(0);
  const [inserting, setInserting] = useState<string | null>(null);

  useEffect(() => () => Object.values(timers.current).forEach(clearTimeout), []);

  const dropDraft = (cellId: string, text: string) => {
    const drafts = state().drafts;
    if (drafts[cellId] !== text) return;
    const next = { ...drafts };
    delete next[cellId];
    usePanel.setState({ drafts: next });
  };

  const save = async (cellId: string, text: string) => {
    clearTimeout(timers.current[cellId]);
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
      // Never drop a draft while the user is mid-composition in that cell (AC10)
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
    clearTimeout(timers.current[cellId]);
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

  const run = async (cell: CellProps) => {
    clearTimeout(timers.current[cell.id]);
    const text = sourceOf(cell);
    const result = await runner.run("nb_run_cell", { version: version(), cell_id: cell.id, source: text });
    if (result && !result.error) dropDraft(cell.id, text);
    return result;
  };

  // Run-all should see what is on screen, not the last save; the version is read after
  // the flush, which may have bumped it
  const runAll = () => runner.run("nb_run_all", () => ({ version: version() }), flushAll);

  const simple = async (name: Parameters<typeof call>[0], extra: Record<string, unknown> = {}) =>
    state().apply(await call(name, { version: version(), ...extra }));

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
    await flush(id); // move the text the user sees, not the last saved version
    return simple("nb_move_cell", { cell_id: id, direction });
  };

  const duplicate = async (id: string) => {
    await flush(id);
    return simple("nb_duplicate_cell", { cell_id: id });
  };

  const remove = (id: string) => simple("nb_delete_cell", { cell_id: id });
  const clearCellOutputs = (id: string) => simple("nb_clear_cell_outputs", { cell_id: id });
  const reorder = (cellId: string, beforeId: string | null) => runner.run("nb_reorder_cell", { version: version(), cell_id: cellId, before_id: beforeId });
  const interrupt = () => runner.run("nb_interrupt", { version: version() });
  const restart = () => runner.run("nb_restart", { version: version() });
  const clearOutputs = () => runner.run("nb_clear_outputs", { version: version() });

  const switchProject = async (id: string) => {
    if (!id || id === state().nb?.project.id) return null;
    await flushAll();
    const result = await call("nb_switch_project", { project_id: id });
    if (result && result.error) state().apply(result);
    return result;
  };

  const createProject = async (name: string) => {
    if (!name || !name.trim()) return null;
    await flushAll();
    const result = await call("nb_create_project", { name: name.trim() });
    if (result && result.error) state().apply(result);
    return result;
  };

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
      await flushAll();
      let result = await call("nb_add_cell", { version: version(), after_id: null, type: "code" });
      if (result && result.cells && !result.error) {
        const cell = result.cells[result.cells.length - 1];
        const updated = await call("nb_update_cell", { version: result.version, cell_id: cell.id, source: loadCode(d) });
        if (updated && updated.cells && !updated.error) {
          usePanel.setState({ tab: "notebook", focus: { id: cell.id, start: 0, end: 0 } });
          setSavedAt(Date.now());
        }
        result = updated || result;
      }
      state().apply(result);
    } finally {
      setInserting(null);
    }
  };

  return {
    runner, pendingSaves, savedAt, inserting,
    save, edit, flush, flushAll, sourceOf,
    run, runAll, add, move, duplicate, remove, clearCellOutputs, reorder, interrupt, restart, clearOutputs,
    switchProject, createProject, dsCancel, dsDelete, insertDatasetCode,
  };
}

export type NotebookActions = ReturnType<typeof useNotebookActions>;
