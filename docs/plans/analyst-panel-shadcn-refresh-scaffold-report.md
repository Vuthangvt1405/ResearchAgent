# Scaffold Report: Analyst Panel UI Refresh (shadcn look)
Status: Implemented — manual checks M1–M8 pending · Plan: [analyst-panel-shadcn-refresh-plan.md](analyst-panel-shadcn-refresh-plan.md) · Date: 2026-11-12

## 9. Scaffold report

### File tree

```
public/
  custom.js                  ✏️ 4 TODO comments only (picker removal, font, observer)
  elements/Notebook.jsx      ✏️ shadcn imports, 3 new S keys, 4 unwired stubs, TODO comments
tests/
  test_panel_ui.py           🆕 19 failing test skeletons (plan §7)
docs/plans/
  analyst-panel-shadcn-refresh-plan.md            ✏️ status, D4 note, 4 consistency fixes
  analyst-panel-shadcn-refresh-scaffold-report.md 🆕 this file
```

**What changed in `Notebook.jsx`** (65 lines added, 0 removed against the pre-scaffold copy; the file already had about 1 060 uncommitted lines from earlier work, which were left untouched):

| Part | What | Effect at runtime |
|---|---|---|
| Imports | `Card`, `CardContent`, `CardHeader`, `Badge`, `Button`, `Input`, `Progress`, the `DropdownMenu*` and `Select*` parts. Each specifier and export name was checked against Chainlit's bundle source map | loaded, not used yet |
| `S` keys | `dsSortOpen`, `overlay` (`"menu:<id>"` / `"sort"` / `"project"`), `overlayItem` (highlighted item label) | new keys only; no existing key changed (A5 said two keys; the third is `overlayItem`, for the highlight restore) |
| Stubs | `BlockMenuRadix`, `DatasetSortSelect`, `ProjectPicker`, `holdWhileOverlayOpen`. Each throws `Error("Not implemented: …")` | defined, never called |
| TODO comments | above `KERNEL`, `CSS`, `BlockMenu`, `DS_CSS`, `DatasetCard`, `DatasetsTab`, the panel, and the `rc:*` constants; all outside template strings and JSX | none |

### Build and test results

| Check | Command | Result |
|---|---|---|
| JSX parses | esbuild `transformSync(…, {loader: "jsx"})` (cached npx copy, nothing installed) | ✅ parses |
| `custom.js` parses | `node --check public/custom.js` | ✅ |
| Python compiles | `python -m compileall tests/test_panel_ui.py` | ✅ |
| Panel loads in the real app | preview server on port 8001 (your own server was not running), panel opened, console checked | ✅ panel renders as before, 0 console errors |
| Test suite | `pytest -q -m "not docker"` | **19 failed** (all new, on purpose), **220 passed**. Before the scaffold: 220 passed, so 0 existing tests broke |

### TODO map

`grep -rn "TODO(" public/ tests/test_panel_ui.py` lists all of it.

| TODO | File:line | Covers |
|---|---|---|
| Remove the `rc:*` bridge and its listeners | `Notebook.jsx:17` | D6, SEC9, E❌5 |
| `KERNEL` hex colours → `--rc-*` | `Notebook.jsx:97` | AC8, AC9, A✅1 |
| Tokens, radius, shadows, fonts, no hex | `Notebook.jsx:109` | AC1, AC9, A✅3, B✅1 |
| Code-cell box recipe | `Notebook.jsx:112` | AC3 |
| Hand-written focus ring | `Notebook.jsx:113` | AC12, M7 |
| Overlay animation + reduced motion | `Notebook.jsx:114` | AC10, M8 |
| No-replay CSS rule (`data-rc-reopen`) | `Notebook.jsx:115` | D4 |
| `BlockMenuRadix` body | `Notebook.jsx:580` | AC4, D3, M1 |
| Block menu: no replay + highlight restore | `Notebook.jsx:582` | D4, M2 |
| Swap `BlockMenu` → `BlockMenuRadix` | `Notebook.jsx:587` | AC4 |
| Dataset CSS → tokens + Card recipe | `Notebook.jsx:741` | AC2, AC8, AC9 |
| `DatasetCard` → Card / Badge / Progress / Button | `Notebook.jsx:849` | AC2, AC7, AC8, SEC1, SEC3 |
| `DatasetSortSelect` body | `Notebook.jsx:956` | AC5, M3 |
| Sort select: no replay + highlight restore | `Notebook.jsx:957` | D4, M2 |
| Native sort `<select>` → `DatasetSortSelect`; filter → `Input` | `Notebook.jsx:961` | AC5 |
| `ProjectPicker` body | `Notebook.jsx:1053` | AC6, D6, M4 |
| `holdWhileOverlayOpen` body (only if D4 stays B) | `Notebook.jsx:1061` | D4 |
| Drop `announce()`, `EVENT_*` and the fallback `<select>`; render `ProjectPicker` | `Notebook.jsx:1067` | D6 |
| Route `S.nb` through `holdWhileOverlayOpen` | `Notebook.jsx:1069` | D4 |
| Remove the picker from `custom.js`; update its header | `custom.js:6`, `:12` | D6, A7, SEC9 |
| No font stack of its own | `custom.js:46` | AC1, D7, B✅2 |
| Observer keeps only `ensureToggle()` | `custom.js:350` | D6 |
| Fill `TAILWIND_ALLOWLIST` | `test_panel_ui.py:20` | Group C |
| 19 test bodies | `test_panel_ui.py` | Groups A–E |

