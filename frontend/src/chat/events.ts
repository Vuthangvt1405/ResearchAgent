// Every message between the page and the server over the chat socket, one-to-one with
// researchchat/server/events.py. The server checks page events strictly, so field names matter.
import type { NotebookProps } from "@/panel/types";

export type ToastKind = "info" | "success" | "warning" | "error";

export interface Choice {
  id: string; // sent back when the button is clicked
  label: string;
}

export interface PickerOption {
  id: string;
  name: string;
  selected: boolean;
  detail: string; // what a model can do, e.g. "thinks · tools"
}

export interface Picker {
  id: string; // "model" or "effort"
  name: string;
  options: PickerOption[];
}

export interface SettingSwitch {
  id: string;
  label: string;
  initial: boolean;
  disabled: boolean; // greyed out: the picked model lacks the feature
  description: string; // what it does, or why it is greyed out
}

export interface ChatLine {
  role: "user" | "assistant";
  text: string;
}

// ---- page → server

export interface ChatSend { type: "chat.send"; text: string; model: string; effort: string }
export interface ChatStop { type: "chat.stop" }
export interface SettingsUpdate { type: "settings.update"; values: Record<string, boolean> }
export interface AskAnswer { type: "ask.answer"; ask_id: string; choice: string }
export interface PanelAction { type: "panel.action"; request_id: string; name: string; payload: Record<string, unknown> }

export type PageEvent = ChatSend | ChatStop | SettingsUpdate | AskAnswer | PanelAction;

// ---- server → page

export interface SessionReady {
  type: "session.ready";
  chat_id: string;
  messages: ChatLine[]; // empty for a new chat; the chat so far after a reconnect
  pickers: Picker[];
  settings: SettingSwitch[];
  panel: NotebookProps;
}
export interface ChatClosed { type: "chat.closed" }
export interface ReplyStarted { type: "reply.started"; message_id: string }
export interface ReplyDelta { type: "reply.delta"; message_id: string; text: string }
export interface ReplyEnded { type: "reply.ended"; message_id: string; text: string }
export interface GroupLabel { type: "group.label"; message_id: string; label: string }
export interface GroupDone { type: "group.done"; message_id: string; label: string }
export interface ThinkingDelta { type: "thinking.delta"; message_id: string; text: string }
export interface StepDone { type: "step.done"; message_id: string; title: string; output: string }
export interface ChatMessage { type: "chat.message"; text: string }
export interface AskOpened { type: "ask.opened"; ask_id: string; markdown: string; choices: Choice[] }
export interface AskClosed { type: "ask.closed"; ask_id: string; choice: string | null }
export interface Toast { type: "toast"; kind: ToastKind; text: string }
export interface SettingsChanged { type: "settings.changed"; switches: SettingSwitch[] }
export interface PickersChanged { type: "pickers.changed"; pickers: Picker[] }
export interface PanelProps { type: "panel.props"; props: NotebookProps }
export interface PanelResult { type: "panel.result"; request_id: string; result: unknown }
export interface KagglePopup { type: "kaggle.popup"; state: "waiting" | "connected" | "failed"; authorize_url: string; message: string }
export interface ErrorEvent { type: "error"; code: "BAD_EVENT" | "BUSY" | "UNKNOWN_ASK" | "INTERNAL"; message: string }

export type ServerEvent =
  | SessionReady | ChatClosed
  | ReplyStarted | ReplyDelta | ReplyEnded
  | GroupLabel | GroupDone | ThinkingDelta | StepDone
  | ChatMessage | AskOpened | AskClosed | Toast
  | SettingsChanged | PickersChanged | PanelProps | PanelResult | KagglePopup | ErrorEvent;
