// The Effort button: each click moves to the next level, wrapping round at the end.
import { Lightbulb } from "lucide-react";
import type { Picker } from "@/chat/events";

export function EffortPicker({ picker, picked, onPick }: { picker: Picker; picked: string; onPick: (level: string) => void }): JSX.Element {
  const index = Math.max(0, picker.options.findIndex((o) => o.id === picked));
  const current = picker.options[index];
  const next = picker.options[(index + 1) % picker.options.length];
  return (
    <button
      type="button"
      onClick={() => next && onPick(next.id)}
      title={next ? `Next: ${next.name}` : undefined}
      className="inline-flex h-8 items-center gap-1.5 rounded-lg border bg-background px-2.5 text-[13px] font-medium hover:bg-accent"
    >
      <Lightbulb className="size-3.5" aria-hidden />
      Effort: {current?.name ?? picked}
    </button>
  );
}
