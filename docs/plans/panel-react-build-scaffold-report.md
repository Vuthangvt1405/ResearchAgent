# Scaffold Report: Notebook panel as a bundled React app
Status: Implemented — desktop and phone checked (D9, D10) · Plan: [panel-react-build-plan.md](panel-react-build-plan.md) · Date: 2026-11-13

## 9. Scaffold report

### 9.1 File tree

```
public/panel/                         🆕 Vite + React 18.3 + TS project
├── package.json                      🆕 exact versions only (SEC2)
├── package-lock.json                 🆕
├── vite.config.ts                    🆕 lib build → public/build/notebook-panel.{js,css}; vitest (jsdom)
├── tsconfig.json                     🆕 strict, "@/*" → src/*
├── components.json                   🆕 shadcn config
└── src/
    ├── main.tsx                      🆕 bootstrap() + window.__rcPanel / __rcPanelReady types
    ├── overlay.ts                    🆕 createOverlay(): fixed root that never moves (D3)
    ├── shim.ts                       🆕 connectShim(): logic for the Notebook.jsx shim
    ├── store.ts                      🆕 Zustand store (props + UI state)
    ├── types.ts                      🆕 NotebookProps / DatasetProps mirror, 17 ActionNames
    ├── styles.css                    🆕 #rc-panel-root; CSS port is a TODO
    ├── lib/{newer,actions,safeHref,markdown,editing,loadCode}.ts(x)  🆕 ported helper signatures
    ├── lib/utils.ts                  🆕 shadcn cn()
    ├── components/{App,Notebook,CodeCell,NoteCell,SourceBox,BlockMenu,InsertRow,
    │               ProjectPicker,DatasetsTab,DatasetCard,DatasetSortSelect}.tsx  🆕 shells
    ├── components/ui/{button,badge,card,input,progress,dropdown-menu,select}.tsx 🆕 shadcn vendor code
    └── *.test.ts(x)  (7 files)       🆕 33 planned tests, red
tests/test_panel_ui.py                ✏️ + Group S2 (3 red tests)
.gitignore                            ✏️ + public/panel/node_modules/, !public/build/
```

**Deferred to the logic phase (on purpose):**
- `public/elements/Notebook.jsx` → shim, and `public/custom.js` → loads the bundle. Changing them now would replace a working panel with a non-working one.
- Retargeting the 19 existing `test_panel_ui.py` rules to `public/panel/src/` (D1). They still pass against the current `Notebook.jsx`, and they should move together with the port.
- `public/build/` output. The build was tried and works (`vite build`, 47 ms), but the placeholder output was deleted because there's nothing to ship yet.

### 9.2 Build and test results

| Command | Result |
|---|---|
| `npm install` (public/panel) | ✅ installed. npm 12 blocked the esbuild postinstall script, but esbuild works anyway (Vite and Vitest run) |
| `npx tsc --noEmit` | ✅ exit 0 |
| `npx vite build` | ✅ builds `notebook-panel.js` and `.css` |
| `npx vitest run` | 🔴 **33 failed / 33**, as planned |
| `pytest tests/test_panel_ui.py` | 🔴 3 new S2 failures, ✅ 19 existing pass |
| `pytest` (rest of the suite) | ✅ 250 passed, 0 broken |

### 9.3 TODO map

| TODO | File | Plan refs |
|---|---|---|
| merge props, reset on project switch | `src/store.ts` setProps / resetForProject | AC3, AC6, SEC4, G2, G1❌1 |
| keep latest callAction | `src/store.ts` setCallAction | AC4, G5✅3 |
| fixed root, follow slot, 300 ms grace | `src/overlay.ts` createOverlay | AC1, AC10, G1✅4–5, G1❌2–4 |
| create root once, expose API | `src/main.tsx` bootstrap | AC1 |
| wait for bundle, fallback | `src/shim.ts` connectShim | AC7, G6 |
| merge rule | `src/lib/newer.ts` | AC3, SEC4, G2 |
| call / useAction / useProjects | `src/lib/actions.ts` | AC4, AC8, G5, D4 |
| safeHref, markdown | `src/lib/safeHref.ts`, `markdown.tsx` | SEC1, S1 |
| editing helpers, loadCode, percent | `src/lib/editing.ts`, `loadCode.ts` | AC4, AC2, G3❌1 |
| 11 components | `src/components/*.tsx` | AC1, AC2, AC4, AC5, AC10 |
| CSS port + z-index | `src/styles.css` | AC9, S2❌3 |
| S2 checks | `tests/test_panel_ui.py` | SEC2, SEC3, AC9 |

List them all with `grep -rn "TODO(" public/panel/src tests/test_panel_ui.py`.

### 9.4 Suggested first test
`G2✅1 newer_version_wins` in `src/lib/newer.test.ts`. It's a pure function ported from `Notebook.jsx:66`, and everything else builds on it.

## 10. Verification

### 10a. Self-verification

