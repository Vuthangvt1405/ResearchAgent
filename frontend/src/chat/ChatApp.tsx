// The page: opens the chat connection and draws the layout.
import { useEffect, useMemo } from "react";
import { AppShell } from "@/chat/components/AppShell";
import { ChatConnection } from "@/chat/connection";
import { ConnectionContext, type ChatSender } from "@/chat/connectionContext";
import { useChat } from "@/chat/store";

export function ChatApp(): JSX.Element {
  const connection = useMemo(
    () =>
      new ChatConnection({
        pageOrigin: window.location.origin,
        openSocket: (url) => new WebSocket(url),
        onEvent: (event) => useChat.getState().apply(event),
        onStatus: (status) => useChat.getState().setStatus(status),
      }),
    [],
  );
  useEffect(() => connection.start(), [connection]);
  const sender = useMemo<ChatSender>(() => ({ send: (event) => connection.send(event), callAction: connection.callAction }), [connection]);
  return (
    <ConnectionContext.Provider value={sender}>
      <AppShell />
    </ConnectionContext.Provider>
  );
}
