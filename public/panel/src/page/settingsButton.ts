// The Settings button, moved from the chat box to the top bar. Chainlit's own one stays
// in the chat box, hidden, and is clicked for us: that keeps its centred window and its
// own open/confirm handling.
import { createIcon } from "@/page/icons";
import { COMPOSER_SETTINGS_ID, THEME_BUTTON_ID } from "@/page/chainlitPage";
import { TOGGLE_ID } from "@/page/sidebarToggle";

export const SETTINGS_BUTTON_ID = "rc-settings-button";

function openSettings(doc: Document) {
  const composerButton = doc.getElementById(COMPOSER_SETTINGS_ID) as HTMLButtonElement | null;
  if (composerButton && !composerButton.disabled) composerButton.click();
}

export function ensureSettingsButton(doc: Document) {
  const theme = doc.getElementById(THEME_BUTTON_ID);
  const composerButton = doc.getElementById(COMPOSER_SETTINGS_ID) as HTMLButtonElement | null;
  let button = doc.getElementById(SETTINGS_BUTTON_ID) as HTMLButtonElement | null;
  if (!theme || !composerButton) {
    // No chat settings on screen (e.g. before a chat starts): no button
    button?.remove();
    return;
  }
  // Sits left of the notebook toggle when there is one, else left of the theme button
  const anchor = doc.getElementById(TOGGLE_ID) || theme;
  if (button && button.nextElementSibling === anchor) {
    button.disabled = composerButton.disabled; // greyed while an answer is being written, like Chainlit's
    return;
  }
  button?.remove();
  button = doc.createElement("button");
  button.id = SETTINGS_BUTTON_ID;
  button.type = "button";
  button.className = theme.className;
  button.title = "Settings";
  button.setAttribute("aria-label", "Settings");
  button.appendChild(createIcon(doc, "settings", 18));
  button.disabled = composerButton.disabled;
  button.addEventListener("click", () => openSettings(doc));
  anchor.insertAdjacentElement("beforebegin", button);
}
