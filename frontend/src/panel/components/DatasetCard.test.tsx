// Progress re-renders only one card (component)
// Baseline: Given 3 datasets with one downloading at 10% · When props arrive with that dataset at 40%
import { describe, it, expect } from "vitest";
import { act, fireEvent, screen, within } from "@testing-library/react";
import { mountPanel } from "@/panel/test/harness";
import { dataset, props } from "@/panel/test/fixtures";
import { usePanel } from "@/panel/store";
import { cardRenders } from "@/panel/components/DatasetCard";

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

describe("Progress re-renders only one card", () => {
  it("progress_updates_bar", async () => {
    // Positive · changed: —
    // Then: the bar shows 40%, the badge says 40% · Demonstrates: progress is visible
    const h = await showDatasets();
    await h.push(three(40, 4));
    const bar = within(card("big")).getByRole("progressbar", { name: "Download progress" });
    expect(bar.getAttribute("aria-valuenow")).toBe("40");
    expect(within(card("big")).getByText("40%")).toBeTruthy();
  });

  it("only_changed_card_renders", async () => {
    // Positive · changed: render counters on all cards
    // Then: only the changed card +1 · Demonstrates: cheap updates
    const h = await showDatasets();
    const before = { ...cardRenders };
    await h.push(three(40, 4));
    expect(cardRenders.big).toBe(before.big + 1);
    expect(cardRenders.iris).toBe(before.iris);
    expect(cardRenders.wine).toBe(before.wine);
  });

  it("queued_shows_position", async () => {
    // Positive · changed: status queued, position 2
    // Then: 2nd in queue, bar at 0 · Demonstrates: ported behaviour
    await showDatasets(three(10, 3, { status: "queued", position_in_queue: 2 }));
    expect(within(card("big")).getByText("2nd in queue")).toBeTruthy();
    expect(within(card("big")).getByRole("progressbar").getAttribute("aria-valuenow")).toBe("0");
  });

  it("zero_size_shows_zero_percent", async () => {
    // Negative · changed: size_bytes = 0
    // Then: 0%, no NaN · Demonstrates: no divide-by-zero
    await showDatasets(three(10, 3, { size_bytes: 0 }));
    expect(within(card("big")).getByText("0%")).toBeTruthy();
    expect(card("big").textContent).not.toContain("NaN");
    void screen;
  });
});

// One list, two kinds (component)
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

