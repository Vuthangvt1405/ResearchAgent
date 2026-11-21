// Message box
// Baseline: Given an idle chat · When you type hi and press Enter
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/chat/components/AppShell";
import { Composer } from "@/chat/components/Composer";
import { useChat } from "@/chat/store";
import { GEMMA, renderWithChat, startChat } from "@/chat/test/renderChat";

const box = () => screen.getByRole("textbox", { name: "Message SillyTherin" }) as HTMLTextAreaElement;
const type = (text: string) => fireEvent.change(box(), { target: { value: text } });
const enter = (over: Partial<KeyboardEventInit> = {}) => fireEvent.keyDown(box(), { key: "Enter", ...over });

beforeEach(() => {
  localStorage.clear();
  startChat();
});

describe("Message box", () => {
  it("enter sends the message with the picks", () => {
    // Changed: —
    // Then: chat.send with hi, the picked model and effort; the box empties
    // Demonstrates: sending works
    const { sender } = renderWithChat(<AppShell />);
    type("hi");
    enter();
    expect(sender.send).toHaveBeenCalledWith({ type: "chat.send", text: "hi", model: "anthropic/claude-sonnet-4.5", effort: "high" });
    expect(box().value).toBe("");
    expect(useChat.getState().messages.map((m) => [m.role, m.text])).toEqual([["user", "hi"]]);
  });

  it("shift enter adds a line and an empty box sends nothing", () => {
    // Changed: Shift+Enter; Enter on spaces
    // Then: a new line; no event sent
    // Demonstrates: no accidental sends
    const onSend = vi.fn(() => true);
    render(<Composer isStreaming={false} onSend={onSend} onStop={vi.fn()} />);
    type("line one");
    enter({ shiftKey: true });
    type("   ");
    enter();
    expect(onSend).not.toHaveBeenCalled();
  });

  it("while streaming the button stops the answer", () => {
    // Changed: an answer is streaming
    // Then: Stop shown; clicking sends chat.stop
    // Demonstrates: you can stop a long answer
    const onStop = vi.fn();
    render(<Composer isStreaming onSend={vi.fn(() => true)} onStop={onStop} />);
    expect(screen.queryByRole("button", { name: "Send message" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /Stop/ }));
    expect(onStop).toHaveBeenCalledTimes(1);
  });

  it("the model search filters by name or id", () => {
    // Changed: type gem
    // Then: only matching models listed, each with what it can do; picking one shows its name on the button
    // Demonstrates: finding a model among hundreds is quick
    render(<Composer isStreaming={false} onSend={vi.fn(() => true)} onStop={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: /Claude Sonnet 4.5/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Search models" }), { target: { value: "gem" } });
    const options = within(screen.getByRole("listbox", { name: "Models" })).getAllByRole("option");
    expect(options.map((o) => o.textContent)).toEqual([`${GEMMA.name}${GEMMA.id}${GEMMA.detail}`]);
    fireEvent.click(options[0]);
    expect(useChat.getState().picked.model).toBe(GEMMA.id);
    expect(screen.getByRole("button", { name: /Gemma 4 31B/ })).toBeTruthy();
  });

  it("effort shows only for thinking models", () => {
    // Changed: pickers without Effort
    // Then: no Effort button
    // Demonstrates: no control that does nothing
    act(() => useChat.getState().apply({ type: "pickers.changed", pickers: useChat.getState().pickers.filter((p) => p.id === "model") }));
    render(<Composer isStreaming={false} onSend={vi.fn(() => true)} onStop={vi.fn()} />);
    expect(screen.queryByRole("button", { name: /Effort/ })).toBeNull();
  });

  it("clicking effort moves to the next level", () => {
    // Changed: click Effort at the last level
    // Then: the next level shows, wrapping round to the first; the next chat.send carries it
    // Demonstrates: effort changes in one click
    const { sender } = renderWithChat(<AppShell />);
    fireEvent.click(screen.getByRole("button", { name: "Effort: High" }));
    expect(screen.getByRole("button", { name: "Effort: Model default" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Effort: Model default" }));
    expect(screen.getByRole("button", { name: "Effort: Low" })).toBeTruthy();
    type("hi");
    enter();
    expect(sender.send).toHaveBeenLastCalledWith(expect.objectContaining({ type: "chat.send", effort: "low" }));
  });
});
