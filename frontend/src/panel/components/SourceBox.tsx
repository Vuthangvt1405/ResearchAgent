// The note text box (port of SourceBox). The panel root never unmounts or
// moves, so focus, the cursor and an IME composition simply stay.
import { useEffect, useRef } from "react";
import { usePanel } from "@/panel/store";

export interface SourceBoxProps {
  id: string;
  value: string;
  onChange: (text: string) => void;
  onShiftEnter: () => void;
  onBlur?: () => void;
  autoFocus?: boolean;
  placeholder?: string;
  className?: string;
}

export function SourceBox({ id, value, onChange, onShiftEnter, onBlur, autoFocus, placeholder, className }: SourceBoxProps) {
  const rows = Math.max(1, value.split("\n").length);
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    // A cell that was just added or inserted asks for the cursor once
    const want = usePanel.getState().focus;
    const el = ref.current;
    if (!el) return;
    if (want && want.id === id) {
      el.focus();
      el.setSelectionRange(want.start, want.end);
      usePanel.setState({ focus: null });
    } else if (autoFocus) {
      el.focus();
    }
  }, []);

  return (
    <textarea
      ref={ref}
      className={className}
      data-cell-src={id}
      value={value}
      rows={rows}
      wrap="soft"
      placeholder={placeholder}
      spellCheck={false}
      aria-label="Note text"
      onChange={(e) => onChange(e.target.value)}
      onCompositionStart={(e) => {
        // From here until compositionend the box shows the user's text, never the server's
        const s = usePanel.getState();
        usePanel.setState({
          composing: id,
          drafts: s.drafts[id] === undefined ? { ...s.drafts, [id]: e.currentTarget.value } : s.drafts,
        });
      }}
      onCompositionEnd={() => {
        if (usePanel.getState().composing === id) usePanel.setState({ composing: null });
      }}
      onBlur={() => onBlur && onBlur()}
      onKeyDown={(e) => {
        // Keys that finish an IME composition (Enter in CJK input) belong to the IME
        if (e.nativeEvent.isComposing || e.keyCode === 229) return;
        // Shift+Enter or Ctrl/Cmd+Enter finishes the note
        if (e.key === "Enter" && (e.shiftKey || e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          onShiftEnter();
          return;
        }
        if (e.key === "Escape" && onBlur) {
          e.currentTarget.blur();
        }
      }}
    />
  );
}
