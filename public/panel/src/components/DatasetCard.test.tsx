// Group 3 — Progress re-renders only one card (AC2 · component)
// Plan: docs/plans/done/panel-react-build-plan.md §7
// Baseline: Given 3 datasets with one downloading at 10% · When props arrive with that dataset at 40%
import { describe, it, expect } from "vitest";
import { act, fireEvent, screen, within } from "@testing-library/react";
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

// PCD-1 Group 8 — One list, two kinds (AC3 · component)
// Plan: docs/plans/PCD-1-created-datasets-plan.md §7
// Baseline: Given downloaded hf-scikit-learn--iris and created Iris.csv · When the cards render with details open
const downloadedIris = () => dataset({ id: "hf-scikit-learn--iris", name: "iris", shared_with: 2 });
const createdIris = (over = {}) =>
  dataset({
    id: "file-iris-csv", name: "Iris.csv", origin: "created", source: "created", license: null, url: null,
    path: "/work/Iris.csv", files: [{ path: "Iris.csv", size: 4551 }], size_bytes: 4551, ...over,
  });

async function showBoth(created = createdIris()) {
  const h = await showDatasets(props({ datasets_rev: 3, datasets: [downloadedIris(), created] }));
  for (const name of ["iris", created.name]) {
    await act(async () => fireEvent.click(screen.getByRole("button", { name: `Show details of ${name}` })));
  }
  return h;
}

describe("PCD-1 Group 8 — One list, two kinds", () => {
  it("created card shows Created by myself and no licence or source", async () => {
    // ✅2 · edge · changed: —
    // Then: label shown; no Licence, Source link or "Also used by" · Demonstrates: AC3
    await showBoth();
    const created = within(card("file-iris-csv"));
    expect(created.getByText("Created by myself")).toBeTruthy();
    expect(created.queryByText("Licence")).toBeNull();
    expect(created.queryByText("Open source page")).toBeNull();
    expect(created.queryByText(/Also used by/)).toBeNull();
    expect(created.getByText("/work/Iris.csv")).toBeTruthy();
  });

  it("downloaded card looks as before", async () => {
    // ✅3 · edge · changed: origin downloaded
    // Then: same text and rows as today · Demonstrates: no regression
    await showBoth();
    const downloaded = within(card("hf-scikit-learn--iris"));
    expect(downloaded.getByText("Hugging Face")).toBeTruthy();
    expect(downloaded.getByText("Licence")).toBeTruthy();
    expect(downloaded.getByText("Open source page")).toBeTruthy();
    expect(downloaded.getByText("Also used by 2 other projects")).toBeTruthy();
    expect(downloaded.getByText("/work/datasets/iris/")).toBeTruthy();
  });
});

// PCD-1 Group 9 — Delete warns that it's the only copy (AC8 · component)
// Baseline: Given created Iris.csv listed with details open · When the user presses Delete
describe("PCD-1 Group 9 — Delete a created file", () => {
  it("created delete confirm says the app keeps no copy", async () => {
    // ✅2 · edge · changed: —
    // Then: text says removed for good, no other copy, can be made again · Demonstrates: AC8 wording
    await showBoth();
    const created = within(card("file-iris-csv"));
    await act(async () => fireEvent.click(created.getByTitle("Delete this dataset")));
    expect(created.getByText(/removed from this project for good, and the app keeps no other copy/)).toBeTruthy();
    expect(created.getByText(/make it again by re-running the code/)).toBeTruthy();
  });

  it("cancel keeps the card", async () => {
    // ✅3 · edge · changed: Keep pressed
    // Then: no ds_delete call; card still there · Demonstrates: AC8 Cancel
    const h = await showBoth();
    const created = within(card("file-iris-csv"));
    await act(async () => fireEvent.click(created.getByTitle("Delete this dataset")));
    await act(async () => fireEvent.click(created.getByRole("button", { name: "Keep" })));
    expect(h.callAction.mock.calls.some(([a]) => a.name === "ds_delete")).toBe(false);
    expect(card("file-iris-csv")).toBeTruthy();
  });
});

// PCD-1 Group S3 — Names are shown as text (SEC6 · component)
// Baseline: negatives only (injection payloads), no baseline row
describe("PCD-1 Group S3 — Names are shown as text", () => {
  it("file name with html renders as text", async () => {
    // ❌1 · negative · changed: name <img src=x onerror=alert(1)>.csv
    // Then: literal text, no element · Demonstrates: no XSS
    const hostile = "<img src=x onerror=alert(1)>.csv";
    await showBoth(createdIris({ name: hostile, path: `/work/${hostile}` }));
    expect(card("file-iris-csv").querySelector("img")).toBeNull();
    expect(within(card("file-iris-csv")).getAllByText(hostile).length).toBeGreaterThan(0);
  });
});
