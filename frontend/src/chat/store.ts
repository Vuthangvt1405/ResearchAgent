// The chat's state. Only applyEvent changes it in answer to the server, so every event's effect
// is one pure function the tests can check without a socket or a page.
import { create } from "zustand";
import type { Choice, ChatLine, Picker, ServerEvent, SessionReady, SettingSwitch, ToastKind } from "@/chat/events";
import type { ConnectionStatus } from "@/chat/connection";
import type { NotebookProps } from "@/panel/types";

export const RESTART_NOTICE = "The app restarted, so this is a new chat.";
export const TOAST_HIDE_MS = 5_000; // info and success toasts; warnings and errors stay

export interface ToolStepView { title: string; output: string }

export interface WorkGroupView {
  label: string | null; // what is happening now; the summary once done
  isDone: boolean;
  thinking: string;
  steps: ToolStepView[];
}

export interface AnswerView {
  id: string;
  role: "assistant";
  text: string;
  isStreaming: boolean;
  group: WorkGroupView | null;
}

export interface UserLine { id: string; role: "user"; text: string }

export type MessageView = UserLine | AnswerView;

export interface PromptView {
  askId: string;
  markdown: string;
  choices: Choice[];
  outcome: "open" | "answered" | "timed-out";
  chosen: string | null;
  answerMessageId: string | null; // the answer the prompt belongs to
}

export interface ToastView { id: number; kind: ToastKind; text: string }

export interface KagglePopupView { state: "waiting" | "connected" | "failed"; authorizeUrl: string; message: string }

export interface ChatState {
  chatId: string | null;
  status: ConnectionStatus;
  notice: string | null; // the restart notice, shown once
  messages: MessageView[];
  prompts: PromptView[];
  pickers: Picker[];
  settings: SettingSwitch[];
  panel: NotebookProps | null;
  toasts: ToastView[];
  kaggle: KagglePopupView | null;
  picked: { model: string; effort: string };
  nextId: number; // for toasts and lines the page adds itself
}

export const emptyChat = (): ChatState => ({
  chatId: null,
  status: "connecting",
  notice: null,
  messages: [],
  prompts: [],
  pickers: [],
  settings: [],
  panel: null,
  toasts: [],
  kaggle: null,
  picked: { model: "", effort: "" },
  nextId: 1,
});

const emptyGroup = (): WorkGroupView => ({ label: null, isDone: false, thinking: "", steps: [] });

function pickedFrom(pickers: Picker[], previous: ChatState["picked"]): ChatState["picked"] {
  const selected = (id: string) => pickers.find((p) => p.id === id)?.options.find((o) => o.selected)?.id;
  return { model: selected("model") ?? previous.model, effort: selected("effort") ?? previous.effort };
}

function linesToMessages(lines: ChatLine[]): MessageView[] {
  return lines.map((line, index) =>
    line.role === "user"
      ? { id: `line-${index}`, role: "user", text: line.text }
      : { id: `line-${index}`, role: "assistant", text: line.text, isStreaming: false, group: null },
  );
}

function sessionReady(state: ChatState, event: SessionReady): ChatState {
  // A reconnect to the same chat keeps what the page already drew (with its work groups)
  const isSameChat = state.chatId === event.chat_id && state.messages.length >= event.messages.length;
  return {
    ...state,
    chatId: event.chat_id,
    status: "open",
    messages: isSameChat ? state.messages : linesToMessages(event.messages),
    prompts: isSameChat ? state.prompts : [],
    pickers: event.pickers,
    settings: event.settings,
    panel: event.panel,
    picked: pickedFrom(event.pickers, state.picked),
  };
}

function findAnswer(state: ChatState, id: string): AnswerView | undefined {
  return state.messages.find((m): m is AnswerView => m.role === "assistant" && m.id === id);
}

function withAnswer(state: ChatState, id: string): ChatState {
  if (findAnswer(state, id)) return state;
  const answer: AnswerView = { id, role: "assistant", text: "", isStreaming: true, group: null };
  return { ...state, messages: [...state.messages, answer] };
}

function updateAnswer(state: ChatState, id: string, change: (answer: AnswerView) => AnswerView): ChatState {
  if (!findAnswer(state, id)) return state;
  return { ...state, messages: state.messages.map((m) => (m.role === "assistant" && m.id === id ? change(m) : m)) };
}

function updateGroup(state: ChatState, id: string, change: (group: WorkGroupView) => WorkGroupView): ChatState {
  return updateAnswer(withAnswer(state, id), id, (answer) => ({ ...answer, group: change(answer.group ?? emptyGroup()) }));
}

