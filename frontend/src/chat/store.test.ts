// Applying server events (pure applyEvent)
// Baseline: Given an empty chat state · When session.ready arrives
import { describe, expect, it } from "vitest";
import type { ServerEvent, SessionReady } from "@/chat/events";
import { RESTART_NOTICE, applyEvent, emptyChat, type AnswerView, type ChatState } from "@/chat/store";
import { props } from "@/panel/test/fixtures";

const ready = (overrides: Partial<SessionReady> = {}): SessionReady => ({
  type: "session.ready",
  chat_id: "chat-1",
  messages: [],
  pickers: [
    { id: "model", name: "Model", options: [{ id: "a/b", name: "A B", selected: true, detail: "thinks · tools" }] },
    { id: "effort", name: "Effort", options: [{ id: "low", name: "Low", selected: true, detail: "" }] },
  ],
  settings: ["show_thinking", "web_search", "notebook", "kaggle_account"].map((id) => ({
    id, label: id, initial: true, disabled: false, description: "",
  })),
  panel: props(),
  ...overrides,
});

const play = (events: ServerEvent[], start: ChatState = emptyChat()): ChatState => events.reduce(applyEvent, start);
const answers = (state: ChatState) => state.messages.filter((m): m is AnswerView => m.role === "assistant" && "group" in m);

