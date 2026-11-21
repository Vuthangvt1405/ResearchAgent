// The message box: Enter sends, Shift+Enter adds a line, Stop while an answer streams.
import { useId, useRef, useState, type KeyboardEvent } from "react";
import { ArrowUp, Square } from "lucide-react";
import { CommandMenu, commandRowId } from "@/chat/components/CommandMenu";
import { EffortPicker } from "@/chat/components/EffortPicker";
import { ModelPicker } from "@/chat/components/ModelPicker";
import type { SlashCommand } from "@/chat/lib/slashCommands";
import { useCommandMenu } from "@/chat/components/useCommandMenu";
import { useChat } from "@/chat/store";

const NO_COMMANDS: SlashCommand[] = [];

export interface ComposerProps {
  isStreaming: boolean;
  onSend: (text: string) => boolean;
  onStop: () => void;
  /** Commands the "/" menu offers; without them the box never shows a menu */
  commands?: SlashCommand[];
}

export function Composer({ isStreaming, onSend, onStop, commands = NO_COMMANDS }: ComposerProps): JSX.Element {
  const [text, setText] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  const menuId = useId();
  const menu = useCommandMenu(text, commands, () => setText(""), box);
  const pickers = useChat((s) => s.pickers);
  const picked = useChat((s) => s.picked);
  const pick = useChat((s) => s.pick);
  const modelPicker = pickers.find((p) => p.id === "model");
  const effortPicker = pickers.find((p) => p.id === "effort");
  const hasText = text.trim().length > 0;

  const submit = () => {
    if (!hasText || isStreaming) return;
    if (onSend(text.trim())) setText("");
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (menu.handleKey(event)) return;
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div className="px-4 pb-4 pt-2">
      <div className="relative mx-auto max-w-3xl rounded-2xl border bg-background shadow-sm">
        {menu.isOpen && (
          <CommandMenu
            listId={menuId}
            rowIdPrefix={`${menuId}-row`}
            commands={menu.matches}
            highlightedIndex={menu.highlightedIndex}
            onChoose={menu.choose}
            onHighlight={menu.highlight}
            menuRef={menu.menuRef}
          />
        )}
        <textarea
          ref={box}
          aria-label="Message SillyTherin"
          aria-expanded={menu.isOpen}
          aria-controls={menu.isOpen ? menuId : undefined}
          aria-activedescendant={menu.isOpen ? commandRowId(`${menuId}-row`, menu.highlightedIndex) : undefined}
          rows={2}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask SillyTherin anything, or paste a dataset link…"
          className="block w-full resize-none rounded-t-2xl bg-transparent px-4 pb-1.5 pt-3.5 text-[15px] outline-none placeholder:text-muted-foreground"
        />
        <div className="flex flex-wrap items-center gap-1.5 px-2.5 pb-2.5 pt-2">
          {modelPicker && <ModelPicker picker={modelPicker} picked={picked.model} onPick={(id) => pick("model", id)} />}
          {effortPicker && <EffortPicker picker={effortPicker} picked={picked.effort} onPick={(id) => pick("effort", id)} />}
          <span className="flex-1" />
          {isStreaming ? (
            <button type="button" onClick={onStop} className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-foreground px-3 text-[13px] font-medium text-background">
              <Square className="size-3 fill-current" aria-hidden />
              Stop
            </button>
          ) : (
            <button
              type="button"
              aria-label="Send message"
              onClick={submit}
              disabled={!hasText}
              className="inline-flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground disabled:opacity-40"
            >
              <ArrowUp className="size-4" aria-hidden />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
