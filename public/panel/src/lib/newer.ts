import type { NotebookProps } from "@/types";

/**
 * Port of newer() in the old Notebook.jsx. Prefer the higher version; on a tie the
 * incoming one (b) has the live outputs. Datasets change apart from the notebook, so
 * their list comes from whichever side has the higher datasets_rev (NB-3, SEC16).
 */
export function newer(a: NotebookProps | null, b: NotebookProps): NotebookProps {
  if (!a || a.project.id !== b.project.id) return b;
  const base = a.version > b.version ? a : b;
  const other = base === a ? b : a;
  if ((other.datasets_rev || 0) > (base.datasets_rev || 0)) {
    return { ...base, datasets: other.datasets, datasets_rev: other.datasets_rev };
  }
  return base;
}
