// Light or dark, remembered in this browser; the first visit follows the system setting.
export type Theme = "light" | "dark";
export const THEME_KEY = "sillytherin.theme";

export function readTheme(storage: Storage, prefersDark: boolean): Theme {
  try {
    const stored = storage.getItem(THEME_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // fall back to the system's choice
  }
  return prefersDark ? "dark" : "light";
}

export function rememberTheme(storage: Storage, theme: Theme): void {
  try {
    storage.setItem(THEME_KEY, theme);
  } catch {
    // not remembered: the theme still applies to this page
  }
}

export function applyTheme(root: HTMLElement, theme: Theme): void {
  root.classList.toggle("dark", theme === "dark");
}