| # | Check | Result |
|---|---|---|
| V1 | Files match "Files affected"; no extras | ✅ apart from the deferred files listed above (Notebook.jsx, custom.js, public/build), which is intentional |
| V2 | Contract matches §4.2 (`attach`, `detach`, `setProps`, `setCallAction`, `__rcPanelReady`) | ✅ `main.tsx`, `overlay.ts` |
| V3 | Types match NotebookProps (§4.3), no fields added | ✅ `types.ts` |
| V4 | No schema or migration | ✅ none planned, none created |
| V5 | Security wiring: exact versions, no external URLs, safeHref and markdown stubs | ✅ |
| V6 | Planned tests present | ✅ planned 36 / found 36 (33 Vitest + 3 pytest), names as in §7 |
| V7 | No logic leaked | ✅ grep for `if`/`&&`/`?:`/`for`/`.map(` in new non-vendor src: 0 hits (shadcn ui files are vendor code) |
| V8 | Build passes, new tests fail, old tests pass | ✅ see 9.2 |

### 10b. Please verify

- ☐ File locations and names look right (`public/panel/src/...`)
- ☐ The shim ↔ bundle contract (`attach`/`detach`/`setProps`/`setCallAction`) is what you want
- ☐ The fixed overlay approach (D3) is OK, including the 300 ms hide grace
- ☐ The test list is complete; are any negative or IME cases missing?
- ☐ It's OK to defer the Notebook.jsx / custom.js switch-over to the end of the logic phase

## 11. Implementation result (2026-11-13)

| Check | Result |
|---|---|
| `npx tsc --noEmit` | ✅ clean |
| `npx vitest run` | ✅ 38 / 38 (33 planned + 5 extra: collapsed sidebar, shim cleanup, find reset on project switch, 2 note cases) |
| `pytest tests/test_panel_ui.py` | ✅ 23 / 23 (19 retargeted rules + 3 S2 + shim-sync check) |
| `pytest` (whole suite) | ✅ 273 passed |
| `npx vite build` | ✅ `notebook-panel.js` 359 kB (115 kB gzip), `notebook-panel.css` 20 kB |

**Real browser, real Chainlit (port 8001), Default project:**
- A push from a second chat of the same project made Chainlit replace the placeholder (old slot removed). The panel's DOM node and the open iris card were the same nodes before and after, and the card stayed open (AC1).
- A textarea with the cursor at 3 stayed the same element, focused, with the cursor at 3–3, through a real remount (AC5).
- The top-bar collapse toggle hides the overlay and showing the sidebar brings it back, with state kept.
- Console: no errors from the panel. One pre-existing Chainlit `DialogTitle` warning remains.

**Not covered automatically:** a real IME composition. jsdom covers composition events (G4✅3, G4❌2), and the browser test shows the focused textarea is never moved or replaced. A manual check with Vietnamese Telex in Chrome and Firefox during a running download is still worth doing.

**Changed during implementation (see Decision log D6–D8):** vendor shadcn files are Chainlit's own; `types.ts` was corrected to the real props (`type: "code" | "markdown"`, image outputs, `path`, `file_count`, `requested_at`); `src/test/{setup,harness,fixtures}.ts` were added for the tests.

**Rebuild after changing the panel:** `cd public/panel && npm ci && npm run build`, then commit `public/build/`.

### 11.1 Fixes after review (2026-11-13)
- **Run all lost its `version`.** The payload was `{}`, which the Python handler rejects because it requires an int `version`. It's now read after the flush. The payload table test now takes its expected values from the old panel (`git show 6010c47:public/elements/Notebook.jsx`), not from the new hook.
- **An empty note closed after its first character.** That would also have ended an IME composition. The editing state is latched in `useState` again, as in the old code. Two note tests were added, one with a composition.
- **Switching projects** clears the find box, the open menu and the drag state again, as the old `switchProject` did.
- **`ds_cancel` / `ds_delete`** are no longer blocked while another action runs, matching the old `act()`.
- **Not built from the plan:** focus forwarding from the placeholder (the panel's Tab order now comes last on the page) and remembering scroll position per tab.

**Measured on real pushes:** Chainlit calls `detach` and `attach` within the same millisecond (gap 0 ms on both pushes), so the 300 ms grace never shows a blink. In light theme the panel's background matches the sidebar card (both `rgb(255,255,255)`).

### 11.2 Open: phone-size layout (regression)
At 375 px wide, Chainlit shows the side view in a Radix dialog (sheet). The fixed overlay on `<body>` sits under that dialog (z-40 < z-50), so the sheet opens **empty**. Raising the z-index won't help: the dialog traps focus and blocks clicks outside itself.

Found while checking: on real pushes (desktop and mobile), Chainlit replaces only the placeholder. Its parent, `#side-view-content` and the dialog all stay the same DOM nodes. That allows a different design: keep the persistent root **inside** `#side-view-content`, and move it only when Chainlit recreates that container (opening the sidebar, or switching between phone and desktop layout), never on a push. This needs a decision because it changes D3 ("never re-parent").

### 11.3 Resolved: root inside the sidebar (D9) and wider sidebar (D10)
- The root now lives in `#side-view-content`. Real pushes (desktop) left the root and its parent as the same nodes; a cell kept focus and its cursor (3–3).
- Phone width (375px): the panel shows inside Chainlit's sheet and focus stays in a cell.
- The sidebar opens at 60% (panel 562px wide in a 1024px window, was 333px), and the colours match the sidebar card.
- Vitest 37/37 (the fixed-overlay rect tests were replaced by "moves only when the container changes"), pytest 23/23 panel.

**Caching note:** browsers cache `/public/custom.js` and `/public/build/*`. After an update, users may need one hard refresh (Ctrl+Shift+R) to get the new panel.
