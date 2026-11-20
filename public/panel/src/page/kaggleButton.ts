// The Kaggle account button in Settings. Chainlit's Settings has no button widget, so the
// server sends a switch (researchchat/workspace/kaggle/settings_switch.py). The switch
// stays in the page, hidden, and the button flips it and presses Confirm: the server
// then connects or disconnects exactly as it does for the switch.
import { SETTINGS_CONFIRM_ID, SETTINGS_MODAL_ID } from "@/page/chainlitPage";

export const KAGGLE_SWITCH_ID = "kaggle_account";
export const KAGGLE_BUTTON_ID = "rc-kaggle-account-button";
export const KAGGLE_CONNECT_LABEL = "Connect Kaggle";
export const KAGGLE_DISCONNECT_LABEL = "Disconnect";

// The same classes as Chainlit's own shadcn Button (size "sm"), so its stylesheet already
// has them (tests/test_panel_ui.py checks each one)
const BUTTON_BASE_CLASS =
  "inline-flex items-center justify-center gap-2 whitespace-nowrap text-sm font-medium ring-offset-background " +
  "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring " +
  "focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 h-9 rounded-md px-3";
// Red in both states (shadcn's destructive variant), so the account button stands apart
const BUTTON_RED_CLASS = "bg-destructive text-destructive-foreground hover:bg-destructive/90";

function kaggleSwitch(doc: Document): HTMLButtonElement | null {
  return doc.querySelector(`#${SETTINGS_MODAL_ID} #${KAGGLE_SWITCH_ID}[role="switch"]`);
}

function isSwitchOn(toggle: HTMLElement): boolean {
  return toggle.getAttribute("aria-checked") === "true";
}

function renderKaggleButton(button: HTMLButtonElement, toggle: HTMLButtonElement) {
  const label = isSwitchOn(toggle) ? KAGGLE_DISCONNECT_LABEL : KAGGLE_CONNECT_LABEL;
  // Writing unchanged text still counts as a page change and would wake the observer again
  if (button.textContent !== label) button.textContent = label;
  button.className = `${BUTTON_BASE_CLASS} ${BUTTON_RED_CLASS}`;
  button.disabled = toggle.disabled;
}

function confirmSettings(doc: Document) {
  const confirm = doc.querySelector<HTMLButtonElement>(`#${SETTINGS_MODAL_ID} #${SETTINGS_CONFIRM_ID}`);
  confirm?.click();
}

function flipKaggleSwitchAndConfirm(doc: Document) {
  const toggle = kaggleSwitch(doc);
  if (!toggle || toggle.disabled) return;
  toggle.click();
  // Confirm after React has stored the switch's new value, so the server sees the change
  setTimeout(() => confirmSettings(doc), 0);
}

export function ensureKaggleButton(doc: Document) {
  const toggle = kaggleSwitch(doc);
  if (!toggle) return;
  let button = doc.getElementById(KAGGLE_BUTTON_ID) as HTMLButtonElement | null;
  if (!button || button.previousElementSibling !== toggle) {
    button?.remove();
    button = doc.createElement("button");
    button.id = KAGGLE_BUTTON_ID;
    button.type = "button";
    button.addEventListener("click", () => flipKaggleSwitchAndConfirm(doc));
    toggle.insertAdjacentElement("afterend", button);
  }
  renderKaggleButton(button, toggle);
}
