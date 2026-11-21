// The "/" menu's state and keys: when it is open, which row is highlighted, and what each key does.
import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { commandQueryOf, commandsMatching, highlightAfter, type SlashCommand } from "@/chat/lib/slashCommands";

export interface CommandMenuState {
  /** The menu is showing: the box starts with "/", some name matches, and it wasn't dismissed for this draft */
  isOpen: boolean;
  /** Rows to show, in list order */
  matches: SlashCommand[];
  /** The row Enter or Tab would run */
  highlightedIndex: number;
  /** Handles ↑ ↓ Enter Tab Esc while open; true when it used the key, so the box skips its own Enter */
  handleKey: (event: KeyboardEvent<HTMLTextAreaElement>) => boolean;
  /** Runs the command and empties the box; nothing is sent to the assistant */
  choose: (command: SlashCommand) => void;
  /** Hovering a row highlights it */
  highlight: (index: number) => void;
  /** The menu element, so a press outside it (and outside the box) closes the menu */
  menuRef: RefObject<HTMLDivElement>;
}

type MenuKeyAction = "next" | "previous" | "run" | "dismiss";

// Shift+Enter is left to the box, so it still adds a line
const MENU_KEYS: Record<string, MenuKeyAction> = { ArrowDown: "next", ArrowUp: "previous", Enter: "run", Tab: "run", Escape: "dismiss" };

function menuActionFor(event: KeyboardEvent<HTMLTextAreaElement>): MenuKeyAction | null {
  const isTypingInInputMethod = event.nativeEvent.isComposing;
  if (isTypingInInputMethod || event.shiftKey) return null;
  return MENU_KEYS[event.key] ?? null;
}

export function useCommandMenu(boxText: string, commands: SlashCommand[], emptyBox: () => void, boxRef: RefObject<HTMLTextAreaElement>): CommandMenuState {
  const menuRef = useRef<HTMLDivElement>(null);
  const [isDismissed, setIsDismissed] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const query = commandQueryOf(boxText);
  const matches = useMemo(() => (query === null ? [] : commandsMatching(commands, query)), [commands, query]);
  const isOpen = matches.length > 0 && !isDismissed;
  const safeHighlight = highlightedIndex < matches.length ? highlightedIndex : 0;

  // each new query starts on the first row; deleting the "/" ends the dismissal for that draft
  useEffect(() => {
    setHighlightedIndex(0);
    if (query === null) setIsDismissed(false);
  }, [query]);
  useCloseOnOutsidePress(isOpen, [menuRef, boxRef], () => setIsDismissed(true));

  const choose = (command: SlashCommand) => {
    command.run();
    emptyBox();
  };
  const runAction = (action: MenuKeyAction) => {
    if (action === "dismiss") setIsDismissed(true);
    else if (action === "run") choose(matches[safeHighlight]);
    else setHighlightedIndex(highlightAfter(safeHighlight, action === "next" ? 1 : -1, matches.length));
  };
  const handleKey = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    const action = isOpen ? menuActionFor(event) : null;
    if (action === null) return false;
    event.preventDefault();
    runAction(action);
    return true;
  };

  return { isOpen, matches, highlightedIndex: safeHighlight, handleKey, choose, highlight: setHighlightedIndex, menuRef };
}

function useCloseOnOutsidePress(isOpen: boolean, insideRefs: RefObject<HTMLElement>[], close: () => void): void {
  const latestClose = useRef(close);
  latestClose.current = close;
  useEffect(() => {
    if (!isOpen) return;
    const onPress = (event: MouseEvent) => {
      const target = event.target as Node;
      const isInside = insideRefs.some((ref) => ref.current?.contains(target));
      if (!isInside) latestClose.current();
    };
    document.addEventListener("mousedown", onPress);
    return () => document.removeEventListener("mousedown", onPress);
    // the refs are stable objects; only opening and closing changes the listener
  }, [isOpen]);
}
