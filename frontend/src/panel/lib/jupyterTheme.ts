// How a code cell's editor looks: Jupyter's classic notebook colours for Python, plus the
// editor chrome (cursor, selection, placeholder). Colours come from the HSL tokens in
// styles.css, so dark mode only has to redefine the tokens.
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { EditorView } from "@codemirror/view";
import { tags } from "@lezer/highlight";
import type { Extension } from "@codemirror/state";

const token = (name: string) => `hsl(var(--rc-jp-${name}))`;

const jupyterPythonColours = HighlightStyle.define([
  { tag: [tags.keyword, tags.controlKeyword, tags.definitionKeyword, tags.moduleKeyword, tags.bool, tags.null], color: token("keyword"), fontWeight: "bold" },
  { tag: [tags.operatorKeyword, tags.arithmeticOperator, tags.bitwiseOperator, tags.compareOperator, tags.updateOperator, tags.definitionOperator], color: token("operator"), fontWeight: "bold" },
  { tag: [tags.modifier, tags.meta], color: token("operator") },
  { tag: tags.number, color: token("number") },
  { tag: [tags.string, tags.special(tags.string)], color: token("string") },
  { tag: tags.escape, color: token("escape"), fontWeight: "bold" },
  { tag: tags.lineComment, color: token("comment"), fontStyle: "italic" },
  { tag: tags.function(tags.definition(tags.variableName)), color: token("definition") },
  { tag: tags.definition(tags.className), color: token("definition"), fontWeight: "bold" },
]);

const editorChrome = EditorView.theme({
  "&": { color: token("code-text"), backgroundColor: "transparent" },
  "&.cm-focused": { outline: "none" },
  ".cm-scroller": { fontFamily: "var(--rc-code-font)", fontSize: "13px", lineHeight: "var(--rc-code-line-height)" },
  ".cm-content": { padding: "6px 0", caretColor: token("code-text") },
  ".cm-line": { padding: "0 10px" },
  ".cm-cursor, .cm-dropCursor": { borderLeftColor: token("code-text") },
  "&.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection": { backgroundColor: token("selection") },
  ".cm-placeholder": { color: "hsl(var(--muted-foreground))" },
  "&.cm-focused .cm-matchingBracket": { backgroundColor: token("bracket-match"), outline: "none" },
});

export const jupyterTheme: Extension = [editorChrome, syntaxHighlighting(jupyterPythonColours)];
