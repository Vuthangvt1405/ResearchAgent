// Dataset helpers, ported unchanged from the old Notebook.jsx.
import type { DatasetProps } from "@/types";

export function fmtBytes(n: number | null | undefined): string {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n || 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i += 1;
  }
  return i === 0 ? `${v} B` : `${v.toFixed(1)} ${units[i]}`;
}

export function ordinal(n: number): string {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

export const isActive = (d: DatasetProps) => d.status === "downloading" || d.status === "queued";

/** Percent for the progress bar; 0 when the size is 0 or unknown (G3❌1) */
export function percent(d: DatasetProps): number {
  return d.size_bytes ? Math.min(100, Math.round((100 * (d.done_bytes || 0)) / d.size_bytes)) : 0;
}

// Python that loads the dataset's data files, for "Copy load code"
const READERS: [RegExp, (p: string) => string][] = [
  [/\.csv(\.gz)?$/i, (p) => `pd.read_csv(${p})`],
  [/\.tsv(\.gz)?$/i, (p) => `pd.read_csv(${p}, sep="\\t")`],
  [/\.parquet$/i, (p) => `pd.read_parquet(${p})`],
  [/\.jsonl$/i, (p) => `pd.read_json(${p}, lines=True)`],
  [/\.json$/i, (p) => `pd.read_json(${p})`],
  [/\.xlsx?$/i, (p) => `pd.read_excel(${p})`],
  [/\.feather$/i, (p) => `pd.read_feather(${p})`],
];

export function loadCode(d: DatasetProps): string {
  const tables: [string, (p: string) => string][] = [];
  for (const f of d.files || []) {
    const reader = READERS.find(([re]) => re.test(f.path));
    if (reader) tables.push([f.path, reader[1]]);
  }
  if (!tables.length) {
    return `import os\n\nfolder = "${d.path}"\nprint(sorted(os.listdir(folder)))\n`;
  }
  const lines = ["import pandas as pd", ""];
  tables.slice(0, 5).forEach(([path, read], i) => {
    lines.push(`${i === 0 ? "df" : `df${i + 1}`} = ${read(JSON.stringify(`${d.path}/${path}`))}`);
  });
  if (tables.length > 5) lines.push(`# ${tables.length - 5} more data files in ${d.path}/`);
  lines.push("df.head()");
  return lines.join("\n") + "\n";
}

export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    // Fallback for browsers that block the clipboard API
    const area = document.createElement("textarea");
    area.value = text;
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  }
}
