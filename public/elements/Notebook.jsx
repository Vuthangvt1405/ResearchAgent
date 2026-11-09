// Notebook panel shown in the right sidebar (plan §4.1, §4.3), styled like a Notion page.
// props = NotebookProps from researchchat/workspace/service.py.
// Talks to the server only through callAction (nb_* actions), and to the
// project bar (public/custom.js) through window events.
import { useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Eraser, FastForward, GripVertical, Play, Plus, RotateCcw, Square, StickyNote, Trash2, Code2, Loader2 } from "lucide-react";

// Events shared with public/custom.js
const EVENT_SWITCH = "rc:switch-project"; // bar -> panel: { project_id }
const EVENT_CREATE = "rc:create-project"; // bar -> panel: { name }
const EVENT_PROJECTS = "rc:projects"; // panel -> bar: { projects, current }
const EVENT_REQUEST = "rc:projects-request"; // bar -> panel: please send EVENT_PROJECTS

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
  fallbackBar: null, // true when custom.js couldn't place the bar
  seen: null, // { project, ids: Set } of blocks already shown (only new ones animate in)
  outSeen: {}, // cell id -> number of outputs already shown
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
  // Prefer the higher version; on a tie the push (b) has the live outputs
  if (!a || a.project.id !== b.project.id) return b;
  return a.version > b.version ? a : b;
}

const KERNEL = {
  off: ["#9b9a97", "Kernel off · starts on first run"],
  starting: ["#d9730d", "Starting kernel…"],
  idle: ["#0f7b6c", "Ready"],
  busy: ["#d9730d", "Running…"],
  dead: ["#e03e3e", "Kernel died"],
  unavailable: ["#e03e3e", "Docker not running"],
};

