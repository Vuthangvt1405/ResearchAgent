// Searching the Kaggle list and how sizes and dates read
import { describe, expect, it } from "vitest";
import { datasetsMatching, formatDatasetSize, formatUpdatedDate, MISSING_DETAIL, type OwnedKaggleDataset } from "@/chat/lib/kaggleDatasets";

const dataset = (title: string, ref: string): OwnedKaggleDataset => ({ title, ref, total_bytes: 1000, licence: "CC0", last_updated: "2026-11-12T08:30:00Z" });
const DATASETS = [
  dataset("Vietnam air quality, daily", "ana/vietnam-air-quality-daily"),
  dataset("Hanoi traffic counts 2025", "ana/hanoi-traffic-counts-2025"),
  dataset("Household energy survey", "ana/household-energy-survey"),
];
const titlesFor = (searchText: string) => datasetsMatching(DATASETS, searchText).map((d) => d.title);

// Search and how values read · unit
// Baseline: three datasets: Vietnam air quality, daily; Hanoi traffic counts 2025; Household energy survey
describe("Search and how values read", () => {
  it("search keeps rows whose title contains the text", () => {
    // Changed: traffic
    // Then: one row
    // Demonstrates: you find a dataset by its title
    expect(titlesFor("traffic")).toEqual(["Hanoi traffic counts 2025"]);
  });

  it("search matches the owner and name too", () => {
    // Changed: energy-survey
    // Then: one row
    // Demonstrates: you find a dataset by its owner/name
    expect(titlesFor("energy-survey")).toEqual(["Household energy survey"]);
  });

  it("search ignores case and surrounding spaces", () => {
    // Changed:   HANOI
    // Then: one row
    // Demonstrates: sloppy typing still finds it
    expect(titlesFor("  HANOI ")).toEqual(["Hanoi traffic counts 2025"]);
  });

  it("an empty search keeps every row", () => {
    // Changed: empty search
    // Then: all three rows
    // Demonstrates: clearing the search shows everything
    expect(titlesFor("")).toHaveLength(3);
    expect(titlesFor("   ")).toHaveLength(3);
  });

  it("sizes read as people write them", () => {
    // Changed: 900, 48 000 000 and 1 200 000 000 bytes
    // Then: 900 B, 48 MB, 1.2 GB
    // Demonstrates: sizes are readable at a glance
    expect([900, 48_000_000, 1_200_000_000, 6_500].map(formatDatasetSize)).toEqual(["900 B", "48 MB", "1.2 GB", "6.5 KB"]);
  });

  it("dates read as day month year", () => {
    // Changed: 2026-11-12T08:30:00Z
    // Then: 12 Nov 2026
    // Demonstrates: dates are readable at a glance
    expect(formatUpdatedDate("2026-11-12T08:30:00Z")).toBe("12 Nov 2026");
  });

  it("a search that matches nothing keeps no rows", () => {
    // Changed: zzz
    // Then: no rows
    // Demonstrates: an unmatched search shows nothing
    expect(titlesFor("zzz")).toEqual([]);
  });

  it("a missing size licence or date shows a dash", () => {
    // Changed: null size, licence and date
    // Then: the dash for each
    // Demonstrates: nothing is made up
    expect(formatDatasetSize(null)).toBe(MISSING_DETAIL);
    expect(formatUpdatedDate(null)).toBe(MISSING_DETAIL);
    expect(formatUpdatedDate("not a date")).toBe(MISSING_DETAIL);
  });
});
