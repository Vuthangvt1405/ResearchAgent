// The cell and note text box (port of SourceBox). The panel root never unmounts or
// moves, so focus, the cursor and an IME composition simply stay (AC5, AC10).
import { useEffect, useRef } from "react";
import { usePanel } from "@/store";
import { autoIndent, indentSelection, toggleComment, type Edit } from "@/lib/editing";

export interface SourceBoxProps {
  id: string;
  value: string;
  onChange: (text: string) => void;
  onShiftEnter: () => void;
  onBlur?: () => void;
  onMove?: (dir: "up" | "down") => void;
  autoFocus?: boolean;
  placeholder?: string;
  className?: string;
  code?: boolean;
}

export function SourceBox({ id, value, onChange, onShiftEnter, onBlur, onMove, autoFocus, placeholder, className, code }: SourceBoxProps) {
  const rows = Math.max(1, value.split("\n").length);
  const ref = useRef<HTMLTextAreaElement>(null);

  const apply = ([next, start, end]: Edit) => {
    onChange(next);
    setTimeout(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(start, end);
    }, 0);
  };

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
      wrap={className === "rcnb-src" ? "off" : "soft"}
      placeholder={placeholder}
      spellCheck={false}
      aria-label={code ? "Python code" : "Note text"}
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
        const el = e.currentTarget;
        const start = el.selectionStart;
        const end = el.selectionEnd;
        // Shift+Enter or Ctrl/Cmd+Enter runs a cell / finishes a note
        if (e.key === "Enter" && (e.shiftKey || e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          onShiftEnter();
          return;
        }
        if (e.key === "Escape" && onBlur) {
          el.blur();
          return;
        }
        if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown") && onMove) {
          e.preventDefault();
          onMove(e.key === "ArrowUp" ? "up" : "down");
          return;
        }
        if (!code) return;
        if (e.key === "Tab") {
          e.preventDefault();
          apply(indentSelection(value, start, end, e.shiftKey));
          return;
        }
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          apply(autoIndent(value, start, end));
          return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key === "/") {
          e.preventDefault();
          apply(toggleComment(value, start, end));
        }
      }}
    />
  );
}
