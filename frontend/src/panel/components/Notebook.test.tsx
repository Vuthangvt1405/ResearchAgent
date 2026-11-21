// The Notebook panel as a whole: status, problems, save badge, tabs, find, shortcuts, drag
// Baseline: Given a project with code cells · When the panel is shown and the user acts on it
import { describe, it, expect } from "vitest";
import { act, fireEvent, screen } from "@testing-library/react";
import { mountPanel, panelRoot } from "@/panel/test/harness";
import { cell, dataset, props } from "@/panel/test/fixtures";
import { usePanel } from "@/panel/store";

const threeCells = () => [cell({ id: "a", source: "x = 1" }), cell({ id: "b", source: "y = 2" }), cell({ id: "c", source: "print(x)" })];
const statusText = () => panelRoot().querySelector(".rcnb-statustext")?.textContent;
const problemText = () => screen.queryByRole("alert")?.textContent ?? null;
const sentActions = (fn: { mock: { calls: unknown[][] } }) =>
  fn.mock.calls.map(([action]) => action as { name: string; payload: Record<string, unknown> });

describe("Kernel status", () => {
  it("shows the kernel state, and Running while a cell runs", async () => {
    // Then: Ready when idle, Running… while a cell runs, Kernel died when dead
    const h = await mountPanel(props({ kernel: "idle" }));
    expect(statusText()).toBe("Ready");
    await h.push(props({ version: 6, running_cell_id: "a" }));
    expect(statusText()).toBe("Running…");
    await h.push(props({ version: 7, kernel: "dead" }));
    expect(statusText()).toBe("Kernel died");
  });
});

describe("Problem line", () => {
  it("explains a dead kernel and a missing Docker", async () => {
    const h = await mountPanel(props({ kernel: "dead" }));
    expect(problemText()).toContain("The kernel died (maybe out of memory). Press Restart.");
    await h.push(props({ version: 6, kernel: "unavailable" }));
    expect(problemText()).toContain("Docker isn't running");
  });

  it("a dismissed server error stays hidden until the next version", async () => {
    // Then: Dismiss hides it; the same error at a newer version shows again
    const failing = (version: number) => props({ version, error: { code: "STALE", message: "Someone else changed it" } });
    const h = await mountPanel(failing(5));
    expect(problemText()).toContain("Someone else changed it");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss error" }));
    expect(problemText()).toBeNull();
    await h.push(failing(6));
    expect(problemText()).toContain("Someone else changed it");
  });
});

describe("Save badge", () => {
  it("says Unsaved while a draft waits to be saved", async () => {
    await mountPanel(props());
    expect(screen.queryByText("Unsaved")).toBeNull();
    await act(async () => usePanel.setState({ drafts: { a: "x = 2" } }));
    expect(screen.getByText("Unsaved")).toBeTruthy();
  });
});

describe("Tabs", () => {
  it("arrow keys switch between Notebook and Datasets", async () => {
    await mountPanel(props({ datasets: [dataset()] }));
    const tabs = screen.getByRole("tablist", { name: "Notebook views" });
    fireEvent.keyDown(tabs, { key: "ArrowRight" });
    expect(usePanel.getState().tab).toBe("datasets");
    expect(screen.getByRole("tab", { name: /Datasets/ }).getAttribute("aria-selected")).toBe("true");
    fireEvent.keyDown(tabs, { key: "ArrowLeft" });
    expect(usePanel.getState().tab).toBe("notebook");
  });

  it("counts cells and datasets, marking an active download as live", async () => {
    await mountPanel(props({ cells: threeCells(), datasets: [dataset({ status: "downloading" })] }));
    expect(screen.getByRole("tab", { name: /Notebook/ }).textContent).toContain("3");
    const datasetCount = screen.getByRole("tab", { name: /Datasets/ }).querySelector(".rcnb-count");
    expect(datasetCount?.textContent).toBe("1");
    expect(datasetCount?.classList.contains("live")).toBe(true);
  });
});

describe("Find", () => {
  it("filters cells by source and says when nothing matches", async () => {
    await mountPanel(props({ cells: threeCells() }));
    fireEvent.click(screen.getByRole("button", { name: "Find" }));
    const input = screen.getByRole("textbox", { name: "Find in notebook" });
    fireEvent.change(input, { target: { value: "x" } });
    expect(screen.getByText("2 of 3")).toBeTruthy();
    fireEvent.change(input, { target: { value: "zzz" } });
    expect(screen.getByText(/No cell matches/)).toBeTruthy();
  });

  it("Escape in the find box clears and closes it", async () => {
    await mountPanel(props({ cells: threeCells() }));
    fireEvent.click(screen.getByRole("button", { name: "Find" }));
    const input = screen.getByRole("textbox", { name: "Find in notebook" });
    fireEvent.change(input, { target: { value: "zzz" } });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("textbox", { name: "Find in notebook" })).toBeNull();
    expect(panelRoot().querySelectorAll("[data-cell-id]").length).toBe(3);
  });
});

describe("Keyboard shortcuts", () => {
  it("Ctrl+Shift+Enter inside the panel runs all cells", async () => {
    const h = await mountPanel(props());
    screen.getByRole("button", { name: "Find" }).focus();
    await act(async () => {
      fireEvent.keyDown(window, { key: "Enter", ctrlKey: true, shiftKey: true });
    });
    expect(sentActions(h.callAction).map((a) => a.name)).toContain("nb_run_all");
  });

  it("the shortcut does nothing while focus is outside the panel", async () => {
    const h = await mountPanel(props());
    await act(async () => {
      fireEvent.keyDown(window, { key: "Enter", ctrlKey: true, shiftKey: true });
    });
    expect(sentActions(h.callAction).map((a) => a.name)).not.toContain("nb_run_all");
  });
});

describe("Drag to reorder", () => {
  it("dropping a block on the lower half of another puts it after that block", async () => {
    // jsdom gives every block a zero-height box, so any drop lands on the lower half
    const h = await mountPanel(props({ cells: threeCells() }));
    const handle = (id: string) => panelRoot().querySelector(`[data-cell-id="${id}"] .rcnb-handle`) as HTMLElement;
    const block = (id: string) => panelRoot().querySelector(`[data-cell-id="${id}"]`) as HTMLElement;
    fireEvent.dragStart(handle("c"));
    fireEvent.dragOver(block("a"), { clientY: 0 });
    await act(async () => {
      fireEvent.drop(block("a"), { clientY: 0 });
    });
    const reorder = sentActions(h.callAction).find((a) => a.name === "nb_reorder_cell");
    expect(reorder?.payload).toEqual({ version: 5, cell_id: "c", before_id: "b" });
  });
});

describe("Empty notebook", () => {
  it("invites the user to add a first block", async () => {
    await mountPanel(props({ cells: [] }));
    expect(screen.getByText("Start your notebook")).toBeTruthy();
  });
});
