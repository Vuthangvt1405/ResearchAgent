// A search box in the chat box Model picker. Chainlit's picker is a plain list with no
// search (OpenRouter has hundreds of models), so the box is added to its popover and
// hides the items that don't match.
import { MODEL_POPOVER_ID } from "@/page/chainlitPage";

export const MODEL_SEARCH_ID = "rc-model-search";
export const MODEL_EMPTY_ID = "rc-model-search-empty";
// An attribute, not a class, so React's re-renders don't undo it
export const HIDDEN_ATTR = "data-rc-hidden";

function modelItems(popover: HTMLElement): HTMLElement[] {
  return Array.from(popover.querySelectorAll<HTMLElement>("[cmdk-item]"));
}

export function filterModels(popover: HTMLElement, query: string) {
  const doc = popover.ownerDocument;
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  let shown = 0;
  for (const item of modelItems(popover)) {
    const text = (item.textContent || "").toLowerCase();
    const matches = words.every((word) => text.includes(word));
    item.toggleAttribute(HIDDEN_ATTR, !matches);
    if (matches) shown += 1;
  }
  let empty = doc.getElementById(MODEL_EMPTY_ID);
  if (shown === 0 && !empty) {
    empty = doc.createElement("div");
    empty.id = MODEL_EMPTY_ID;
    empty.textContent = "No model matches";
    popover.appendChild(empty);
  } else if (shown > 0 && empty) {
    empty.remove();
  }
}

function pickFirstMatch(popover: HTMLElement) {
  const first = modelItems(popover).find((item) => !item.hasAttribute(HIDDEN_ATTR));
  first?.click();
}

function onSearchKey(e: KeyboardEvent, popover: HTMLElement) {
  if (e.key === "Escape") return; // let the picker close as usual
  // The picker's own arrow and Enter keys count hidden items too, so keep them out of here
  e.stopPropagation();
  if (e.key === "Enter") {
    e.preventDefault();
    pickFirstMatch(popover);
  }
}

export function ensureModelSearch(doc: Document) {
  const popover = doc.getElementById(MODEL_POPOVER_ID);
  if (!popover) return;
  const existing = doc.getElementById(MODEL_SEARCH_ID) as HTMLInputElement | null;
  if (existing && popover.contains(existing)) {
    filterModels(popover, existing.value); // items re-drawn by Chainlit get the same filter
    return;
  }
  const input = doc.createElement("input");
  input.id = MODEL_SEARCH_ID;
  input.type = "search";
  input.placeholder = "Search models…";
  input.setAttribute("aria-label", "Search models");
  input.autocomplete = "off";
  input.addEventListener("input", () => filterModels(popover, input.value));
  input.addEventListener("keydown", (e) => onSearchKey(e, popover));
  popover.insertAdjacentElement("afterbegin", input);
  setTimeout(() => input.focus(), 0);
}
