// Mirrors NotebookProps / DatasetProps in researchchat/workspace/service.py (plan §4.3).
// No fields are added or removed: the Python contract is unchanged.

export type CellType = "code" | "markdown";
export type CellStatus = "idle" | "queued" | "running" | "ok" | "error" | "interrupted" | "timeout" | string;

export interface OutputProps {
  kind: "stdout" | "stderr" | "result" | "error" | "image" | string;
  text: string;
  /** base64 PNG for kind == "image" */
  image?: string;
}

export interface CellProps {
  id: string;
  type: CellType;
  source: string;
  execution_count: number | null;
  status: CellStatus;
  outputs: OutputProps[];
}

export interface ErrorProps {
  code: string;
  message: string;
}

export type DatasetStatus = "queued" | "downloading" | "ready" | "failed" | "missing";

export interface DatasetFile {
  path: string;
  size: number;
}

export interface DatasetProps {
  id: string;
  name: string;
  source: string;
  status: DatasetStatus;
  /** Bytes downloaded so far; only set while downloading (drives the progress bar) */
  done_bytes: number | null;
  position_in_queue: number | null;
  license: string | null;
  size_bytes: number;
  file_count: number;
  url: string | null;
  path: string;
  downloaded_at: string | null;
  requested_at: string;
  files: DatasetFile[];
  error: string | null;
  /** Other projects using the same stored copy (NB-4); deleting here then frees nothing */
  shared_with: number;
}

export interface ProjectRef {
  id: string;
  name: string;
}

export interface NotebookProps {
  project: ProjectRef;
  /** Bumps on every notebook change; the higher one wins in newer() */
  version: number;
  kernel: "off" | "starting" | "idle" | "busy" | "dead" | "unavailable" | string;
  running_cell_id: string | null;
  cells: CellProps[];
  error: ErrorProps | null;
  datasets: DatasetProps[];
  /** Bumps on every dataset change; datasets come from the higher one (SEC16) */
  datasets_rev: number;
}

export type CallAction = (action: { name: string; payload: Record<string, unknown> }) => Promise<unknown>;

/** The 17 actions the panel sends today (AC4) */
export type ActionName =
  | "nb_add_cell" | "nb_clear_cell_outputs" | "nb_clear_outputs" | "nb_create_project"
  | "nb_delete_cell" | "nb_duplicate_cell" | "nb_interrupt" | "nb_list_projects"
  | "nb_move_cell" | "nb_reorder_cell" | "nb_restart" | "nb_run_all" | "nb_run_cell"
  | "nb_switch_project" | "nb_update_cell" | "ds_cancel" | "ds_delete";

/** A reply to an nb_* / ds_* action: new props, maybe with an error, or a project list */
export type ActionResult = (Partial<NotebookProps> & { projects?: ProjectRef[] }) | null | undefined;
