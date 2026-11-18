// Actions (component with a mocked callAction)
// Baseline: Given the app has a callAction mock · When a button is clicked
import { describe, it, expect, vi } from "vitest";
import { act, fireEvent, renderHook, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { mountPanel } from "@/test/harness";
import { cell, dataset, props } from "@/test/fixtures";
import { useNotebookActions } from "@/lib/notebookActions";
import { loadCode } from "@/lib/loadCode";
import { resetStore, usePanel } from "@/store";

const lists = (a: { name: string }) => (a.name === "nb_list_projects" ? { projects: [] } : null);

describe("Actions", () => {
  it("run_cell_calls_nb_run_cell", async () => {
    // Positive · changed: —
    // Then: called with name nb_run_cell and payload cell_id · Demonstrates: same contract
    const h = await mountPanel(props());
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run cell" }));
    });
    expect(h.callAction).toHaveBeenCalledWith({ name: "nb_run_cell", payload: { version: 5, cell_id: "a", source: "print(1)" } });
  });

  it("each_action_payload_matches_today", async () => {
    // Positive · changed: table-driven over all 17 actions
    // Then: the payloads equal the current ones · Demonstrates: 1:1 port
    // Expected payloads come from the OLD panel (git show 6010c47:public/elements/Notebook.jsx,
    // lines 1350-1589 and 988/1069), not from the new hook: run_all carries the version.
    resetStore();
    const fn = vi.fn(async (a: { name: string; payload: Record<string, unknown> }) =>
      a.name === "nb_add_cell" ? { ...props({ version: 6 }), cells: [cell(), cell({ id: "b" })] } : a.name === "nb_list_projects" ? { projects: [] } : null);
    usePanel.setState({ nb: props(), callAction: fn });
    const client = new QueryClient();
    const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
    const { result } = renderHook(() => useNotebookActions(), { wrapper });
    const d = dataset();
    const cases: [() => Promise<unknown>, string, Record<string, unknown>][] = [
      [() => result.current.save("a", "x = 1"), "nb_update_cell", { version: 5, cell_id: "a", source: "x = 1" }],
      [() => result.current.run(cell()), "nb_run_cell", { version: 5, cell_id: "a", source: "print(1)" }],
      [() => result.current.runAll(), "nb_run_all", { version: 5 }],
      [() => result.current.add("a", "code"), "nb_add_cell", { version: 5, after_id: "a", type: "code" }],
      [() => result.current.move("a", "up"), "nb_move_cell", { version: 6, cell_id: "a", direction: "up" }],
      [() => result.current.duplicate("a"), "nb_duplicate_cell", { version: 6, cell_id: "a" }],
      [() => result.current.remove("a"), "nb_delete_cell", { version: 6, cell_id: "a" }],
      [() => result.current.clearCellOutputs("a"), "nb_clear_cell_outputs", { version: 6, cell_id: "a" }],
      [() => result.current.reorder("b", "a"), "nb_reorder_cell", { version: 6, cell_id: "b", before_id: "a" }],
      [() => result.current.interrupt(), "nb_interrupt", { version: 6 }],
      [() => result.current.restart(), "nb_restart", { version: 6 }],
      [() => result.current.clearOutputs(), "nb_clear_outputs", { version: 6 }],
      [() => result.current.switchProject("p2"), "nb_switch_project", { project_id: "p2" }],
      [() => result.current.createProject("  New one "), "nb_create_project", { name: "New one" }],
      [() => result.current.dsCancel("iris"), "ds_cancel", { dataset_id: "iris" }],
      [() => result.current.dsDelete("iris"), "ds_delete", { dataset_id: "iris" }],
      [() => client.fetchQuery({ queryKey: ["p"], queryFn: () => usePanel.getState().callAction!({ name: "nb_list_projects", payload: {} }) }), "nb_list_projects", {}],
    ];
    const seen = new Set<string>();
    for (const [go, name, payload] of cases) {
      fn.mockClear();
      await act(async () => {
        await go();
      });
      expect(fn, name).toHaveBeenCalledWith({ name, payload });
      seen.add(name);
    }
    expect(seen.size).toBe(17);
    void d;
  });

  it("uses_latest_callAction_after_remount", async () => {
    // Positive · changed: a new fn set after remount
    // Then: the new fn is called, the old one isn't · Demonstrates: no stale closure
    const h = await mountPanel(props());
    const fresh = vi.fn(async (a: { name: string }) => lists(a));
    await h.push(props({ version: 6 }), fresh);
    h.callAction.mockClear();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Run cell" }));
    });
    expect(fresh).toHaveBeenCalledWith(expect.objectContaining({ name: "nb_run_cell" }));
    expect(h.callAction).not.toHaveBeenCalled();
  });

  it("rejected_action_clears_busy_and_shows_error", async () => {
    // Negative · changed: the mock rejects
    // Then: the button is enabled again, an error is shown · Demonstrates: no stuck spinner
    const fn = vi.fn(async (a: { name: string }) => {
      if (a.name === "nb_restart") throw new Error("Kernel restart failed");
      return lists(a);
    });
    await mountPanel(props(), fn);
    const restart = screen.getByRole("button", { name: "Restart kernel" });
    await act(async () => {
      fireEvent.click(restart);
    });
    expect((restart as HTMLButtonElement).disabled).toBe(false);
    expect(screen.getByRole("alert").textContent).toContain("Kernel restart failed");
  });

  it("double_click_sends_once", async () => {
    // Negative · changed: 2 fast clicks
    // Then: 1 call · Demonstrates: no double run or delete
    let release!: () => void;
    const fn = vi.fn((a: { name: string }) =>
      a.name === "nb_run_all" ? new Promise((r) => (release = () => r(null))) : Promise.resolve(lists(a)));
    await mountPanel(props(), fn);
    const runAll = screen.getByRole("button", { name: "Run all" });
    await act(async () => {
      fireEvent.click(runAll);
      fireEvent.click(runAll);
    });
    expect(fn.mock.calls.filter(([a]) => a.name === "nb_run_all")).toHaveLength(1);
    await act(async () => release());
  });
});

