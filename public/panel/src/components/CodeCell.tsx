// A code cell: run button, [n] label, status tag, source box and outputs (port of CodeCell).
import { useRef, useState } from "react";
import { Check, ChevronDown, ChevronsUpDown, Copy, Loader2, MoreHorizontal, Play } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SourceBox } from "@/components/SourceBox";
import type { CellProps, OutputProps } from "@/types";

export function Output({ output }: { output: OutputProps }) {
  if (output.kind === "image") {
    return (
      <div className="rcnb-img">
        <img src={`data:image/png;base64,${output.image}`} alt="chart output" />
      </div>
    );
  }
  const err = output.kind === "error" || output.kind === "stderr";
  return <pre className={`rcnb-pre${err ? " err" : ""}`}>{output.text}</pre>;
}

export function outputSize(outputs: OutputProps[]) {
  return outputs.reduce((n, o) => n + (o.kind === "image" ? 400 : (o.text || "").length), 0) + outputs.length;
}

const TAGS: Record<string, [string, string]> = {
  error: ["Error", "bad"],
  interrupted: ["Interrupted", "bad"],
  timeout: ["Timed out", "bad"],
  queued: ["Queued", "wait"],
};

export interface CodeCellProps {
  cell: CellProps;
  source: string;
  running: boolean;
  match: boolean;
  canRun: boolean;
  copied: boolean;
  onChange: (text: string) => void;
  onRun: () => void;
  onCopy: () => void;
  onMenu: () => void;
  onMove: (dir: "up" | "down") => void;
}

export function CodeCell({ cell, source, running, match, canRun, copied, onChange, onRun, onCopy, onMenu, onMove }: CodeCellProps) {
  const label = cell.status === "queued" ? "…" : cell.execution_count ? cell.execution_count : " ";
  const tag = TAGS[cell.status];
  // Only outputs that weren't on screen before animate in
  const seen = useRef<number | null>(null);
  const shown = seen.current === null ? cell.outputs.length : Math.min(seen.current, cell.outputs.length);
  seen.current = cell.outputs.length;
  const state = running ? " running" : cell.status === "queued" ? " queued" : "";
  const long = outputSize(cell.outputs) > 900;
  const [open, setOpen] = useState(false);
  return (
    <>
      <div className={`rcnb-code${state}${match ? " rcnb-match" : ""}`}>
        <div className="rcnb-codehead">
          <button className="rcnb-run" title={canRun ? "Run (Shift+Enter or Ctrl+Enter)" : "Docker isn't running"} aria-label="Run cell" disabled={!canRun} onClick={onRun}>
            {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={12} fill="currentColor" />}
          </button>
          <span className="rcnb-count-run">[{running ? "*" : label}]</span>
          {tag && <Badge variant="outline" className={`rcnb-tag ${tag[1]}`}>{tag[0]}</Badge>}
          <span className="rcnb-sep" />
          <button className={`rcnb-mini${copied ? " copied" : ""}`} title="Copy code" aria-label="Copy code" onClick={onCopy}>
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
          <button className="rcnb-mini" title="More block actions" aria-label="More block actions" aria-haspopup="menu" data-rc-toggle={`menu:${cell.id}`} onClick={onMenu}>
            <MoreHorizontal size={15} />
          </button>
          <span className="rcnb-lang">Python</span>
        </div>
        <SourceBox id={cell.id} code className="rcnb-src" value={source} onChange={onChange} onShiftEnter={onRun} onMove={onMove} placeholder="Write Python… Shift+Enter runs · Tab indents · Ctrl+/ comments" />
      </div>
      {cell.outputs.length > 0 && (
        <>
          {long && (
            <div className="rcnb-outbar">
              <span>{cell.outputs.length} output{cell.outputs.length === 1 ? "" : "s"}</span>
              <span className="rcnb-sep" />
              <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => setOpen(!open)}>
                {open ? <ChevronDown size={13} /> : <ChevronsUpDown size={13} />}
                {open ? "Collapse" : "Show all"}
              </Button>
            </div>
          )}
          <div className={`rcnb-out${long && !open ? " collapsed" : ""}`}>
            {cell.outputs.map((o, i) => (
              <div key={i} className={i >= shown ? "rcnb-out-enter" : undefined}>
                <Output output={o} />
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}
