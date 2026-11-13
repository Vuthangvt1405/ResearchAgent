// NB-4 AC25 — a dataset other projects use says so, and deleting it here frees nothing
// Plan: docs/plans/NB-4-dataset-pool-plan.md (AC25)
// Baseline: Given a ready dataset · When its details and the delete confirm are opened
import { describe, it, expect } from "vitest";
import { act, fireEvent } from "@testing-library/react";
import { mountPanel } from "@/test/harness";
import { dataset, props } from "@/test/fixtures";
import { usePanel } from "@/store";

async function openCard(shared_with: number) {
  await mountPanel(props({ datasets_rev: 1, datasets: [dataset({ id: "iris", name: "Iris", shared_with })] }));
  await act(async () => usePanel.setState({ tab: "datasets" }));
  const card = document.querySelector('[data-dataset-id="iris"]') as HTMLElement;
  await act(async () => fireEvent.click(card.querySelector('[aria-controls="rcds-details-iris"]') as HTMLElement));
  return card;
}

const confirmDelete = async (card: HTMLElement) => {
  const button = Array.from(card.querySelectorAll("button")).find((b) => b.textContent === "Delete") as HTMLElement;
  await act(async () => fireEvent.click(button));
};

describe("NB-4 — shared datasets", () => {
  it("shared_dataset_says_who_else_uses_it", async () => {
    // ✅1 · changed: shared_with = 2 · Then: details and confirm name the other projects; frees 0 MB here
    const card = await openCard(2);
    expect(card.textContent).toContain("Also used by 2 other projects");
    await confirmDelete(card);
    expect(card.textContent).toContain("Delete Iris from this project? Also used by 2 other projects: frees 0 MB here.");
  });

  it("unshared_dataset_shows_the_space_it_frees", async () => {
    // ✅2 · changed: shared_with = 0 · Then: no "Also used by"; confirm shows the size freed
    const card = await openCard(0);
    expect(card.textContent).not.toContain("Also used by");
    await confirmDelete(card);
    expect(card.textContent).toContain("Delete Iris and free");
  });
});
