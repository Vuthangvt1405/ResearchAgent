// The Python a dataset card copies or inserts to load the dataset's data files.
import type { DatasetProps } from "@/panel/types";

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

/** Load a created file straight from its /work path (d.path is the file, not a folder) */
export function createdLoadCode(d: DatasetProps): string {
  const reader = READERS.find(([re]) => re.test(d.path));
  // JSON.stringify gives a valid Python string literal, so a file name can never become code
  const quotedPath = JSON.stringify(d.path);
  if (!reader) return `print(open(${quotedPath}).read(2000))\n`;
  return ["import pandas as pd", "", `df = ${reader[1](quotedPath)}`, "df.head()"].join("\n") + "\n";
}

export function loadCode(d: DatasetProps): string {
  if (d.origin === "created") return createdLoadCode(d);
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
