// "+ Code / + Note" between blocks (port of InsertRow).
import { Plus } from "lucide-react";
import type { CellType } from "@/types";

export interface InsertRowProps {
  afterId: string | null;
  onAdd: (afterId: string | null, type: CellType) => void;
}

export function InsertRow({ afterId, onAdd }: InsertRowProps) {
  return (
    <div className="rcnb-insert" aria-hidden="false">
      <div className="rcnb-insertbtns">
        <button className="rcnb-insertbtn" title="Add a code cell here" onClick={() => onAdd(afterId, "code")}><Plus size={12} />Code</button>
        <button className="rcnb-insertbtn" title="Add a note here" onClick={() => onAdd(afterId, "markdown")}><Plus size={12} />Note</button>
      </div>
    </div>
  );
}
