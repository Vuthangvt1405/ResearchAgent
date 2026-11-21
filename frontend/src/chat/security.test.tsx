// Nothing in an answer can run
// Baseline: Given an answer whose text is the payload · When it renders
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Answer } from "@/chat/components/Answer";
import { KaggleSignInDialog } from "@/chat/components/KaggleSignInDialog";

describe("Nothing in an answer can run", () => {
  it("script tags in an answer stay text", () => {
    // Changed: <script>alert(1)</script>
    // Then: shown as text; no script element
    // Demonstrates: model output can't run code in the page
    const { container } = render(<Answer text={"Look: <script>alert(1)</script> done"} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.textContent).toContain("<script>alert(1)</script>");
  });

  it("html with handlers stays text", () => {
    // Changed: <img src=x onerror=alert(1)>
    // Then: shown as text; no img element
    // Demonstrates: no hidden handlers
    const { container } = render(<Answer text={"<img src=x onerror=alert(1)>"} />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("[onerror]")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)>");
  });

  it("javascript links are not links", () => {
    // Changed: [click](javascript:alert(1))
    // Then: plain text, no link
    // Demonstrates: links can't run script
    const { container } = render(<Answer text="[click](javascript:alert(1))" />);
    expect(container.querySelector("a")).toBeNull();
    expect(container.textContent).toContain("click");
  });

  it("links open apart from the page", () => {
    // Changed: [site](https://example.org)
    // Then: a link with target _blank and rel noopener noreferrer
    // Demonstrates: a linked site can't take over the page
    render(<Answer text="[site](https://example.org)" />);
    const link = screen.getByRole("link", { name: "site" });
    expect([link.getAttribute("href"), link.getAttribute("target"), link.getAttribute("rel")]).toEqual(["https://example.org", "_blank", "noopener noreferrer"]);
  });

  it("the sign-in pop-up opens only kaggle", () => {
    // Changed: authorize_url https://evil.example/?…
    // Then: Open Kaggle sign-in does nothing; window.open never called
    // Demonstrates: only Kaggle's sign-in can open
    const openWindow = vi.fn();
    const { rerender } = render(<KaggleSignInDialog popup={{ state: "waiting", authorizeUrl: "https://evil.example/?state=x", message: "" }} onClose={vi.fn()} openWindow={openWindow} />);
    fireEvent.click(screen.getByRole("button", { name: "Open Kaggle sign-in" }));
    expect(openWindow).not.toHaveBeenCalled();
    const kaggle = "https://www.kaggle.com/api/v1/oauth2/authorize?state=x";
    rerender(<KaggleSignInDialog popup={{ state: "waiting", authorizeUrl: kaggle, message: "" }} onClose={vi.fn()} openWindow={openWindow} />);
    fireEvent.click(screen.getByRole("button", { name: "Open Kaggle sign-in" }));
    expect(openWindow).toHaveBeenCalledWith(kaggle, "_blank", "noopener,noreferrer");
  });
});
