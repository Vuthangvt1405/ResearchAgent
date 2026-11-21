// Answers
// Baseline: Given one finished answer · When it renders
import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AssistantMessage } from "@/chat/components/AssistantMessage";
import { MessageList } from "@/chat/components/MessageList";
import type { AnswerView } from "@/chat/store";
import { useChat } from "@/chat/store";
import { renderWithChat, startChat } from "@/chat/test/renderChat";

const MARKDOWN = [
  "Two **open** sources:",
  "",
  "| Dataset | Source |",
  "|---|---|",
  "| Hanoi PM2.5 | OpenAQ |",
  "",
  "- first",
  "- second",
  "",
  "```python",
  "import pandas as pd",
  "```",
].join("\n");

const answer = (over: Partial<AnswerView> = {}): AnswerView => ({
  id: "m1", role: "assistant", text: MARKDOWN, isStreaming: false, group: null, ...over,
});

describe("Answers", () => {
  it("answers render markdown with tables and code", () => {
    // Changed: a table, a list, bold, a Python block
    // Then: a table, list items, strong text, a code block with a Copy button and coloured keywords
    // Demonstrates: answers read well
    const { container } = render(<AssistantMessage answer={answer()} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["first", "second"]);
    expect(container.querySelector("strong")?.textContent).toBe("open");
    const code = container.querySelector("pre.st-code") as HTMLElement;
    expect(code.textContent).toBe("import pandas as pd");
    expect(code.querySelector(".tok-keyword")?.textContent).toBe("import");
    expect(screen.getByRole("button", { name: "Copy" })).toBeTruthy();
  });

  it("the work group starts closed and opens on click", () => {
    // Changed: click the group
    // Then: the steps show; its label is the summary
    // Demonstrates: work stays out of the way until wanted
    const group = { label: "2 steps · 4s", isDone: true, thinking: "Looking up sources", steps: [{ title: "Web search: hanoi", output: "3 results" }] };
    render(<AssistantMessage answer={answer({ group })} />);
    const toggle = screen.getByRole("button", { name: /2 steps · 4s/ });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Web search: hanoi")).toBeNull();
    fireEvent.click(toggle);
    expect(screen.getByText("Web search: hanoi")).toBeTruthy();
    expect(screen.getByText("Looking up sources")).toBeTruthy();
  });

  it("copy puts the answer on the clipboard", async () => {
    // Changed: click Copy
    // Then: the answer's text is copied
    // Demonstrates: answers are easy to reuse
    const writeText = vi.fn(async () => {});
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<AssistantMessage answer={answer({ text: "Plain answer" })} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy answer" })));
    expect(writeText).toHaveBeenCalledWith("Plain answer");
  });

  it("auto-scroll follows unless you scrolled up", () => {
    // Changed: stream while at the bottom, then after scrolling up
    // Then: follows, then stays put
    // Demonstrates: reading back isn't interrupted
    startChat([{ type: "reply.started", message_id: "m1" }]);
    renderWithChat(<MessageList />);
    const list = screen.getByTestId("message-list");
    Object.defineProperty(list, "scrollHeight", { value: 1000, configurable: true });
    Object.defineProperty(list, "clientHeight", { value: 400, configurable: true });
    act(() => useChat.getState().apply({ type: "reply.delta", message_id: "m1", text: "more" }));
    expect(list.scrollTop).toBe(1000);
    list.scrollTop = 100;
    fireEvent.scroll(list);
    act(() => useChat.getState().apply({ type: "reply.delta", message_id: "m1", text: " text" }));
    expect(list.scrollTop).toBe(100);
  });
});