function addToast(state: ChatState, kind: ToastKind, text: string): ChatState {
  return { ...state, toasts: [...state.toasts, { id: state.nextId, kind, text }], nextId: state.nextId + 1 };
}

function streamingAnswerId(state: ChatState): string | null {
  const streaming = [...state.messages].reverse().find((m): m is AnswerView => m.role === "assistant" && m.isStreaming);
  return streaming?.id ?? null;
}

/** The state after one server event; events it can't place leave it unchanged */
export function applyEvent(state: ChatState, event: ServerEvent): ChatState {
  switch (event.type) {
    case "session.ready":
      return sessionReady(state, event);
    case "chat.closed":
      return { ...state, chatId: null, messages: [], prompts: [], notice: RESTART_NOTICE };
    case "reply.started":
      return withAnswer(state, event.message_id);
    case "reply.delta":
      return updateAnswer(state, event.message_id, (a) => ({ ...a, text: a.text + event.text }));
    case "reply.ended":
      return updateAnswer(withAnswer(state, event.message_id), event.message_id, (a) => ({ ...a, text: event.text, isStreaming: false }));
    case "group.label":
      return updateGroup(state, event.message_id, (g) => ({ ...g, label: event.label }));
    case "thinking.delta":
      return updateGroup(state, event.message_id, (g) => ({ ...g, thinking: g.thinking + event.text }));
    case "step.done":
      return updateGroup(state, event.message_id, (g) => ({ ...g, steps: [...g.steps, { title: event.title, output: event.output }] }));
    case "group.done":
      return updateGroup(state, event.message_id, (g) => ({ ...g, label: event.label, isDone: true }));
    case "chat.message": {
      const line: AnswerView = { id: `note-${state.nextId}`, role: "assistant", text: event.text, isStreaming: false, group: null };
      return { ...state, messages: [...state.messages, line], nextId: state.nextId + 1 };
    }
    case "ask.opened": {
      const prompt: PromptView = {
        askId: event.ask_id, markdown: event.markdown, choices: event.choices,
        outcome: "open", chosen: null, answerMessageId: streamingAnswerId(state),
      };
      return { ...state, prompts: [...state.prompts, prompt] };
    }
    case "ask.closed": {
      if (!state.prompts.some((p) => p.askId === event.ask_id)) return state;
      const outcome = event.choice === null ? "timed-out" : "answered";
      return { ...state, prompts: state.prompts.map((p) => (p.askId === event.ask_id ? { ...p, outcome, chosen: event.choice } : p)) };
    }
    case "toast":
      return addToast(state, event.kind, event.text);
    case "error":
      return addToast(state, "error", event.message);
    case "settings.changed":
      return { ...state, settings: event.switches };
    case "pickers.changed":
      return { ...state, pickers: event.pickers, picked: pickedFrom(event.pickers, state.picked) };
    case "panel.props":
      return { ...state, panel: event.props };
    case "kaggle.popup":
      return { ...state, kaggle: { state: event.state, authorizeUrl: event.authorize_url, message: event.message } };
    default:
      return state; // panel.result goes to the connection; newer event types are ignored
  }
}

/** The page's own line for a message it just sent */
export function addUserLine(state: ChatState, text: string): ChatState {
  const line: UserLine = { id: `you-${state.nextId}`, role: "user", text };
  return { ...state, messages: [...state.messages, line], notice: null, nextId: state.nextId + 1 };
}

export interface ChatStore extends ChatState {
  apply: (event: ServerEvent) => void;
  sent: (text: string) => void;
  setStatus: (status: ConnectionStatus) => void;
  dismissToast: (id: number) => void;
  pick: (pickerId: string, optionId: string) => void;
  closeKaggle: () => void;
  /** Show a Settings switch at its new position before the server confirms it */
  setSetting: (switchId: string, value: boolean) => void;
  reset: () => void;
}

export const useChat = create<ChatStore>()((set) => ({
  ...emptyChat(),
  apply: (event) => set((state) => applyEvent(state, event)),
  sent: (text) => set((state) => addUserLine(state, text)),
  setStatus: (status) => set({ status }),
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
  pick: (pickerId, optionId) => set((state) => ({ picked: { ...state.picked, [pickerId]: optionId } })),
  closeKaggle: () => set({ kaggle: null }),
  setSetting: (switchId, value) =>
    set((state) => ({ settings: state.settings.map((row) => (row.id === switchId ? { ...row, initial: value } : row)) })),
  reset: () => set(emptyChat()),
}));
