// One dataset row: name, source, size; the chevron opens details and actions
// (port of DatasetCard). Memoised on the dataset's content, so a progress push
// re-renders only the card whose numbers changed (AC2).
import { memo, useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Code2, Copy, Database, FileCode2, Trash2, X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { usePanel } from "@/store";
import { copyText, fmtBytes, isActive, loadCode, ordinal, percent } from "@/lib/loadCode";
import { safeHref } from "@/lib/safeHref";
import type { DatasetProps } from "@/types";

const DS_BADGE: Record<string, string> = { queued: "Queued", downloading: "Downloading", failed: "Failed", missing: "Files missing" };
const SOURCES: Record<string, string> = { huggingface: "Hugging Face", zenodo: "Zenodo", kaggle: "Kaggle" };

/** Renders per card id, for the "only the changed card re-renders" test (G3✅2) */
export const cardRenders: Record<string, number> = {};

export interface DatasetCardProps {
  d: DatasetProps;
  inserting: boolean;
  onCancel: (id: string) => void;
  onDelete: (id: string) => void;
  onInsert: (d: DatasetProps) => void;
}

function DatasetCardView({ d, inserting, onCancel, onDelete, onInsert }: DatasetCardProps) {
  cardRenders[d.id] = (cardRenders[d.id] || 0) + 1;
  const open = usePanel((s) => !!s.dsOpen[d.id]);
  const [confirming, setConfirming] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  useEffect(() => () => clearTimeout(timer.current), []);
  const active = isActive(d);
  const pct = percent(d);
  const href = safeHref(d.url);
  const copy = async (key: string, text: string) => {
    if (await copyText(text)) {
      setCopied(key);
      clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(null), 1500);
    }
  };
  const setOpen = (on: boolean) => usePanel.setState({ dsOpen: { ...usePanel.getState().dsOpen, [d.id]: on } });
  const files = d.files || [];
  const detailsId = `rcds-details-${d.id}`;
  return (
    <Card className={`rcds-card ${d.status}${open ? " open" : ""}`} data-dataset-id={d.id}>
      <div className="rcds-row">
        <div className="rcds-icon" aria-hidden="true"><Database size={15} /></div>
        <div className="rcds-head">
          <div className="rcds-name" title={d.name}>{d.name}</div>
          <div className="rcds-meta">
            <span>{SOURCES[d.source] || d.source}</span>
            <span className="rcds-dot">·</span>
            <span className="rcds-size">{active ? `${fmtBytes(d.done_bytes)} of ${fmtBytes(d.size_bytes)}` : fmtBytes(d.size_bytes)}</span>
          </div>
        </div>
        {d.status !== "ready" && (
          <Badge variant="outline" className={`rcds-badge ${d.status}`}>
            {d.status === "downloading" ? `${pct}%` : d.status === "queued" ? `${ordinal(d.position_in_queue || 1)} in queue` : DS_BADGE[d.status] || d.status}
          </Badge>
        )}
        {active && (
          <Button variant="ghost" size="sm" className="rcds-iconbtn" title="Cancel download" aria-label="Cancel download" onClick={() => onCancel(d.id)}>
            <X size={15} />
          </Button>
        )}
        <Button
          variant="ghost"
          size="sm"
          className="rcds-iconbtn rcds-more"
          title={open ? "Hide details" : "Show details"}
          aria-label={open ? `Hide details of ${d.name}` : `Show details of ${d.name}`}
          aria-expanded={open}
          aria-controls={detailsId}
          onClick={() => setOpen(!open)}
        >
          <ChevronDown size={16} />
        </Button>
      </div>

      {active && <Progress className="rcds-progress" value={d.status === "queued" ? 0 : pct} aria-label="Download progress" />}
      {d.status === "failed" && d.error && <div className="rcds-error">{d.error}</div>}
      {d.status === "missing" && <div className="rcds-error">Some files were deleted. Ask the assistant to download it again; only the missing files are fetched.</div>}

      {open && (
        <div className="rcds-details" id={detailsId}>
          <dl className="rcds-facts">
            <dt>Licence</dt>
            <dd>{d.license || "Not stated"}</dd>
            <dt>Files</dt>
            <dd>{d.file_count}</dd>
            {d.downloaded_at && (
              <>
                <dt>Added</dt>
                <dd>{new Date(d.downloaded_at).toLocaleString()}</dd>
              </>
            )}
            {href && (
              <>
                <dt>Source</dt>
                <dd><a href={href} target="_blank" rel="noopener noreferrer">Open source page</a></dd>
              </>
            )}
          </dl>

          {!active && (
            <div className="rcds-path" title="Path in notebook code">
              <span>{d.path}/</span>
              <Button variant="ghost" size="sm" className="rcds-iconbtn" title="Copy path" aria-label="Copy dataset path" onClick={() => copy("path", `${d.path}/`)}>
                {copied === "path" ? <Check size={13} /> : <Copy size={13} />}
              </Button>
            </div>
          )}

          {!active && files.length > 0 && (
            <div className="rcds-files">
              {files.map((f) => (
                <div className="rcds-file" key={f.path}><span title={f.path}>{f.path}</span><span>{fmtBytes(f.size)}</span></div>
              ))}
              {d.file_count > files.length && <div className="rcds-file more">and {d.file_count - files.length} more</div>}
            </div>
          )}

          {!active && !confirming && (
            <div className="rcds-actions">
              {d.status === "ready" && (
                <>
                  <Button variant="outline" size="sm" className="rcds-btn" title="Copy Python that loads this dataset with pandas" onClick={() => copy("code", loadCode(d))}>
                    {copied === "code" ? <Check size={13} /> : <Code2 size={13} />}{copied === "code" ? "Copied" : "Copy load code"}
                  </Button>
                  <Button variant="outline" size="sm" className="rcds-btn" title="Add this code as a new notebook cell" disabled={inserting} onClick={() => onInsert(d)}>
                    <FileCode2 size={13} />{inserting ? "Adding…" : "Insert code"}
                  </Button>
                </>
              )}
              <span style={{ flex: 1 }} />
              <Button variant="ghost" size="sm" className="rcds-btn danger" title="Delete this dataset" onClick={() => setConfirming(true)}><Trash2 size={13} />Delete</Button>
            </div>
          )}

          {confirming && (
            <div className="rcds-confirm">
              <span style={{ flex: 1 }}>Delete {d.name} and free {fmtBytes(d.size_bytes)}?</span>
              <Button variant="destructive" size="sm" className="rcds-btn" onClick={() => { setConfirming(false); onDelete(d.id); }}>Delete</Button>
              <Button variant="outline" size="sm" className="rcds-btn" onClick={() => setConfirming(false)}>Keep</Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

// Each push carries new objects, so compare the dataset by content
const same = (a: DatasetCardProps, b: DatasetCardProps) =>
  a.inserting === b.inserting && JSON.stringify(a.d) === JSON.stringify(b.d);

export const DatasetCard = memo(DatasetCardView, same);
