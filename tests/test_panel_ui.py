"""Static checks on the Notebook panel's front end (analyst panel shadcn refresh).

The front end has no build step and no JS test runner (plan D8), so these tests
read public/elements/Notebook.jsx and public/custom.js as text and check rules
that must hold: theme colours only, Chainlit's fonts, Tailwind classes that exist
in Chainlit's pre-built CSS, imports Chainlit exposes, and the security rules.

Plan: docs/plans/analyst-panel-shadcn-refresh-plan.md (§7). Browser checks M1-M8
are a manual checklist in docs/plans/analyst-panel-shadcn-refresh-scaffold-report.md.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PANEL = ROOT / "public" / "elements" / "Notebook.jsx"
CUSTOM_JS = ROOT / "public" / "custom.js"

# Tailwind classes the panel relies on from Chainlit's shadcn recipes (cards, menus,
# selects, hover and animation states). Each must exist in Chainlit's built CSS; classes
# written in the panel's own className attributes are checked too (_panel_tailwind_classes).
# Never list ring-2 / ring-ring / ring-offset-2: they are purged (§2.3), so the focus
# ring (AC12) is hand-written CSS.
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


def _panel() -> str:
    return PANEL.read_text(encoding="utf-8")


def _css_blocks(src: str) -> str:
    """The panel's CSS template strings plus the KERNEL colour map."""
    blocks = re.findall(r"const (?:CSS|DS_CSS) = `(.*?)`;", src, re.S)
    assert len(blocks) == 2, "expected the CSS and DS_CSS blocks"
    kernel = re.search(r"const KERNEL = \{(.*?)\};", src, re.S)
    return "\n".join(blocks) + "\n" + (kernel.group(1) if kernel else "")


def _without_allowed(css: str) -> str:
    # Hex inside url(...) (e.g. an encoded data-URI image) is not a colour rule
    return re.sub(r"url\([^)]*\)", "url()", css)


def _hex_colours(src: str) -> list[str]:
    return HEX.findall(_without_allowed(_css_blocks(src)))


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
    own = set(re.findall(r"\.([A-Za-z][\w-]*)", _css_blocks(src)))  # the panel's hand-written classes
    return {c for c in out if c not in own and not c.startswith("rc")}


def _imports(src: str) -> list[str]:
    return re.findall(r'^import .* from "([^"]+)";', src, re.M)


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


# ---- Group A: theme tokens and colours (AC1, AC5, AC8, AC9) ------------------
# Baseline: Given the panel CSS in Notebook.jsx · When the colour rules are inspected


def test_panel_css_has_no_hardcoded_hex_colours():
    # A✅1 baseline, A❌1 negative (a stray #2383e2 is reintroduced).
    # Then: no #rgb/#rrggbb literal in the CSS or DS_CSS blocks (or KERNEL map).
    # Demonstrates: every colour follows the theme.
    assert _hex_colours(_panel()) == []


def test_panel_css_allows_hex_only_in_the_documented_allowlist():
    # A✅2 edge: a hex literal in an allow-listed place (e.g. a data-URI) still passes.
    # Demonstrates: the guard is not a blanket ban.
    src = _panel().replace(
        "const CSS = `", "const CSS = `\n.x { background: url(data:image/svg+xml;utf8,%23fff); }\n", 1
    )
    assert _hex_colours(src) == []


def test_panel_defines_a_light_and_a_dark_value_for_every_semantic_colour():
    # A✅3 edge: --rc-info, --rc-warn, --rc-ok, --rc-danger each have a light value
    # on .rcnb and an override under .dark.
    # Demonstrates: status colours stay legible in both themes.
    css = _css_blocks(_panel())
    light, dark = _rule_body(css, LIGHT), _rule_body(css, DARK)
    for name in SEMANTIC_COLOURS:
        assert f"{name}:" in light, f"{name} has no light value"
    # --rc-danger too: Chainlit's dark --destructive (30% lightness) is unreadable as text
    for name in SEMANTIC_COLOURS:
        assert f"{name}:" in dark, f"{name} has no dark value"


def test_semantic_colours_are_defined_for_both_themes():
    # A❌2 negative: the .dark block is dropped, only the light value exists -> fails.
    # Demonstrates: dark mode cannot silently lose a colour.
    src = _panel()
    css = _css_blocks(src)
    dark = _rule_body(css, DARK)
    assert dark, "no .dark override block"
    stripped = src.replace(DARK + " {" + dark + "}", "")
    assert _rule_body(_css_blocks(stripped), DARK) == ""


def test_semantic_colours_are_not_taken_from_chart_tokens():
    # A❌3 negative: a status colour uses var(--chart-N) -> fails.
    # Demonstrates: chart tokens change meaning between themes (D5).
    assert "--chart-" not in _css_blocks(_panel())


# ---- Group B: fonts (AC1, D7) --------------------------------------------------
# Baseline: Given the panel CSS · When font-family declarations are inspected


def test_panel_uses_the_chainlit_font_variables():
    # B✅1 baseline, B❌1 negative (font-family: ui-sans-serif, … is reintroduced).
    # Then: every font-family is var(--font-sans), var(--font-mono) or inherit.
    # Demonstrates: the panel and the chat share a typeface.
    bad = [f for f in _font_families(_css_blocks(_panel())) if not FONT_OK.match(f)]
    assert bad == []


def test_no_font_family_is_declared_outside_the_panel():
    # B✅2 edge: public/custom.js declares no font family of its own (only var(--font-sans)).
    # Demonstrates: what remains in custom.js inherits Chainlit's font.
    bad = [f for f in _font_families(CUSTOM_JS.read_text(encoding="utf-8")) if not FONT_OK.match(f)]
    assert bad == []


