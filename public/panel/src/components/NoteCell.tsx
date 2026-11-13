// A Markdown note: click to edit, Shift+Enter or blur to finish (port of NoteCell).
import { useState } from "react";
import { Code2 } from "lucide-react";
import { usePanel } from "@/store";
import { SourceBox } from "@/components/SourceBox";
import { renderMarkdown } from "@/lib/markdown";

export interface NoteCellProps {
  id: string;
  source: string;
  match: boolean;
  onChange: (text: string) => void;
  onSave: () => void;
}

export function NoteCell({ id, source, match, onChange, onSave }: NoteCellProps) {
  // New and empty notes open ready to type. Latched in state, like the old code: typing
  // the first character must not flip the note out of editing (and end an IME composition)
  const [editing, setEditingState] = useState(() => !!usePanel.getState().editing[id] || !source);
  const setEditing = (on: boolean) => {
    const next = { ...usePanel.getState().editing };
    if (on) next[id] = true;
    else delete next[id];
    usePanel.setState({ editing: next });
    setEditingState(on);
  };
  const finish = () => {
    setEditing(false);
    onSave();
  };
  if (editing) {
    return <SourceBox id={id} className="rcnb-src rcnb-notesrc" value={source} onChange={onChange} onShiftEnter={finish} onBlur={finish} autoFocus placeholder="Write a note… Markdown works. Shift+Enter or Ctrl+Enter finishes" />;
  }
  return (
    // Click to edit, like Notion; clicking a link opens the link instead
    <div className={`rcnb-note${match ? " rcnb-match" : ""}`} onClick={(e) => (e.target as HTMLElement).closest("a") || setEditing(true)}>
      {renderMarkdown(source)}
      <span className="rcnb-note-edit">
        <button className="rcnb-mini" title="Edit note" aria-label="Edit note" onClick={(e) => { e.stopPropagation(); setEditing(true); }}><Code2 size={13} /></button>
      </span>
    </div>
  );
}
