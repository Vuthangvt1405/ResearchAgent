// A code cell's Python editor (CodeMirror). The panel root never unmounts or moves, so
// the editor, its focus, cursor and any IME composition simply stay across pushes.
import { useEffect, useRef } from "react";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { bracketMatching, indentUnit } from "@codemirror/language";
import { python } from "@codemirror/lang-python";
import { Annotation, EditorSelection, EditorState, Prec } from "@codemirror/state";
import { EditorView, keymap, placeholder as placeholderText, type KeyBinding } from "@codemirror/view";
import { usePanel } from "@/store";
import { jupyterTheme } from "@/lib/jupyterTheme";

const PYTHON_INDENT = "    ";

/** Marks a change that came from the server, so it isn't echoed back as an edit */
const fromServer = Annotation.define<boolean>();

export interface CodeEditorProps {
  id: string;
  value: string;
  onChange: (text: string) => void;
  onRun: () => void;
  onMove: (dir: "up" | "down") => void;
  placeholder: string;
}

type EditorCallbacks = Pick<CodeEditorProps, "onChange" | "onRun" | "onMove">;

export function CodeEditor({ id, value, onChange, onRun, onMove, placeholder }: CodeEditorProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<EditorView | null>(null);
  // The editor is built once; its handlers read the latest callbacks through this ref
  const callbacksRef = useRef<EditorCallbacks>({ onChange, onRun, onMove });
  callbacksRef.current = { onChange, onRun, onMove };

  useEffect(() => {
    const view = new EditorView({
      parent: hostRef.current!,
      state: EditorState.create({ doc: value, extensions: buildExtensions(id, placeholder, callbacksRef) }),
    });
    viewRef.current = view;
    placeRequestedCursor(view, id);
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, []);

  useEffect(() => {
    const view = viewRef.current;
    if (view) showServerText(view, value);
  }, [value]);

  return <div ref={hostRef} className="rcnb-editor" />;
}

function buildExtensions(id: string, placeholder: string, callbacksRef: { current: EditorCallbacks }) {
  const cellKeys: KeyBinding[] = [
    { key: "Shift-Enter", run: () => runCell(callbacksRef) },
    { key: "Mod-Enter", run: () => runCell(callbacksRef) },
    { key: "Alt-ArrowUp", run: () => moveCell(callbacksRef, "up") },
    { key: "Alt-ArrowDown", run: () => moveCell(callbacksRef, "down") },
  ];
  return [
    python(),
    indentUnit.of(PYTHON_INDENT),
    history(),
    bracketMatching(),
    jupyterTheme,
    placeholderText(placeholder),
    EditorView.contentAttributes.of({ "aria-label": "Python code", "data-cell-src": id, spellcheck: "false" }),
    // Cell keys win over CodeMirror's own Alt+Arrow (move line) bindings
    Prec.highest(keymap.of(cellKeys)),
    keymap.of([indentWithTab, ...defaultKeymap, ...historyKeymap]),
    EditorView.domEventHandlers({
      compositionstart: (_event, view) => startComposing(id, view.state.doc.toString()),
      compositionend: () => endComposing(id),
    }),
    EditorView.updateListener.of((update) => {
      const isUserEdit = update.docChanged && !update.transactions.some((tr) => tr.annotation(fromServer));
      if (isUserEdit) callbacksRef.current.onChange(update.state.doc.toString());
    }),
  ];
}

function runCell(callbacksRef: { current: EditorCallbacks }): boolean {
  callbacksRef.current.onRun();
  return true;
}

function moveCell(callbacksRef: { current: EditorCallbacks }, dir: "up" | "down"): boolean {
  callbacksRef.current.onMove(dir);
  return true;
}

/** A cell that was just added or inserted asks for the cursor once */
function placeRequestedCursor(view: EditorView, id: string) {
  const requested = usePanel.getState().focus;
  if (!requested || requested.id !== id) return;
  const length = view.state.doc.length;
  view.dispatch({ selection: EditorSelection.range(Math.min(requested.start, length), Math.min(requested.end, length)) });
  view.focus();
  usePanel.setState({ focus: null });
}

/** Replace the editor text with the server's, keeping the cursor where it can stay */
function showServerText(view: EditorView, text: string) {
  const isSame = view.state.doc.toString() === text;
  // Mid-composition the editor shows the user's text, never the server's
  if (isSame || view.composing) return;
  const { anchor, head } = view.state.selection.main;
  view.dispatch({
    changes: { from: 0, to: view.state.doc.length, insert: text },
    selection: EditorSelection.range(Math.min(anchor, text.length), Math.min(head, text.length)),
    annotations: fromServer.of(true),
  });
}

// From compositionstart until compositionend the cell keeps the user's text as a draft
function startComposing(id: string, text: string) {
  const state = usePanel.getState();
  const hasDraft = state.drafts[id] !== undefined;
  usePanel.setState({ composing: id, drafts: hasDraft ? state.drafts : { ...state.drafts, [id]: text } });
}

function endComposing(id: string) {
  if (usePanel.getState().composing === id) usePanel.setState({ composing: null });
}
