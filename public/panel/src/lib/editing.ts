// Textarea editing helpers, ported unchanged from the old Notebook.jsx.
// Each returns [nextText, selectionStart, selectionEnd].
export type Edit = [string, number, number];

const INDENT = "    ";

function selectionLines(text: string, start: number, end: number): [number, number] {
  const first = text.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
  const at = text.indexOf("\n", end);
  return [first, at === -1 ? text.length : at];
}

export function indentSelection(text: string, start: number, end: number, outdent: boolean): Edit {
  const [first, last] = selectionLines(text, start, end);
  const lines = text.slice(first, last).split("\n");
  let delta = 0;
  let firstDelta = 0;
  const next = lines.map((line, i) => {
    if (outdent) {
      const hit = line.match(/^(\t| {1,4})/);
      if (!hit) return line;
      const d = -hit[1].length;
      if (i === 0) firstDelta = d;
      delta += d;
      return line.slice(hit[1].length);
    }
    if (i === 0) firstDelta = INDENT.length;
    delta += INDENT.length;
    return INDENT + line;
  }).join("\n");
  const nextText = text.slice(0, first) + next + text.slice(last);
  if (start === end && !outdent) {
    const pos = start + INDENT.length;
    return [nextText, pos, pos];
  }
  const nextStart = Math.max(first, start + firstDelta);
  const nextEnd = Math.max(nextStart, end + delta);
  return [nextText, nextStart, nextEnd];
}

export function autoIndent(text: string, start: number, end: number): Edit {
  const lineStart = text.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
  const before = text.slice(lineStart, start);
  const base = (before.match(/^\s*/) || [""])[0];
  const extra = /:\s*(#.*)?$/.test(before) ? INDENT : "";
  const insert = "\n" + base + extra;
  const next = text.slice(0, start) + insert + text.slice(end);
  const pos = start + insert.length;
  return [next, pos, pos];
}

export function toggleComment(text: string, start: number, end: number): Edit {
  const [first, last] = selectionLines(text, start, end);
  const lines = text.slice(first, last).split("\n");
  const live = lines.filter((line) => line.trim());
  if (!live.length) return [text, start, end];
  const commented = live.every((line) => /^\s*#/.test(line));
  let delta = 0;
  let firstDelta = 0;
  const next = lines.map((line, i) => {
    const ws = (line.match(/^\s*/) || [""])[0].length;
    if (!line.trim()) return line;
    if (commented) {
      const hit = line.slice(ws).match(/^# ?/);
      if (!hit) return line;
      const d = -hit[0].length;
      if (i === 0) firstDelta = d;
      delta += d;
      return line.slice(0, ws) + line.slice(ws + hit[0].length);
    }
    if (i === 0) firstDelta = 2;
    delta += 2;
    return line.slice(0, ws) + "# " + line.slice(ws);
  }).join("\n");
  const nextText = text.slice(0, first) + next + text.slice(last);
  return [nextText, Math.max(first, start + firstDelta), Math.max(first, end + delta)];
}
