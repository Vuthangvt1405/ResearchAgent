"""Static checks on the Notebook panel's front end.

The panel is a bundled React app in public/panel/src (built to public/build), shown
through the thin shim public/elements/Notebook.jsx. Behaviour is tested with Vitest in
public/panel; these tests read the sources as text and check rules that must hold:
theme colours only, Chainlit's fonts, Tailwind classes that exist in Chainlit's
pre-built CSS, imports the shim can resolve, pinned dependencies, and the security rules.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SHIM = ROOT / "public" / "elements" / "Notebook.jsx"  # what Chainlit compiles
CUSTOM_JS = ROOT / "public" / "custom.js"
PANEL_DIR = ROOT / "public" / "panel"
PANEL_SRC = PANEL_DIR / "src"
PANEL_CSS = PANEL_SRC / "styles.css"
BUILD = ROOT / "public" / "build"

# Tailwind classes the panel relies on from Chainlit's shadcn recipes (cards, menus,
# selects, hover and animation states). Each must exist in Chainlit's built CSS; classes
# written in the panel's own className attributes are checked too (_panel_tailwind_classes).
# Never list ring-2 / ring-ring / ring-offset-2: they are purged, so the focus
# ring is hand-written CSS.
TAILWIND_ALLOWLIST: list[str] = [
    "bg-card", "text-card-foreground", "shadow-sm", "rounded-lg", "border",
    "bg-popover", "text-popover-foreground", "shadow-md", "rounded-md", "z-50",
    "hover:bg-accent", "hover:text-accent-foreground", "focus:bg-accent", "focus:text-accent-foreground",
    "data-[state=open]:animate-in", "data-[state=closed]:animate-out",
    "data-[state=open]:fade-in-0", "data-[state=closed]:fade-out-0",
    "data-[state=open]:zoom-in-95", "data-[state=closed]:zoom-out-95",
    "bg-destructive", "text-destructive-foreground", "bg-secondary", "animate-spin",
]

# Tokens live on the panel and on its Radix overlays, which render outside it (portal)
LIGHT = ".rcnb, [data-rc-overlay]"
DARK = ".dark .rcnb, .dark [data-rc-overlay]"
SEMANTIC_COLOURS = ("--rc-info", "--rc-warn", "--rc-ok", "--rc-danger")
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def _panel_files() -> list[Path]:
    """The app's own source files (no tests, no test helpers)."""
    files = [
        f
        for f in sorted(PANEL_SRC.rglob("*.ts*"))
        if ".test." not in f.name and "test" not in f.relative_to(PANEL_SRC).parts[:-1]
    ]
    assert files, "public/panel/src has no sources"
    return files


def _panel() -> str:
    """The shim plus every panel source file, as one text."""
    return "\n".join(f.read_text(encoding="utf-8") for f in [SHIM, *_panel_files()])


def _css_blocks(src: str | None = None) -> str:
    """The panel's stylesheet plus the KERNEL colour map in Notebook.tsx."""
    css = PANEL_CSS.read_text(encoding="utf-8") if src is None else src
    nb = (PANEL_SRC / "components" / "Notebook.tsx").read_text(encoding="utf-8")
    kernel = re.search(r"const KERNEL[^=]*= \{(.*?)\};", nb, re.S)
    assert kernel, "the KERNEL colour map was not found"
    return css + "\n" + kernel.group(1)


def _without_allowed(css: str) -> str:
    # Hex inside url(...) (e.g. an encoded data-URI image) is not a colour rule
    return re.sub(r"url\([^)]*\)", "url()", css)


def _hex_colours(css: str | None = None) -> list[str]:
    return HEX.findall(_without_allowed(_css_blocks(css)))


def _font_families(css: str) -> list[str]:
    """Every font-family value, plus the family part of each font: shorthand."""
    out = [v.strip() for v in re.findall(r"font-family\s*:\s*([^;}]+)", css)]
    for v in re.findall(r"(?<![-\w])font\s*:\s*([^;}]+)", css):
        v = v.strip()
        if v != "inherit":
            out.append(v)
    return out


