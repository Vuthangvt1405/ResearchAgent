// A code cell's prompts follow Jupyter: [n]: beside the code and beside a result, [*]: while waiting
import { describe, it, expect } from "vitest";
import { mountPanel, panelRoot } from "@/panel/test/harness";
import { cell, props } from "@/panel/test/fixtures";

const outputPrompts = () => Array.from(panelRoot().querySelectorAll(".rcnb-outprompt")).map((prompt) => prompt.textContent);
const inputPrompt = () => panelRoot().querySelector(".rcnb-count-run")?.textContent;

describe("Code cell prompts", () => {
  it("result_gets_the_count_and_printed_text_does_not", async () => {
    await mountPanel(props({ cells: [cell({ execution_count: 3, outputs: [{ kind: "stdout", text: "hi" }, { kind: "result", text: "42" }] })] }));
    expect(inputPrompt()).toBe("[3]:");
    expect(outputPrompts()).toEqual(["", "[3]:"]);
  });

  it("queued_cell_shows_a_star", async () => {
    await mountPanel(props({ cells: [cell({ execution_count: 3, status: "queued" })] }));
    expect(inputPrompt()).toBe("[*]:");
  });
});
