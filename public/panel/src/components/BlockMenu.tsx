// Block actions menu (port of BlockMenu). The root never remounts now, so the old
// overlay re-open and focus-restore workarounds are gone.
import { ArrowDown, ArrowUp, Code2, Copy, Eraser, StickyNote, Trash2 } from "lucide-react";
import type { ReactNode } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { CellProps, CellType } from "@/types";

export interface BlockActions {
  add: (afterId: string | null, type: CellType) => void;
  duplicate: (id: string) => void;
  copy: (cell: CellProps) => void;
  clearOutputs: (id: string) => void;
  move: (id: string, dir: "up" | "down") => void;
  remove: (id: string) => void;
}

export interface BlockMenuProps {
  cell: CellProps;
  actions: BlockActions;
  open: boolean;
  setMenu: (id: string | null) => void;
}

export function BlockMenu({ cell, actions, open, setMenu }: BlockMenuProps) {
  const key = `menu:${cell.id}`;
  const item = (icon: ReactNode, label: string, fn: () => void, cls = "", keyHint = "") => (
    <DropdownMenuItem data-rc-item={label} className={`rcnb-mitem ${cls}`} onSelect={fn}>
      {icon}
      <span>{label}</span>
      {keyHint && <DropdownMenuShortcut>{keyHint}</DropdownMenuShortcut>}
    </DropdownMenuItem>
  );
  return (
    <DropdownMenu modal={false} open={open} onOpenChange={(o) => setMenu(o ? cell.id : null)}>
      <DropdownMenuTrigger asChild>
        <span className="rcnb-anchor" aria-hidden="true" tabIndex={-1} />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        data-rc-overlay={key}
        className="rcnb-mcontent"
        align="start"
        sideOffset={2}
        aria-label="Block actions"
        onInteractOutside={(e) => {
          // The handle and the ⋯ button toggle the menu themselves
          const t = e.target as HTMLElement | null;
          if (t && t.closest && t.closest(`[data-rc-toggle="${CSS.escape(key)}"]`)) e.preventDefault();
        }}
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          const h = document.querySelector<HTMLElement>(`[data-cell-id="${CSS.escape(cell.id)}"] .rcnb-handle`);
          if (h && !document.activeElement?.closest("textarea, input")) h.focus();
        }}
      >
        {item(<Code2 />, "Add code below", () => actions.add(cell.id, "code"))}
        {item(<StickyNote />, "Add note below", () => actions.add(cell.id, "markdown"))}
        <DropdownMenuSeparator />
        {item(<Copy />, "Duplicate", () => actions.duplicate(cell.id))}
        {item(<Copy />, cell.type === "code" ? "Copy code" : "Copy note", () => actions.copy(cell))}
        {cell.type === "code" && cell.outputs.length > 0 && item(<Eraser />, "Clear output", () => actions.clearOutputs(cell.id))}
        <DropdownMenuSeparator />
        {item(<ArrowUp />, "Move up", () => actions.move(cell.id, "up"), "", "Alt+↑")}
        {item(<ArrowDown />, "Move down", () => actions.move(cell.id, "down"), "", "Alt+↓")}
        <DropdownMenuSeparator />
        {item(<Trash2 />, "Delete", () => actions.remove(cell.id), "danger")}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