FONT_OK = re.compile(r"^(?:.*\s)?(?:var\(--font-(?:sans|mono)\)|inherit)$")


def _chainlit_assets() -> Path | None:
    try:
        import chainlit
    except ImportError:
        return None
    assets = Path(chainlit.__file__).parent / "frontend" / "dist" / "assets"
    return assets if assets.is_dir() else None


def _chainlit_css() -> str:
    assets = _chainlit_assets()
    files = sorted(assets.glob("index-*.css")) if assets else []
    if not files:
        pytest.skip("Chainlit's built CSS (chainlit/frontend/dist/assets/index-*.css) not found")
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


def _chainlit_import_map() -> set[str]:
    """Module specifiers Chainlit exposes to custom elements (Imports.ts, from the source map)."""
    import json

    assets = _chainlit_assets()
    for f in sorted(assets.glob("index-*.js.map")) if assets else []:
        data = json.loads(f.read_text(encoding="utf-8"))
        for name, src in zip(data["sources"], data.get("sourcesContent") or []):
            if name.endswith("CustomElement/Imports.ts") and src:
                body = src[src.index("const Imports") :]
                return set(re.findall(r"^\s*'?([\w@/.-]+)'?\s*:", body[: body.index("};")], re.M))
    pytest.skip("Chainlit's custom-element import map not found")


def _tw_selector(cls: str) -> str:
    return "." + re.sub(r"([^A-Za-z0-9_-])", r"\\\1", cls)


def _missing_classes(classes, css: str) -> list[str]:
    return [c for c in classes if not re.search(re.escape(_tw_selector(c)) + r"(?![A-Za-z0-9_\\-])", css)]


def _panel_tailwind_classes(src: str) -> set[str]:
    """Static class names in className="…" and className={`…`} that aren't the panel's own rc* classes."""
    out = set()
    for lit in re.findall(r'className=(?:"([^"]*)"|\{`([^`]*)`\})', src):
        text = re.sub(r"\$\{[^}]*\}", " ", lit[0] or lit[1])
        out.update(text.split())
    own = set(re.findall(r"\.([A-Za-z][\w-]*)", _css_blocks()))  # the panel's hand-written classes
    return {c for c in out if c not in own and not c.startswith("rc")}


def _imports(src: str) -> list[str]:
    return re.findall(r"""^import .* from ["']([^"']+)["'];""", src, re.M)


def _code(src: str) -> str:
    """Source without // line comments (a URL or name in a comment isn't code)."""
    return re.sub(r"(?m)^\s*//.*$", "", src)


def _hrefs_are_safe(src: str) -> bool:
    """Every href={x} uses a variable that was assigned from safeHref(...)."""
    names = re.findall(r"href=\{(\w+)\}", src)
    others = re.findall(r"href=(?!\{\w+\})", src)
    safe = set(re.findall(r"const (\w+) = [^;]*\bsafeHref\(", src))
    return not others and all(n in safe for n in names)


def _fetched_urls(src: str) -> list[str]:
    urls = re.findall(r"https?://[^\s\"'`)>]+", _code(src))
    return [u for u in urls if not u.startswith("http://www.w3.org/")]  # SVG namespace, never fetched


RC_EVENT = re.compile(r"[\"'`]rc:[a-z-]+[\"'`]")


def _rule_body(css: str, selector: str) -> str:
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", css)
    return m.group(1) if m else ""


# ---- theme tokens and colours ------------------
# Baseline: Given the panel CSS (public/panel/src/styles.css) · When the colour rules are inspected


def test_panel_css_has_no_hardcoded_hex_colours():
    # baseline, negative (a stray #2383e2 is reintroduced).
    # Then: no #rgb/#rrggbb literal in the CSS or DS_CSS blocks (or KERNEL map).
    # Demonstrates: every colour follows the theme.
    assert _hex_colours() == []
    # negative: a stray hex colour would be caught
    assert _hex_colours(".x { color: #2383e2; }") == ["#2383e2"]


