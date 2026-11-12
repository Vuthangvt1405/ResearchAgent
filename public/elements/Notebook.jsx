// Notebook panel shown in the right sidebar (plan §4.1, §4.3), styled like a Notion page.
// props = NotebookProps from researchchat/workspace/service.py.
// Talks to the server only through callAction (nb_* actions). Uses Chainlit's own
// shadcn components, so it looks like the chat next to it.
import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Eraser, FastForward, GripVertical, Play, Plus, RotateCcw, Square, StickyNote, Trash2, Code2, Loader2, Database, ChevronRight, ChevronDown, X, Copy, Check, Search, MoreHorizontal, FileCode2, ChevronsUpDown, NotebookPen, AlertCircle, SearchX } from "lucide-react";
// Chainlit's own shadcn components (shadcn refresh plan §2.1). Every specifier and
// name here was checked against Chainlit's custom-element import map.
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuShortcut } from "@/components/ui/dropdown-menu";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

const SAVE_DELAY_MS = 600;

// Chainlit recompiles this file whenever props change, which remounts the
// component. Anything that must survive a push (unsaved text, which note is
// open, the cursor, an open menu) lives here on window instead of in React state.
const S = (window.__rcNotebook = window.__rcNotebook || {
  nb: null, // latest NotebookProps seen (from a push or an action reply)
  drafts: {}, // cell id -> unsaved text
  timers: {}, // cell id -> pending save
  editing: {}, // note id -> true while open for editing
  focus: null, // { id, start, end } of the focused text box
  menu: null, // cell id whose block menu is open
  projects: null, // { forProject, list }
  seen: null, // { project, ids: Set } of blocks already shown (only new ones animate in)
  outSeen: {}, // cell id -> number of outputs already shown
  outOpen: {}, // cell id -> true when a long output is expanded
  copied: null, // key of the button that just copied (shows a check)
  pendingSaves: 0, // edits waiting for the server
  savedAt: 0, // when the last edit finished saving
  find: "", // notebook search text
  findOpen: false, // search box shown
  findFocus: false,
  drag: null, // cell id being dragged
  drop: null, // { id, before } drop indicator
  busy: null, // name of the action in flight (disables its button)
  scroll: {}, // "project:tab" -> scrollTop, kept across props pushes
  lastRunning: null,
  overlay: null, // which Radix overlay is open: "menu:<cell id>" | "sort" | "project" (D4)
  overlayShown: null, // that overlay has been drawn once, so a remount skips its animation
  overlayItem: null, // data-rc-item of its highlighted item, refocused after a remount
  overlayByPointer: false, // it was closed by a click elsewhere (focus stays there)
  newProject: null, // name typed in the picker's "New project" field, or null
});

// True the first time a block id is drawn for this project (so it can animate in).
// Remounts after a push don't count as new.
function isNewBlock(projectId, id) {
  if (!S.seen || S.seen.project !== projectId) {
    S.seen = { project: projectId, ids: new Set(), first: true };
  }
  S.enterUntil = S.enterUntil || {};
  if (!S.seen.ids.has(id)) {
    S.seen.ids.add(id);
    // Stay "new" briefly, so a re-render right after doesn't cut the animation
    if (!S.seen.first) S.enterUntil[id] = Date.now() + 400;
  }
  return Date.now() < (S.enterUntil[id] || 0);
}

function newer(a, b) {
  // Prefer the higher version; on a tie the push (b) has the live outputs.
  // Datasets change apart from the notebook, so their list comes from
  // whichever side has the higher datasets_rev (NB-3, SEC16).
  if (!a || a.project.id !== b.project.id) return b;
  const base = a.version > b.version ? a : b;
  const other = base === a ? b : a;
  if ((other.datasets_rev || 0) > (base.datasets_rev || 0)) {
    return { ...base, datasets: other.datasets, datasets_rev: other.datasets_rev };
  }
  return base;
}

// The ElementSidebar owns the scroll container; find it so props pushes don't
// send the reader back to the top of the page.
function findScrollParent(el) {
  let node = el && el.parentElement;
  while (node) {
    const style = getComputedStyle(node);
    if (/(auto|scroll)/.test(style.overflowY) && node.scrollHeight > node.clientHeight) return node;
    node = node.parentElement;
  }
  return document.scrollingElement;
}

// Status dot colours follow the panel's light/dark tokens (AC8)
const KERNEL = {
  off: ["hsl(var(--muted-foreground))", "Kernel off · starts on first run"],
  starting: ["hsl(var(--rc-warn))", "Starting kernel…"],
  idle: ["hsl(var(--rc-ok))", "Ready"],
  busy: ["hsl(var(--rc-warn))", "Running…"],
  dead: ["hsl(var(--rc-danger))", "Kernel died"],
  unavailable: ["hsl(var(--rc-danger))", "Docker not running"],
};

