// The Datasets tab: totals, filter, sort and one card per dataset (port of DatasetsTab).
import { useRef } from "react";
import { Database, Search, SearchX, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { DatasetCard } from "@/components/DatasetCard";
import { DatasetSortSelect } from "@/components/DatasetSortSelect";
import { usePanel } from "@/store";
import { fmtBytes, isActive } from "@/lib/loadCode";
import type { DatasetProps } from "@/types";

export interface DatasetsTabProps {
  datasets: DatasetProps[];
  inserting: string | null;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
  onInsert: (d: DatasetProps) => void;
}

export function DatasetsTab({ datasets, inserting, onCancel, onDelete, onInsert }: DatasetsTabProps) {
  const filter = usePanel((s) => s.dsFilter);
  const sort = usePanel((s) => s.dsSort);
  const search = useRef<HTMLInputElement>(null);
  const setFilter = (v: string) => usePanel.setState({ dsFilter: v });

  if (!datasets.length) {
    return (
      <div className="rcds">
        <Card className="rcds-empty">
          <Database size={20} style={{ opacity: 0.6 }} />
          <div>No datasets in this project yet.</div>
          <div>Ask the assistant, e.g. “find and download an iris dataset”.</div>
        </Card>
      </div>
    );
  }

  const total = datasets.reduce((n, d) => n + (d.size_bytes || 0), 0);
  const live = datasets.filter(isActive).length;
  const failed = datasets.filter((d) => d.status === "failed" || d.status === "missing").length;
  const q = filter.trim().toLowerCase();
  const shown = datasets
    .filter((d) => !q || d.name.toLowerCase().includes(q) || d.id.includes(q) || (d.license || "").toLowerCase().includes(q))
    .sort((a, b) => {
      // Active downloads always first, then the chosen order
      if (isActive(a) !== isActive(b)) return isActive(a) ? -1 : 1;
      if (sort === "name") return a.name.localeCompare(b.name);
      if (sort === "size") return (b.size_bytes || 0) - (a.size_bytes || 0);
      return (b.requested_at || "").localeCompare(a.requested_at || "");
    });

  return (
    <div className="rcds">
      <div className="rcds-summary">
        {datasets.length} dataset{datasets.length === 1 ? "" : "s"} · {fmtBytes(total)}
        {live > 0 && ` · ${live} downloading`}
        {failed > 0 && ` · ${failed} need attention`}
      </div>
      {datasets.length > 1 && (
        <div className="rcds-tools">
          <label className="rcds-search">
            <Search size={13} />
            <Input
              ref={search}
              className="rcds-input"
              placeholder="Filter by name or licence"
              aria-label="Filter datasets"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Escape") { setFilter(""); e.currentTarget.blur(); } }}
            />
            {!!filter && (
              <button className="rcnb-mini" title="Clear filter" aria-label="Clear dataset filter" onClick={() => { setFilter(""); search.current?.focus(); }}>
                <X size={12} />
              </button>
            )}
          </label>
          <DatasetSortSelect />
        </div>
      )}
      {shown.map((d) => <DatasetCard key={d.id} d={d} inserting={inserting === d.id} onCancel={onCancel} onDelete={onDelete} onInsert={onInsert} />)}
      {!shown.length && (
        <Card className="rcds-empty">
          <SearchX size={18} style={{ opacity: 0.6 }} />
          <div>No dataset matches “{filter}”.</div>
          <Button variant="outline" size="sm" className="rcds-btn" onClick={() => setFilter("")}>Clear filter</Button>
        </Card>
      )}
    </div>
  );
}
