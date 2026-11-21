// The connection (fake WebSocket)
// Baseline: Given the page at http://127.0.0.1:8000 · When it connects
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatConnection, RECONNECT_FIRST_DELAY_MS, type ConnectionStatus } from "@/chat/connection";
import type { ServerEvent } from "@/chat/events";

class FakeSocket {
  readyState = 0;
  sent: Record<string, unknown>[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((message: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  constructor(readonly url: string) {}
  send(data: string) { this.sent.push(JSON.parse(data)); }
  close() { this.drop(); }
  open() { this.readyState = 1; this.onopen?.(); }
  receive(event: object) { this.onmessage?.({ data: JSON.stringify(event) }); }
  drop() { this.readyState = 3; this.onclose?.(); }
}

let sockets: FakeSocket[];
let events: ServerEvent[];
let statuses: ConnectionStatus[];

function connect(): ChatConnection {
  const connection = new ChatConnection({
    pageOrigin: "http://127.0.0.1:8000",
    openSocket: (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket as unknown as WebSocket;
    },
    onEvent: (event) => events.push(event),
    onStatus: (status) => statuses.push(status),
  });
  connection.start();
  return connection;
}

const ready = (chatId: string) => ({ type: "session.ready", chat_id: chatId, messages: [], pickers: [], settings: [], panel: {} });

beforeEach(() => {
  sockets = [];
  events = [];
  statuses = [];
  vi.useFakeTimers();
});
afterEach(() => vi.useRealTimers());

describe("The connection (fake WebSocket)", () => {
  it("connects to the chat socket of this page", () => {
    // Changed: —
    // Then: socket opened on ws://127.0.0.1:8000/ws/chat with no chat id
    // Demonstrates: the page talks to its own server
    connect();
    expect(sockets.map((s) => s.url)).toEqual(["ws://127.0.0.1:8000/ws/chat"]);
    sockets[0].open();
    sockets[0].receive(ready("c1"));
    expect(events.map((e) => e.type)).toEqual(["session.ready"]);
    expect(statuses[statuses.length - 1]).toBe("open");
  });

  it("a drop reconnects to the same chat", () => {
    // Changed: the socket closes after session.ready
    // Then: a new socket on ?chat_id=<id> after a short wait, growing on repeated drops
    // Demonstrates: a short break keeps the chat
    connect();
    sockets[0].open();
    sockets[0].receive(ready("c1"));
    sockets[0].drop();
    expect(statuses[statuses.length - 1]).toBe("reconnecting");
    vi.advanceTimersByTime(RECONNECT_FIRST_DELAY_MS - 1);
    expect(sockets).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(sockets[1].url).toBe("ws://127.0.0.1:8000/ws/chat?chat_id=c1");
    sockets[1].drop();
    vi.advanceTimersByTime(RECONNECT_FIRST_DELAY_MS * 2 - 1);
    expect(sockets).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(3);
  });

  it("panel actions resolve with their own result", async () => {
    // Changed: two panel actions in flight
    // Then: each promise gets the panel.result with its own request id
    // Demonstrates: the panel works over the socket
    const connection = connect();
    sockets[0].open();
    const first = connection.callAction({ name: "nb_add_cell", payload: { version: 1 } });
    const second = connection.callAction({ name: "nb_run_all", payload: { version: 1 } });
    const [a, b] = sockets[0].sent as { type: string; request_id: string; name: string }[];
    expect([a.type, a.name, b.name]).toEqual(["panel.action", "nb_add_cell", "nb_run_all"]);
    sockets[0].receive({ type: "panel.result", request_id: b.request_id, result: { version: 3 } });
    sockets[0].receive({ type: "panel.result", request_id: a.request_id, result: { version: 2 } });
    await expect(first).resolves.toEqual({ version: 2 });
    await expect(second).resolves.toEqual({ version: 3 });
    expect(events.filter((e) => e.type === "panel.result")).toEqual([]);
  });

  it("a panel action fails when the socket closes first", async () => {
    // Changed: the socket closes before the result
    // Then: the promise resolves to an error the panel shows
    // Demonstrates: nothing hangs
    const connection = connect();
    sockets[0].open();
    const pending = connection.callAction({ name: "nb_run_all", payload: { version: 1 } });
    sockets[0].drop();
    await expect(pending).resolves.toMatchObject({ error: { code: "OFFLINE" } });
    await expect(connection.callAction({ name: "nb_run_all", payload: {} })).resolves.toMatchObject({ error: { code: "OFFLINE" } });
  });

  it("a reload starts a new chat", () => {
    // Changed: a new page load
    // Then: no chat id is sent and none is stored
    // Demonstrates: reloading starts fresh
    const stored = [vi.spyOn(localStorage, "setItem"), vi.spyOn(sessionStorage, "setItem")];
    connect();
    sockets[0].open();
    sockets[0].receive(ready("c1"));
    connect(); // the reloaded page builds a new connection
    expect(sockets[1].url).toBe("ws://127.0.0.1:8000/ws/chat");
    for (const spy of stored) expect(spy).not.toHaveBeenCalled();
  });
});
