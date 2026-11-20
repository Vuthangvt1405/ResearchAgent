// The small toolbar that floats on a cell's top edge while the cell is hovered or focused,
// like the cell toolbar in VS Code's notebooks.
import { ArrowDown, ArrowUp, Check, Copy, MoreHorizontal, Trash2 } from "lucide-react";
import type { BlockActions } from "@/components/BlockMenu";
import type { CellProps } from "@/types";

export interface CellToolbarProps {
  cell: CellProps;
  actions: BlockActions;
  copied: boolean;
  isMenuOpen: boolean;
  setMenu: (id: string | null) => void;
}

const ICON_SIZE = 14;

export function CellToolbar({ cell, actions, copied, isMenuOpen, setMenu }: CellToolbarProps) {
  const isCode = cell.type === "code";
  return (
    <div className={`rcnb-celltools${isMenuOpen ? " open" : ""}`} role="toolbar" aria-label="Cell actions">
      {isCode && (
        <button className={`rcnb-mini${copied ? " copied" : ""}`} title="Copy code" aria-label="Copy code" onClick={() => actions.copy(cell)}>
          {copied ? <Check size={ICON_SIZE} /> : <Copy size={ICON_SIZE} />}
        </button>
      )}
      <button className="rcnb-mini" title="Move up (Alt+↑)" aria-label="Move up" onClick={() => actions.move(cell.id, "up")}>
        <ArrowUp size={ICON_SIZE} />
      </button>
      <button className="rcnb-mini" title="Move down (Alt+↓)" aria-label="Move down" onClick={() => actions.move(cell.id, "down")}>
        <ArrowDown size={ICON_SIZE} />
      </button>
      <button
        className="rcnb-mini"
        title="More block actions"
        aria-label="More block actions"
        aria-haspopup="menu"
        data-rc-toggle={`menu:${cell.id}`}
        onClick={() => setMenu(isMenuOpen ? null : cell.id)}
      >
        <MoreHorizontal size={ICON_SIZE + 1} />
      </button>
      <button className="rcnb-mini rcnb-tool-danger" title="Delete" aria-label="Delete" onClick={() => actions.remove(cell.id)}>
        <Trash2 size={ICON_SIZE} />
      </button>
    </div>
  );
}
