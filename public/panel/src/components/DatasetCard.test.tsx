// Group 3 — Progress re-renders only one card (AC2 · component)
// Plan: docs/plans/done/panel-react-build-plan.md §7
// Baseline: Given 3 datasets with one downloading at 10% · When props arrive with that dataset at 40%
import { describe, it, expect } from "vitest";
import { act, screen, within } from "@testing-library/react";
import { mountPanel } from "@/test/harness";
import { dataset, props } from "@/test/fixtures";
import { usePanel } from "@/store";
import { cardRenders } from "@/components/DatasetCard";

const three = (pct: number, rev: number, over = {}) =>
  props({
    datasets_rev: rev,
    datasets: [
      dataset({ id: "big", name: "Big", status: "downloading", size_bytes: 1000, done_bytes: pct * 10, ...over }),
      dataset({ id: "iris", name: "Iris" }),
      dataset({ id: "wine", name: "Wine" }),
    ],
  });

async function showDatasets(first = three(10, 3)) {
  const h = await mountPanel(first);
  await act(async () => usePanel.setState({ tab: "datasets" }));
  return h;
}

const card = (id: string) => document.querySelector(`[data-dataset-id="${id}"]`) as HTMLElement;

describe("Group 3 — Progress re-renders only one card", () => {
  it("progress_updates_bar", async () => {
    // ✅1 · changed: —
    // Then: the bar shows 40%, the badge says 40% · Demonstrates: progress is visible
    const h = await showDatasets();
    await h.push(three(40, 4));
    const bar = within(card("big")).getByRole("progressbar", { name: "Download progress" });
    expect(bar.getAttribute("aria-valuenow")).toBe("40");
    expect(within(card("big")).getByText("40%")).toBeTruthy();
  });

  it("only_changed_card_renders", async () => {
    // ✅2 · changed: render counters on all cards
    // Then: only the changed card +1 · Demonstrates: cheap updates
    const h = await showDatasets();
    const before = { ...cardRenders };
    await h.push(three(40, 4));
    expect(cardRenders.big).toBe(before.big + 1);
    expect(cardRenders.iris).toBe(before.iris);
    expect(cardRenders.wine).toBe(before.wine);
  });

  it("queued_shows_position", async () => {
    // ✅3 · changed: status queued, position 2
    // Then: 2nd in queue, bar at 0 · Demonstrates: ported behaviour
    await showDatasets(three(10, 3, { status: "queued", position_in_queue: 2 }));
    expect(within(card("big")).getByText("2nd in queue")).toBeTruthy();
    expect(within(card("big")).getByRole("progressbar").getAttribute("aria-valuenow")).toBe("0");
  });

  it("zero_size_shows_zero_percent", async () => {
    // ❌1 · changed: size_bytes = 0
    // Then: 0%, no NaN · Demonstrates: no divide-by-zero
    await showDatasets(three(10, 3, { size_bytes: 0 }));
    expect(within(card("big")).getByText("0%")).toBeTruthy();
    expect(card("big").textContent).not.toContain("NaN");
    void screen;
  });
});
