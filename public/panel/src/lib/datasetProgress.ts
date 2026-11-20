// Where a dataset's download stands.
import type { DatasetProps } from "@/types";

export const isActive = (d: DatasetProps) => d.status === "downloading" || d.status === "queued";

/** Percent for the progress bar; 0 when the size is 0 or unknown */
export function percent(d: DatasetProps): number {
  return d.size_bytes ? Math.min(100, Math.round((100 * (d.done_bytes || 0)) / d.size_bytes)) : 0;
}
