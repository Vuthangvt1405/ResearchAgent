// The toolbar on each cell's top edge sends the same actions as the block menu
import { describe, it, expect } from "vitest";
import { act, fireEvent, within } from "@testing-library/react";
import { mountPanel, panelRoot } from "@/panel/test/harness";
import { cell, props } from "@/panel/test/fixtures";

const toolbarOf = (cellId: string) =>
  within(panelRoot().querySelector(`[data-cell-id="${cellId}"]`) as HTMLElement).getByRole("toolbar", { name: "Cell actions" });

async function click(button: HTMLElement) {
  await act(async () => {
    fireEvent.click(button);
  });
}

describe("Cell toolbar", () => {
  it("move_down_sends_nb_move_cell", async () => {
    const h = await mountPanel(props({ cells: [cell({ id: "a" }), cell({ id: "b" })] }));
    await click(within(toolbarOf("a")).getByRole("button", { name: "Move down" }));
    expect(h.callAction).toHaveBeenCalledWith(expect.objectContaining({ name: "nb_move_cell", payload: expect.objectContaining({ cell_id: "a", direction: "down" }) }));
  });

  it("delete_sends_nb_delete_cell", async () => {
    const h = await mountPanel(props({ cells: [cell({ id: "a" })] }));
    await click(within(toolbarOf("a")).getByRole("button", { name: "Delete" }));
    expect(h.callAction).toHaveBeenCalledWith(expect.objectContaining({ name: "nb_delete_cell", payload: expect.objectContaining({ cell_id: "a" }) }));
  });

  it("more_opens_the_block_menu", async () => {
    await mountPanel(props({ cells: [cell({ id: "a" })] }));
    await click(within(toolbarOf("a")).getByRole("button", { name: "More block actions" }));
    expect(document.querySelector('[data-rc-overlay="menu:a"]')).not.toBeNull();
  });

  it("notes_have_no_copy_code_button", async () => {
    await mountPanel(props({ cells: [cell({ id: "n", type: "markdown", source: "hi" })] }));
    expect(within(toolbarOf("n")).queryByRole("button", { name: "Copy code" })).toBeNull();
    expect(within(toolbarOf("n")).getByRole("button", { name: "Delete" })).toBeTruthy();
  });
});