def test_panel_css_allows_hex_only_in_the_documented_allowlist():
    # edge: a hex literal in an allow-listed place (e.g. a data-URI) still passes.
    # Demonstrates: the guard is not a blanket ban.
    css = ".x { background: url(data:image/svg+xml;utf8,#fff); }\n" + PANEL_CSS.read_text(encoding="utf-8")
    assert _hex_colours(css) == []


def test_panel_defines_a_light_and_a_dark_value_for_every_semantic_colour():
    # edge: --rc-info, --rc-warn, --rc-ok, --rc-danger each have a light value
    # on .rcnb and an override under .dark.
    # Demonstrates: status colours stay legible in both themes.
    css = _css_blocks()
    light, dark = _rule_body(css, LIGHT), _rule_body(css, DARK)
    for name in SEMANTIC_COLOURS:
        assert f"{name}:" in light, f"{name} has no light value"
    # --rc-danger too: Chainlit's dark --destructive (30% lightness) is unreadable as text
    for name in SEMANTIC_COLOURS:
        assert f"{name}:" in dark, f"{name} has no dark value"


def test_semantic_colours_are_defined_for_both_themes():
    # negative: the .dark block is dropped, only the light value exists -> fails.
    # Demonstrates: dark mode cannot silently lose a colour.
    css = PANEL_CSS.read_text(encoding="utf-8")
    dark = _rule_body(css, DARK)
    assert dark, "no .dark override block"
    stripped = css.replace(DARK + " {" + dark + "}", "")
    assert _rule_body(_css_blocks(stripped), DARK) == ""


def test_semantic_colours_are_not_taken_from_chart_tokens():
    # negative: a status colour uses var(--chart-N) -> fails.
    # Demonstrates: chart tokens change meaning between themes.
    assert "--chart-" not in _css_blocks()


# ---- fonts --------------------------------------------------
# Baseline: Given the panel CSS · When font-family declarations are inspected


def test_panel_uses_the_chainlit_font_variables():
    # baseline, negative (font-family: ui-sans-serif, … is reintroduced).
    # Then: every font-family is var(--font-sans), var(--font-mono) or inherit.
    # Demonstrates: the panel and the chat share a typeface.
    bad = [f for f in _font_families(_css_blocks()) if not FONT_OK.match(f)]
    assert bad == []


def test_no_font_family_is_declared_outside_the_panel():
    # edge: public/custom.js declares no font family of its own (only var(--font-sans)).
    # Demonstrates: what remains in custom.js inherits Chainlit's font.
    bad = [f for f in _font_families(CUSTOM_JS.read_text(encoding="utf-8")) if not FONT_OK.match(f)]
    assert bad == []


def test_no_theme_json_is_added():
    # negative: a public/theme.json appears -> fails.
    # Demonstrates: the panel cannot change the app-wide font.
    assert not (ROOT / "public" / "theme.json").exists()


# ---- Tailwind classes exist in Chainlit's build --------
# Baseline: Given TAILWIND_ALLOWLIST · When Chainlit's pre-built stylesheet is searched


def test_every_allowlisted_tailwind_class_exists_in_chainlits_css():
    # baseline, negative (a purged class such as shadow-xl is added).
    # Then: each class selector is found in chainlit/frontend/dist/assets/index-*.css;
    # a missing one fails, naming the class.
    # Demonstrates: no class is silently dropped by Tailwind's purge.
    css = _chainlit_css()
    classes = sorted(set(TAILWIND_ALLOWLIST) | _panel_tailwind_classes(_panel()))
    assert _missing_classes(classes, css) == []
    # negative: a purged class is reported by name
    assert _missing_classes(["shadow-xl", "ring-offset-2"], css) == ["shadow-xl", "ring-offset-2"]


def test_the_allowlist_is_not_empty():
    # edge. Demonstrates: the class check actually tests something.
    assert TAILWIND_ALLOWLIST


def test_the_chainlit_css_file_is_found():
    # negative: when Chainlit's built CSS is missing, _chainlit_css() SKIPS with a clear
    # reason instead of failing.
    assert ".bg-card" in _chainlit_css()


# ---- imports resolvable by Chainlit's custom-element scope --
# Baseline: Given the import statements in the shim Notebook.jsx (the only file Chainlit
# compiles; the bundle resolves its own imports at build time) · When checked against Chainlit's map


