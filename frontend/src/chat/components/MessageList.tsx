// Every message, following the stream unless the reader scrolled up.
import { useLayoutEffect, useRef } from "react";
import { AssistantMessage } from "@/chat/components/AssistantMessage";
import { PromptCard } from "@/chat/components/PromptCard";
import { UserMessage } from "@/chat/components/UserMessage";
import { useConnection } from "@/chat/connectionContext";
import { useChat } from "@/chat/store";

const AT_BOTTOM_PX = 48; // closer than this counts as "at the bottom"

export function MessageList(): JSX.Element {
  const messages = useChat((s) => s.messages);
  const prompts = useChat((s) => s.prompts);
  const notice = useChat((s) => s.notice);
  const { send } = useConnection();
  const box = useRef<HTMLDivElement>(null);
  const isFollowing = useRef(true);

  useLayoutEffect(() => {
    const el = box.current;
    if (el && isFollowing.current) el.scrollTop = el.scrollHeight;
  });

  const onScroll = () => {
    const el = box.current;
    if (el) isFollowing.current = el.scrollHeight - el.scrollTop - el.clientHeight < AT_BOTTOM_PX;
  };
  const answer = (askId: string, choice: string) => send({ type: "ask.answer", ask_id: askId, choice });
  const answerIds = new Set(messages.map((m) => m.id));
  const unplaced = prompts.filter((p) => !p.answerMessageId || !answerIds.has(p.answerMessageId));

  return (
    <div ref={box} onScroll={onScroll} data-testid="message-list" className="min-h-0 flex-1 overflow-y-auto px-4 py-6">
      <div className="mx-auto flex max-w-3xl flex-col gap-6">
        {notice && <p className="text-center text-sm text-muted-foreground">{notice}</p>}
        {messages.map((message) =>
          message.role === "user" ? (
            <UserMessage key={message.id} text={message.text} />
          ) : (
            <AssistantMessage key={message.id} answer={message} prompts={prompts.filter((p) => p.answerMessageId === message.id)} onAnswer={answer} />
          ),
        )}
        {unplaced.map((prompt) => (
          <PromptCard key={prompt.askId} prompt={prompt} onAnswer={answer} />
        ))}
      </div>
    </div>
  );
}
