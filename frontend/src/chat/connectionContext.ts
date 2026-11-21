// How components reach the chat socket; tests provide a fake.
import { createContext, useContext } from "react";
import type { PageEvent } from "@/chat/events";
import type { CallAction } from "@/panel/types";

export interface ChatSender {
  send: (event: PageEvent) => boolean;
  callAction: CallAction;
}

export const ConnectionContext = createContext<ChatSender | null>(null);

export function useConnection(): ChatSender {
  const sender = useContext(ConnectionContext);
  if (!sender) throw new Error("useConnection needs a ConnectionContext provider");
  return sender;
}