def test_every_imported_module_is_exposed_by_chainlit():
    # baseline, negative (@/components/ui/alert-dialog is imported).
    # Then: each specifier is in Chainlit's Imports map; a missing one fails, naming it.
    # Demonstrates: the panel cannot fail with "Module not found".
    exposed = _chainlit_import_map()
    shim = SHIM.read_text(encoding="utf-8")
    assert _imports(shim), "the shim's imports were not found"
    assert [m for m in _imports(shim) if m not in exposed] == []
    # negative: a module Chainlit doesn't expose is reported by name
    assert "@/components/ui/alert-dialog" not in exposed


def test_the_helper_cn_is_not_imported():
    # edge: @/lib/utils is not imported by the shim (the bundle has its own cn()).
    # Demonstrates: the shim does not rely on a helper Chainlit doesn't give it.
    assert "@/lib/utils" not in _imports(SHIM.read_text(encoding="utf-8"))


def test_no_new_dependencies_are_added():
    # negative: a package.json appears at the repo root or in public/ -> fails.
    # npm packages are allowed only inside public/panel, pinned.
    # Demonstrates: dependencies stay in one reviewed place.
    assert not (ROOT / "package.json").exists()
    assert not (ROOT / "public" / "package.json").exists()
    assert not (ROOT / "node_modules").exists()


# ---- security invariants ---------------------------------------------
# Baseline: Given the shim, the panel sources and custom.js · When they are inspected for unsafe patterns


def test_panel_never_uses_dangerously_set_inner_html():
    # baseline, negative (raw HTML for a badge is introduced).
    # Demonstrates: catalog text stays text.
    src = _panel()
    assert "dangerouslySetInnerHTML" not in src
    assert "innerHTML" not in src
    # negative: the check sees it when it is added
    assert "dangerouslySetInnerHTML" in src + "<span dangerouslySetInnerHTML={{ __html: d.license }} />"


def test_every_href_still_goes_through_safe_href():
    # baseline, negative (a raw d.url href is used).
    # Demonstrates: javascript: URLs cannot appear.
    src = _panel()
    assert re.search(r"href=\{\w+\}", src), "the panel's links were not found"
    assert _hrefs_are_safe(src)
    # negative: a raw dataset URL is caught
    assert not _hrefs_are_safe(src + '<a href={d.url}>x</a>')


def test_project_names_are_rendered_as_react_text():
    # baseline, negative (the picker builds HTML from a name).
    # Then: no innerHTML / dangerouslySetInnerHTML near p.name; custom.js no longer
    # renders project names at all.
    # Demonstrates: the moved picker cannot inject HTML.
    src = _panel()
    assert re.search(r">\{p\.name\}<", src), "the picker should render p.name as a React child"
    assert "innerHTML" not in src
    # custom.js no longer touches projects at all, so it cannot render a name as HTML
    assert not re.search(r"(?i)project", _code(CUSTOM_JS.read_text(encoding="utf-8")))


def test_no_new_external_stylesheet_or_script_is_fetched():
    # baseline, negative (a font CDN URL is added).
    # Demonstrates: no new supply-chain surface.
    for path in (SHIM, *_panel_files(), PANEL_CSS, CUSTOM_JS):
        src = path.read_text(encoding="utf-8")
        assert _fetched_urls(src) == [], path.name
        assert "@import" not in src and "<link" not in src, path.name
    # negative: a font CDN would be caught
    assert _fetched_urls('@import url("https://fonts.googleapis.com/css2?family=Inter");')


def test_the_rc_event_bridge_is_gone():
    # negative: a stale rc:switch-project / rc:create-project / rc:projects /
    # rc:projects-request name survives in either file -> fails.
    # Demonstrates: the picker move leaves no half-removed bridge behind.
    for path in (SHIM, *_panel_files(), CUSTOM_JS):
        assert not RC_EVENT.search(path.read_text(encoding="utf-8")), path.name
    assert RC_EVENT.search('const EVENT_SWITCH = "rc:switch-project";')


