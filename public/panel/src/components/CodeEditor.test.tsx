// Typing in a code cell survives a push, and the code is coloured like Jupyter
import { describe, it, expect } from "vitest";
import { act, fireEvent, screen } from "@testing-library/react";
import { EditorView } from "@codemirror/view";
import { mountPanel } from "@/test/harness";
import { cell, props } from "@/test/fixtures";

const content = () => screen.getByRole("textbox", { name: "Python code" });
const editor = () => EditorView.findFromDOM(content())!;
const text = () => editor().state.doc.toString();

function typeIntoCell(insert: string) {
  const view = editor();
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert } });
}

describe("Typing in a code cell survives a push", () => {
  it("focus_and_cursor_restored", async () => {
    const h = await mountPanel(props({ cells: [cell({ source: "print(1)\nx = 2" })] }));
    const view = editor();
    view.focus();
    view.dispatch({ selection: { anchor: 7 } });
    await h.push(props({ version: 6, cells: [cell({ source: "print(1)\nx = 2", outputs: [{ kind: "stdout", text: "1" }] })] }));
    expect(editor()).toBe(view);
    expect(document.activeElement).toBe(view.contentDOM);
    expect(view.state.selection.main.head).toBe(7);
  });

  it("draft_kept_over_server_source", async () => {
    const h = await mountPanel(props());
    await act(async () => typeIntoCell("print(2)"));
    await h.push(props({ version: 6 }));
    expect(text()).toBe("print(2)");
  });

  it("server_source_shown_when_there_is_no_draft", async () => {
    const h = await mountPanel(props({ cells: [cell({ source: "a = 1" })] }));
    await h.push(props({ version: 6, cells: [cell({ source: "a = 2" })] }));
    expect(text()).toBe("a = 2");
  });

  it("push_does_not_overwrite_composing_text", async () => {
    const h = await mountPanel(props({ cells: [cell({ source: "Xin cha" })] }));
    await act(async () => {
      fireEvent.compositionStart(content());
    });
    await h.push(props({ version: 6, cells: [cell({ source: "edited elsewhere" })] }));
    expect(text()).toBe("Xin cha");
  });

  it("no_focus_steal_when_not_focused", async () => {
    const h = await mountPanel(props());
    const chat = document.createElement("input");
    document.body.appendChild(chat);
    chat.focus();
    await h.push(props({ version: 6 }));
    expect(document.activeElement).toBe(chat);
  });
});

describe("Code cell editor", () => {
  it("shift_enter_runs_the_cell", async () => {
    const h = await mountPanel(props({ cells: [cell({ source: "print(1)" })] }));
    await act(async () => {
      fireEvent.keyDown(content(), { key: "Enter", shiftKey: true });
    });
    expect(h.callAction).toHaveBeenCalledWith(expect.objectContaining({ name: "nb_run_cell" }));
    expect(text()).toBe("print(1)");
  });

  it("python_keywords_and_strings_are_coloured", async () => {
    await mountPanel(props({ cells: [cell({ source: 'def greet():\n    return "hi"  # say hi' })] }));
    const colouredSpans = Array.from(content().querySelectorAll("span[class]")).map((span) => span.textContent);
    expect(colouredSpans).toEqual(expect.arrayContaining(["def", "greet", "return", '"hi"', "# say hi"]));
  });
});
