// Markdown for notes (AC15, SEC6 of the notebook plan; SEC1 here). Builds React
// elements only: raw HTML stays text, and links must be http(s).
import type { ReactNode } from "react";
import { safeHref } from "@/lib/safeHref";

const INLINE_RE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(_[^_\s][^_]*_)|(\[[^\]]+\]\([^)\s]+\))/g;

function inline(text: string, keyBase: number): ReactNode[] {
  const parts: ReactNode[] = [];
  let last = 0;
  let m: RegExpExecArray | null;
  INLINE_RE.lastIndex = 0;
  while ((m = INLINE_RE.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const t = m[0];
    const key = `${keyBase}-${m.index}`;
    if (m[1]) parts.push(<code key={key}>{t.slice(1, -1)}</code>);
    else if (m[2]) parts.push(<strong key={key}>{t.slice(2, -2)}</strong>);
    else if (m[3] || m[4]) parts.push(<em key={key}>{t.slice(1, -1)}</em>);
    else {
      const label = t.slice(1, t.indexOf("]("));
      const href = safeHref(t.slice(t.indexOf("](") + 2, -1));
      parts.push(href ? <a key={key} href={href} target="_blank" rel="noopener noreferrer">{label}</a> : t);
    }
    last = m.index + t.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

export function renderMarkdown(source: string): ReactNode {
  const lines = (source || "").split("\n");
  const blocks: ReactNode[] = [];
  const listRe = /^\s*([-*+]|\d+[.)])\s+(.*)$/;
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith("```")) {
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].trim().startsWith("```")) code.push(lines[i++]);
      i++;
      blocks.push(<pre key={`c${i}`}>{code.join("\n")}</pre>);
      continue;
    }
    const h = line.match(/^(#{1,6})\s+(.*)$/);
    if (h) {
      const Tag = h[1].length === 1 ? "h1" : h[1].length === 2 ? "h2" : "h3";
      blocks.push(<Tag key={`h${i}`}>{inline(h[2], i)}</Tag>);
      i++;
      continue;
    }
    if (listRe.test(line)) {
      const ordered = /^\s*\d/.test(line);
      const items: ReactNode[] = [];
      while (i < lines.length && listRe.test(lines[i])) {
        items.push(<li key={i}>{inline((lines[i].match(listRe) as RegExpMatchArray)[2], i)}</li>);
        i++;
      }
      blocks.push(ordered ? <ol key={`l${i}`}>{items}</ol> : <ul key={`l${i}`}>{items}</ul>);
      continue;
    }
    if (!line.trim()) {
      i++;
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```)/.test(lines[i]) && !listRe.test(lines[i])) para.push(lines[i++]);
    blocks.push(<p key={`p${i}`}>{inline(para.join(" "), i)}</p>);
  }
  return blocks.length ? blocks : <span className="rcnb-placeholder">Empty note. Click to write.</span>;
}