### Suggested first test

`test_panel_css_has_no_hardcoded_hex_colours` (A✅1). It is the simplest baseline: one regex over the `CSS`, `DS_CSS` and `KERNEL` text. It drives phase 1 (tokens), which every later phase builds on.

### D4: a finding that changes option B

You chose **B (freeze the panel while a menu is open)** so the menu would stay perfectly still during a run. Reading the code shows that B cannot deliver that on its own:

- Every push re-sends the element with a **new key** (`researchchat/workspace/panel.py:36-41`). Chainlit then recompiles the JSX and **remounts the panel from outside**. The panel cannot stop that.
- Freezing only changes *which props* the remounted panel draws. The Radix popover is still destroyed and rebuilt 4 times a second, so its entrance animation still replays and its highlighted item still resets.
- So B alone gives the cost (no updates while a menu is open) without the benefit (a still menu).

What actually keeps the menu still is to make each remount look like nothing happened:

1. Tag a re-created overlay with `data-rc-reopen`, and add a CSS rule that removes its entrance animation (this was option C).
2. Remember the highlighted item in `S.overlayItem` and focus it again after the remount.

Both are scaffolded as TODOs above. With them in place, the freeze adds nothing, and the panel can keep updating while a menu is open.

**Recommendation: C + highlight restore, and drop the freeze.** The menu stays still and the cells keep updating. `holdWhileOverlayOpen` and its two TODOs would then be deleted. If you'd rather keep the freeze as well, it can stay; it is cheap but has no visible benefit.

## 10. Verification

### 10a. Self-verification

| # | Check | Result |
|---|---|---|
| V1 | Only the planned files changed: `Notebook.jsx`, `custom.js`, new `tests/test_panel_ui.py`, plus the plan and this report. `requirements.txt`, `researchchat/**` and `config.toml` are untouched by the scaffold. (`app.py`, `researchchat/workspace/*` and `tests/test_workspace_service.py` were already modified before the scaffold and were not edited.) | ✅ |
| V2 | Endpoints: none planned, none added; the `nb_*` actions are unchanged | ✅ |
| V3 | DTOs: `NotebookProps` unchanged; the only new state is 3 `S` keys | ✅ (3 keys instead of the 2 in A5; see the `S` keys row above) |
| V4 | Migration: none planned, none created, nothing run | ✅ |
| V5 | Security wiring: stubs document `modal={false}` (SEC4), React-text project names (SEC2), `safeHref` links (SEC3); no `dangerouslySetInnerHTML`, no new URL | ✅ |
| V6 | Planned tests vs found: **planned 19 / found 19**, exact names from §7 | ✅ |
| V7 | No logic leaked: new function bodies are TODO comments plus `throw new Error(…)`; nothing calls them; the diff against the pre-scaffold copy removes 0 lines | ✅ |
| V8 | Builds and parses; 19 new tests fail; 220 existing tests still pass; the panel loads with 0 console errors | ✅ |

Not covered: the browser checks M1–M8 need the real implementation and are still to do.