// Notion-like canvas with Chainlit's shadcn chrome: its fonts, radius, borders,
// shadows and menus (shadcn refresh plan). Colours are theme variables, so light and
// dark mode both work. AC14: code and text outputs never wrap; they scroll sideways.
// Radix menus render in a portal on <body>, outside .rcnb, so the tokens and overlay
// rules below also target [data-rc-overlay].
const CSS = `
.rcnb, [data-rc-overlay] {
  /* Panel tokens (shadcn refresh plan §4.1, D5). Colours are HSL triplets like Chainlit's own. */
  --rc-radius: var(--radius); --rc-radius-sm: calc(var(--radius) - 4px);
  --rc-shadow: 0 1px 2px 0 rgb(0 0 0 / .05);
  --rc-shadow-lift: 0 4px 6px -1px rgb(0 0 0 / .1), 0 2px 4px -2px rgb(0 0 0 / .1);
  --rc-info: 199 89% 40%; --rc-warn: 30 95% 42%; --rc-ok: 168 72% 30%; --rc-danger: 0 72% 50%;
}
.dark .rcnb, .dark [data-rc-overlay] { --rc-info: 199 89% 62%; --rc-warn: 38 92% 60%; --rc-ok: 168 62% 48%; --rc-danger: 0 84% 66%; }
.rcnb { font-family: var(--font-sans); color: hsl(var(--foreground)); font-size: 14px; line-height: 1.6; min-height: 100%; display: flex; flex-direction: column; position: relative; container-type: inline-size; overflow: visible; }
.rcnb-page { padding: 20px 16px 16px; flex: 1; overflow-x: clip; }
.rcnb-titlebar { display: flex; align-items: flex-start; gap: 12px; margin: 0 0 14px; }
.rcnb-titleicon { flex: none; margin-top: 4px; color: hsl(var(--muted-foreground)); }
.rcnb-titlewrap { flex: 1; min-width: 0; }
.rcnb-eyebrow { font-size: 10px; font-weight: 700; letter-spacing: .09em; text-transform: uppercase; color: hsl(var(--muted-foreground)); line-height: 1.4; }
.rcnb-title { font-size: 24px; font-weight: 700; line-height: 1.2; margin: 0; word-break: break-word; }
.rcnb-titlebtn { display: inline-flex; align-items: center; gap: 6px; max-width: 100%; margin: 0 0 0 -6px; padding: 1px 6px; border: 0; border-radius: var(--rc-radius-sm); background: none; color: inherit; font: inherit; text-align: left; cursor: pointer; transition: background .12s ease; }
.rcnb-titlebtn:hover, .rcnb-titlebtn[data-state="open"] { background: hsl(var(--accent)); }
.rcnb-titletext { min-width: 0; overflow-wrap: anywhere; }
.rcnb-titlechev { flex: none; color: hsl(var(--muted-foreground)); }

/* Focus ring (AC12): looks like Chainlit's ring-2 ring-ring ring-offset-2, which is
   purged from its stylesheet, so it is written out here. */
.rcnb :is(button, a, input, [role="tab"]):focus-visible, .rcds-sort:focus-visible { outline: none; box-shadow: 0 0 0 2px hsl(var(--background)), 0 0 0 4px hsl(var(--ring)); }

/* Radix menus and selects (AC4-AC6, AC10, D4). Chainlit's classes draw the popover;
   these only size it for the panel. */
.rcnb-anchor { position: absolute; left: 2px; top: 26px; width: 24px; height: 0; pointer-events: none; }
.rcnb-mcontent { min-width: 210px; max-height: min(360px, var(--radix-dropdown-menu-content-available-height, 360px)); overflow-y: auto; font-family: var(--font-sans); }
.rcnb-mcontent .rcnb-mitem { padding-top: 6px; padding-bottom: 6px; cursor: pointer; }
.rcnb-mcontent .rcnb-mitem.danger { color: hsl(var(--rc-danger)); }
.rcnb-mcontent .rcnb-mitem.danger:focus { background: hsl(var(--rc-danger) / .1); color: hsl(var(--rc-danger)); }
.rcnb-mhead { padding: 6px 8px 4px; font-size: 11px; font-weight: 600; letter-spacing: .04em; text-transform: uppercase; color: hsl(var(--muted-foreground)); }
.rcnb-mspacer { width: 16px; flex: none; }
.rcnb-mlabel { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rcnb-projects { max-width: 320px; }
.rcnb-mnew { display: flex; gap: 6px; padding: 4px; }
.rcnb-mnew .rcnb-mnew-input { flex: 1; min-width: 0; height: 32px; padding: 0 8px; font-size: 13px; border-radius: var(--rc-radius-sm); }
.rcnb-mnew .rcnb-mnew-btn { height: 32px; padding: 0 12px; font-size: 13px; border-radius: var(--rc-radius-sm); }
.rcnb-mnew-input:focus-visible { outline: none; box-shadow: 0 0 0 2px hsl(var(--popover)), 0 0 0 4px hsl(var(--ring)); }
/* A push rebuilt this overlay: don't replay its entrance animation (D4) */
[data-rc-overlay][data-rc-reopen][data-state="open"] { animation: none !important; }
.rcnb-save { flex: none; display: inline-flex; align-items: center; gap: 4px; margin-top: 2px; color: hsl(var(--muted-foreground)); font-size: 11px; white-space: nowrap; }
.rcnb-save.saving { color: hsl(var(--rc-warn)); }
.rcnb-save .spin { animation: rcnb-spin .9s linear infinite; }
.rcnb-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.rcnb-sep { flex: 1; }

/* Tabs and the run/kernel toolbar stay visible while the notebook scrolls. */
.rcnb-head { position: sticky; top: 0; z-index: 30; margin: 0 -16px 12px; padding: 2px 16px 0; background: hsl(var(--card)); transition: box-shadow .15s ease; }
.rcnb-head.stuck { box-shadow: 0 1px 0 hsl(var(--border)), 0 7px 14px -10px rgba(0,0,0,.5); }
.rcnb-head::after { content: ""; position: absolute; left: 0; right: 0; bottom: -6px; height: 6px; background: linear-gradient(hsl(var(--card)), transparent); pointer-events: none; }
.rcnb-tabs { display: flex; gap: 4px; margin: 0 0 4px; border-bottom: 1px solid hsl(var(--border)); }
.rcnb-tab { display: inline-flex; align-items: center; gap: 6px; border: 0; background: none; color: hsl(var(--muted-foreground)); font: inherit; font-size: 13px; padding: 8px 10px; margin-bottom: -1px; border-bottom: 2px solid transparent; cursor: pointer; white-space: nowrap; }
.rcnb-tab:hover { color: hsl(var(--foreground)); }
.rcnb-tab.on { color: hsl(var(--foreground)); border-bottom-color: hsl(var(--foreground)); font-weight: 600; }
.rcnb-count { font-size: 11px; min-width: 18px; padding: 0 5px; border-radius: 9px; background: hsl(var(--accent)); text-align: center; font-weight: 500; line-height: 17px; }
.rcnb-count.live { background: hsl(var(--rc-info) / .15); color: hsl(var(--rc-info)); }
.rcnb-count.warn { background: hsl(var(--rc-danger) / .12); color: hsl(var(--rc-danger)); }

.rcnb-meta { display: flex; align-items: center; flex-wrap: nowrap; gap: 2px 6px; min-height: 38px; color: hsl(var(--muted-foreground)); font-size: 12px; }
.rcnb-status { display: inline-flex; align-items: center; min-width: 0; margin-right: 4px; }
.rcnb-statustext { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rcnb-meta .rcnb-sep { flex: 1 1 4px; }
.rcnb-act { display: inline-flex; align-items: center; gap: 4px; height: 26px; border: 0; background: none; color: inherit; font: inherit; font-size: 12px; font-weight: 400; padding: 0 7px; border-radius: var(--rc-radius-sm); cursor: pointer; white-space: nowrap; }
.rcnb-act svg { width: 13px; height: 13px; }
.rcnb-act:hover:not(:disabled) { background: hsl(var(--accent)); color: hsl(var(--foreground)); }
.rcnb-act:disabled { opacity: .4; cursor: default; }
.rcnb-act.primary { background: hsl(var(--foreground) / .07); color: hsl(var(--foreground)); font-weight: 500; }
.rcnb-act.primary:hover:not(:disabled) { background: hsl(var(--foreground) / .13); }
.rcnb-callout { margin: 0 0 12px; padding: 9px 11px; border-radius: 6px; background: hsl(var(--rc-danger) / .09); color: hsl(var(--rc-danger)); font-size: 13px; display: flex; gap: 8px; align-items: flex-start; }
.rcnb-callout svg { flex: none; margin-top: 2px; }
.rcnb-block { position: relative; display: flex; align-items: flex-start; padding: 4px 0; }
.rcnb-block.dragging { opacity: .4; }
.rcnb-block.drop-before::before, .rcnb-block.drop-after::after { content: ""; position: absolute; left: 28px; right: 2px; height: 2px; border-radius: 2px; background: hsl(var(--rc-info)); pointer-events: none; }
.rcnb-block.drop-before::before { top: -2px; }
.rcnb-block.drop-after::after { bottom: -2px; }
.rcnb-gutter { width: 28px; flex: none; display: flex; justify-content: center; padding-top: 6px; opacity: 0; transition: opacity .12s; }
.rcnb-block:hover .rcnb-gutter, .rcnb-block:focus-within .rcnb-gutter, .rcnb-gutter.open { opacity: 1; }
.rcnb-handle { border: 0; background: none; color: hsl(var(--muted-foreground)); cursor: grab; border-radius: 3px; padding: 1px; display: flex; }
.rcnb-handle:active { cursor: grabbing; }
.rcnb-handle:hover { background: hsl(var(--accent)); color: hsl(var(--foreground)); }
.rcnb-body { flex: 1; min-width: 0; }

/* Notion-style hover row between blocks: add a code cell or a note right there. */
.rcnb-insert { position: relative; height: 14px; margin-left: 28px; opacity: 0; transition: opacity .12s; }
.rcnb-block:hover + .rcnb-insert, .rcnb-insert:hover, .rcnb-insert:focus-within { opacity: 1; }
.rcnb-insert::before { content: ""; position: absolute; left: 0; right: 2px; top: 50%; height: 1px; background: hsl(var(--border)); }
.rcnb-insertbtns { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); display: flex; gap: 2px; padding: 0 4px; background: hsl(var(--card)); }
.rcnb-insertbtn { display: inline-flex; align-items: center; gap: 3px; border: 1px solid hsl(var(--border)); background: hsl(var(--card)); color: hsl(var(--muted-foreground)); font: inherit; font-size: 11px; line-height: 18px; padding: 0 6px; border-radius: 999px; cursor: pointer; white-space: nowrap; }
.rcnb-insertbtn:hover { background: hsl(var(--accent)); color: hsl(var(--foreground)); }

.rcnb-code { background: hsl(var(--muted) / .55); border: 1px solid hsl(var(--border)); border-radius: var(--rc-radius); box-shadow: var(--rc-shadow); position: relative; }
.rcnb-codehead { display: flex; align-items: center; gap: 8px; padding: 8px 10px 0 8px; font-size: 12px; color: hsl(var(--muted-foreground)); min-height: 30px; }
.rcnb-run { width: 23px; height: 23px; border-radius: 50%; border: 0; display: flex; align-items: center; justify-content: center; background: hsl(var(--foreground) / .08); color: hsl(var(--foreground)); cursor: pointer; flex: none; }
.rcnb-run:hover:not(:disabled) { background: hsl(var(--foreground) / .16); }
.rcnb-run:disabled { opacity: .4; cursor: default; }
.rcnb-mini { width: 22px; height: 22px; border: 0; border-radius: 4px; background: none; color: hsl(var(--muted-foreground)); display: inline-flex; align-items: center; justify-content: center; cursor: pointer; }
.rcnb-mini:hover { background: hsl(var(--foreground) / .08); color: hsl(var(--foreground)); }
.rcnb-mini.copied { color: hsl(var(--rc-ok)); }
.rcnb-count-run { font-family: var(--font-mono); font-size: 11px; }
.rcnb-tag { font-size: 11px; padding: 0 7px; line-height: 18px; border-color: transparent; }
.rcnb-tag.bad { background: hsl(var(--rc-danger) / .12); color: hsl(var(--rc-danger)); }
.rcnb-tag.wait { background: hsl(var(--rc-warn) / .12); color: hsl(var(--rc-warn)); }
.rcnb-lang { font-size: 11px; opacity: .8; }
.rcnb-src { display: block; width: 100%; resize: none; border: 0; outline: none; background: transparent; color: inherit; font-family: var(--font-mono); font-size: 13px; line-height: 1.55; padding: 8px 16px 14px; white-space: pre; overflow-x: auto; overflow-y: hidden; tab-size: 4; }
.rcnb-src:focus { box-shadow: inset 0 0 0 1px hsl(var(--ring) / .45); border-radius: 0 0 var(--rc-radius) var(--rc-radius); }
.rcnb-src::placeholder { color: hsl(var(--muted-foreground)); }
.rcnb-out { padding: 6px 4px 8px; }
.rcnb-out.collapsed { position: relative; max-height: 180px; overflow: hidden; }
.rcnb-out.collapsed::after { content: ""; position: absolute; left: 0; right: 0; bottom: 0; height: 56px; background: linear-gradient(transparent, hsl(var(--card))); pointer-events: none; }
.rcnb-outbar { display: flex; align-items: center; gap: 4px; padding: 1px 2px 2px; color: hsl(var(--muted-foreground)); font-size: 11px; }
.rcnb-outbar .rcnb-sep { flex: 1; }
.rcnb-pre { margin: 0; padding: 2px 4px; white-space: pre; overflow-x: auto; font-family: var(--font-mono); font-size: 12.5px; line-height: 1.5; }
.rcnb-pre.err { color: hsl(var(--rc-danger)); }
.rcnb-img { overflow-x: auto; padding: 4px 0; }
.rcnb-img img { max-width: none; border-radius: 4px; }
.rcnb-note { position: relative; padding: 3px 2px; min-height: 28px; cursor: text; border-radius: 3px; overflow-x: auto; }
.rcnb-note h1, .rcnb-note h2, .rcnb-note h3 { font-weight: 600; line-height: 1.3; margin: 10px 0 2px; }
.rcnb-note h1 { font-size: 22px; } .rcnb-note h2 { font-size: 18px; } .rcnb-note h3 { font-size: 15px; }
.rcnb-note p { margin: 2px 0; }
.rcnb-note ul { list-style: disc; padding-left: 22px; margin: 2px 0; }
.rcnb-note ol { list-style: decimal; padding-left: 22px; margin: 2px 0; }
.rcnb-note a { color: inherit; text-decoration: underline; text-decoration-color: hsl(var(--muted-foreground)); }
.rcnb-note code { font-family: var(--font-mono); font-size: 85%; color: hsl(var(--rc-danger)); background: hsl(var(--muted)); padding: 1px 4px; border-radius: 3px; }
.rcnb-note pre { background: hsl(var(--muted)); border-radius: 4px; padding: 10px 14px; white-space: pre; overflow-x: auto; font-family: var(--font-mono); font-size: 13px; }
.rcnb-note-edit { position: absolute; top: 2px; right: 2px; opacity: 0; transition: opacity .12s; }
.rcnb-note:hover .rcnb-note-edit, .rcnb-note-edit:focus-within { opacity: 1; }
.rcnb-placeholder { color: hsl(var(--muted-foreground)); }
.rcnb-notesrc { font-family: inherit; font-size: 14px; line-height: 1.6; padding: 3px 2px; white-space: pre-wrap; overflow-x: hidden; }
.rcnb-add { display: flex; flex-wrap: wrap; gap: 6px; margin: 14px 0 0 28px; color: hsl(var(--muted-foreground)); font-size: 13px; }
.rcnb-empty { margin: 6px 0 0; padding: 24px 16px; text-align: center; color: hsl(var(--muted-foreground)); border: 1px dashed hsl(var(--border)); border-radius: 8px; font-size: 13px; }
.rcnb-empty svg { opacity: .65; }
.rcnb-empty h3 { margin: 8px 0 2px; color: hsl(var(--foreground)); font-size: 15px; }
.rcnb-empty .rcnb-add { justify-content: center; margin: 12px 0 0; }

/* Find in notebook */
.rcnb-findbar { display: flex; align-items: center; gap: 6px; margin: 0 0 6px; padding: 4px 8px; border: 1px solid hsl(var(--border)); border-radius: 6px; color: hsl(var(--muted-foreground)); }
.rcnb-findbar:focus-within { border-color: hsl(var(--ring)); }
.rcnb-findbar input { flex: 1; min-width: 0; border: 0; outline: 0; background: none; color: hsl(var(--foreground)); font: inherit; font-size: 13px; }
.rcnb-findcount { font-size: 11px; white-space: nowrap; }
.rcnb-findempty { padding: 20px 10px; text-align: center; color: hsl(var(--muted-foreground)); font-size: 13px; }

.rcnb-code.rcnb-match { box-shadow: inset 0 0 0 1px hsl(var(--rc-info) / .4); }
.rcnb-code.rcnb-match .rcnb-codehead { color: hsl(var(--rc-info)); }
.rcnb-note.rcnb-match { background: hsl(var(--rc-info) / .07); box-shadow: inset 0 0 0 1px hsl(var(--rc-info) / .28); }
.rcnb-save.saved { color: hsl(var(--rc-ok)); }
.rcnb-save.dirty { color: hsl(var(--muted-foreground)); }
/* ---- motion ---- */
.rcnb-page.rcnb-first { animation: rcnb-fade .35s ease both; }
.rcnb-enter { animation: rcnb-in .32s cubic-bezier(.2,.8,.2,1) both; }
.rcnb-out-enter { animation: rcnb-in .25s ease both; }
.rcnb-code { overflow: hidden; transition: box-shadow .25s ease; }
.rcnb-code.running { animation: rcnb-glow 1.6s ease-in-out infinite; }
.rcnb-code.running::before { content: ""; position: absolute; top: 0; left: -40%; width: 40%; height: 2px; background: linear-gradient(90deg, transparent, hsl(var(--rc-warn)), transparent); animation: rcnb-scan 1.1s linear infinite; }
.rcnb-code.queued { box-shadow: inset 0 0 0 1px hsl(var(--rc-warn) / .35); }
.rcnb-run { transition: background .15s ease, transform .1s ease; }
.rcnb-run:active:not(:disabled) { transform: scale(.88); }
.rcnb-tag { animation: rcnb-pop .2s cubic-bezier(.2,.9,.3,1.3) both; }
.rcnb-dot { transition: background .3s ease; }
.rcnb-dot.pulse { animation: rcnb-pulse 1.3s ease-out infinite; }
.rcnb-callout { animation: rcnb-in .25s ease both; }
.rcnb-act { transition: background .12s ease, color .12s ease, transform .1s ease; }
.rcnb-act:active:not(:disabled) { transform: scale(.94); }
.rcnb-note, .rcnb-notesrc { animation: rcnb-fade .18s ease both; }
.rcnb-note { transition: background .12s ease, box-shadow .12s ease; }
.rcnb-note:hover { background: hsl(var(--accent) / .5); box-shadow: inset 2px 0 0 hsl(var(--border)); }
.rcnb-handle { transition: background .12s ease, transform .15s ease; }
.rcnb-gutter.open .rcnb-handle { transform: rotate(90deg); }
@keyframes rcnb-fade { from { opacity: 0 } to { opacity: 1 } }
@keyframes rcnb-in { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: none } }
@keyframes rcnb-pop { from { opacity: 0; transform: scale(.94) } to { opacity: 1; transform: none } }
@keyframes rcnb-scan { to { left: 100% } }
@keyframes rcnb-spin { to { transform: rotate(360deg) } }
@keyframes rcnb-glow { 0%, 100% { box-shadow: inset 0 0 0 1px hsl(var(--rc-warn) / .25) } 50% { box-shadow: inset 0 0 0 1px hsl(var(--rc-warn) / .7), 0 0 14px hsl(var(--rc-warn) / .18) } }
@keyframes rcnb-pulse { 0% { box-shadow: 0 0 0 0 currentColor } 100% { box-shadow: 0 0 0 6px transparent } }

/* Touch and narrow panels: keep the controls that matter, drop the words. */
@media (hover: none) {
  .rcnb-gutter { opacity: 1; }
  .rcnb-note-edit { opacity: 1; }
}
@container (max-width: 620px) {
  .rcnb-meta .rcnb-actlabel { display: none; }
  .rcnb-meta .rcnb-act.rcnb-runall .rcnb-actlabel { display: inline; }
  .rcnb-meta .rcnb-act { padding: 4px; }
  .rcnb-status { max-width: 150px; }
  .rcnb-meta .rcnb-sep { flex: 1 1 4px; }
}
@container (max-width: 380px) {
  .rcds-icon { display: none; }
  .rcds-error { padding-left: 0; }
  .rcnb-page { padding: 14px 10px 12px; }
  .rcnb-head { margin-left: -10px; margin-right: -10px; padding-left: 10px; padding-right: 10px; }
  .rcnb-title { font-size: 21px; }
  .rcnb-status { max-width: 92px; }
  .rcnb-actlabel, .rcnb-lang, .rcnb-meta .rcnb-act.rcnb-runall .rcnb-actlabel { display: none; }
  .rcnb-insert { margin-left: 20px; }
  .rcnb-block { padding-left: 22px; }
  .rcnb-gutter { width: 22px; margin-left: -22px; }
  .rcnb-empty .rcnb-add { margin-left: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .rcnb *, .rcnb *::before, [data-rc-overlay] { animation: none !important; transition: none !important; }
}
`;

