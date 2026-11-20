// Page-level extras around Chainlit's UI
// Baseline: Given a page with Chainlit's own markup (top bar, sidebar, Settings, Model picker)
// · When the extras run over it
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { startPageExtras, refreshPageExtras } from "@/page";
import { COLLAPSED_CLASS, TOGGLE_ID } from "@/page/sidebarToggle";
import { SETTINGS_BUTTON_ID } from "@/page/settingsButton";
import { HIDDEN_ATTR, MODEL_EMPTY_ID, MODEL_SEARCH_ID } from "@/page/modelSearch";
import { KAGGLE_BUTTON_ID, KAGGLE_CONNECT_LABEL, KAGGLE_DISCONNECT_LABEL } from "@/page/kaggleButton";

function topBar({ withSidebar = true, withComposerSettings = true } = {}) {
  document.body.innerHTML = "";
  const bar = document.createElement("div");
  const theme = document.createElement("button");
  theme.id = "theme-toggle";
  theme.className = "chainlit-topbar-button";
  bar.appendChild(theme);
  document.body.appendChild(bar);
  if (withSidebar) {
    const sidebar = document.createElement("div");
    sidebar.id = "side-view-content";
    document.body.appendChild(sidebar);
  }
  if (withComposerSettings) {
    const composer = document.createElement("button");
    composer.id = "chat-settings-open-modal";
    document.body.appendChild(composer);
  }
  return theme;
}

function settingsWithKaggleSwitch(isOn: boolean) {
  const modal = document.createElement("div");
  modal.id = "chat-settings";
  const toggle = document.createElement("button");
  toggle.id = "kaggle_account";
  toggle.setAttribute("role", "switch");
  toggle.setAttribute("aria-checked", String(isOn));
  // Plays Chainlit's switch: a click flips aria-checked
  toggle.addEventListener("click", () => toggle.setAttribute("aria-checked", String(toggle.getAttribute("aria-checked") !== "true")));
  const confirm = document.createElement("button");
  confirm.id = "confirm";
  modal.append(toggle, confirm);
  document.body.appendChild(modal);
  return { toggle, confirm };
}

function modelPicker(names: string[]) {
  const popover = document.createElement("div");
  popover.id = "mode-picker-popover-model";
  for (const name of names) {
    const item = document.createElement("div");
    item.setAttribute("cmdk-item", "");
    item.textContent = name;
    popover.appendChild(item);
  }
  document.body.appendChild(popover);
  return popover;
}

const typeInto = (input: HTMLInputElement, text: string) => {
  input.value = text;
  input.dispatchEvent(new Event("input"));
};

// jsdom's blank page has no localStorage; an in-memory one plays the browser's
function memoryStorage(): Storage {
  const items = new Map<string, string>();
  return {
    get length() { return items.size; },
    clear: () => items.clear(),
    getItem: (key) => items.get(key) ?? null,
    key: (index) => Array.from(items.keys())[index] ?? null,
    removeItem: (key) => void items.delete(key),
    setItem: (key, value) => void items.set(key, String(value)),
  };
}

beforeEach(() => {
  Object.defineProperty(window, "localStorage", { value: memoryStorage(), configurable: true });
  document.documentElement.className = "";
});

afterEach(() => {
  vi.useRealTimers();
});

describe("Sidebar toggle", () => {
  it("sits left of the theme button while a sidebar is shown", () => {
    const theme = topBar();
    refreshPageExtras(document);
    const toggle = document.getElementById(TOGGLE_ID)!;
    expect(toggle.nextElementSibling).toBe(theme);
    expect(toggle.className).toBe(theme.className);
    expect(toggle.getAttribute("aria-label")).toBe("Hide notebook (Ctrl+\\)");
  });

  it("is removed when there is no sidebar", () => {
    topBar();
    refreshPageExtras(document);
    document.getElementById("side-view-content")!.remove();
    refreshPageExtras(document);
    expect(document.getElementById(TOGGLE_ID)).toBeNull();
  });

  it("a click collapses the sidebar and the choice is remembered", () => {
    topBar();
    refreshPageExtras(document);
    document.getElementById(TOGGLE_ID)!.click();
    expect(document.documentElement.classList.contains(COLLAPSED_CLASS)).toBe(true);
    expect(localStorage.getItem("rc-notebook-collapsed")).toBe("1");
    expect(document.getElementById(TOGGLE_ID)!.getAttribute("aria-label")).toBe("Show notebook (Ctrl+\\)");
  });

  it("Ctrl+\\ toggles it, and a remembered choice is applied on start", () => {
    localStorage.setItem("rc-notebook-collapsed", "1");
    topBar();
    const stop = startPageExtras(window);
    expect(document.documentElement.classList.contains(COLLAPSED_CLASS)).toBe(true);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "\\", ctrlKey: true }));
    expect(document.documentElement.classList.contains(COLLAPSED_CLASS)).toBe(false);
    stop();
  });
});

