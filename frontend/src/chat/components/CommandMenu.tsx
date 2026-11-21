// The "Commands" list above the message box: one row per command, the highlighted one shaded, a key hint below.
import type { RefObject } from "react";
import { Database } from "lucide-react";
import type { SlashCommand } from "@/chat/lib/slashCommands";

export interface CommandMenuProps {
  listId: string;
  rowIdPrefix: string;
  commands: SlashCommand[];
  highlightedIndex: number;
  onChoose: (command: SlashCommand) => void;
  onHighlight: (index: number) => void;
  menuRef: RefObject<HTMLDivElement>;
}

export function commandRowId(rowIdPrefix: string, index: number): string {
  return `${rowIdPrefix}-${index}`;
}

export function CommandMenu({ listId, rowIdPrefix, commands, highlightedIndex, onChoose, onHighlight, menuRef }: CommandMenuProps): JSX.Element {
  return (
    <div ref={menuRef} className="absolute inset-x-0 bottom-full mb-2 rounded-xl border bg-card p-1.5 shadow-lg">
      <div id={listId} role="listbox" aria-label="Commands">
        <div aria-hidden className="px-2.5 pb-1 pt-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Commands</div>
        {commands.map((command, index) => (
          <div
            key={command.name}
            id={commandRowId(rowIdPrefix, index)}
            role="option"
            aria-selected={index === highlightedIndex}
            onMouseEnter={() => onHighlight(index)}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => onChoose(command)}
            className="flex cursor-pointer items-center gap-3 rounded-lg px-2.5 py-2 aria-selected:bg-muted"
          >
            <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Database className="size-4" aria-hidden />
            </span>
            <span className="font-mono text-[13px] font-semibold">/{command.name}</span>
            <span className="min-w-0 truncate text-[13px] text-muted-foreground">{command.description}</span>
          </div>
        ))}
      </div>
      <div aria-hidden className="mt-1 flex gap-4 border-t px-2.5 pb-1 pt-2 text-xs text-muted-foreground">
        <span>↑ ↓ move</span>
        <span>Enter or Tab run</span>
        <span>Esc close</span>
      </div>
    </div>
  );
}
