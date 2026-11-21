// What the server answers about the connected account's own Kaggle datasets, the window's wording,
// and how the window searches the list and writes sizes and dates.

export const LIST_MY_DATASETS_ACTION = "kg_list_my_datasets";

export type MyDatasetsState = "listed" | "not_connected" | "signed_out" | "unreachable";

/** One dataset the connected account owns, with only what the window shows */
export interface OwnedKaggleDataset {
  /** First line of the row; searched */
  title: string;
  /** "owner/slug": second line of the row; searched; what a later download uses */
  ref: string;
  /** Size column; null when Kaggle doesn't say */
  total_bytes: number | null;
  /** Licence column, as Kaggle names it; null when Kaggle doesn't say */
  licence: string | null;
  /** Updated column, ISO-8601 UTC; null when Kaggle doesn't say */
  last_updated: string | null;
}

/** The answer to LIST_MY_DATASETS_ACTION; rows only when state is "listed" */
export interface MyDatasetsAnswer {
  state: MyDatasetsState;
  /** "Connected as …"; null unless listed */
  username: string | null;
  datasets: OwnedKaggleDataset[];
  /** The list stopped at the most recently updated MAX_LISTED_DATASETS */
  is_truncated: boolean;
}

export const MAX_LISTED_DATASETS = 1000;
export const WINDOW_TITLE = "My Kaggle datasets";
export const LOADING_TEXT = "Loading your Kaggle datasets…";
export const NOT_CONNECTED_TEXT = "Connect your Kaggle account to see your datasets";
export const NO_DATASETS_TEXT = "You have no datasets on Kaggle yet.";
export const UNREACHABLE_TEXT = "Couldn't reach Kaggle. Try again.";
export const SIGNED_OUT_TEXT = "Kaggle signed you out. Connect again.";
export const TRUNCATED_TEXT = `Showing your ${MAX_LISTED_DATASETS} most recently updated datasets`;
export const PRIVACY_NOTE = "Only datasets your Kaggle account owns. The assistant isn't sent this list.";
export const SEARCH_LABEL = "Search my datasets";
export const SEARCH_PLACEHOLDER = "Search by title or name";
export const MISSING_DETAIL = "—";

const LISTING_STATES: MyDatasetsState[] = ["listed", "not_connected", "signed_out", "unreachable"];
export const UNREACHABLE_ANSWER: MyDatasetsAnswer = { state: "unreachable", username: null, datasets: [], is_truncated: false };

/** The server's answer, or "unreachable" for anything else (offline, a rejected action, a surprise shape) */
export function answerFromServer(result: unknown): MyDatasetsAnswer {
  const answer = result as Partial<MyDatasetsAnswer> | null;
  const isAnswer = !!answer && LISTING_STATES.includes(answer.state as MyDatasetsState) && Array.isArray(answer.datasets);
  if (!isAnswer) return UNREACHABLE_ANSWER;
  // rows only ever come with a listed answer, so a failure can't show an old or half list
  const datasets = answer.state === "listed" ? (answer.datasets as OwnedKaggleDataset[]) : [];
  return { state: answer.state as MyDatasetsState, username: answer.username ?? null, datasets, is_truncated: !!answer.is_truncated };
}

/** Rows whose title or owner/name contains the search text, ignoring case and surrounding spaces */
export function datasetsMatching(datasets: OwnedKaggleDataset[], searchText: string): OwnedKaggleDataset[] {
  const needle = searchText.trim().toLowerCase();
  if (!needle) return datasets;
  return datasets.filter((d) => d.title.toLowerCase().includes(needle) || d.ref.toLowerCase().includes(needle));
}

const BYTES_PER_UNIT = 1000;
const SIZE_UNITS = ["B", "KB", "MB", "GB", "TB"];

/** A size as people write it: "900 B", "48 MB", "1.2 GB" (1000-based); a dash when unknown */
export function formatDatasetSize(totalBytes: number | null): string {
  if (totalBytes === null) return MISSING_DETAIL;
  let size = totalBytes;
  let unitIndex = 0;
  while (size >= BYTES_PER_UNIT && unitIndex < SIZE_UNITS.length - 1) {
    size /= BYTES_PER_UNIT;
    unitIndex += 1;
  }
  const rounded = Math.round(size * 10) / 10;
  return `${rounded} ${SIZE_UNITS[unitIndex]}`;
}

// Written out so every browser shows "Sep", not a locale's "Sept"
const SHORT_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** A date as "12 Nov 2026" in the browser's time zone; a dash when unknown */
export function formatUpdatedDate(lastUpdated: string | null): string {
  const date = lastUpdated === null ? null : new Date(lastUpdated);
  if (date === null || Number.isNaN(date.getTime())) return MISSING_DETAIL;
  return `${date.getDate()} ${SHORT_MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}
