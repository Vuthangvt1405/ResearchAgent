// Shared test data (plan §7 baselines)
import type { CellProps, DatasetProps, NotebookProps } from "@/types";

export function dataset(over: Partial<DatasetProps> = {}): DatasetProps {
  return {
    id: "iris",
    name: "Iris",
    source: "huggingface",
    status: "ready",
    done_bytes: null,
    position_in_queue: null,
    license: "CC-BY-4.0",
    size_bytes: 1000,
    file_count: 1,
    url: "https://huggingface.co/datasets/iris",
    path: "/work/datasets/iris",
    downloaded_at: null,
    requested_at: "2026-11-13T10:00:00Z",
    files: [{ path: "iris.csv", size: 1000 }],
    error: null,
    shared_with: 0,
    ...over,
  };
}

export function cell(over: Partial<CellProps> = {}): CellProps {
  return { id: "a", type: "code", source: "print(1)", execution_count: null, status: "idle", outputs: [], ...over };
}

export function props(over: Partial<NotebookProps> = {}): NotebookProps {
  return {
    project: { id: "p1", name: "Project one" },
    version: 5,
    kernel: "idle",
    running_cell_id: null,
    cells: [cell()],
    error: null,
    datasets: [],
    datasets_rev: 3,
    ...over,
  };
}