// Load code for a created file (unit)
// Baseline: Given a created card {path: "/work/Iris.csv", files: [{path: "Iris.csv"}]} · When load code is built
const createdCard = (path = "/work/Iris.csv") =>
  dataset({ id: "file-iris-csv", name: path.split("/").pop(), origin: "created", source: "created", path, files: [{ path: path.split("/").pop()!, size: 4551 }] });

describe("Load code for a created file", () => {
  it("loads a created csv from its work path", () => {
    // Positive · baseline · changed: —
    // Then: df = pd.read_csv("/work/Iris.csv") · Demonstrates: a created file loads from its /work path
    expect(loadCode(createdCard())).toBe('import pandas as pd\n\ndf = pd.read_csv("/work/Iris.csv")\ndf.head()\n');
  });

  it("quotes a name with spaces and quotes safely", () => {
    // Positive · edge · changed: /work/my "iris".csv
    // Then: the path sits inside one JSON string literal · Demonstrates: a file name can't become code
    expect(loadCode(createdCard('/work/my "iris".csv'))).toContain('pd.read_csv("/work/my \\"iris\\".csv")');
  });

  it("uses the right reader per extension", () => {
    // Positive · edge · changed: .parquet, .jsonl, .xlsx
    // Then: read_parquet, read_json(lines=True), read_excel · Demonstrates: every table type loads
    expect(loadCode(createdCard("/work/a.parquet"))).toContain('pd.read_parquet("/work/a.parquet")');
    expect(loadCode(createdCard("/work/a.jsonl"))).toContain('pd.read_json("/work/a.jsonl", lines=True)');
    expect(loadCode(createdCard("/work/a.xlsx"))).toContain('pd.read_excel("/work/a.xlsx")');
  });

  it("injection in a file name stays a string", () => {
    // Negative · changed: name a"); import os #.csv
    // Then: no code outside the literal · Demonstrates: file names can't run code
    const code = loadCode(createdCard('/work/a"); import os #.csv'));
    expect(code).toContain('pd.read_csv("/work/a\\"); import os #.csv")');
    expect(code.split("\n").filter((line) => line.startsWith("import "))).toEqual(["import pandas as pd"]);
  });

  it("downloaded card load code is unchanged", () => {
    // Negative · changed: origin downloaded
    // Then: same output as today · Demonstrates: no regression
    const downloaded = dataset({ origin: "downloaded" });
    expect(loadCode(downloaded)).toBe('import pandas as pd\n\ndf = pd.read_csv("/work/datasets/iris/iris.csv")\ndf.head()\n');
    expect(loadCode(dataset())).toBe(loadCode(downloaded));
  });
});