def test_no_theme_json_is_added():
    # B❌2 negative: a public/theme.json appears -> fails.
    # Demonstrates: the panel cannot change the app-wide font (D7).
    assert not (ROOT / "public" / "theme.json").exists()


# ---- Group C: Tailwind classes exist in Chainlit's build (AC2-AC4, AC7) --------
# Baseline: Given TAILWIND_ALLOWLIST · When Chainlit's pre-built stylesheet is searched


def test_every_allowlisted_tailwind_class_exists_in_chainlits_css():
    # C✅1 baseline, C❌1 negative (a purged class such as shadow-xl is added).
    # Then: each class selector is found in chainlit/frontend/dist/assets/index-*.css;
    # a missing one fails, naming the class.
    # Demonstrates: no class is silently dropped by Tailwind's purge.
    css = _chainlit_css()
    classes = sorted(set(TAILWIND_ALLOWLIST) | _panel_tailwind_classes(_panel()))
    assert _missing_classes(classes, css) == []
    # C❌1: a purged class is reported by name
    assert _missing_classes(["shadow-xl", "ring-offset-2"], css) == ["shadow-xl", "ring-offset-2"]


def test_the_allowlist_is_not_empty():
    # C✅2 edge. Demonstrates: the class check actually tests something.
    assert TAILWIND_ALLOWLIST


def test_the_chainlit_css_file_is_found():
    # C❌2: when Chainlit's built CSS is missing, _chainlit_css() SKIPS with a clear
    # reason instead of failing.
    assert ".bg-card" in _chainlit_css()


# ---- Group D: imports resolvable by Chainlit's custom-element scope (AC4, AC5) --
# Baseline: Given the import statements in Notebook.jsx · When checked against Chainlit's map


def test_every_imported_module_is_exposed_by_chainlit():
    # D✅1 baseline, D❌1 negative (@/components/ui/alert-dialog is imported).
    # Then: each specifier is in Chainlit's Imports map; a missing one fails, naming it.
    # Demonstrates: the panel cannot fail with "Module not found".
    exposed = _chainlit_import_map()
    assert [m for m in _imports(_panel()) if m not in exposed] == []
    # D❌1: a module Chainlit doesn't expose is reported by name
    assert "@/components/ui/alert-dialog" not in exposed


def test_the_helper_cn_is_not_imported():
    # D✅2 edge: @/lib/utils is not imported.
    # Demonstrates: the panel does not rely on a helper it cannot have.
    assert "@/lib/utils" not in _imports(_panel())


def test_no_new_dependencies_are_added():
    # D❌2 negative: requirements.txt gains a package or a package.json appears -> fails.
    # Demonstrates: the front end stays dependency-free (D8).
    assert not (ROOT / "package.json").exists()
    assert not (ROOT / "public" / "package.json").exists()
    assert not (ROOT / "node_modules").exists()


# ---- Group E: security invariants (Security #1-#3, #6, #9) ---------------------
# Baseline: Given the two front-end files · When they are inspected for unsafe patterns


def test_panel_never_uses_dangerously_set_inner_html():
    # E✅1 baseline, E❌1 negative (raw HTML for a badge is introduced).
    # Demonstrates: catalog text stays text.
    src = _panel()
    assert "dangerouslySetInnerHTML" not in src
    assert "innerHTML" not in src
    # E❌1: the check sees it when it is added
    assert "dangerouslySetInnerHTML" in src + "<span dangerouslySetInnerHTML={{ __html: d.license }} />"


def test_every_href_still_goes_through_safe_href():
    # E✅2 baseline, E❌2 negative (a raw d.url href is used).
    # Demonstrates: javascript: URLs cannot appear.
    src = _panel()
    assert re.search(r"href=\{\w+\}", src), "the panel's links were not found"
    assert _hrefs_are_safe(src)
    # E❌2: a raw dataset URL is caught
    assert not _hrefs_are_safe(src + '<a href={d.url}>x</a>')


def test_project_names_are_rendered_as_react_text():
    # E✅3 baseline, E❌4 negative (the picker builds HTML from a name).
    # Then: no innerHTML / dangerouslySetInnerHTML near p.name; custom.js no longer
    # renders project names at all.
    # Demonstrates: the moved picker cannot inject HTML (D6).
    src = _panel()
    assert re.search(r">\{p\.name\}<", src), "the picker should render p.name as a React child"
    assert "innerHTML" not in src
    # custom.js no longer touches projects at all, so it cannot render a name as HTML
    assert not re.search(r"(?i)project", _code(CUSTOM_JS.read_text(encoding="utf-8")))


def test_no_new_external_stylesheet_or_script_is_fetched():
    # E✅4 baseline, E❌3 negative (a font CDN URL is added).
    # Demonstrates: no new supply-chain surface.
    for path in (PANEL, CUSTOM_JS):
        src = path.read_text(encoding="utf-8")
        assert _fetched_urls(src) == [], path.name
        assert "@import" not in src and "<link" not in src, path.name
    # E❌3: a font CDN would be caught
    assert _fetched_urls('@import url("https://fonts.googleapis.com/css2?family=Inter");')


def test_the_rc_event_bridge_is_gone():
    # E❌5 negative: a stale rc:switch-project / rc:create-project / rc:projects /
    # rc:projects-request name survives in either file -> fails.
    # Demonstrates: the picker move leaves no half-removed bridge behind.
    for path in (PANEL, CUSTOM_JS):
        assert not RC_EVENT.search(path.read_text(encoding="utf-8")), path.name
    assert RC_EVENT.search('const EVENT_SWITCH = "rc:switch-project";')