describe("One list, two kinds", () => {
  it("created card shows Created by myself and no licence or source", async () => {
    // Positive · edge · changed: —
    // Then: label shown; no Licence, Source link or "Also used by" · Demonstrates: a created file has its own card layout
    await showBoth();
    const created = within(card("file-iris-csv"));
    expect(created.getByText("Created by myself")).toBeTruthy();
    expect(created.queryByText("Licence")).toBeNull();
    expect(created.queryByText("Open source page")).toBeNull();
    expect(created.queryByText(/Also used by/)).toBeNull();
    expect(created.getByText("/work/Iris.csv")).toBeTruthy();
  });

  it("downloaded card looks as before", async () => {
    // Positive · edge · changed: origin downloaded
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

// Delete warns that it's the only copy (component)
// Baseline: Given created Iris.csv listed with details open · When the user presses Delete
describe("Delete a created file", () => {
  it("created delete confirm says the app keeps no copy", async () => {
    // Positive · edge · changed: —
    // Then: text says removed for good, no other copy, can be made again · Demonstrates: the warning wording
    await showBoth();
    const created = within(card("file-iris-csv"));
    await act(async () => fireEvent.click(created.getByTitle("Delete this dataset")));
    expect(created.getByText(/removed from this project for good, and the app keeps no other copy/)).toBeTruthy();
    expect(created.getByText(/make it again by re-running the code/)).toBeTruthy();
  });

  it("cancel keeps the card", async () => {
    // Positive · edge · changed: Keep pressed
    // Then: no ds_delete call; card still there · Demonstrates: Keep cancels
    const h = await showBoth();
    const created = within(card("file-iris-csv"));
    await act(async () => fireEvent.click(created.getByTitle("Delete this dataset")));
    await act(async () => fireEvent.click(created.getByRole("button", { name: "Keep" })));
    expect(h.callAction.mock.calls.some(([a]) => a.name === "ds_delete")).toBe(false);
    expect(card("file-iris-csv")).toBeTruthy();
  });
});

// Names are shown as text (component)
// Baseline: negatives only (injection payloads), no baseline row
describe("Names are shown as text", () => {
  it("file name with html renders as text", async () => {
    // Negative · changed: name <img src=x onerror=alert(1)>.csv
    // Then: literal text, no element · Demonstrates: no XSS
    const hostile = "<img src=x onerror=alert(1)>.csv";
    await showBoth(createdIris({ name: hostile, path: `/work/${hostile}` }));
    expect(card("file-iris-csv").querySelector("img")).toBeNull();
    expect(within(card("file-iris-csv")).getAllByText(hostile).length).toBeGreaterThan(0);
  });
});

// A card for a file downloaded from a pasted link
// Baseline: Given a ready dataset with source "link", url https://example.org/data/iris.csv and no licence · When the card renders
const linkDataset = (over = {}) =>
  dataset({
    id: "link-example-org--iris-csv", name: "iris.csv", source: "link", license: null,
    url: "https://example.org/data/iris.csv", path: "/work/datasets/link-example-org--iris-csv", ...over,
  });

async function showLinkCard(d = linkDataset()) {
  await showDatasets(props({ datasets_rev: 1, datasets: [d] }));
  return card(d.id);
}

async function openDetails(el: HTMLElement) {
  await act(async () => fireEvent.click(within(el).getByRole("button", { name: /Show details/ })));
}

describe("pasted-link card", () => {
  it("shows the website host as source", async () => {
    // Then: the source label is example.org
    // Demonstrates: the user sees which website the file came from
    const el = await showLinkCard();
    expect(el.querySelector(".rcds-meta")?.textContent).toContain("example.org");
  });

  it("link licence says unknown", async () => {
    // Then: the open details show "Unknown — check the source"
    // Demonstrates: no licence is ever invented for a link
    const el = await showLinkCard();
    await openDetails(el);
    expect(within(el).getByText("Unknown — check the source")).toBeTruthy();
  });

  it("downloading with unknown size", async () => {
    // Then: while downloading with size 0 the card shows "1.2 MB of unknown size" and no percent value
    // Demonstrates: progress without a size doesn't show nonsense
    const el = await showLinkCard(linkDataset({ status: "downloading", size_bytes: 0, done_bytes: 1_200_000 }));
    expect(el.querySelector(".rcds-size")?.textContent).toBe("1.2 MB of unknown size");
    expect(within(el).getByRole("progressbar", { name: "Download progress" }).getAttribute("aria-valuenow")).toBeNull();
    expect(within(el).queryByText("0%")).toBeNull();
  });

  it("catalog licence fallback unchanged", async () => {
    // Then: a Zenodo card without a licence still says "Not stated"
    // Demonstrates: existing cards don't change
    const el = await showLinkCard(dataset({ id: "zenodo-1", source: "zenodo", license: null }));
    await openDetails(el);
    expect(within(el).getByText("Not stated")).toBeTruthy();
  });

  it("non-https url shows no host or link", async () => {
    // Then: with no url the label is "Website" and there is no source link
    // Demonstrates: unsafe links are never rendered
    const el = await showLinkCard(linkDataset({ url: null }));
    expect(el.querySelector(".rcds-meta")?.textContent).toContain("Website");
    await openDetails(el);
    expect(within(el).queryByText("Open source page")).toBeNull();
  });

  it("script-like host is shown as text", async () => {
    // Then: a name like <img onerror> is rendered as plain text, no img element
    // Demonstrates: a website can't inject markup into the panel
    const hostile = '<img src=x onerror="alert(1)">';
    const el = await showLinkCard(linkDataset({ name: hostile }));
    expect(el.querySelector("img")).toBeNull();
    expect(within(el).getAllByText(hostile).length).toBeGreaterThan(0);
  });
});

// The card shows the assistant's description (component)
// Baseline: Given a card with assistant_description "Model scores per run" · When rendered
const described = (assistant_description: string | null) =>
  dataset({ id: "results", name: "results.xls", origin: "created", source: "created", path: "/work/results.xls", assistant_description });

async function showOpenCard(d = described("Model scores per run")) {
  await showDatasets(props({ datasets_rev: 1, datasets: [d] }));
  const el = card(d.id);
  await openDetails(el);
  return el;
}

describe("The card shows the assistant's description", () => {
  it('shows "Described by the assistant" with the text', async () => {
    // Positive · changed: —
    // Then: the label and the text are visible · Demonstrates: the user sees what the assistant noted
    const el = await showOpenCard();
    expect(within(el).getByText("Described by the assistant")).toBeTruthy();
    expect(within(el).getByText("Model scores per run")).toBeTruthy();
  });

  it("shows no description line when there is none", async () => {
    // Negative · changed: assistant_description null
    // Then: no "Described by the assistant" label
    const el = await showOpenCard(described(null));
    expect(within(el).queryByText("Described by the assistant")).toBeNull();
  });

  it("renders a description with HTML as plain text", async () => {
    // Negative · changed: assistant_description '<img src=x onerror=alert(1)>'
    // Then: shown as text, no img element · Demonstrates: a description can't run code in the panel
    const hostile = "<img src=x onerror=alert(1)>";
    const el = await showOpenCard(described(hostile));
    expect(el.querySelector("img")).toBeNull();
    expect(within(el).getByText(hostile)).toBeTruthy();
  });
});
