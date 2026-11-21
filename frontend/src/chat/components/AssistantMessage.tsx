// One answer: its work group, its questions, the answer text and Copy.
import { Answer, CopyButton } from "@/chat/components/Answer";
import { PromptCard } from "@/chat/components/PromptCard";
import { WorkGroup } from "@/chat/components/WorkGroup";
import type { AnswerView, PromptView } from "@/chat/store";
import mark from "@/assets/favicon.svg";

export interface AssistantMessageProps {
  answer: AnswerView;
  prompts?: PromptView[];
  onAnswer?: (askId: string, choiceId: string) => void;
}

export function AssistantMessage({ answer, prompts = [], onAnswer = () => {} }: AssistantMessageProps): JSX.Element {
  const isWaiting = answer.isStreaming && !answer.text && !answer.group;
  return (
    <div className="st-enter flex items-start gap-3">
      <img src={mark} alt="" className="mt-0.5 size-7 shrink-0" />
      <div className="flex min-w-0 flex-1 flex-col gap-3">
        {answer.group && <WorkGroup group={answer.group} />}
        {prompts.map((prompt) => (
          <PromptCard key={prompt.askId} prompt={prompt} onAnswer={onAnswer} />
        ))}
        {isWaiting && <span className="text-sm text-muted-foreground">…</span>}
        {answer.text && <Answer text={answer.text} />}
        {answer.text && !answer.isStreaming && (
          <div className="-ml-2 flex items-center text-xs text-muted-foreground">
            <CopyButton text={answer.text} label="Copy answer" />
          </div>
        )}
      </div>
    </div>
  );
}