### 10b. Please verify

- ☐ The stub names (`BlockMenuRadix`, `DatasetSortSelect`, `ProjectPicker`, `holdWhileOverlayOpen`) and where they sit look right
- ☐ The 3 new `S` keys (`dsSortOpen`, `overlay`, `overlayItem`) are acceptable
- ☐ The imported shadcn parts are the ones you want
- ☐ The test list is complete: any missing negative or security case?
- ☐ The TODO map covers all the work
- ☐ **D4:** switch to C + highlight restore and drop the freeze (recommended), or keep B as well

Reply "verified" (with your D4 choice) to start implementing test by test, or tell me what to change in the scaffold.

## 11. Implementation report

Verified by the user on 2026-11-12, with **D4 = C + highlight restore, no freeze**.

### What changed

| Area | Result |
|---|---|
| Tokens and colours (AC8, AC9) | `--rc-radius`, `--rc-shadow`, `--rc-shadow-lift`, `--rc-info/warn/ok/danger` are defined on `.rcnb` and `[data-rc-overlay]`, with `.dark` overrides. All hex and status `rgba()` colours are gone. **Deviation:** `--rc-danger` got its own light and dark values, because Chainlit's dark `--destructive` (30% lightness) can't be read as text |
| Fonts (AC1) | `var(--font-sans)` / `var(--font-mono)` everywhere (Inter, as in the chat) |
| Boxes (AC2, AC3) | Code cells use a 12px radius, a 1px border and `shadow-sm`; the empty states are shadcn `Card`s |
| Controls (AC7) | Toolbar and output buttons are shadcn ghost `Button`s; cell status tags are `Badge`s; the dataset filter is an `Input` |
| Block menu (AC4) | Radix `DropdownMenu`, `modal={false}`. It is anchored to an invisible span, so the handle can still be dragged. It closes on an outside click or Escape, and keyboard close returns focus to the handle |
| Dataset sort (AC5) | Radix `Select` |
| Project picker (AC6, D6) | `DropdownMenu` on the panel title. "New project…" turns into a name field inside the menu (no browser prompt). The `rc:*` events, the fallback `<select>` and the whole picker in `custom.js` are gone; `custom.js` keeps the sidebar toggle and the scrollbars |
| D4 remount | `S.overlay` keeps the overlay open; a rebuilt overlay gets `data-rc-reopen` (no entrance animation); the highlighted item is recorded (focus, keys, hover) and refocused after the remount |
| Focus ring (AC12) | One hand-written rule that looks like `ring-2 ring-ring ring-offset-2` |
| Reduced motion (AC10) | Covers the portal overlays too |
| Spacing (user request) | Looser page, title, tab, toolbar, block, code-cell and output spacing |
| Dataset cards (user request) | **Redesigned:** one compact row with an icon, the name, source · size, and a chevron. The chevron opens the details: licence, file count, added date, source link, the path with copy, the file list, and the Copy load code / Insert code / Delete actions. Download progress, status badges and errors stay visible when the card is collapsed |

### Tests

`tests/test_panel_ui.py`: **19 / 19 pass**. The full suite (`pytest -m "not docker"`): **239 passed**, 0 failed. `Notebook.jsx` parses with esbuild; `custom.js` passes `node --check`.

### Browser checks done

- Panel loads with 0 console errors; dark mode tokens are applied (`--rc-info` = dark value); the font is Inter.
- Block menu: rendered in a portal on `<body>`, Chainlit's popover classes, 10px radius, `shadow-md`, the page is not locked (`body.style.pointerEvents` empty), and Delete uses the danger colour.
- Dataset cards: compact rows and the open details render as designed.

### Still to check by hand

- **M2** (a menu stays still during a push): **mechanics verified.** With a block menu open in one session, a no-op save from a second session remounted the panel (version 70 → 72). The menu node was rebuilt, stayed open, had `data-rc-reopen` and `animation-name: none`, and focus returned to "Duplicate". Still worth a look by eye during a real long-running cell.
- Sort list, project picker, the in-menu new-project field and light-mode tokens were checked in a background tab: all render, and the page unlocks after the sort list closes.
- M1, M3–M8 by eye in a focused browser window (keyboard navigation, the sort list flipping, picker parity, light mode, narrow widths, focus ring, reduced motion).