// Notion-like look. Colours come from Chainlit's theme variables so light and
// dark mode both work. AC14: code and text outputs never wrap; they scroll sideways.
const CSS = `
.rcnb { font-family: ui-sans-serif, -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: hsl(var(--foreground)); font-size: 14px; line-height: 1.6; overflow-x: hidden; min-height: 100%; display: flex; flex-direction: column; }
.rcnb-page { padding: 20px 12px 12px 4px; flex: 1; }
.rcnb-title { font-size: 26px; font-weight: 700; line-height: 1.2; margin: 0 0 6px 28px; word-break: break-word; }
.rcnb-meta { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; margin: 0 0 14px 28px; color: hsl(var(--muted-foreground)); font-size: 12px; }
.rcnb-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; margin-right: 6px; }
.rcnb-act { display: inline-flex; align-items: center; gap: 4px; border: 0; background: none; color: inherit; font: inherit; padding: 2px 6px; border-radius: 4px; cursor: pointer; }
.rcnb-act:hover:not(:disabled) { background: hsl(var(--accent)); color: hsl(var(--foreground)); }
.rcnb-act:disabled { opacity: .4; cursor: default; }
.rcnb-sep { flex: 1; }
.rcnb-callout { margin: 0 0 12px 28px; padding: 10px 12px; border-radius: 4px; background: rgba(224, 62, 62, .09); font-size: 13px; display: flex; gap: 8px; }
.rcnb-block { position: relative; display: flex; align-items: flex-start; padding: 2px 0; }
.rcnb-gutter { width: 28px; flex: none; display: flex; justify-content: center; padding-top: 6px; opacity: 0; transition: opacity .12s; }
.rcnb-block:hover .rcnb-gutter, .rcnb-gutter.open { opacity: 1; }
.rcnb-handle { border: 0; background: none; color: hsl(var(--muted-foreground)); cursor: pointer; border-radius: 3px; padding: 1px; display: flex; }
.rcnb-handle:hover { background: hsl(var(--accent)); }
.rcnb-body { flex: 1; min-width: 0; }
.rcnb-menu { position: absolute; left: 26px; top: 26px; z-index: 20; min-width: 190px; padding: 4px; border-radius: 6px; background: hsl(var(--popover)); color: hsl(var(--popover-foreground)); box-shadow: 0 0 0 1px rgba(15,15,15,.05), 0 3px 6px rgba(15,15,15,.1), 0 9px 24px rgba(15,15,15,.2); }
.rcnb-item { display: flex; width: 100%; align-items: center; gap: 8px; border: 0; background: none; color: inherit; font: inherit; font-size: 13px; padding: 5px 8px; border-radius: 4px; cursor: pointer; text-align: left; }
.rcnb-item:hover { background: hsl(var(--accent)); }
.rcnb-item.danger { color: #e03e3e; }
.rcnb-rule { height: 1px; background: hsl(var(--border)); margin: 4px 0; }
.rcnb-code { background: hsl(var(--muted)); border-radius: 4px; position: relative; }
.rcnb-codehead { display: flex; align-items: center; gap: 6px; padding: 6px 8px 0 6px; font-size: 12px; color: hsl(var(--muted-foreground)); }
.rcnb-run { width: 22px; height: 22px; border-radius: 50%; border: 0; display: flex; align-items: center; justify-content: center; background: hsl(var(--foreground) / .08); color: hsl(var(--foreground)); cursor: pointer; }
.rcnb-run:hover { background: hsl(var(--foreground) / .16); }
.rcnb-count { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 11px; }
.rcnb-tag { font-size: 11px; padding: 0 6px; border-radius: 3px; }
.rcnb-tag.bad { background: rgba(224, 62, 62, .12); color: #e03e3e; }
.rcnb-tag.wait { background: rgba(217, 115, 13, .12); color: #d9730d; }
.rcnb-src { display: block; width: 100%; resize: none; border: 0; outline: none; background: transparent; color: inherit; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; line-height: 1.55; padding: 6px 14px 12px; white-space: pre; overflow-x: auto; overflow-y: hidden; }
.rcnb-src::placeholder { color: hsl(var(--muted-foreground)); }
.rcnb-out { padding: 4px 2px 6px; }
.rcnb-pre { margin: 0; padding: 2px 4px; white-space: pre; overflow-x: auto; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12.5px; line-height: 1.5; }
.rcnb-pre.err { color: #e03e3e; }
.rcnb-img { overflow-x: auto; padding: 4px 0; }
.rcnb-img img { max-width: none; border-radius: 4px; }
.rcnb-note { padding: 3px 2px; min-height: 28px; cursor: text; border-radius: 3px; overflow-x: auto; }
.rcnb-note h1, .rcnb-note h2, .rcnb-note h3 { font-weight: 600; line-height: 1.3; margin: 10px 0 2px; }
.rcnb-note h1 { font-size: 22px; } .rcnb-note h2 { font-size: 18px; } .rcnb-note h3 { font-size: 15px; }
.rcnb-note p { margin: 2px 0; }
.rcnb-note ul { list-style: disc; padding-left: 22px; margin: 2px 0; }
.rcnb-note ol { list-style: decimal; padding-left: 22px; margin: 2px 0; }
.rcnb-note a { color: inherit; text-decoration: underline; text-decoration-color: hsl(var(--muted-foreground)); }
.rcnb-note code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 85%; color: #eb5757; background: hsl(var(--muted)); padding: 1px 4px; border-radius: 3px; }
.rcnb-note pre { background: hsl(var(--muted)); border-radius: 4px; padding: 10px 14px; white-space: pre; overflow-x: auto; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 13px; }
.rcnb-placeholder { color: hsl(var(--muted-foreground)); }
.rcnb-notesrc { font-family: inherit; font-size: 14px; line-height: 1.6; padding: 3px 2px; white-space: pre-wrap; overflow-x: hidden; }
.rcnb-add { display: flex; gap: 2px; margin: 8px 0 0 28px; color: hsl(var(--muted-foreground)); font-size: 13px; }
.rcnb-empty { margin: 4px 0 0 28px; color: hsl(var(--muted-foreground)); font-size: 14px; }
.rcnb-bar { display: flex; gap: 8px; align-items: center; padding: 8px 12px; border-top: 1px solid hsl(var(--border)); position: sticky; bottom: 0; background: hsl(var(--background)); font-size: 12px; color: hsl(var(--muted-foreground)); }
.rcnb-bar select { flex: 1; font: inherit; color: hsl(var(--foreground)); background: transparent; border: 0; padding: 2px 4px; border-radius: 4px; }
.rcnb-bar select:hover { background: hsl(var(--accent)); }

/* ---- motion ---- */
.rcnb-page.rcnb-first { animation: rcnb-fade .35s ease both; }
.rcnb-enter { animation: rcnb-in .32s cubic-bezier(.2,.8,.2,1) both; }
.rcnb-out-enter { animation: rcnb-in .25s ease both; }
.rcnb-menu { transform-origin: top left; animation: rcnb-pop .15s cubic-bezier(.2,.9,.3,1.2); }
.rcnb-menu .rcnb-item { animation: rcnb-in .2s ease both; }
.rcnb-menu > :nth-child(2) { animation-delay: .02s } .rcnb-menu > :nth-child(4) { animation-delay: .04s }
.rcnb-menu > :nth-child(5) { animation-delay: .06s } .rcnb-menu > :nth-child(7) { animation-delay: .08s }
.rcnb-code { overflow: hidden; transition: box-shadow .25s ease; }
.rcnb-code.running { animation: rcnb-glow 1.6s ease-in-out infinite; }
.rcnb-code.running::before { content: ""; position: absolute; top: 0; left: -40%; width: 40%; height: 2px; background: linear-gradient(90deg, transparent, #d9730d, transparent); animation: rcnb-scan 1.1s linear infinite; }
.rcnb-code.queued { box-shadow: inset 0 0 0 1px rgba(217,115,13,.35); }
.rcnb-run { transition: background .15s ease, transform .1s ease; }
.rcnb-run:active { transform: scale(.88); }
.rcnb-tag { animation: rcnb-pop .2s cubic-bezier(.2,.9,.3,1.3) both; }
.rcnb-dot { transition: background .3s ease; }
.rcnb-dot.pulse { animation: rcnb-pulse 1.3s ease-out infinite; }
.rcnb-callout { animation: rcnb-in .25s ease both; }
.rcnb-act { transition: background .12s ease, color .12s ease, transform .1s ease; }
.rcnb-act:active:not(:disabled) { transform: scale(.94); }
.rcnb-note, .rcnb-notesrc { animation: rcnb-fade .18s ease both; }
.rcnb-note { transition: background .12s ease; }
.rcnb-note:hover { background: hsl(var(--accent) / .5); }
.rcnb-handle { transition: background .12s ease, transform .15s ease; }
.rcnb-gutter.open .rcnb-handle { transform: rotate(90deg); }
@keyframes rcnb-fade { from { opacity: 0 } to { opacity: 1 } }
@keyframes rcnb-in { from { opacity: 0; transform: translateY(6px) } to { opacity: 1; transform: none } }
@keyframes rcnb-pop { from { opacity: 0; transform: scale(.94) } to { opacity: 1; transform: none } }
@keyframes rcnb-scan { to { left: 100% } }
@keyframes rcnb-glow { 0%, 100% { box-shadow: inset 0 0 0 1px rgba(217,115,13,.25) } 50% { box-shadow: inset 0 0 0 1px rgba(217,115,13,.7), 0 0 14px rgba(217,115,13,.18) } }
@keyframes rcnb-pulse { 0% { box-shadow: 0 0 0 0 currentColor } 100% { box-shadow: 0 0 0 6px transparent } }
@media (prefers-reduced-motion: reduce) {
  .rcnb *, .rcnb *::before { animation: none !important; transition: none !important; }
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

function SourceBox({ id, value, onChange, onShiftEnter, onBlur, autoFocus, placeholder, className }) {
  const rows = Math.max(1, value.split("\n").length);
  const ref = useRef(null);
  const mounted = useRef(true);
  const remember = (e) => (S.focus = { id, start: e.target.selectionStart, end: e.target.selectionEnd });

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
        if (e.key === "Enter" && e.shiftKey) {
          e.preventDefault();
          onShiftEnter();
        }
        if (e.key === "Escape" && onBlur) e.target.blur();
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

function BlockMenu({ cell, actions, close }) {
  const item = (icon, label, fn, cls = "") => (
    <button className={`rcnb-item ${cls}`} onClick={() => { close(); fn(); }}>
      {icon}
      {label}
    </button>
  );
  return (
    <div className="rcnb-menu" onMouseDown={(e) => e.stopPropagation()}>
      {item(<Code2 size={15} />, "Add code below", () => actions.add(cell.id, "code"))}
      {item(<StickyNote size={15} />, "Add note below", () => actions.add(cell.id, "markdown"))}
      <div className="rcnb-rule" />
      {item(<ArrowUp size={15} />, "Move up", () => actions.move(cell.id, "up"))}
      {item(<ArrowDown size={15} />, "Move down", () => actions.move(cell.id, "down"))}
      <div className="rcnb-rule" />
      {item(<Trash2 size={15} />, "Delete", () => actions.remove(cell.id), "danger")}
    </div>
  );
}

function Block({ cell, fresh, menuOpen, setMenu, actions, children }) {
  return (
    <div className={`rcnb-block${fresh ? " rcnb-enter" : ""}`}>
      <div className={`rcnb-gutter${menuOpen ? " open" : ""}`}>
        <button className="rcnb-handle" title="Move, add or delete" onClick={() => setMenu(menuOpen ? null : cell.id)}>
          <GripVertical size={16} />
        </button>
      </div>
      {menuOpen && <BlockMenu cell={cell} actions={actions} close={() => setMenu(null)} />}
      <div className="rcnb-body">{children}</div>
    </div>
  );
}

function CodeCell({ cell, source, running, onChange, onRun }) {
  const label = cell.status === "queued" ? "…" : cell.execution_count ? cell.execution_count : " ";
  const tag = { error: ["Error", "bad"], interrupted: ["Interrupted", "bad"], timeout: ["Timed out", "bad"], queued: ["Queued", "wait"] }[cell.status];
  // Only outputs that weren't on screen before animate in (pushes remount everything)
  const shown = S.outSeen[cell.id] === undefined ? cell.outputs.length : Math.min(S.outSeen[cell.id], cell.outputs.length);
  S.outSeen[cell.id] = cell.outputs.length;
  const state = running ? " running" : cell.status === "queued" ? " queued" : "";
  return (
    <>
      <div className={`rcnb-code${state}`}>
        <div className="rcnb-codehead">
          <button className="rcnb-run" title="Run (Shift+Enter)" onClick={onRun}>
            {running ? <Loader2 size={13} className="animate-spin" /> : <Play size={12} fill="currentColor" />}
          </button>
          <span className="rcnb-count">[{running ? "*" : label}]</span>
          {tag && <span className={`rcnb-tag ${tag[1]}`}>{tag[0]}</span>}
          <span className="rcnb-sep" />
          <span>Python</span>
        </div>
        <SourceBox id={cell.id} className="rcnb-src" value={source} onChange={onChange} onShiftEnter={onRun} placeholder="Write Python… Shift+Enter to run" />
      </div>
      {cell.outputs.length > 0 && (
        <div className="rcnb-out">
          {cell.outputs.map((o, i) => (
            <div key={i} className={i >= shown ? "rcnb-out-enter" : undefined}>
              <Output output={o} />
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function NoteCell({ id, source, onChange, onSave }) {
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
    return <SourceBox id={id} className="rcnb-src rcnb-notesrc" value={source} onChange={onChange} onShiftEnter={finish} onBlur={finish} autoFocus placeholder="Write a note… Markdown works. Shift+Enter to finish" />;
  }
  return (
    // Click to edit, like Notion; clicking a link opens the link instead
    <div className="rcnb-note" onClick={(e) => e.target.closest("a") || setEditing(true)}>
      {renderMarkdown(source)}
    </div>
  );
}

// ---- the panel -----------------------------------------------------------------

export default function Notebook() {
  // Re-render trigger; the data itself lives in S (see top of file)
  const [, setTick] = useState(0);
  const rerender = () => setTick((n) => n + 1);

  S.nb = newer(S.nb, props);
  const nb = S.nb;
  const projects = S.projects && S.projects.forProject === nb.project.id ? S.projects.list : [];

  useEffect(() => {
    // Replies to actions started by an older (remounted) copy re-render this one
    S.rerender = rerender;
    const closeMenu = () => {
      if (S.menu) {
        S.menu = null;
        rerender();
      }
    };
    const onKey = (e) => e.key === "Escape" && closeMenu();
    window.addEventListener("mousedown", closeMenu);
    window.addEventListener("keydown", onKey);
    return () => {
      if (S.rerender === rerender) S.rerender = null;
      window.removeEventListener("mousedown", closeMenu);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const apply = (result) => {
    if (result && result.cells) {
      S.nb = newer(S.nb, result);
      if (result.error) S.nb = { ...S.nb, error: result.error };
      if (S.rerender) S.rerender();
    }
    return result;
  };

  // ---- projects ----
  const announce = (list) =>
    window.dispatchEvent(new CustomEvent(EVENT_PROJECTS, { detail: { projects: list, current: S.nb.project.id } }));

  const loadProjects = async () => {
    const r = await call("nb_list_projects", {});
    if (r && r.projects) {
      S.projects = { forProject: S.nb.project.id, list: r.projects };
      announce(r.projects);
      if (S.rerender) S.rerender();
    }
  };

  const switchProject = (id) => call("nb_switch_project", { project_id: id });
  const createProject = async (name) => {
    const n = name || window.prompt("Name of the new project?");
    if (n && n.trim()) await call("nb_create_project", { name: n.trim() });
  };

  useEffect(() => {
    // Only ask the server when the project changed; otherwise reuse the list
    if (projects.length) announce(projects);
    else loadProjects();
    const onSwitch = (e) => switchProject(e.detail.project_id);
    const onCreate = (e) => createProject(e.detail && e.detail.name);
    const onRequest = () => (S.projects ? announce(S.projects.list) : loadProjects());
    window.addEventListener(EVENT_SWITCH, onSwitch);
    window.addEventListener(EVENT_CREATE, onCreate);
    window.addEventListener(EVENT_REQUEST, onRequest);
    // If custom.js couldn't place the bar under the message box, show ours
    const t =
      S.fallbackBar === null &&
      setTimeout(() => {
        S.fallbackBar = !window.__rcProjectBarMounted;
        if (S.rerender) S.rerender();
      }, 2000);
    return () => {
      window.removeEventListener(EVENT_SWITCH, onSwitch);
      window.removeEventListener(EVENT_CREATE, onCreate);
      window.removeEventListener(EVENT_REQUEST, onRequest);
      if (t) clearTimeout(t);
    };
  }, [nb.project.id]);

  // ---- editing ----
  const sourceOf = (cell) => (S.drafts[cell.id] !== undefined ? S.drafts[cell.id] : cell.source);

  const save = async (cellId, text) => {
    clearTimeout(S.timers[cellId]);
    const before = (S.nb.cells || []).find((c) => c.id === cellId);
    let result = await call("nb_update_cell", { version: S.nb.version, cell_id: cellId, source: text });
    // STALE because something else changed (e.g. a run finished): retry once if this cell wasn't edited elsewhere
    if (result && result.error && result.error.code === "STALE") {
      const server = (result.cells || []).find((c) => c.id === cellId);
      if (server && before && server.source === before.source) {
        result = await call("nb_update_cell", { version: result.version, cell_id: cellId, source: text });
      }
    }
    if (result && !result.error && S.drafts[cellId] === text) delete S.drafts[cellId];
    apply(result);
    return result;
  };

  const edit = (cellId, text) => {
    S.drafts[cellId] = text;
    rerender();
    clearTimeout(S.timers[cellId]);
    S.timers[cellId] = setTimeout(() => save(cellId, text), SAVE_DELAY_MS);
  };

  const flush = async (cellId) => {
    if (S.drafts[cellId] !== undefined) await save(cellId, S.drafts[cellId]);
  };

  const run = async (cell) => {
    clearTimeout(S.timers[cell.id]);
    const text = sourceOf(cell);
    const result = await call("nb_run_cell", { version: S.nb.version, cell_id: cell.id, source: text });
    if (result && !result.error && S.drafts[cell.id] === text) delete S.drafts[cell.id];
    apply(result);
  };

  const simple = async (name, extra = {}) => apply(await call(name, { version: S.nb.version, ...extra }));
  const add = async (afterId, type) => {
    const result = await call("nb_add_cell", { version: S.nb.version, after_id: afterId, type });
    if (result && result.cells && !result.error && type === "markdown") {
      const i = afterId ? result.cells.findIndex((c) => c.id === afterId) + 1 : result.cells.length - 1;
      if (result.cells[i]) S.editing[result.cells[i].id] = true;
    }
    apply(result);
  };
  const actions = {
    add,
    move: (id, direction) => simple("nb_move_cell", { cell_id: id, direction }),
    remove: (id) => simple("nb_delete_cell", { cell_id: id }),
  };
  const setMenu = (id) => {
    S.menu = id;
    rerender();
  };

  const kernel = nb.kernel;
  const busy = kernel === "busy" || !!nb.running_cell_id;
  const [colour, status] = (busy ? KERNEL.busy : KERNEL[kernel]) || KERNEL.off;
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

  return (
    <div className="rcnb">
      <style>{CSS}</style>
      <div className={`rcnb-page${firstShow ? " rcnb-first" : ""}`}>
        <h1 className="rcnb-title">{nb.project.name}</h1>
        <div className="rcnb-meta">
          <span style={{ display: "inline-flex", alignItems: "center", marginRight: 6 }}>
            <span className={`rcnb-dot${busy || kernel === "starting" ? " pulse" : ""}`} style={{ background: colour, color: colour }} />
            {status}
          </span>
          <span className="rcnb-sep" />
          <button className="rcnb-act" title="Run all code blocks" onClick={() => simple("nb_run_all")}><FastForward size={13} />Run all</button>
          <button className="rcnb-act" title="Stop the running block" disabled={!busy} onClick={() => simple("nb_interrupt")}><Square size={12} /></button>
          <button className="rcnb-act" title="Restart kernel (clears variables)" onClick={() => simple("nb_restart")}><RotateCcw size={13} /></button>
          <button className="rcnb-act" title="Clear all outputs" onClick={() => simple("nb_clear_outputs")}><Eraser size={13} /></button>
        </div>

        {problem && <div className="rcnb-callout"><span>⚠️</span><span>{problem}</span></div>}

        {nb.cells.length === 0 && <div className="rcnb-empty">Empty page. Add a code block or a note below.</div>}
        {nb.cells.map((cell) => (
          <Block key={cell.id} cell={cell} fresh={isNewBlock(nb.project.id, cell.id)} menuOpen={S.menu === cell.id} setMenu={setMenu} actions={actions}>
            {cell.type === "markdown" ? (
              <NoteCell id={cell.id} source={sourceOf(cell)} onChange={(t) => edit(cell.id, t)} onSave={() => flush(cell.id)} />
            ) : (
              <CodeCell cell={cell} source={sourceOf(cell)} running={cell.id === nb.running_cell_id} onChange={(t) => edit(cell.id, t)} onRun={() => run(cell)} />
            )}
          </Block>
        ))}

        <div className="rcnb-add">
          <button className="rcnb-act" onClick={() => add(null, "code")}><Plus size={14} />Code</button>
          <button className="rcnb-act" onClick={() => add(null, "markdown")}><Plus size={14} />Note</button>
        </div>
      </div>

      {S.fallbackBar === true && projects.length > 0 && (
        <div className="rcnb-bar">
          <span>Project</span>
          <select value={nb.project.id} onChange={(e) => (e.target.value === "__new" ? createProject() : switchProject(e.target.value))}>
            {projects.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            <option value="__new">+ New project…</option>
          </select>
        </div>
      )}
    </div>
  );
}
