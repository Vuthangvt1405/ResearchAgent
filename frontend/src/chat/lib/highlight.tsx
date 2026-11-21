// Python colours for code blocks in answers, from the CodeMirror parser the panel already ships.
import type { ReactNode } from "react";
import { pythonLanguage } from "@codemirror/lang-python";
import { classHighlighter, highlightCode } from "@lezer/highlight";

export function highlightPython(code: string): ReactNode {
  const parts: ReactNode[] = [];
  try {
    highlightCode(
      code,
      pythonLanguage.parser.parse(code),
      classHighlighter,
      (text, classes) => parts.push(classes ? <span key={parts.length} className={classes}>{text}</span> : text),
      () => parts.push("\n"),
    );
  } catch {
    return code;
  }
  return parts;
}
