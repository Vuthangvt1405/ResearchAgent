"""Static checks on the Notebook panel's front end.

The panel is part of the React page in frontend/src/panel (built to frontend/dist). Behaviour
is tested with Vitest in frontend; these tests read the sources as text and check
rules that must hold: theme colours only, the shared font variables, pinned
dependencies, and the security rules.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL_DIR = ROOT / "frontend"
PANEL_SRC = PANEL_DIR / "src" / "panel"
PANEL_CSS = PANEL_SRC / "styles.css"
BUILD = PANEL_DIR / "dist"


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
    assert files, "frontend/src/panel has no sources"
    return files


def _panel() -> str:
    """The shim plus every panel source file, as one text."""
    return "\n".join(f.read_text(encoding="utf-8") for f in _panel_files())


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


# Code cells use Jupyter's code font, kept in one panel variable; everything else uses the page's fonts
FONT_OK = re.compile(r"^(?:.*\s)?(?:var\(--font-(?:sans|mono)\)|var\(--rc-code-font\)|inherit)$")


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
# Baseline: Given the panel CSS (frontend/src/panel/styles.css) · When the colour rules are inspected


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
    # --rc-danger too: the dark theme's --destructive (30% lightness) is unreadable as text
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


def test_panel_uses_the_shared_font_variables():
    # baseline, negative (font-family: ui-sans-serif, … is reintroduced).
    # Then: every font-family is var(--font-sans), var(--font-mono), the code-cell font or inherit.
    # Demonstrates: the panel and the chat share a typeface.
    bad = [f for f in _font_families(_css_blocks()) if not FONT_OK.match(f)]
    assert bad == []


def test_no_new_dependencies_are_added():
    # negative: a package.json appears at the repo root or in public/ -> fails.
    # npm packages are allowed only inside frontend, pinned.
    # Demonstrates: dependencies stay in one reviewed place.
    assert not (ROOT / "package.json").exists()
    assert not (ROOT / "public" / "package.json").exists()
    assert not (ROOT / "node_modules").exists()


# ---- security invariants ---------------------------------------------
# Baseline: Given the panel sources · When they are inspected for unsafe patterns


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


def test_no_new_external_stylesheet_or_script_is_fetched():
    # baseline, negative (a font CDN URL is added).
    # Demonstrates: no new supply-chain surface.
    for path in (*_panel_files(), PANEL_CSS):
        src = path.read_text(encoding="utf-8")
        assert _fetched_urls(src) == [], path.name
        assert "@import" not in src and "<link" not in src, path.name
    # negative: a font CDN would be caught
    assert _fetched_urls('@import url("https://fonts.googleapis.com/css2?family=Inter");')


def test_the_rc_event_bridge_is_gone():
    # negative: a stale rc:switch-project / rc:create-project / rc:projects /
    # rc:projects-request name survives in either file -> fails.
    # Demonstrates: the picker move leaves no half-removed bridge behind.
    for path in _panel_files():
        assert not RC_EVENT.search(path.read_text(encoding="utf-8")), path.name
    assert RC_EVENT.search('const EVENT_SWITCH = "rc:switch-project";')


# ---- bundled panel dependencies and scripts (panel React build) --
# Baseline: none (negatives only)
PANEL_PKG = PANEL_DIR / "package.json"
EXACT = re.compile(r"^\d+\.\d+\.\d+$")


def _remote_imports(js: str) -> list[str]:
    return re.findall(r"""(?:\bimport\s*\(|\bfrom\s*)["'](https?:)?//""", js)


def test_no_external_script_or_stylesheet():
    # the built page imports a remote module -> fails.
    # Then: the build loads only its own files.
    # Demonstrates: no third-party script surface.
    built = "\n".join(path.read_text(encoding="utf-8") for path in sorted((BUILD / "assets").glob("*.js")))
    assert _remote_imports(built) == []
    # a remote import would be caught
    assert _remote_imports('import("https://cdn.example.com/x.js")')


def test_lockfile_present_and_versions_pinned():
    # a ^ or ~ range in frontend/package.json -> fails.
    # Then: package-lock.json exists and every version is exact.
    # Demonstrates: reproducible builds.
    import json

    pkg = json.loads(PANEL_PKG.read_text(encoding="utf-8"))
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    assert deps, "frontend/package.json lists no dependencies"
    assert {k: v for k, v in deps.items() if not EXACT.match(v)} == {}
    lock = json.loads((PANEL_DIR / "package-lock.json").read_text(encoding="utf-8"))
    locked = lock["packages"][""]
    assert {**locked.get("dependencies", {}), **locked.get("devDependencies", {})} == deps
    assert not EXACT.match("^18.3.1") and not EXACT.match("~5.0.3")


def test_colours_and_fonts_rules_on_new_css():
    # a hex colour in frontend/src/panel/styles.css -> fails.
    # Then: the colour and font rules hold for the new CSS, and the built CSS is the same rules.
    # Demonstrates: the look is kept.
    css = PANEL_CSS.read_text(encoding="utf-8")
    assert HEX.findall(_without_allowed(css)) == []
    assert [f for f in _font_families(css) if not FONT_OK.match(f)] == []
    built = "\n".join(path.read_text(encoding="utf-8") for path in sorted((BUILD / "assets").glob("*.css")))
    assert ".rcnb" in built and "#rc-panel-root" in built
    assert HEX.findall(".x{color:#fff}")
