// The Model button and its searchable list; each model says what it can do.
import { useMemo, useState } from "react";
import { Bot, Check, ChevronDown, Search } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import type { Picker } from "@/chat/events";

export function ModelPicker({ picker, picked, onPick }: { picker: Picker; picked: string; onPick: (modelId: string) => void }): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const label = picker.options.find((o) => o.id === picked)?.name ?? picked;
  const matches = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return picker.options;
    return picker.options.filter((o) => o.name.toLowerCase().includes(needle) || o.id.toLowerCase().includes(needle));
  }, [picker.options, query]);
  const pick = (modelId: string) => {
    onPick(modelId);
    setIsOpen(false);
    setQuery("");
  };
  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger className="inline-flex h-8 max-w-[16rem] items-center gap-1.5 rounded-lg border bg-background px-2.5 text-[13px] font-medium hover:bg-accent">
        <Bot className="size-3.5 shrink-0" aria-hidden />
        <span className="truncate">{label}</span>
        <ChevronDown className="size-3.5 shrink-0" aria-hidden />
      </PopoverTrigger>
      <PopoverContent side="top" className="w-[24rem] max-w-[calc(100vw-2rem)] p-0" aria-label="Choose a model">
        <div className="flex items-center gap-2 border-b px-3 py-2 text-muted-foreground">
          <Search className="size-4" aria-hidden />
          <input
            autoFocus
            aria-label="Search models"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={`Search ${picker.options.length} models`}
            className="h-7 min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div role="listbox" aria-label="Models" className="max-h-80 overflow-y-auto p-1.5">
          {matches.map((option) => (
            <button
              key={option.id}
              type="button"
              role="option"
              aria-selected={option.id === picked}
              onClick={() => pick(option.id)}
              className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left hover:bg-accent aria-selected:bg-muted"
            >
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[13.5px] font-medium">{option.name}</span>
                <span className="truncate text-xs text-muted-foreground">{option.id}</span>
              </span>
              {option.detail && <span className="shrink-0 text-[11px] text-muted-foreground">{option.detail}</span>}
              <span className="w-4 shrink-0 text-primary">{option.id === picked && <Check className="size-4" aria-hidden />}</span>
            </button>
          ))}
          {matches.length === 0 && <p className="px-2.5 py-4 text-sm text-muted-foreground">No model matches “{query}”.</p>}
        </div>
      </PopoverContent>
    </Popover>
  );
}