# ---- bundled panel dependencies and scripts (panel React build) --
# Baseline: none (negatives only)
PANEL_PKG = PANEL_DIR / "package.json"
EXACT = re.compile(r"^\d+\.\d+\.\d+$")


def _loaded_urls(js: str) -> list[str]:
    """URLs custom.js loads as a script or stylesheet (its PANEL_JS / PANEL_CSS constants)."""
    return re.findall(r'const PANEL_(?:JS|CSS) = "([^"]+)";', js)


def _remote_imports(js: str) -> list[str]:
    return re.findall(r"""(?:\bimport\s*\(|\bfrom\s*)["'](https?:)?//""", js)


def test_no_external_script_or_stylesheet():
    # custom.js or the build references a non-/public URL -> fails.
    # Then: only same-origin /public/build/... is loaded.
    # Demonstrates: no third-party script surface.
    urls = _loaded_urls(CUSTOM_JS.read_text(encoding="utf-8"))
    assert sorted(urls) == ["/public/build/notebook-panel.css", "/public/build/notebook-panel.js"]
    built = (BUILD / "notebook-panel.js").read_text(encoding="utf-8")
    assert _remote_imports(built) == []
    # a CDN script or a remote import would be caught
    assert _loaded_urls('const PANEL_JS = "https://cdn.example.com/x.js";') != ["/public/build/notebook-panel.js"]
    assert _remote_imports('import("https://cdn.example.com/x.js")')


