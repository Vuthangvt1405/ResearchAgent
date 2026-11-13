// Group S1 — Rendering stays safe (SEC1 · component + source scan)
// Plan: docs/plans/done/panel-react-build-plan.md §7
// Baseline: none (negatives only)
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import { renderMarkdown } from "@/lib/markdown";

// Every non-test source file in src/, as text (Vite's import.meta.glob)
const SOURCES = import.meta.glob(["./**/*.{ts,tsx}", "!./**/*.test.*", "!./test/**"], { query: "?raw", import: "default", eager: true }) as Record<string, string>;

describe("Group S1 — Rendering stays safe", () => {
  it("note_html_rendered_as_text", () => {
    // ❌1 · changed: the note contains <img onerror=…>
    // Then: the text shows literally, no element · Demonstrates: no XSS
    const { container } = render(<div>{renderMarkdown('hi <img src=x onerror="alert(1)">')}</div>);
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
  });

  it("javascript_link_not_linked", () => {
    // ❌2 · changed: [x](javascript:alert(1))
    // Then: plain text, no <a> · Demonstrates: safeHref holds
    const { container } = render(<div>{renderMarkdown("[x](javascript:alert(1)) and [ok](https://example.com)")}</div>);
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(1);
    expect(links[0].getAttribute("href")).toBe("https://example.com");
    expect(container.textContent).toContain("[x](javascript:alert(1))");
  });

  it("no_dangerouslySetInnerHTML_in_src", () => {
    // ❌3 · changed: grep over src/
    // Then: 0 hits · Demonstrates: rule enforced
    expect(Object.keys(SOURCES).length).toBeGreaterThan(10);
    const hits = Object.entries(SOURCES).filter(([, text]) => /dangerouslySetInnerHTML|\.innerHTML\s*=/.test(text));
    expect(hits.map(([f]) => f)).toEqual([]);
  });
});