async function call(name, payload) {
  const r = await callAction({ name, payload });
  return r && r.response !== undefined ? r.response : r;
}

// ---- Markdown for notes (AC15, SEC6) ---------------------------------------
// Builds React elements only: raw HTML stays text, links must be http(s).

const INLINE_RE = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\*[^*\s][^*]*\*)|(_[^_\s][^_]*_)|(\[[^\]]+\]\([^)\s]+\))/g;

function safeHref(url) {
  return /^https?:\/\//i.test(url) ? url : null;
}

function inline(text, keyBase) {
  const parts = [];
  let last = 0;
  let m;
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

function renderMarkdown(source) {
  const lines = (source || "").split("\n");
  const blocks = [];
  const listRe = /^\s*([-*+]|\d+[.)])\s+(.*)$/;
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim().startsWith("```")) {
      const code = [];
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
      const items = [];
      while (i < lines.length && listRe.test(lines[i])) {
        items.push(<li key={i}>{inline(lines[i].match(listRe)[2], i)}</li>);
        i++;
      }
      blocks.push(ordered ? <ol key={`l${i}`}>{items}</ol> : <ul key={`l${i}`}>{items}</ul>);
      continue;
    }
    if (!line.trim()) {
      i++;
      continue;
    }
    const para = [];
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```)/.test(lines[i]) && !listRe.test(lines[i])) para.push(lines[i++]);
    blocks.push(<p key={`p${i}`}>{inline(para.join(" "), i)}</p>);
  }
  return blocks.length ? blocks : <span className="rcnb-placeholder">Empty note. Click to write.</span>;
}

// ---- pieces ------------------------------------------------------------------

// Textarea editing helpers. Every change is controlled by React, so the caret
// is restored explicitly after the parent re-renders with the new value.
const INDENT = "    ";

function selectionLines(text, start, end) {
  const first = text.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
  const at = text.indexOf("\n", end);
  return [first, at === -1 ? text.length : at];
}

function indentSelection(text, start, end, outdent) {
  const [first, last] = selectionLines(text, start, end);
  const block = text.slice(first, last);
  const lines = block.split("\n");
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
  const collapsed = start === end;
  if (collapsed && !outdent) {
    const pos = start + INDENT.length;
    return [nextText, pos, pos];
  }
  const nextStart = Math.max(first, start + firstDelta);
  const nextEnd = Math.max(nextStart, end + delta);
  return [nextText, nextStart, nextEnd];
}

function autoIndent(text, start, end) {
  const lineStart = text.lastIndexOf("\n", Math.max(0, start - 1)) + 1;
  const before = text.slice(lineStart, start);
  const base = (before.match(/^\s*/) || [""])[0];
  const extra = /:\s*(#.*)?$/.test(before) ? INDENT : "";
  const insert = "\n" + base + extra;
  const next = text.slice(0, start) + insert + text.slice(end);
  const pos = start + insert.length;
  return [next, pos, pos];
}

function toggleComment(text, start, end) {
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

function SourceBox({ id, value, onChange, onShiftEnter, onBlur, onMove, autoFocus, placeholder, className, code }) {
  const rows = Math.max(1, value.split("\n").length);
  const ref = useRef(null);
  const mounted = useRef(true);
  const remember = (e) => (S.focus = { id, start: e.target.selectionStart, end: e.target.selectionEnd });
  const apply = (next, start, end) => {
    S.focus = { id, start, end };
    onChange(next);
    setTimeout(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(start, end);
    }, 0);
  };

  useEffect(() => {
    mounted.current = true;
    // Put the cursor back after a remount
    const saved = S.focus; // focus() below fires onFocus, which would overwrite it
    if (saved && saved.id === id && ref.current) {
      ref.current.focus();
      ref.current.setSelectionRange(saved.start, saved.end);
      S.focus = saved;
    } else if (autoFocus && ref.current) {
      ref.current.focus();
    }
    return () => {
      mounted.current = false;
    };
  }, []);

  return (
    <textarea
      ref={ref}
      className={className}
      value={value}
      rows={rows}
      wrap={className === "rcnb-src" ? "off" : "soft"}
      placeholder={placeholder}
      spellCheck={false}
      aria-label={code ? "Python code" : "Note text"}
      onChange={(e) => {
        remember(e);
        onChange(e.target.value);
      }}
      onFocus={remember}
      onSelect={remember}
      onBlur={() => {
        // A remount also blurs; only a blur that leaves us mounted is real
        setTimeout(() => {
          if (!mounted.current) return;
          if (S.focus && S.focus.id === id) S.focus = null;
          if (onBlur) onBlur();
        }, 0);
      }}
      onKeyDown={(e) => {
        const start = e.target.selectionStart;
        const end = e.target.selectionEnd;
        // Shift+Enter or Ctrl/Cmd+Enter runs a cell / finishes a note
        if (e.key === "Enter" && (e.shiftKey || e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          onShiftEnter();
          return;
        }
        if (e.key === "Escape" && onBlur) {
          e.target.blur();
          return;
        }
        if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown") && onMove) {
          e.preventDefault();
          onMove(e.key === "ArrowUp" ? "up" : "down");
          return;
        }
        if (!code) return;
        if (e.key === "Tab") {
          e.preventDefault();
          apply(...indentSelection(value, start, end, e.shiftKey));
          return;
        }
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          apply(...autoIndent(value, start, end));
          return;
        }
        if ((e.ctrlKey || e.metaKey) && e.key === "/") {
          e.preventDefault();
          apply(...toggleComment(value, start, end));
        }
      }}
    />
  );
}

function Output({ output }) {
  if (output.kind === "image") {
    return (
      <div className="rcnb-img">
        <img src={`data:image/png;base64,${output.image}`} alt="chart output" />
      </div>
    );
  }
  const err = output.kind === "error" || output.kind === "stderr";
  return <pre className={`rcnb-pre${err ? " err" : ""}`}>{output.text}</pre>;
}

function outputText(outputs) {
  return outputs.map((o) => (o.kind === "image" ? "[image output]" : o.text || "")).join("\n").trimEnd();
}

function outputSize(outputs) {
  return outputs.reduce((n, o) => n + (o.kind === "image" ? 400 : (o.text || "").length), 0) + outputs.length;
}

// ---- Radix overlays (AC4-AC6, D3, D4) -------------------------------------------
// A push remounts the whole panel, which rebuilds any open Radix overlay. Which
// overlay is open lives in S.overlay, so it stays open across the remount. A rebuilt
// overlay is marked data-rc-reopen so it skips its entrance animation, and keyboard
// focus goes back to the item that had it (restoreOverlayFocus), so a menu neither
// flickers nor loses its place while a cell runs.
function setOverlay(key) {
  if (S.overlay !== key) {
    S.overlay = key;
    S.overlayShown = null;
    S.overlayItem = null;
    S.overlayByPointer = false;
    S.newProject = null;
  }
}

function overlayProps(key) {
  return {
    "data-rc-overlay": key,
    "data-rc-reopen": S.overlayShown === key ? "" : undefined,
    ref: (el) => {
      if (el && S.overlay === key) S.overlayShown = key;
    },
    onFocus: (e) => {
      const item = e.target.getAttribute && e.target.getAttribute("data-rc-item");
      if (item) S.overlayItem = item;
    },
    // Radix moves the highlight on keys and hover; note it once it has moved
    onKeyDown: noteHighlight,
    onPointerMove: noteHighlight,
  };
}

function noteHighlight(e) {
  const el = e.currentTarget;
  setTimeout(() => {
    const active = el.contains(document.activeElement) && document.activeElement.closest("[data-rc-item]");
    const h = el.querySelector("[data-highlighted][data-rc-item]") || active;
    if (h) S.overlayItem = h.getAttribute("data-rc-item");
  }, 0);
}

function restoreOverlayFocus() {
  if (!S.overlay || !S.overlayItem) return;
  const sel = `[data-rc-overlay="${window.CSS.escape(S.overlay)}"] [data-rc-item="${window.CSS.escape(S.overlayItem)}"]`;
  setTimeout(() => {
    const el = document.querySelector(sel);
    if (el && document.activeElement !== el) el.focus();
  }, 0);
}

// Block actions (AC4). The handle stays a plain draggable button; the menu is
// anchored to an invisible span so pressing the handle can still start a drag.
function BlockMenu({ cell, actions, open, setMenu }) {
  const key = `menu:${cell.id}`;
  const item = (icon, label, fn, cls = "", keyHint = "") => (
    <DropdownMenuItem data-rc-item={label} className={`rcnb-mitem ${cls}`} onSelect={fn}>
      {icon}
      <span>{label}</span>
      {keyHint && <DropdownMenuShortcut>{keyHint}</DropdownMenuShortcut>}
    </DropdownMenuItem>
  );
  return (
    <DropdownMenu modal={false} open={open} onOpenChange={(o) => setMenu(o ? cell.id : null)}>
      <DropdownMenuTrigger asChild>
        <span className="rcnb-anchor" aria-hidden="true" tabIndex={-1} />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        {...overlayProps(key)}
        className="rcnb-mcontent"
        align="start"
        sideOffset={2}
        aria-label="Block actions"
        onInteractOutside={(e) => {
          // The handle and the ⋯ button toggle the menu themselves (pointer or focus)
          const t = e.target;
          if (t && t.closest && t.closest(`[data-rc-toggle="${window.CSS.escape(key)}"]`)) e.preventDefault();
        }}
        onPointerDownOutside={() => (S.overlayByPointer = true)}
        onCloseAutoFocus={(e) => {
          e.preventDefault();
          // Closed by keyboard or by picking an item: focus returns to the handle.
          // Not on a remount (S.overlay still set) or after a click elsewhere.
          if (S.overlay || S.overlayByPointer) return;
          const h = document.querySelector(`[data-cell-id="${window.CSS.escape(cell.id)}"] .rcnb-handle`);
          if (h) h.focus();
        }}
      >
        {item(<Code2 />, "Add code below", () => actions.add(cell.id, "code"))}
        {item(<StickyNote />, "Add note below", () => actions.add(cell.id, "markdown"))}
        <DropdownMenuSeparator />
        {item(<Copy />, "Duplicate", () => actions.duplicate(cell.id))}
        {item(<Copy />, cell.type === "code" ? "Copy code" : "Copy note", () => actions.copy(cell))}
        {cell.type === "code" && cell.outputs.length > 0 && item(<Eraser />, "Clear output", () => actions.clearOutputs(cell.id))}
        <DropdownMenuSeparator />
        {item(<ArrowUp />, "Move up", () => actions.move(cell.id, "up"), "", "Alt+↑")}
        {item(<ArrowDown />, "Move down", () => actions.move(cell.id, "down"), "", "Alt+↓")}
        <DropdownMenuSeparator />
        {item(<Trash2 />, "Delete", () => actions.remove(cell.id), "danger")}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Block({ cell, fresh, menuOpen, setMenu, actions, dragging, drop, onDragStart, onDragOver, onDrop, onDragEnd, children }) {
  const dropCls = drop && drop.id === cell.id && S.drag && S.drag !== cell.id ? (drop.before ? " drop-before" : " drop-after") : "";
  return (
    <div
      className={`rcnb-block${fresh ? " rcnb-enter" : ""}${S.drag === cell.id ? " dragging" : ""}${dropCls}`}
      data-cell-id={cell.id}
      onDragOver={(e) => onDragOver(e, cell)}
      onDrop={(e) => onDrop(e, cell)}
    >
      <div className={`rcnb-gutter${menuOpen ? " open" : ""}`}>
        <button
          className="rcnb-handle"
          title="Drag to reorder, or click for actions"
          aria-label="Block actions"
          aria-haspopup="menu"
          aria-expanded={menuOpen}
          data-rc-toggle={`menu:${cell.id}`}
          draggable
          onDragStart={(e) => onDragStart(e, cell)}
          onDragEnd={onDragEnd}
          onClick={() => setMenu(menuOpen ? null : cell.id)}
        >
          <GripVertical size={16} />
        </button>
      </div>
      <BlockMenu cell={cell} actions={actions} open={menuOpen} setMenu={setMenu} />
      <div className="rcnb-body">{children}</div>
    </div>
  );
}

function CodeCell({ cell, source, running, onChange, onRun, onCopy, copied, onMenu, canRun, actions }) {
  const label = cell.status === "queued" ? "…" : cell.execution_count ? cell.execution_count : " ";
  const tag = { error: ["Error", "bad"], interrupted: ["Interrupted", "bad"], timeout: ["Timed out", "bad"], queued: ["Queued", "wait"] }[cell.status];
  // Only outputs that weren't on screen before animate in (pushes remount everything)
  const shown = S.outSeen[cell.id] === undefined ? cell.outputs.length : Math.min(S.outSeen[cell.id], cell.outputs.length);
  S.outSeen[cell.id] = cell.outputs.length;
  const state = running ? " running" : cell.status === "queued" ? " queued" : "";
  const long = outputSize(cell.outputs) > 900;
  const open = !!S.outOpen[cell.id];
  const matches = S.findCount ? !!S.findMatch[cell.id] : false;
  return (
    <>
      <div className={`rcnb-code${state}${matches ? " rcnb-match" : ""}`}>
        <div className="rcnb-codehead">
          <button className="rcnb-run" title={canRun ? "Run (Shift+Enter or Ctrl+Enter)" : "Docker isn't running"} aria-label="Run cell" disabled={!canRun} onClick={onRun}>
            {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={12} fill="currentColor" />}
          </button>
          <span className="rcnb-count-run">[{running ? "*" : label}]</span>
          {tag && <Badge variant="outline" className={`rcnb-tag ${tag[1]}`}>{tag[0]}</Badge>}
          <span className="rcnb-sep" />
          <button className={`rcnb-mini${copied ? " copied" : ""}`} title="Copy code" aria-label="Copy code" onClick={() => onCopy(cell)}>
            {copied ? <Check size={13} /> : <Copy size={13} />}
          </button>
          <button className="rcnb-mini" title="More block actions" aria-label="More block actions" aria-haspopup="menu" data-rc-toggle={`menu:${cell.id}`} onClick={onMenu}>
            <MoreHorizontal size={15} />
          </button>
          <span className="rcnb-lang">Python</span>
        </div>
        <SourceBox id={cell.id} code className="rcnb-src" value={source} onChange={onChange} onShiftEnter={onRun} onMove={(dir) => actions.move(cell.id, dir)} placeholder="Write Python… Shift+Enter runs · Tab indents · Ctrl+/ comments" />
      </div>
      {cell.outputs.length > 0 && (
        <>
          {long && (
            <div className="rcnb-outbar">
              <span>{cell.outputs.length} output{cell.outputs.length === 1 ? "" : "s"}</span>
              <span className="rcnb-sep" />
              <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => { S.outOpen[cell.id] = !open; S.rerender && S.rerender(); }}>
                {open ? <ChevronDown size={13} /> : <ChevronsUpDown size={13} />}
                {open ? "Collapse" : "Show all"}
              </Button>
            </div>
          )}
          <div className={`rcnb-out${long && !open ? " collapsed" : ""}`}>
            {cell.outputs.map((o, i) => (
              <div key={i} className={i >= shown ? "rcnb-out-enter" : undefined}>
                <Output output={o} />
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function NoteCell({ id, source, onChange, onSave, match }) {
  // New and empty notes open ready to type; open notes stay open across remounts
  const [editing, setEditingState] = useState(!!S.editing[id] || !source);
  const setEditing = (on) => {
    if (on) S.editing[id] = true;
    else delete S.editing[id];
    setEditingState(on);
  };
  const finish = () => {
    setEditing(false);
    onSave();
  };
  if (editing) {
    return <SourceBox id={id} className="rcnb-src rcnb-notesrc" value={source} onChange={onChange} onShiftEnter={finish} onBlur={finish} autoFocus placeholder="Write a note… Markdown works. Shift+Enter or Ctrl+Enter finishes" />;
  }
  return (
    // Click to edit, like Notion; clicking a link opens the link instead
    <div className={`rcnb-note${match ? " rcnb-match" : ""}`} onClick={(e) => e.target.closest("a") || setEditing(true)}>
      {renderMarkdown(source)}
      <span className="rcnb-note-edit">
        <button className="rcnb-mini" title="Edit note" aria-label="Edit note" onClick={(e) => { e.stopPropagation(); setEditing(true); }}><Code2 size={13} /></button>
      </span>
    </div>
  );
}

function InsertRow({ afterId, actions }) {
  return (
    <div className="rcnb-insert" aria-hidden="false">
      <div className="rcnb-insertbtns">
        <button className="rcnb-insertbtn" title="Add a code cell here" onClick={() => actions.add(afterId, "code")}><Plus size={12} />Code</button>
        <button className="rcnb-insertbtn" title="Add a note here" onClick={() => actions.add(afterId, "markdown")}><Plus size={12} />Note</button>
      </div>
    </div>
  );
}

// ---- datasets tab (NB-3) ------------------------------------------------------------
// A manager for the project's datasets: totals, filter and sort, and one card per
// dataset. Downloading cards show progress, licence and Cancel; ready cards show
// size, files, the /work path, "Copy load code" and Delete (confirmed here first).
// Catalog text is rendered as React text only; links go through safeHref.

// Dataset styles. Cards, badges, buttons and the progress bar are Chainlit's shadcn
// components; these rules only size them for the narrow panel and add status colours.
const DS_CSS = `
.rcds { display: flex; flex-direction: column; gap: 10px; }
.rcds-summary { font-size: 12px; color: hsl(var(--muted-foreground)); }
.rcds-tools { display: flex; gap: 8px; margin-bottom: 2px; }
.rcds-search { position: relative; flex: 1; min-width: 0; color: hsl(var(--muted-foreground)); }
.rcds-search > svg { position: absolute; left: 10px; top: 50%; transform: translateY(-50%); pointer-events: none; }
.rcds-search .rcds-input { height: 34px; padding: 0 32px 0 30px; font-size: 13px; border-radius: var(--rc-radius-sm); }
.rcds-search .rcnb-mini { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); }
.rcds-sort { width: auto; height: 34px; gap: 4px; padding: 0 8px 0 12px; font-size: 12px; border-radius: var(--rc-radius-sm); flex: none; }
.rcds-sort svg { width: 14px !important; height: 14px !important; opacity: .6; }
/* Card: one compact row (icon, name, source · size, chevron); details open below */
.rcds-card { display: flex; flex-direction: column; gap: 10px; padding: 10px 10px 10px 12px; border-radius: var(--rc-radius); box-shadow: var(--rc-shadow); transition: box-shadow .15s ease, border-color .15s ease; animation: rcnb-in .25s ease both; }
.rcds-card:hover { box-shadow: var(--rc-shadow-lift); border-color: hsl(var(--foreground) / .18); }
.rcds-card.failed, .rcds-card.missing { border-color: hsl(var(--rc-danger) / .45); }
.rcds-row { display: flex; align-items: center; gap: 10px; min-width: 0; }
.rcds-icon { flex: none; width: 32px; height: 32px; display: flex; align-items: center; justify-content: center; border-radius: var(--rc-radius-sm); background: hsl(var(--muted)); color: hsl(var(--muted-foreground)); }
.rcds-head { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.rcds-name { font-weight: 600; font-size: 13.5px; line-height: 1.35; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rcds-meta { display: flex; align-items: center; gap: 6px; min-width: 0; font-size: 12px; line-height: 1.4; color: hsl(var(--muted-foreground)); white-space: nowrap; }
.rcds-meta .rcds-dot { opacity: .5; }
.rcds-size { font-variant-numeric: tabular-nums; }
.rcds-badge { padding: 0 8px; font-size: 11px; line-height: 20px; white-space: nowrap; flex: none; }
.rcds-badge.downloading { color: hsl(var(--rc-info)); background: hsl(var(--rc-info) / .12); border-color: transparent; }
.rcds-badge.queued { color: hsl(var(--rc-warn)); background: hsl(var(--rc-warn) / .12); border-color: transparent; }
.rcds-badge.failed, .rcds-badge.missing { color: hsl(var(--rc-danger)); background: hsl(var(--rc-danger) / .12); border-color: transparent; }
.rcds-iconbtn { flex: none; width: 30px; height: 30px; padding: 0; border-radius: var(--rc-radius-sm); color: hsl(var(--muted-foreground)); }
.rcds-iconbtn svg { width: 15px; height: 15px; }
.rcds-more svg { transition: transform .2s ease; }
.rcds-card.open .rcds-more svg { transform: rotate(180deg); }
.rcds-card.open .rcds-more { background: hsl(var(--accent)); color: hsl(var(--foreground)); }
.rcds-progress { height: 4px; background: hsl(var(--muted)); }
.rcds-progress > div { background: hsl(var(--rc-info)); transition: transform .4s ease; }
.rcds-error { font-size: 12px; color: hsl(var(--rc-danger)); padding-left: 42px; }
.rcds-details { display: flex; flex-direction: column; gap: 10px; margin: 0 -10px -10px -12px; padding: 12px; border-top: 1px solid hsl(var(--border)); animation: rcnb-in .2s ease both; }
.rcds-facts { display: grid; grid-template-columns: auto 1fr; gap: 4px 16px; margin: 0; font-size: 12px; }
.rcds-facts dt { color: hsl(var(--muted-foreground)); }
.rcds-facts dd { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.rcds-facts a { color: inherit; text-decoration: underline; text-underline-offset: 2px; text-decoration-color: hsl(var(--muted-foreground)); }
.rcds-path { display: flex; align-items: center; gap: 6px; height: 34px; padding: 0 2px 0 12px; border: 1px solid hsl(var(--border)); border-radius: var(--rc-radius-sm); background: hsl(var(--muted) / .45); font-family: var(--font-mono); font-size: 12px; }
.rcds-path span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rcds-files { display: flex; flex-direction: column; gap: 2px; max-height: 160px; overflow-y: auto; font-size: 12px; }
.rcds-file { display: flex; gap: 8px; padding: 2px 0; }
.rcds-file span:first-child { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-family: var(--font-mono); }
.rcds-file span:last-child, .rcds-file.more { color: hsl(var(--muted-foreground)); white-space: nowrap; }
.rcds-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.rcds-btn { height: 30px; padding: 0 10px; gap: 6px; font-size: 12px; border-radius: var(--rc-radius-sm); }
.rcds-btn svg { width: 13px; height: 13px; }
.rcds-btn.danger { color: hsl(var(--rc-danger)); }
.rcds-btn.danger:hover { color: hsl(var(--rc-danger)); background: hsl(var(--rc-danger) / .1); }
.rcds-confirm { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 10px; border-radius: var(--rc-radius-sm); background: hsl(var(--rc-danger) / .08); font-size: 12px; }
.rcds-empty { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 28px 16px; text-align: center; color: hsl(var(--muted-foreground)); font-size: 13px; border-radius: var(--rc-radius); box-shadow: var(--rc-shadow); }
.rcds-empty .rcds-btn { margin-top: 4px; }
.rcds a { color: inherit; text-underline-offset: 2px; }
`;

const DS_BADGE = { queued: "Queued", downloading: "Downloading", failed: "Failed", missing: "Files missing" };
const DS_SORTS = { newest: "Newest", name: "Name", size: "Size" };

function fmtBytes(n) {
  const units = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  let v = n || 0;
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000;
    i += 1;
  }
  return i === 0 ? `${v} B` : `${v.toFixed(1)} ${units[i]}`;
}

function ordinal(n) {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
}

const isActive = (d) => d.status === "downloading" || d.status === "queued";

// Python that loads the dataset's data files, for "Copy load code"
const READERS = [
  [/\.csv(\.gz)?$/i, (p) => `pd.read_csv(${p})`],
  [/\.tsv(\.gz)?$/i, (p) => `pd.read_csv(${p}, sep="\\t")`],
  [/\.parquet$/i, (p) => `pd.read_parquet(${p})`],
  [/\.jsonl$/i, (p) => `pd.read_json(${p}, lines=True)`],
  [/\.json$/i, (p) => `pd.read_json(${p})`],
  [/\.xlsx?$/i, (p) => `pd.read_excel(${p})`],
  [/\.feather$/i, (p) => `pd.read_feather(${p})`],
];

function loadCode(d) {
  const tables = [];
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

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (e) {
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

const SOURCES = { huggingface: "Hugging Face", zenodo: "Zenodo", kaggle: "Kaggle" };

// A dataset is one compact row: name, where it came from and its size. The chevron
// opens the details (licence, files, path in code, source page) and the actions.
function DatasetCard({ d, act, rerender, onInsert }) {
  const open = !!S.dsOpen[d.id];
  const confirming = S.dsConfirm === d.id;
  const active = isActive(d);
  const inserting = S.dsInserting === d.id;
  const pct = d.size_bytes ? Math.min(100, Math.round((100 * (d.done_bytes || 0)) / d.size_bytes)) : 0;
  const href = d.url ? safeHref(d.url) : null;
  const set = (fn) => {
    fn();
    rerender();
  };
  const copy = async (key, text) => {
    if (await copyText(text)) {
      set(() => (S.dsCopied = key));
      setTimeout(() => S.dsCopied === key && set(() => (S.dsCopied = null)), 1500);
    }
  };
  const copied = (key) => S.dsCopied === key;
  const files = d.files || [];
  const detailsId = `rcds-details-${d.id}`;
  return (
    <Card className={`rcds-card ${d.status}${open ? " open" : ""}`}>
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
          <Button variant="ghost" size="sm" className="rcds-iconbtn" title="Cancel download" aria-label="Cancel download" onClick={() => act("ds_cancel", d.id)}>
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
          onClick={() => set(() => (S.dsOpen[d.id] = !open))}
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
              <Button variant="ghost" size="sm" className="rcds-iconbtn" title="Copy path" aria-label="Copy dataset path" onClick={() => copy(`path:${d.id}`, `${d.path}/`)}>
                {copied(`path:${d.id}`) ? <Check size={13} /> : <Copy size={13} />}
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
                  <Button variant="outline" size="sm" className="rcds-btn" title="Copy Python that loads this dataset with pandas" onClick={() => copy(`code:${d.id}`, loadCode(d))}>
                    {copied(`code:${d.id}`) ? <Check size={13} /> : <Code2 size={13} />}{copied(`code:${d.id}`) ? "Copied" : "Copy load code"}
                  </Button>
                  <Button variant="outline" size="sm" className="rcds-btn" title="Add this code as a new notebook cell" disabled={inserting} onClick={() => onInsert(d)}>
                    <FileCode2 size={13} />{inserting ? "Adding…" : "Insert code"}
                  </Button>
                </>
              )}
              <span style={{ flex: 1 }} />
              <Button variant="ghost" size="sm" className="rcds-btn danger" title="Delete this dataset" onClick={() => set(() => (S.dsConfirm = d.id))}><Trash2 size={13} />Delete</Button>
            </div>
          )}

          {confirming && (
            <div className="rcds-confirm">
              <span style={{ flex: 1 }}>Delete {d.name} and free {fmtBytes(d.size_bytes)}?</span>
              <Button variant="destructive" size="sm" className="rcds-btn" onClick={() => { S.dsConfirm = null; act("ds_delete", d.id); }}>Delete</Button>
              <Button variant="outline" size="sm" className="rcds-btn" onClick={() => set(() => (S.dsConfirm = null))}>Keep</Button>
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

// Dataset sort (AC5): a shadcn Select instead of the browser's own dropdown.
// Select has no modal option; it behaves like Chainlit's own selects (§2.7).
function DatasetSortSelect() {
  const rerender = () => S.rerender && S.rerender();
  return (
    <Select
      value={S.dsSort}
      open={S.overlay === "sort"}
      onOpenChange={(o) => { setOverlay(o ? "sort" : null); rerender(); }}
      onValueChange={(v) => { S.dsSort = v; rerender(); }}
    >
      <SelectTrigger className="rcds-sort" title="Sort" aria-label="Sort datasets">
        <SelectValue />
      </SelectTrigger>
      <SelectContent {...overlayProps("sort")} className="rcnb-mcontent">
        {Object.entries(DS_SORTS).map(([k, label]) => (
          <SelectItem key={k} value={k} data-rc-item={k}>{label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function DatasetsTab({ datasets, apply, insertCode }) {
  S.dsOpen = S.dsOpen || {};
  S.dsSort = S.dsSort || "newest";
  const rerender = () => S.rerender && S.rerender();
  const act = async (name, id) => apply(await call(name, { dataset_id: id }));
  const search = useRef(null);

  useEffect(() => {
    // Pushes remount the panel; keep typing in the filter box
    if (S.dsFilterFocus && search.current) {
      const el = search.current;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  });

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
  const q = (S.dsFilter || "").trim().toLowerCase();
  const shown = datasets
    .filter((d) => !q || d.name.toLowerCase().includes(q) || d.id.includes(q) || (d.license || "").toLowerCase().includes(q))
    .sort((a, b) => {
      // Active downloads always first, then the chosen order
      if (isActive(a) !== isActive(b)) return isActive(a) ? -1 : 1;
      if (S.dsSort === "name") return a.name.localeCompare(b.name);
      if (S.dsSort === "size") return (b.size_bytes || 0) - (a.size_bytes || 0);
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
              value={S.dsFilter || ""}
              onChange={(e) => { S.dsFilter = e.target.value; rerender(); }}
              onFocus={() => (S.dsFilterFocus = true)}
              onBlur={() => (S.dsFilterFocus = false)}
              onKeyDown={(e) => { if (e.key === "Escape") { S.dsFilter = ""; rerender(); e.target.blur(); } }}
            />
            {!!S.dsFilter && (
              <button className="rcnb-mini" title="Clear filter" aria-label="Clear dataset filter" onClick={() => { S.dsFilter = ""; rerender(); search.current && search.current.focus(); }}>
                <X size={12} />
              </button>
            )}
          </label>
          <DatasetSortSelect />
        </div>
      )}
      {shown.map((d) => <DatasetCard key={d.id} d={d} act={act} rerender={rerender} onInsert={insertCode} />)}
      {!shown.length && (
        <Card className="rcds-empty">
          <SearchX size={18} style={{ opacity: .6 }} />
          <div>No dataset matches “{S.dsFilter}”.</div>
          <Button variant="outline" size="sm" className="rcds-btn" onClick={() => { S.dsFilter = ""; rerender(); }}>Clear filter</Button>
        </Card>
      )}
    </div>
  );
}

// Project picker in the panel header (AC6, D6). Same dropdown as the block menu.
// Switching and creating go through nb_switch_project / nb_create_project.
// Project names are React text only (SEC2).
function ProjectPicker({ name, projects, current, onOpen, onSwitch, onCreate }) {
  const key = "project";
  const rerender = () => S.rerender && S.rerender();
  return (
    <DropdownMenu
      modal={false}
      open={S.overlay === key}
      onOpenChange={(o) => {
        setOverlay(o ? key : null);
        if (o) onOpen();
        rerender();
      }}
    >
      <DropdownMenuTrigger asChild>
        <button className="rcnb-titlebtn" title="Switch project" aria-label={`Project ${name}, switch project`}>
          <span className="rcnb-titletext">{name}</span>
          <ChevronsUpDown size={16} className="rcnb-titlechev" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        {...overlayProps(key)}
        className="rcnb-mcontent rcnb-projects"
        align="start"
        sideOffset={4}
        aria-label="Projects"
        onCloseAutoFocus={(e) => S.overlay && e.preventDefault()}
      >
        <div className="rcnb-mhead">Projects</div>
        {!projects.length && <DropdownMenuItem disabled className="rcnb-mitem">Loading…</DropdownMenuItem>}
        {projects.map((p) => (
          <DropdownMenuItem key={p.id} data-rc-item={p.id} className="rcnb-mitem" onSelect={() => onSwitch(p.id)}>
            {p.id === current ? <Check /> : <span className="rcnb-mspacer" />}
            <span className="rcnb-mlabel">{p.name}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        {S.newProject == null ? (
          <DropdownMenuItem
            data-rc-item="__new"
            className="rcnb-mitem"
            onSelect={(e) => {
              // Turn the item into a name field in place; the menu stays open
              e.preventDefault();
              S.newProject = "";
              S.overlayItem = "__name";
              rerender();
            }}
          >
            <Plus />
            <span>New project…</span>
          </DropdownMenuItem>
        ) : (
          <form
            className="rcnb-mnew"
            onSubmit={(e) => {
              e.preventDefault();
              const n = S.newProject.trim();
              if (!n) return;
              setOverlay(null);
              rerender();
              onCreate(n);
            }}
          >
            <Input
              data-rc-item="__name"
              className="rcnb-mnew-input"
              value={S.newProject}
              maxLength={80}
              placeholder="Project name"
              aria-label="New project name"
              onChange={(e) => { S.newProject = e.target.value; rerender(); }}
              // Typing must not trigger the menu's type-to-select; Escape still closes it
              onKeyDown={(e) => e.key !== "Escape" && e.stopPropagation()}
            />
            <Button type="submit" size="sm" className="rcnb-mnew-btn" disabled={!S.newProject.trim()}>Create</Button>
          </form>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// ---- the panel -----------------------------------------------------------------

export default function Notebook() {
  // Re-render trigger; the data itself lives in S (see top of file)
  const [, setTick] = useState(0);
  const rerender = () => setTick((n) => n + 1);
  const rootRef = useRef(null);
  const findRef = useRef(null);

  S.nb = newer(S.nb, props);
  const nb = S.nb;
  const projects = S.projects && S.projects.forProject === nb.project.id ? S.projects.list : [];
  const tab = S.tab === "datasets" ? "datasets" : "notebook";
  const datasets = nb.datasets || [];
  const kernel = nb.kernel;
  const busy = kernel === "busy" || !!nb.running_cell_id;
  const [colour, status] = (busy ? KERNEL.busy : KERNEL[kernel]) || KERNEL.off;

  useEffect(() => {
    // Replies to actions started by an older (remounted) copy re-render this one
    S.rerender = rerender;
    const closeMenu = () => {
      if (S.overlay) {
        S.menu = null;
        setOverlay(null);
        rerender();
      }
    };
    const onKey = (e) => {
      if (e.key === "Escape") {
        closeMenu();
        if (S.findOpen && rootRef.current && rootRef.current.contains(document.activeElement)) {
          S.find = "";
          S.findOpen = false;
          rerender();
        }
        return;
      }
      const inside = rootRef.current && rootRef.current.contains(document.activeElement);
      const mod = e.ctrlKey || e.metaKey;
      if (inside && mod && !e.shiftKey && e.key.toLowerCase() === "s") {
        e.preventDefault();
        flushAll();
      }
      if (inside && mod && e.shiftKey && e.key === "Enter") {
        e.preventDefault();
        runAll();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      if (S.rerender === rerender) S.rerender = null;
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  // D4: after a remount, put focus back on the highlighted item of an open overlay
  useEffect(restoreOverlayFocus);

  const apply = (result) => {
    if (result && result.cells) {
      S.nb = newer(S.nb, result);
      if (result.error) S.nb = { ...S.nb, error: result.error };
      if (S.rerender) S.rerender();
    }
    return result;
  };

  // ---- editing and saving ----
  const sourceOf = (cell) => (S.drafts[cell.id] !== undefined ? S.drafts[cell.id] : cell.source);

  const save = async (cellId, text) => {
    clearTimeout(S.timers[cellId]);
    delete S.timers[cellId];
    S.pendingSaves += 1;
    rerender();
    const before = (S.nb.cells || []).find((c) => c.id === cellId);
    try {
      let result = await call("nb_update_cell", { version: S.nb.version, cell_id: cellId, source: text });
      // STALE because something else changed (e.g. a run finished): retry once
      // if this cell wasn't edited elsewhere.
      if (result && result.error && result.error.code === "STALE") {
        const server = (result.cells || []).find((c) => c.id === cellId);
        if (server && before && server.source === before.source) {
          result = await call("nb_update_cell", { version: result.version, cell_id: cellId, source: text });
        }
      }
      if (result && !result.error && S.drafts[cellId] === text) delete S.drafts[cellId];
      apply(result);
      return result;
    } catch (e) {
      return null;
    } finally {
      S.pendingSaves = Math.max(0, S.pendingSaves - 1);
      S.savedAt = Date.now();
      rerender();
    }
  };

  const edit = (cellId, text) => {
    S.drafts[cellId] = text;
    S.savedAt = 0;
    rerender();
    clearTimeout(S.timers[cellId]);
    S.timers[cellId] = setTimeout(() => save(cellId, text), SAVE_DELAY_MS);
  };

  const flush = async (cellId) => {
    if (S.drafts[cellId] !== undefined) return save(cellId, S.drafts[cellId]);
    return null;
  };

  const flushAll = async () => {
    for (const cellId of Object.keys(S.drafts)) await save(cellId, S.drafts[cellId]);
  };

  // ---- actions ----
  const run = async (cell) => {
    if (S.busy) return null;
    S.busy = `run:${cell.id}`;
    rerender();
    clearTimeout(S.timers[cell.id]);
    const text = sourceOf(cell);
    try {
      const result = await call("nb_run_cell", { version: S.nb.version, cell_id: cell.id, source: text });
      if (result && !result.error && S.drafts[cell.id] === text) delete S.drafts[cell.id];
      apply(result);
      return result;
    } finally {
      S.busy = null;
      rerender();
    }
  };

  const runAction = async (name, extra = {}) => {
    if (S.busy) return null;
    S.busy = name;
    rerender();
    try {
      const result = await call(name, { version: S.nb.version, ...extra });
      apply(result);
      return result;
    } finally {
      S.busy = null;
      rerender();
    }
  };

  const runAll = async () => {
    if (S.busy) return null;
    S.busy = "nb_run_all";
    rerender();
    try {
      await flushAll(); // Run-all should see what is on screen, not the last save
      const result = await call("nb_run_all", { version: S.nb.version });
      apply(result);
      return result;
    } finally {
      S.busy = null;
      rerender();
    }
  };

  const simple = async (name, extra = {}) => apply(await call(name, { version: S.nb.version, ...extra }));

  const add = async (afterId, type) => {
    const result = await call("nb_add_cell", { version: S.nb.version, after_id: afterId, type });
    if (result && result.cells && !result.error) {
      const i = afterId ? result.cells.findIndex((c) => c.id === afterId) + 1 : result.cells.length - 1;
      const cell = result.cells[i];
      if (cell) {
        if (type === "markdown") S.editing[cell.id] = true;
        else S.focus = { id: cell.id, start: 0, end: 0 };
      }
    }
    apply(result);
    return result;
  };

  const copyTo = async (key, text) => {
    if (!(await copyText(text))) return false;
    S.copied = key;
    rerender();
    setTimeout(() => {
      if (S.copied === key) {
        S.copied = null;
        rerender();
      }
    }, 1500);
    return true;
  };

  const copyCell = (cell) => copyTo(`cell:${cell.id}`, sourceOf(cell));

  const actions = {
    add,
    move: async (id, direction) => {
      await flush(id); // move the text the user sees, not the last saved version
      return simple("nb_move_cell", { cell_id: id, direction });
    },
    remove: (id) => simple("nb_delete_cell", { cell_id: id }),
    duplicate: async (id) => {
      await flush(id);
      return simple("nb_duplicate_cell", { cell_id: id });
    },
    copy: copyCell,
    clearOutputs: (id) => simple("nb_clear_cell_outputs", { cell_id: id }),
  };

  const setMenu = (id) => {
    S.menu = id;
    setOverlay(id ? `menu:${id}` : null);
    rerender();
  };

  // ---- projects ----
  const loadProjects = async () => {
    const r = await call("nb_list_projects", {});
    if (r && r.projects) {
      S.projects = { forProject: S.nb.project.id, list: r.projects };
      if (S.rerender) S.rerender();
    }
  };

  const switchProject = async (id) => {
    if (!id || id === S.nb.project.id) return;
    await flushAll();
    S.menu = null;
    setOverlay(null);
    S.find = "";
    S.findOpen = false;
    const result = await call("nb_switch_project", { project_id: id });
    if (result && result.error) apply(result);
  };
  const createProject = async (n) => {
    if (!n || !n.trim()) return;
    await flushAll();
    const result = await call("nb_create_project", { name: n.trim() });
    if (result && result.error) apply(result);
  };

  useEffect(() => {
    // Only ask the server when the project changed; otherwise reuse the list
    if (!projects.length) loadProjects();
  }, [nb.project.id]);

  // ---- dataset -> notebook bridge ----
  const insertDatasetCode = async (d) => {
    if (S.dsInserting) return;
    S.dsInserting = d.id;
    rerender();
    try {
      await flushAll();
      let result = await call("nb_add_cell", { version: S.nb.version, after_id: null, type: "code" });
      if (result && result.cells && !result.error) {
        const cell = result.cells[result.cells.length - 1];
        const updated = await call("nb_update_cell", { version: result.version, cell_id: cell.id, source: loadCode(d) });
        if (updated && updated.cells && !updated.error) {
          S.tab = "notebook";
          S.focus = { id: cell.id, start: 0, end: 0 };
          S.savedAt = Date.now();
        }
        result = updated || result;
      }
      apply(result);
    } finally {
      S.dsInserting = null;
      rerender();
    }
  };

  // ---- drag and drop ----
  const startDrag = (e, cell) => {
    S.drag = cell.id;
    S.drop = null;
    rerender();
    if (e.dataTransfer) {
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", cell.id); } catch (err) { /* older browsers */ }
    }
  };

  const overBlock = (e, cell) => {
    if (!S.drag || S.drag === cell.id) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
    const rect = e.currentTarget.getBoundingClientRect();
    const before = e.clientY < rect.top + rect.height / 2;
    if (!S.drop || S.drop.id !== cell.id || S.drop.before !== before) {
      S.drop = { id: cell.id, before };
      rerender();
    }
  };

  const endDrag = () => {
    if (S.drag || S.drop) {
      S.drag = null;
      S.drop = null;
      rerender();
    }
  };

  const dropOn = async (e, cell) => {
    e.preventDefault();
    e.stopPropagation();
    const dragId = S.drag;
    const drop = S.drop;
    S.drag = null;
    S.drop = null;
    rerender();
    if (!dragId || dragId === cell.id) return;
    let beforeId = cell.id;
    if (drop && drop.id === cell.id && !drop.before) {
      const i = S.nb.cells.findIndex((c) => c.id === cell.id);
      beforeId = S.nb.cells[i + 1] ? S.nb.cells[i + 1].id : null;
    }
    await runAction("nb_reorder_cell", { cell_id: dragId, before_id: beforeId });
  };

  // ---- view state ----
  const q = (S.find || "").trim().toLowerCase();
  const matches = (cell) => !q
    || cell.source.toLowerCase().includes(q)
    || (cell.outputs || []).some((o) => (o.text || "").toLowerCase().includes(q));
  const visible = nb.cells.filter((cell) => matches(cell) || (q && S.focus && S.focus.id === cell.id));
  S.findCount = q ? visible.length : 0;
  S.findMatch = {};
  if (q) for (const cell of visible) S.findMatch[cell.id] = true;

  const toggleFind = () => {
    S.findOpen = !S.findOpen;
    if (!S.findOpen) S.find = "";
    rerender();
    if (S.findOpen) setTimeout(() => findRef.current && findRef.current.focus(), 0);
  };

  useEffect(() => {
    // Put the cursor back in the find box after a live-output push remounts us
    if (S.findOpen && S.findFocus && findRef.current && document.activeElement !== findRef.current) {
      const el = findRef.current;
      el.focus();
      el.setSelectionRange(el.value.length, el.value.length);
    }
  });

  useEffect(() => {
    // Keep the reader's place across props pushes; remember it per tab.
    const el = findScrollParent(rootRef.current);
    if (!el) return undefined;
    const key = `${nb.project.id}:${tab}`;
    if (S.scroll[key] !== undefined) el.scrollTop = S.scroll[key];
    const sync = () => {
      S.scroll[key] = el.scrollTop;
      const stuck = el.scrollTop > 4;
      if (S.headStuck !== stuck) {
        S.headStuck = stuck;
        rerender();
      }
    };
    sync();
    el.addEventListener("scroll", sync, { passive: true });
    return () => el.removeEventListener("scroll", sync);
  }, [nb.project.id, tab, nb.cells.length]);

  useEffect(() => {
    // Bring a newly running cell into view, without jumping when it is already visible
    const rid = nb.running_cell_id;
    if (rid && rid !== S.lastRunning) {
      S.lastRunning = rid;
      const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const t = setTimeout(() => {
        const node = rootRef.current && rootRef.current.querySelector(`[data-cell-id="${rid}"]`);
        if (node) node.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
      }, 80);
      return () => clearTimeout(t);
    }
    if (!rid) S.lastRunning = null;
    return undefined;
  }, [nb.running_cell_id]);

  // The page fades in once per project; after that only new blocks animate
  if (!S.seen || S.seen.project !== nb.project.id) S.firstUntil = Date.now() + 400;
  const firstShow = Date.now() < (S.firstUntil || 0);
  useEffect(() => {
    if (S.seen) S.seen.first = false;
  });

  const problem = nb.error
    ? nb.error.message
    : kernel === "dead"
      ? "The kernel died (maybe out of memory). Press Restart."
      : kernel === "unavailable"
        ? "Docker isn't running: start Docker Desktop, then press Restart."
        : null;
  const errorKey = `${nb.project.id}:${nb.version}`;
  const showProblem = problem && (!nb.error || S.hideError !== errorKey);

  const drafts = Object.keys(S.drafts).length;
  const saveState = S.pendingSaves ? "saving" : drafts ? "dirty" : S.savedAt ? "saved" : "";

  const setTab = (next) => {
    if (next === tab) return;
    S.tab = next;
    rerender();
  };
  const onTabKey = (e) => {
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      setTab(tab === "notebook" ? "datasets" : "notebook");
    }
  };

  return (
    <div className="rcnb" ref={rootRef}>
      <style>{CSS}</style>
      <style>{DS_CSS}</style>
      <div className={`rcnb-page${firstShow ? " rcnb-first" : ""}`}>
        <div className="rcnb-titlebar">
          <NotebookPen className="rcnb-titleicon" size={20} />
          <div className="rcnb-titlewrap">
            <div className="rcnb-eyebrow">Project notebook</div>
            <h1 className="rcnb-title">
              <ProjectPicker
                name={nb.project.name}
                projects={projects}
                current={nb.project.id}
                onOpen={() => !projects.length && loadProjects()}
                onSwitch={switchProject}
                onCreate={(name) => createProject(name)}
              />
            </h1>
          </div>
          {saveState && (
            <span className={`rcnb-save ${saveState}`} aria-live="polite" title={saveState === "saving" ? "Saving your edits…" : saveState === "dirty" ? "Waiting to save" : "All changes saved"}>
              {saveState === "saving" ? <Loader2 size={12} className="spin" /> : saveState === "saved" ? <Check size={12} /> : <AlertCircle size={12} />}
              {saveState === "saving" ? "Saving…" : saveState === "saved" ? "Saved" : "Unsaved"}
            </span>
          )}
        </div>

        <div className={`rcnb-head${S.headStuck ? " stuck" : ""}`}>
          <div className="rcnb-tabs" role="tablist" aria-label="Notebook views" onKeyDown={onTabKey}>
            <button
              role="tab"
              id="rcnb-tab-notebook"
              aria-selected={tab === "notebook"}
              aria-controls="rcnb-view-notebook"
              className={`rcnb-tab${tab === "notebook" ? " on" : ""}`}
              onClick={() => setTab("notebook")}
            >
              <Code2 size={13} />Notebook
              {nb.cells.length > 0 && <span className="rcnb-count">{nb.cells.length}</span>}
            </button>
            <button
              role="tab"
              id="rcnb-tab-datasets"
              aria-selected={tab === "datasets"}
              aria-controls="rcnb-view-datasets"
              className={`rcnb-tab${tab === "datasets" ? " on" : ""}`}
              onClick={() => setTab("datasets")}
            >
              <Database size={13} />Datasets
              {datasets.length > 0 && <span className={`rcnb-count${datasets.some(isActive) ? " live" : datasets.some((d) => d.status === "failed" || d.status === "missing") ? " warn" : ""}`}>{datasets.length}</span>}
            </button>
          </div>

          {tab === "notebook" && (
            <div className="rcnb-meta" role="toolbar" aria-label="Notebook actions">
              <span className="rcnb-status" aria-live="polite" title={status}>
                <span className={`rcnb-dot${busy || kernel === "starting" ? " pulse" : ""}`} style={{ background: colour, color: colour }} />
                <span className="rcnb-statustext">{status}</span>
              </span>
              <span className="rcnb-sep" />
              <Button variant="ghost" size="sm" className="rcnb-act primary rcnb-runall" title="Run all code blocks (Ctrl+Shift+Enter)" aria-label="Run all" disabled={!!S.busy} onClick={runAll}>
                {S.busy === "nb_run_all" ? <Loader2 size={13} className="spin" /> : <FastForward size={13} />}
                <span className="rcnb-actlabel">Run all</span>
              </Button>
              <Button variant="ghost" size="sm" className="rcnb-act" title="Stop the running block" aria-label="Stop" disabled={!busy} onClick={() => runAction("nb_interrupt")}>
                <Square size={12} /><span className="rcnb-actlabel">Stop</span>
              </Button>
              <Button variant="ghost" size="sm" className="rcnb-act" title="Restart kernel (clears variables, keeps cells)" aria-label="Restart kernel" disabled={!!S.busy} onClick={() => runAction("nb_restart")}>
                <RotateCcw size={13} /><span className="rcnb-actlabel">Restart</span>
              </Button>
              <Button variant="ghost" size="sm" className="rcnb-act" title="Clear all outputs" aria-label="Clear all outputs" disabled={!!S.busy} onClick={() => runAction("nb_clear_outputs")}>
                <Eraser size={13} /><span className="rcnb-actlabel">Clear</span>
              </Button>
              <Button variant="ghost" size="sm" className={`rcnb-act${S.findOpen ? " primary" : ""}`} title="Find in cells and outputs" aria-label="Find" aria-expanded={S.findOpen} onClick={toggleFind}>
                <Search size={13} /><span className="rcnb-actlabel">Find</span>
              </Button>
            </div>
          )}

          {tab === "notebook" && S.findOpen && (
            <label className="rcnb-findbar">
              <Search size={13} />
              <input
                ref={findRef}
                value={S.find || ""}
                placeholder="Find in cells and outputs"
                aria-label="Find in notebook"
                onChange={(e) => { S.find = e.target.value; rerender(); }}
                onFocus={() => (S.findFocus = true)}
                onBlur={() => (S.findFocus = false)}
                onKeyDown={(e) => {
                  if (e.key === "Escape") {
                    S.find = "";
                    S.findOpen = false;
                    rerender();
                    e.target.blur();
                  }
                }}
              />
              {q && <span className="rcnb-findcount">{S.findCount} of {nb.cells.length}</span>}
              {!!S.find && (
                <button className="rcnb-mini" title="Clear search" aria-label="Clear search" onClick={() => { S.find = ""; rerender(); findRef.current && findRef.current.focus(); }}>
                  <X size={12} />
                </button>
              )}
            </label>
          )}
        </div>

        {tab === "datasets" ? (
          <div role="tabpanel" id="rcnb-view-datasets" aria-labelledby="rcnb-tab-datasets">
            {showProblem && (
              <div className="rcnb-callout" role="alert">
                <AlertCircle size={15} />
                <span style={{ flex: 1 }}>{problem}</span>
                {nb.error && (
                  <button className="rcnb-mini" title="Dismiss" aria-label="Dismiss error" onClick={() => { S.hideError = errorKey; rerender(); }}>
                    <X size={13} />
                  </button>
                )}
              </div>
            )}
            <DatasetsTab datasets={datasets} apply={apply} insertCode={insertDatasetCode} />
          </div>
        ) : (
          <div role="tabpanel" id="rcnb-view-notebook" aria-labelledby="rcnb-tab-notebook">
            {showProblem && (
              <div className="rcnb-callout" role="alert">
                <AlertCircle size={15} />
                <span style={{ flex: 1 }}>{problem}</span>
                {nb.error && (
                  <button className="rcnb-mini" title="Dismiss" aria-label="Dismiss error" onClick={() => { S.hideError = errorKey; rerender(); }}>
                    <X size={13} />
                  </button>
                )}
              </div>
            )}

            {!nb.cells.length && !q && (
              <div className="rcnb-empty">
                <NotebookPen size={24} />
                <h3>Start your notebook</h3>
                <div>Run Python in this project's own kernel, and keep notes beside it.</div>
                <div className="rcnb-add">
                  <Button variant="ghost" size="sm" className="rcnb-act primary" onClick={() => add(null, "code")}><Plus size={14} />Code block</Button>
                  <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => add(null, "markdown")}><StickyNote size={14} />Note</Button>
                </div>
              </div>
            )}

            {visible.map((cell) => (
              <div key={cell.id}>
                <Block
                  cell={cell}
                  fresh={isNewBlock(nb.project.id, cell.id)}
                  menuOpen={S.menu === cell.id}
                  setMenu={setMenu}
                  actions={actions}
                  dragging={S.drag}
                  drop={S.drop}
                  onDragStart={startDrag}
                  onDragOver={overBlock}
                  onDrop={dropOn}
                  onDragEnd={endDrag}
                >
                  {cell.type === "markdown" ? (
                    <NoteCell
                      id={cell.id}
                      source={sourceOf(cell)}
                      match={!!S.findMatch[cell.id]}
                      onChange={(t) => edit(cell.id, t)}
                      onSave={() => flush(cell.id)}
                    />
                  ) : (
                    <CodeCell
                      cell={cell}
                      source={sourceOf(cell)}
                      running={cell.id === nb.running_cell_id}
                      onChange={(t) => edit(cell.id, t)}
                      onRun={() => run(cell)}
                      onCopy={copyCell}
                      copied={S.copied === `cell:${cell.id}`}
                      onMenu={() => setMenu(S.menu === cell.id ? null : cell.id)}
                      canRun={kernel !== "unavailable" && !S.busy}
                      actions={actions}
                    />
                  )}
                </Block>
                {!q && <InsertRow afterId={cell.id} actions={actions} />}
              </div>
            ))}

            {q && !visible.length && (
              <div className="rcnb-findempty">
                <SearchX size={18} style={{ opacity: .6 }} />
                <div style={{ marginTop: 6 }}>No cell matches “{S.find}”.</div>
                <Button variant="ghost" size="sm" className="rcnb-act" style={{ marginTop: 6 }} onClick={() => { S.find = ""; rerender(); findRef.current && findRef.current.focus(); }}>Clear search</Button>
              </div>
            )}

            {!q && (
              <div className="rcnb-add">
                <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => add(null, "code")}><Plus size={14} />Code</Button>
                <Button variant="ghost" size="sm" className="rcnb-act" onClick={() => add(null, "markdown")}><Plus size={14} />Note</Button>
              </div>
            )}
          </div>
        )}
      </div>

    </div>
  );
}
