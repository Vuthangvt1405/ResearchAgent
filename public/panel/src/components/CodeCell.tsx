// A code cell laid out like Jupyter: a prompt column ([n]: and the run button) beside the
// editor, and the outputs below with [n]: beside a result. Copy, move, the menu and delete
// live in the cell toolbar that floats on its top edge.
import { useRef, useState } from "react";
import { ChevronDown, ChevronsUpDown, Loader2, Play } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { CodeEditor } from "@/components/CodeEditor";
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

const LONG_OUTPUT_CHARS = 900;

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
  onChange: (text: string) => void;
  onRun: () => void;
  onMove: (dir: "up" | "down") => void;
}

/** What goes inside the brackets: * while running or waiting, like Jupyter */
function promptCount(cell: CellProps, running: boolean): string {
  const isWaiting = running || cell.status === "queued";
  if (isWaiting) return "*";
  return cell.execution_count ? String(cell.execution_count) : " ";
}

export function CodeCell({ cell, source, running, match, canRun, onChange, onRun, onMove }: CodeCellProps) {
  const count = promptCount(cell, running);
  const tag = TAGS[cell.status];
  const runState = running ? " running" : cell.status === "queued" ? " queued" : "";
  return (
    <div className={`rcnb-code${runState}${match ? " rcnb-match" : ""}`}>
      <div className="rcnb-row">
        <div className="rcnb-prompt">
          <span className="rcnb-count-run">[{count}]:</span>
          <button className="rcnb-run" title={canRun ? "Run (Shift+Enter or Ctrl+Enter)" : "Docker isn't running"} aria-label="Run cell" disabled={!canRun} onClick={onRun}>
            {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={12} fill="currentColor" />}
          </button>
        </div>
        <CodeEditor id={cell.id} value={source} onChange={onChange} onRun={onRun} onMove={onMove} placeholder="Write Python… Shift+Enter runs · Tab indents · Ctrl+/ comments" />
      </div>
      {tag && (
        <div className="rcnb-row">
          <div className="rcnb-prompt" />
          <Badge variant="outline" className={`rcnb-tag ${tag[1]}`}>{tag[0]}</Badge>
        </div>
      )}
      {cell.outputs.length > 0 && <Outputs outputs={cell.outputs} count={count} />}
    </div>
  );
}

function Outputs({ outputs, count }: { outputs: OutputProps[]; count: string }) {
  // Only outputs that weren't on screen before animate in
  const seenCount = useRef<number | null>(null);
  const shownBefore = seenCount.current === null ? outputs.length : Math.min(seenCount.current, outputs.length);
  seenCount.current = outputs.length;
  const isLong = outputSize(outputs) > LONG_OUTPUT_CHARS;
  const [isExpanded, setExpanded] = useState(false);
  return (
    <>
      {isLong && (
        <div className="rcnb-row">
          <div className="rcnb-prompt" />
          <div className="rcnb-outbar">
            <span>{outputs.length} output{outputs.length === 1 ? "" : "s"}</span>
            <span className="rcnb-sep" />
            <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => setExpanded(!isExpanded)}>
              {isExpanded ? <ChevronDown size={13} /> : <ChevronsUpDown size={13} />}
              {isExpanded ? "Collapse" : "Show all"}
            </Button>
          </div>
        </div>
      )}
      <div className={`rcnb-out${isLong && !isExpanded ? " collapsed" : ""}`}>
        {outputs.map((output, index) => (
          <div key={index} className={`rcnb-row${index >= shownBefore ? " rcnb-out-enter" : ""}`}>
            {/* Jupyter labels only a cell's result with its count; printed text has no prompt */}
            <div className="rcnb-prompt rcnb-outprompt">{output.kind === "result" ? `[${count}]:` : ""}</div>
            <div className="rcnb-outcell"><Output output={output} /></div>
          </div>
        ))}
      </div>
    </>
  );
}