describe("Applying server events (pure applyEvent)", () => {
  it("session ready sets the pickers, settings and panel", () => {
    // Changed: —
    // Then: chat id, Model/Effort pickers, four Settings rows and the panel props are in the state
    // Demonstrates: the page draws what the server sent
    const state = play([ready()]);
    expect(state.chatId).toBe("chat-1");
    expect(state.status).toBe("open");
    expect(state.pickers.map((p) => p.id)).toEqual(["model", "effort"]);
    expect(state.settings).toHaveLength(4);
    expect(state.panel?.project.id).toBe(props().project.id);
    expect(state.picked).toEqual({ model: "a/b", effort: "low" });
  });

  it("reply events build one answer in order", () => {
    // Changed: reply.started, two deltas, reply.ended
    // Then: one assistant message whose text is the final text
    // Demonstrates: streaming lands in the right place
    const state = play([
      ready(),
      { type: "reply.started", message_id: "m1" },
      { type: "reply.delta", message_id: "m1", text: "Hel" },
      { type: "reply.delta", message_id: "m1", text: "lo" },
    ]);
    expect(answers(state)[0]).toMatchObject({ text: "Hello", isStreaming: true });
    const ended = applyEvent(state, { type: "reply.ended", message_id: "m1", text: "Hello!" });
    expect(answers(ended)).toHaveLength(1);
    expect(answers(ended)[0]).toMatchObject({ text: "Hello!", isStreaming: false });
  });

  it("work group collects activity, thinking and steps", () => {
    // Changed: group.label twice, thinking.delta, step.done, group.done
    // Then: the message's group has the labels, the thinking text, one step and the summary
    // Demonstrates: the work group shows what happened
    const state = play([
      ready(),
      { type: "group.label", message_id: "m1", label: "Thinking" },
      { type: "thinking.delta", message_id: "m1", text: "Let me look" },
      { type: "group.label", message_id: "m1", label: "Web search: hanoi" },
      { type: "step.done", message_id: "m1", title: "Web search: hanoi", output: "3 results" },
      { type: "group.done", message_id: "m1", label: "2 steps · 4s" },
    ]);
    expect(answers(state)[0].group).toEqual({
      label: "2 steps · 4s", isDone: true, thinking: "Let me look", steps: [{ title: "Web search: hanoi", output: "3 results" }],
    });
  });

  it("a prompt opens and closes with the choice", () => {
    // Changed: ask.opened then ask.closed run / null
    // Then: one prompt card, then marked chosen / timed out
    // Demonstrates: prompts follow the server
    const opened = play([
      ready(),
      { type: "reply.started", message_id: "m1" },
      { type: "ask.opened", ask_id: "q1", markdown: "Run this?", choices: [{ id: "run", label: "Run" }, { id: "skip", label: "Skip" }] },
    ]);
    expect(opened.prompts).toEqual([expect.objectContaining({ askId: "q1", outcome: "open", answerMessageId: "m1" })]);
    expect(applyEvent(opened, { type: "ask.closed", ask_id: "q1", choice: "run" }).prompts[0]).toMatchObject({ outcome: "answered", chosen: "run" });
    expect(applyEvent(opened, { type: "ask.closed", ask_id: "q1", choice: null }).prompts[0]).toMatchObject({ outcome: "timed-out", chosen: null });
  });

  it("a reconnect redraws the chat so far", () => {
    // Changed: session.ready with two messages
    // Then: both messages shown, nothing duplicated
    // Demonstrates: a short break keeps the chat
    const lines = [{ role: "user" as const, text: "hi" }, { role: "assistant" as const, text: "Hello" }];
    const afterReconnect = play([ready({ messages: lines }), ready({ messages: lines })]);
    expect(afterReconnect.messages.map((m) => [m.role, m.text])).toEqual([["user", "hi"], ["assistant", "Hello"]]);
  });

  it("a restart notice starts a new chat", () => {
    // Changed: chat.closed then session.ready
    // Then: old messages cleared; the restart notice shown
    // Demonstrates: a restart is explained
    const before = play([ready({ messages: [{ role: "user", text: "old" }] })]);
    const state = play([{ type: "chat.closed" }, ready({ chat_id: "chat-2" })], before);
    expect(state.messages).toEqual([]);
    expect(state.chatId).toBe("chat-2");
    expect(state.notice).toBe(RESTART_NOTICE);
  });

  it("pickers and settings follow a model change", () => {
    // Changed: pickers.changed, settings.changed
    // Then: new options and rows replace the old ones
    // Demonstrates: a new model changes what is offered
    const state = play([
      ready(),
      { type: "pickers.changed", pickers: [{ id: "model", name: "Model", options: [{ id: "c/d", name: "C D", selected: true, detail: "" }] }] },
      { type: "settings.changed", switches: [{ id: "web_search", label: "Web search", initial: false, disabled: true, description: "This model can't use tools." }] },
    ]);
    expect(state.pickers.map((p) => p.id)).toEqual(["model"]);
    expect(state.picked.model).toBe("c/d");
    expect(state.settings).toEqual([expect.objectContaining({ id: "web_search", disabled: true })]);
  });

  it("toasts and errors are queued", () => {
    // Changed: toast, then error BUSY
    // Then: two toasts, the error one kept until closed
    // Demonstrates: problems are visible
    const state = play([
      ready(),
      { type: "toast", kind: "success", text: "Kaggle connected" },
      { type: "error", code: "BUSY", message: "Wait for the reply to finish, or press Stop." },
    ]);
    expect(state.toasts.map((t) => [t.kind, t.text])).toEqual([
      ["success", "Kaggle connected"],
      ["error", "Wait for the reply to finish, or press Stop."],
    ]);
    expect(new Set(state.toasts.map((t) => t.id)).size).toBe(2);
  });

  it("events for an unknown answer are ignored", () => {
    // Changed: reply.delta with a message id never started
    // Then: state unchanged, no crash
    // Demonstrates: a stray event can't break the page
    const state = play([ready()]);
    expect(applyEvent(state, { type: "reply.delta", message_id: "never", text: "x" })).toEqual(state);
    expect(applyEvent(state, { type: "ask.closed", ask_id: "never", choice: "run" })).toEqual(state);
  });

  it("unknown event types are ignored", () => {
    // Changed: type nope
    // Then: state unchanged
    // Demonstrates: the page survives a newer server
    const state = play([ready()]);
    expect(applyEvent(state, { type: "nope" } as unknown as ServerEvent)).toBe(state);
  });
});
