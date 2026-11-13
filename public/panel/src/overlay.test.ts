// Group 1 — The root survives Chainlit remounts (AC1, AC6, AC10 · integration)
// Plan: docs/plans/done/panel-react-build-plan.md §7
// Baseline: Given the app is attached with props v1 and a DatasetCard is open · When the shim is unmounted and a new shim mounts with props v2
import { describe, it, expect, vi, afterEach } from "vitest";
import { act, fireEvent, screen } from "@testing-library/react";
import { mountPanel, panelRoot } from "@/test/harness";
import { cell, dataset, props } from "@/test/fixtures";
import { usePanel } from "@/store";
import { createOverlay, HIDE_GRACE_MS } from "@/overlay";

const v = (version: number, over = {}) =>
  props({ version, datasets_rev: version, datasets: [dataset({ id: "iris", name: "Iris" }), dataset({ id: "wine", name: "Wine" })], ...over });

async function openIrisCard() {
  await act(async () => usePanel.setState({ tab: "datasets" }));
  fireEvent.click(screen.getByRole("button", { name: "Show details of Iris" }));
}


afterEach(() => vi.useRealTimers());

describe("Group 1 — The root survives Chainlit remounts", () => {
  it("keeps_card_open_across_remount", async () => {
    // ✅1 · changed: —
    // Then: the card is still open; the panel DOM node is the same one (mounted once)
    // Demonstrates: a push no longer resets UI state
    const h = await mountPanel(v(1));
    await openIrisCard();
    const page = panelRoot().querySelector(".rcnb");
    await h.push(v(2));
    expect(screen.getByRole("button", { name: "Hide details of Iris" })).toBeTruthy();
    expect(panelRoot().querySelector(".rcnb")).toBe(page);
  });

  it("keeps_select_open_across_remount", async () => {
    // ✅2 · changed: the sort Select is open
    // Then: it stays open, with no animation replay · Demonstrates: Radix overlays survive
    const h = await mountPanel(v(1));
    await act(async () => usePanel.setState({ tab: "datasets" }));
    const trigger = screen.getByRole("combobox", { name: "Sort datasets" });
    await act(async () => {
      fireEvent.keyDown(trigger, { key: "Enter" });
    });
    const listbox = screen.getByRole("listbox");
    await h.push(v(2));
    expect(screen.getByRole("listbox")).toBe(listbox);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
  });

  it("ten_remounts_mount_once", async () => {
    // ✅3 · changed: 10 remounts in a row
    // Then: the component mounted once · Demonstrates: no leak from repeated attach/detach
    const h = await mountPanel(v(1));
    const page = panelRoot().querySelector(".rcnb");
    for (let i = 2; i <= 11; i++) await h.push(v(i));
    expect(panelRoot().querySelector(".rcnb")).toBe(page);
    expect(document.querySelectorAll("#rc-panel-root")).toHaveLength(1);
    expect(h.sidebar.querySelectorAll("[data-rc-panel-slot]")).toHaveLength(1);
  });

  it("root_parent_never_changes", async () => {
    // ✅4 (revised by D9) · changed: 10 remounts
    // Then: #rc-panel-root stays in the same side-view container every time, never re-appended
    // Demonstrates: the app DOM is never moved by a push
    const h = await mountPanel(v(1));
    const root = panelRoot();
    expect(root.parentNode).toBe(h.sidebar);
    let moves = 0;
    root.addEventListener("rc-panel-moved", () => moves++);
    for (let i = 2; i <= 11; i++) {
      await h.push(v(i));
      expect(panelRoot()).toBe(root);
      expect(root.parentNode).toBe(h.sidebar);
    }
    expect(moves).toBe(0);
  });

  it("moves_only_when_container_changes", () => {
    // ✅5 (revised by D9) · changed: the slot shows up in a new side-view container (phone sheet)
    // Then: the root moves there once and fires rc-panel-moved · Demonstrates: phone and desktop both work
    document.body.innerHTML = "";
    const overlay = createOverlay(document);
    const desk = Object.assign(document.createElement("div"), { id: "side-view-content" });
    const a = document.createElement("div");
    desk.appendChild(a);
    document.body.appendChild(desk);
    overlay.attach(a);
    expect(overlay.root.parentNode).toBe(desk);
    desk.remove();
    const sheet = Object.assign(document.createElement("div"), { id: "side-view-content" });
    sheet.setAttribute("role", "dialog");
    const b = document.createElement("div");
    sheet.appendChild(b);
    document.body.appendChild(sheet);
    let moved = 0;
    overlay.root.addEventListener("rc-panel-moved", () => moved++);
    overlay.detach(a);
    overlay.attach(b);
    expect(overlay.root.parentNode).toBe(sheet);
    expect(moved).toBe(1);
    expect(overlay.root.hidden).toBe(false);
  });

  it("project_switch_resets_project_state", async () => {
    // ❌1 · changed: props v2 has a different project.id
    // Then: drafts and open cards are cleared · Demonstrates: no state leaks between projects
    const h = await mountPanel(v(1));
    await openIrisCard();
    await act(async () => usePanel.setState({ drafts: { a: "unsaved" } }));
    await h.push(v(1, { project: { id: "p2", name: "Project two" } }));
    expect(usePanel.getState().drafts).toEqual({});
    expect(usePanel.getState().dsOpen).toEqual({});
    expect(usePanel.getState().nb?.project.id).toBe("p2");
  });

  it("project_switch_clears_find", async () => {
    // ❌1 extra (AC6): the find box was open with a query
    // Then: the new project opens unfiltered · Demonstrates: the old switchProject reset is kept
    const h = await mountPanel(v(1));
    fireEvent.click(screen.getByRole("button", { name: "Find" }));
    await act(async () => {
      fireEvent.change(screen.getByRole("textbox", { name: "Find in notebook" }), { target: { value: "zzz" } });
    });
    await h.push(v(1, { project: { id: "p2", name: "Project two" } }));
    expect(screen.queryByRole("textbox", { name: "Find in notebook" })).toBeNull();
  });

  it("detach_without_attach_is_noop", () => {
    // ❌2 · changed: detach is called before any attach
    // Then: no throw, no DOM change · Demonstrates: safe ordering
    document.body.innerHTML = "";
    const overlay = createOverlay(document);
    const before = document.body.innerHTML;
    expect(() => overlay.detach(document.createElement("div"))).not.toThrow();
    expect(document.body.innerHTML).toBe(before);
  });

  it("hides_when_slot_gone_over_300ms", async () => {
    // ❌3 · changed: no slot for 400 ms (sidebar closed)
    // Then: overlay hidden, state kept · Demonstrates: it doesn't float over the chat
    vi.useFakeTimers();
    document.body.innerHTML = "";
    const overlay = createOverlay(document);
    const a = document.createElement("div");
    document.body.append(a);
    overlay.attach(a);
    a.remove();
    overlay.detach(a);
    vi.advanceTimersByTime(HIDE_GRACE_MS - 10);
    expect(overlay.root.hidden).toBe(false);
    vi.advanceTimersByTime(110);
    expect(overlay.root.hidden).toBe(true);
    expect(overlay.root.isConnected).toBe(true); // hidden, not removed: React state is kept
  });

  it("stays_visible_during_quick_swap", () => {
    // ❌4 · changed: the new slot arrives after 50 ms
    // Then: no hide or flicker · Demonstrates: pushes don't blink
    vi.useFakeTimers();
    document.body.innerHTML = "";
    const overlay = createOverlay(document);
    const a = document.createElement("div");
    const b = document.createElement("div");
    document.body.append(a);
    overlay.attach(a);
    const seen: boolean[] = [];
    new MutationObserver(() => seen.push(overlay.root.hidden)).observe(overlay.root, { attributes: true, attributeFilter: ["hidden"] });
    a.remove();
    overlay.detach(a);
    vi.advanceTimersByTime(50);
    document.body.append(b);
    overlay.attach(b);
    vi.advanceTimersByTime(1000);
    expect(overlay.root.hidden).toBe(false);
    expect(seen).not.toContain(true);
  });

});
