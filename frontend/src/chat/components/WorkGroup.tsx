// The collapsible box of one answer's work: thinking and tool steps.
import { useState } from "react";
import { Check, ChevronRight } from "lucide-react";
import { Answer } from "@/chat/components/Answer";
import type { WorkGroupView } from "@/chat/store";

const WORKING = "Working…";

export function WorkGroup({ group }: { group: WorkGroupView }): JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <button
        type="button"
        aria-expanded={isOpen}
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left text-[13px] font-medium text-muted-foreground hover:bg-accent/60"
      >
        {group.isDone ? (
          <Check className="size-4" aria-hidden />
        ) : (
          <span className="size-2 animate-pulse rounded-full bg-primary" aria-hidden />
        )}
        <span className="flex-1 text-foreground">{group.label ?? WORKING}</span>
        <ChevronRight className={`size-4 transition-transform duration-200 ease-out ${isOpen ? "rotate-90" : ""}`} aria-hidden />
      </button>
      {isOpen && (
        <div className="st-expand space-y-3 border-t px-3.5 py-3 text-[13px]">
          {group.thinking && (
            <div>
              <div className="font-medium">Thinking</div>
              <p className="whitespace-pre-wrap italic text-muted-foreground">{group.thinking}</p>
            </div>
          )}
          {group.steps.map((step, index) => (
            <div key={index}>
              <div className="font-medium">{step.title}</div>
              <div className="text-muted-foreground [&_p]:text-[13px]">
                <Answer text={step.output} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
