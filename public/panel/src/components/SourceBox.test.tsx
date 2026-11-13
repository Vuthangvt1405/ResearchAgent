// Group 4 — Typing survives a push (AC5, AC10 · integration)
// Plan: docs/plans/panel-react-build-plan.md §7
// Baseline: Given focus is in cell A's textarea with the cursor at 7 and an unsaved draft · When a remount happens
import { describe, it, expect } from "vitest";
import { act, fireEvent, screen } from "@testing-library/react";
import { mountPanel } from "@/test/harness";
import { cell, props } from "@/test/fixtures";

const box = () => screen.getByRole("textbox", { name: "Python code" }) as HTMLTextAreaElement;

describe("Group 4 — Typing survives a push", () => {
  it("focus_and_cursor_restored", async () => {
    // ✅1 · changed: —
    // Then: active element = cell A, selection 7–7 · Demonstrates: no lost cursor
    const h = await mountPanel(props({ cells: [cell({ source: "print(1)\nx = 2" })] }));
    const el = box();
    el.focus();
    el.setSelectionRange(7, 7);
    await h.push(props({ version: 6, cells: [cell({ source: "print(1)\nx = 2", outputs: [{ kind: "stdout", text: "1" }] })] }));
    expect(document.activeElement).toBe(el);
    expect(box()).toBe(el);
    expect([el.selectionStart, el.selectionEnd]).toEqual([7, 7]);
  });

  it("draft_kept_over_server_source", async () => {
    // ✅2 · changed: the push carries the old source
    // Then: the textarea shows the draft · Demonstrates: unsaved text wins
    const h = await mountPanel(props());
    await act(async () => {
      fireEvent.change(box(), { target: { value: "print(2)" } });
    });
    await h.push(props({ version: 6 }));
    expect(box().value).toBe("print(2)");
  });

  it("ime_composition_survives_push", async () => {
    // ✅3 · changed: compositionstart fired, no end yet
    // Then: no compositionend, no blur, same document.activeElement (plus manual Telex check in a browser)
    // Demonstrates: Telex/VNI typing isn't cut off
    const h = await mountPanel(props({ cells: [cell({ source: "vi" })] }));
    const el = box();
    el.focus();
    const events: string[] = [];
    el.addEventListener("compositionend", () => events.push("compositionend"));
    el.addEventListener("blur", () => events.push("blur"));
    const parent = el.parentNode;
    await act(async () => {
      fireEvent.compositionStart(el);
      fireEvent.change(el, { target: { value: "viê" } });
    });
    for (let i = 6; i < 10; i++) await h.push(props({ version: i, cells: [cell({ source: "vi" })] }));
    expect(events).toEqual([]);
    expect(document.activeElement).toBe(el);
    expect(el.parentNode).toBe(parent);
    expect(el.value).toBe("viê");
  });

  it("no_focus_steal_when_not_focused", async () => {
    // ❌1 · changed: focus is in the chat input
    // Then: focus stays in the chat · Demonstrates: the panel doesn't grab focus
    const h = await mountPanel(props());
    const chat = document.createElement("input");
    document.body.appendChild(chat);
    chat.focus();
    await h.push(props({ version: 6 }));
    expect(document.activeElement).toBe(chat);
  });

  it("push_does_not_overwrite_composing_text", async () => {
    // ❌2 · changed: the push carries a new source for the composing cell
    // Then: the textarea value is unchanged until composition ends · Demonstrates: server text never clobbers mid-word input
    const h = await mountPanel(props({ cells: [cell({ source: "Xin cha" })] }));
    const el = box();
    el.focus();
    await act(async () => {
      fireEvent.compositionStart(el);
    });
    await h.push(props({ version: 6, cells: [cell({ source: "edited elsewhere" })] }));
    expect(el.value).toBe("Xin cha");
    await act(async () => {
      fireEvent.change(el, { target: { value: "Xin chào" } });
      fireEvent.compositionEnd(el);
    });
    expect(el.value).toBe("Xin chào");
  });
});

// Extra cases for notes (advisor review): the note editor must not close mid-word
describe("Group 4 — Typing survives a push (notes)", () => {
  const note = () => screen.getByRole("textbox", { name: "Note text" }) as HTMLTextAreaElement;

  it("empty_note_stays_open_after_first_character", async () => {
    // edge: an empty note is open; the user types one character
    // Then: the same textarea is still there and focused · Demonstrates: typing doesn't close the note
    await mountPanel(props({ cells: [cell({ id: "n", type: "markdown", source: "" })] }));
    const el = note();
    el.focus();
    await act(async () => {
      fireEvent.change(el, { target: { value: "X" } });
    });
    expect(note()).toBe(el);
    expect(document.activeElement).toBe(el);
  });

  it("note_ime_composition_survives_push", async () => {
    // AC10 for notes: composition in an empty note, then pushes arrive
    // Then: same element, focused, no compositionend · Demonstrates: Telex in a note isn't cut off
    const h = await mountPanel(props({ cells: [cell({ id: "n", type: "markdown", source: "" })] }));
    const el = note();
    el.focus();
    const events: string[] = [];
    el.addEventListener("compositionend", () => events.push("compositionend"));
    await act(async () => {
      fireEvent.compositionStart(el);
      fireEvent.change(el, { target: { value: "ghi chú" } });
    });
    for (let i = 6; i < 9; i++) await h.push(props({ version: i, cells: [cell({ id: "n", type: "markdown", source: "" })] }));
    expect(note()).toBe(el);
    expect(document.activeElement).toBe(el);
    expect(el.value).toBe("ghi chú");
    expect(events).toEqual([]);
  });
});