describe("Settings button", () => {
  it("opens Chainlit's own Settings window", () => {
    topBar();
    const composer = document.getElementById("chat-settings-open-modal")!;
    const opened = vi.fn();
    composer.addEventListener("click", opened);
    refreshPageExtras(document);
    const settings = document.getElementById(SETTINGS_BUTTON_ID)!;
    expect(settings.nextElementSibling?.id).toBe(TOGGLE_ID);
    settings.click();
    expect(opened).toHaveBeenCalledOnce();
  });

  it("is greyed out while Chainlit's is", () => {
    topBar();
    const composer = document.getElementById("chat-settings-open-modal") as HTMLButtonElement;
    composer.disabled = true;
    refreshPageExtras(document);
    expect((document.getElementById(SETTINGS_BUTTON_ID) as HTMLButtonElement).disabled).toBe(true);
  });

  it("is not shown before a chat has settings", () => {
    topBar({ withComposerSettings: false });
    refreshPageExtras(document);
    expect(document.getElementById(SETTINGS_BUTTON_ID)).toBeNull();
  });
});

describe("Model picker search", () => {
  it("hides models that don't match every word, and says when none do", () => {
    const popover = modelPicker(["anthropic/claude-sonnet", "openai/gpt-5", "anthropic/claude-haiku"]);
    refreshPageExtras(document);
    const search = document.getElementById(MODEL_SEARCH_ID) as HTMLInputElement;
    typeInto(search, "claude haiku");
    const shown = Array.from(popover.querySelectorAll("[cmdk-item]")).filter((item) => !item.hasAttribute(HIDDEN_ATTR));
    expect(shown.map((item) => item.textContent)).toEqual(["anthropic/claude-haiku"]);
    typeInto(search, "zzz");
    expect(document.getElementById(MODEL_EMPTY_ID)?.textContent).toBe("No model matches");
  });

  it("Enter picks the first match", () => {
    const popover = modelPicker(["openai/gpt-5", "anthropic/claude-haiku"]);
    refreshPageExtras(document);
    const picked = vi.fn();
    popover.querySelectorAll("[cmdk-item]")[1].addEventListener("click", picked);
    const search = document.getElementById(MODEL_SEARCH_ID) as HTMLInputElement;
    typeInto(search, "claude");
    search.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    expect(picked).toHaveBeenCalledOnce();
  });
});

describe("Kaggle button in Settings", () => {
  it("says Connect Kaggle when the switch is off and Disconnect when on, red both times", () => {
    const { toggle } = settingsWithKaggleSwitch(false);
    refreshPageExtras(document);
    const button = document.getElementById(KAGGLE_BUTTON_ID)!;
    expect(button.previousElementSibling).toBe(toggle);
    expect(button.textContent).toBe(KAGGLE_CONNECT_LABEL);
    expect(button.className).toContain("bg-destructive");
    toggle.setAttribute("aria-checked", "true");
    refreshPageExtras(document);
    expect(button.textContent).toBe(KAGGLE_DISCONNECT_LABEL);
    expect(button.className).toContain("bg-destructive");
  });

  it("a click flips the switch, then presses Confirm", () => {
    vi.useFakeTimers();
    const { toggle, confirm } = settingsWithKaggleSwitch(false);
    const confirmed = vi.fn(() => expect(toggle.getAttribute("aria-checked")).toBe("true"));
    confirm.addEventListener("click", confirmed);
    refreshPageExtras(document);
    document.getElementById(KAGGLE_BUTTON_ID)!.click();
    expect(confirmed).not.toHaveBeenCalled();
    vi.runAllTimers();
    expect(confirmed).toHaveBeenCalledOnce();
  });

  it("does nothing while the switch is disabled", () => {
    vi.useFakeTimers();
    const { toggle, confirm } = settingsWithKaggleSwitch(false);
    toggle.disabled = true;
    const confirmed = vi.fn();
    confirm.addEventListener("click", confirmed);
    refreshPageExtras(document);
    const button = document.getElementById(KAGGLE_BUTTON_ID) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    button.click();
    vi.runAllTimers();
    expect(confirmed).not.toHaveBeenCalled();
  });

  it("is not drawn when Settings has no Kaggle switch", () => {
    topBar();
    refreshPageExtras(document);
    expect(document.getElementById(KAGGLE_BUTTON_ID)).toBeNull();
  });
});
