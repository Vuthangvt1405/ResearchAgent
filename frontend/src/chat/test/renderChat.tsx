// Renders chat components the way the page does, with a fake connection and a fresh store.
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { vi } from "vitest";
import { ConnectionContext } from "@/chat/connectionContext";
import type { ServerEvent, SessionReady } from "@/chat/events";
import { useChat } from "@/chat/store";
import { props } from "@/panel/test/fixtures";

export const GEMMA = { id: "google/gemma-4-31b-it", name: "Gemma 4 31B", selected: false, detail: "thinks · tools" };

export function sessionReady(overrides: Partial<SessionReady> = {}): SessionReady {
  return {
    type: "session.ready",
    chat_id: "chat-1",
    messages: [],
    pickers: [
      {
        id: "model",
        name: "Model",
        options: [
          { id: "anthropic/claude-sonnet-4.5", name: "Claude Sonnet 4.5", selected: true, detail: "thinks · tools" },
          GEMMA,
          { id: "vendor/plain", name: "Plain", selected: false, detail: "" },
        ],
      },
      {
        id: "effort",
        name: "Effort",
        options: [
          { id: "default", name: "Model default", selected: false, detail: "" },
          { id: "low", name: "Low", selected: false, detail: "" },
          { id: "high", name: "High", selected: true, detail: "" },
        ],
      },
    ],
    settings: [
      { id: "show_thinking", label: "Show thinking", initial: true, disabled: false, description: "Show the model's reasoning above its answer." },
      { id: "web_search", label: "Web search", initial: true, disabled: false, description: "Let the model search the internet." },
      { id: "notebook", label: "Notebook", initial: true, disabled: false, description: "Let the model read your project notebook and run code in it." },
      { id: "kaggle_account", label: "Kaggle account", initial: false, disabled: false, description: "Not connected." },
    ],
    panel: props(),
    ...overrides,
  };
}

/** A fresh chat that has received session.ready and then `events` */
export function startChat(events: ServerEvent[] = [], ready: SessionReady = sessionReady()): void {
  useChat.getState().reset();
  for (const event of [ready, ...events]) useChat.getState().apply(event);
}

export function fakeSender(isSent = true) {
  return { send: vi.fn(() => isSent), callAction: vi.fn(async () => null as unknown) };
}

export function renderWithChat(ui: ReactElement, sender = fakeSender()) {
  const view = render(<ConnectionContext.Provider value={sender}>{ui}</ConnectionContext.Provider>);
  return { ...view, sender };
}
