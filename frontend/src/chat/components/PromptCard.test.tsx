// Prompt card
// Baseline: Given an open Run / Skip prompt · When Run is clicked
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { PromptCard, TIMED_OUT } from "@/chat/components/PromptCard";
import type { PromptView } from "@/chat/store";

const prompt = (over: Partial<PromptView> = {}): PromptView => ({
  askId: "q1",
  markdown: "The assistant wants to run this code:\n\n```python\n!ls\n```\n\n**Asking because it:**\n- runs a shell command",
  choices: [{ id: "run", label: "Run" }, { id: "skip", label: "Skip" }],
  outcome: "open",
  chosen: null,
  answerMessageId: "m1",
  ...over,
});

describe("Prompt card", () => {
  it("run answers the prompt once", () => {
    // Changed: —
    // Then: ask.answer with its ask id and run; buttons disabled
    // Demonstrates: you approve exactly once
    const onAnswer = vi.fn();
    render(<PromptCard prompt={prompt()} onAnswer={onAnswer} />);
    expect(screen.getByText("runs a shell command")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    fireEvent.click(screen.getByRole("button", { name: "Run" }));
    expect(onAnswer).toHaveBeenCalledTimes(1);
    expect(onAnswer).toHaveBeenCalledWith("q1", "run");
    expect((screen.getByRole("button", { name: "Skip" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("a closed prompt shows what happened", () => {
    // Changed: ask.closed run / null
    // Then: You chose Run / No answer, skipped
    // Demonstrates: the outcome stays visible
    const { rerender } = render(<PromptCard prompt={prompt({ outcome: "answered", chosen: "run" })} onAnswer={vi.fn()} />);
    expect(screen.getByText("You chose Run")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Run" })).toBeNull();
    rerender(<PromptCard prompt={prompt({ outcome: "timed-out" })} onAnswer={vi.fn()} />);
    expect(screen.getByText(TIMED_OUT)).toBeTruthy();
  });
});
