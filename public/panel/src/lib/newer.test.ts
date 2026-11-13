// Group 2 — Props merge (AC3, SEC4 · unit)
// Plan: docs/plans/done/panel-react-build-plan.md §7
// Baseline: Given the stored props have version 5 and datasets_rev 3 · When setProps is called
import { describe, it, expect } from "vitest";
import { newer } from "@/lib/newer";
import { cell, dataset, props } from "@/test/fixtures";

const stored = props({ version: 5, datasets_rev: 3, cells: [cell({ source: "v5" })], datasets: [dataset({ name: "rev3" })] });

describe("Group 2 — Props merge", () => {
  it("newer_version_wins", () => {
    // ✅1 · changed: incoming version 6
    // Then: the store holds v6 · Demonstrates: fresh data is shown
    const incoming = props({ version: 6, datasets_rev: 3, cells: [cell({ source: "v6" })] });
    expect(newer(stored, incoming)).toBe(incoming);
  });

  it("newer_datasets_rev_wins_on_older_version", () => {
    // ✅2 · changed: v4, rev 4
    // Then: cells from v5, datasets from rev 4 · Demonstrates: datasets update apart from cells
    const incoming = props({ version: 4, datasets_rev: 4, cells: [cell({ source: "v4" })], datasets: [dataset({ name: "rev4" })] });
    const out = newer(stored, incoming);
    expect(out.version).toBe(5);
    expect(out.cells[0].source).toBe("v5");
    expect(out.datasets_rev).toBe(4);
    expect(out.datasets[0].name).toBe("rev4");
  });

  it("older_version_ignored", () => {
    // ❌1 · changed: v4, rev 3
    // Then: the store is unchanged · Demonstrates: late pushes can't roll back
    const incoming = props({ version: 4, datasets_rev: 3, cells: [cell({ source: "v4" })] });
    expect(newer(stored, incoming)).toBe(stored);
  });

  it("equal_version_lower_rev_keeps_datasets", () => {
    // ❌2 · changed: v5, rev 2
    // Then: the datasets are unchanged · Demonstrates: a stale dataset list never wins
    const incoming = props({ version: 5, datasets_rev: 2, datasets: [dataset({ name: "rev2" })] });
    const out = newer(stored, incoming);
    expect(out.datasets_rev).toBe(3);
    expect(out.datasets[0].name).toBe("rev3");
  });
});
