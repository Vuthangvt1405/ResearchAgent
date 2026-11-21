// The chat socket: one per tab. It keeps the chat id only in memory, so a dropped link
// resumes the same chat while a page reload starts a new one.
import type { PageEvent, ServerEvent } from "@/chat/events";
import type { CallAction } from "@/panel/types";

export const SOCKET_PATH = "/ws/chat";
export const RECONNECT_FIRST_DELAY_MS = 500; // doubles on each failed try
export const RECONNECT_MAX_DELAY_MS = 10_000;
const SOCKET_OPEN = 1;
const OFFLINE = { error: { code: "OFFLINE", message: "Lost the link to the app. Try again in a moment." } };
const NOT_SENT = "Not connected to the app yet. Try again in a moment.";

export type ConnectionStatus = "connecting" | "open" | "reconnecting";

export interface ConnectionDeps {
  /** Where the page came from, e.g. "http://127.0.0.1:8000" */
  pageOrigin: string;
  /** Opens a socket; tests pass a fake */
  openSocket: (url: string) => WebSocket;
  onEvent: (event: ServerEvent) => void;
  onStatus: (status: ConnectionStatus) => void;
}

export class ChatConnection {
  private socket: WebSocket | null = null;
  private chatId: string | null = null;
  private failedTries = 0;
  private requestCount = 0;
  private readonly waiting = new Map<string, (result: unknown) => void>();

  constructor(private readonly deps: ConnectionDeps) {}

  /** Open the socket for a new chat */
  start(): void {
    this.open();
  }

  send(event: PageEvent): boolean {
    if (!this.isOpen()) {
      this.deps.onEvent({ type: "toast", kind: "warning", text: NOT_SENT });
      return false;
    }
    this.socket!.send(JSON.stringify(event));
    return true;
  }

  /** The panel's callAction: a panel.action answered by the panel.result with the same request id */
  readonly callAction: CallAction = ({ name, payload }) =>
    new Promise((resolve) => {
      if (!this.isOpen()) {
        resolve(OFFLINE);
        return;
      }
      this.requestCount += 1;
      const requestId = `r${this.requestCount}`;
      this.waiting.set(requestId, resolve);
      this.socket!.send(JSON.stringify({ type: "panel.action", request_id: requestId, name, payload }));
    });

  /** The socket URL for this page, with the chat id when resuming */
  socketUrl(chatId: string | null): string {
    const url = new URL(SOCKET_PATH, this.deps.pageOrigin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    if (chatId) url.searchParams.set("chat_id", chatId);
    return url.toString();
  }

  private isOpen(): boolean {
    return this.socket !== null && this.socket.readyState === SOCKET_OPEN;
  }

  private open(): void {
    const socket = this.deps.openSocket(this.socketUrl(this.chatId));
    this.socket = socket;
    this.deps.onStatus(this.chatId ? "reconnecting" : "connecting");
    socket.onmessage = (message: MessageEvent) => this.receive(socket, JSON.parse(String(message.data)) as ServerEvent);
    socket.onclose = () => this.dropped(socket);
  }

  private receive(socket: WebSocket, event: ServerEvent): void {
    if (socket !== this.socket) return;
    if (event.type === "panel.result") {
      this.waiting.get(event.request_id)?.(event.result);
      this.waiting.delete(event.request_id);
      return;
    }
    if (event.type === "session.ready") {
      this.chatId = event.chat_id;
      this.failedTries = 0;
      this.deps.onStatus("open");
    }
    this.deps.onEvent(event);
  }

  private dropped(socket: WebSocket): void {
    if (socket !== this.socket) return;
    this.socket = null;
    for (const resolve of this.waiting.values()) resolve(OFFLINE);
    this.waiting.clear();
    this.deps.onStatus("reconnecting");
    const delay = Math.min(RECONNECT_FIRST_DELAY_MS * 2 ** this.failedTries, RECONNECT_MAX_DELAY_MS);
    this.failedTries += 1;
    setTimeout(() => this.open(), delay);
  }
}