def test_lockfile_present_and_versions_pinned():
    # a ^ or ~ range in public/panel/package.json -> fails.
    # Then: package-lock.json exists and every version is exact.
    # Demonstrates: reproducible builds.
    import json

    pkg = json.loads(PANEL_PKG.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert deps, "public/panel/package.json lists no dependencies"
    assert {k: v for k, v in deps.items() if not EXACT.match(v)} == {}
    lock = json.loads((PANEL_DIR / "package-lock.json").read_text(encoding="utf-8"))
    locked = lock["packages"][""]
    assert {**locked.get("dependencies", {}), **locked.get("devDependencies", {})} == deps
    assert not EXACT.match("^18.3.1") and not EXACT.match("~5.0.3")


def test_colours_and_fonts_rules_on_new_css():
    # a hex colour in public/panel/src/styles.css -> fails.
    # Then: the colour and font rules hold for the new CSS, and the built CSS is the same rules.
    # Demonstrates: the look is kept.
    css = PANEL_CSS.read_text(encoding="utf-8")
    assert HEX.findall(_without_allowed(css)) == []
    assert [f for f in _font_families(css) if not FONT_OK.match(f)] == []
    built = (BUILD / "notebook-panel.css").read_text(encoding="utf-8")
    assert ".rcnb" in built and "#rc-panel-root" in built
    assert HEX.findall(".x{color:#fff}")


def test_shim_matches_the_tested_connect_logic():
    # Extra: Notebook.jsx carries a plain-JS copy of connectShim (public/panel/src/shim.ts,
    # tested by Vitest). Same window names, timeout and fallback text in both.
    shim = SHIM.read_text(encoding="utf-8")
    ts = (PANEL_SRC / "shim.ts").read_text(encoding="utf-8")
    for name in ("__rcPanelReady", "__rcPanelResolve", "setCallAction", "setProps", "attach", "detach"):
        assert name in shim and name in ts, name

    def timeout_ms(src: str) -> int:
        return int(re.search(r"READY_TIMEOUT_MS = ([\d_]+)", src).group(1).replace("_", ""))

    def fallback_text(src: str) -> str:
        return re.search(r'FALLBACK_TEXT = "([^"]+)"', src).group(1)

    assert timeout_ms(shim) == timeout_ms(ts) == 10000
    assert fallback_text(shim) == fallback_text(ts)


# ---- Chainlit page parts that the page extras find by name --
# Baseline: Given the ids, attributes and classes of Chainlit's own markup that the page
# extras (public/panel/src/page) look for · When Chainlit's built JS is searched
# A Chainlit upgrade that renames one would silently switch a page feature off.

PAGE_SRC = PANEL_SRC / "page"

# the page extras look for -> how Chainlit's built JS writes it
CHAINLIT_PAGE_PARTS: dict[str, str] = {
    "theme-toggle": 'id:"theme-toggle"',
    "side-view-content": 'id:"side-view-content"',
    "side-view-title": 'id:"side-view-title"',
    "data-panel": "data-panel",
    "data-resize-handle": "data-resize-handle",
    "chat-settings-open-modal": 'id:"chat-settings-open-modal"',
    "chat-settings": 'id:"chat-settings"',
    "confirm": 'id:"confirm"',
    "space-y-2": '("space-y-2"',  # a Settings field: label, control, help text
    'role="switch"': 'role:"switch"',
    "mode-picker-popover-": "id:`mode-picker-popover-${",
    "cmdk-item": "cmdk-item",
}
# Names the page extras own: their own elements, and the Kaggle switch id the server sends
OWN_PAGE_NAMES = re.compile(r"^(rc-|kaggle_account$)")


def _chainlit_js() -> str:
    assets = _chainlit_assets()
    files = sorted(assets.glob("index-*.js")) if assets else []
    if not files:
        pytest.skip("Chainlit's built JS (chainlit/frontend/dist/assets/index-*.js) not found")
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


def _page_sources() -> str:
    files = sorted(f for f in PAGE_SRC.glob("*") if f.suffix in (".ts", ".css") and ".test." not in f.name)
    assert files, "public/panel/src/page has no sources"
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


def _ids_looked_up(js: str) -> set[str]:
    """Element ids the page extras name: *_ID constants, getElementById calls and #id selectors."""
    constants = re.findall(r'const \w+_ID = "([^"]+)"', js)
    lookups = re.findall(r'getElementById\("([^"]+)"\)', js)
    selectors = re.findall(r"#([a-z][\w-]*)\b", js)
    return {name for name in [*constants, *lookups, *selectors] if not OWN_PAGE_NAMES.match(name)}


def _is_listed(page_id: str) -> bool:
    return any(page_id == part or (part.endswith("-") and page_id.startswith(part)) for part in CHAINLIT_PAGE_PARTS)


def test_every_page_part_the_extras_rely_on_is_in_chainlits_build():
    # Then: each listed part is still written by Chainlit's built JS; a missing one is named.
    # Demonstrates: a Chainlit upgrade that renames a part fails here, not silently in the browser.
    js = _chainlit_js()
    assert [part for part, markup in CHAINLIT_PAGE_PARTS.items() if markup not in js] == []
    # negative: a part Chainlit never writes is reported
    assert 'id:"rc-no-such-part"' not in js


def test_every_chainlit_id_the_extras_use_is_listed():
    # Then: every id the page extras look up that they don't own is in CHAINLIT_PAGE_PARTS.
    # Demonstrates: a new lookup can't skip the check above.
    unlisted = sorted(page_id for page_id in _ids_looked_up(_page_sources()) if not _is_listed(page_id))
    assert unlisted == []
    # negative: a new lookup of an unlisted Chainlit id is caught
    assert _ids_looked_up('document.getElementById("new-chainlit-id")') == {"new-chainlit-id"}
    assert not _is_listed("new-chainlit-id")


def _kaggle_button_classes() -> list[str]:
    """The shadcn Button classes the Kaggle button copies (BUTTON_BASE_CLASS and BUTTON_VARIANT_CLASS)."""
    src = (PAGE_SRC / "kaggleButton.ts").read_text(encoding="utf-8")
    block = src[src.index("const BUTTON_BASE_CLASS") : src.index("};", src.index("const BUTTON_VARIANT_CLASS"))]
    return sorted({c for text in re.findall(r'"([^"]*)"', block) for c in text.split()})


def test_the_kaggle_button_classes_exist_in_chainlits_css():
    # Then: every class of the Kaggle button is in Chainlit's built CSS (the button is drawn
    # outside the panel, so only Chainlit's stylesheet styles it).
    # Demonstrates: the button can't silently lose its look.
    classes = _kaggle_button_classes()
    assert "bg-destructive" in classes and "h-9" in classes
    assert _missing_classes(classes, _chainlit_css()) == []
