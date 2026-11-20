// Typing survives a push (integration)
// The note editor keeps focus and mid-word input across pushes
import { describe, it, expect } from "vitest";
import { act, fireEvent, screen } from "@testing-library/react";
import { mountPanel } from "@/test/harness";
import { cell, props } from "@/test/fixtures";

describe("Typing survives a push (notes)", () => {
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
    // For notes too: composition in an empty note, then pushes arrive
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
