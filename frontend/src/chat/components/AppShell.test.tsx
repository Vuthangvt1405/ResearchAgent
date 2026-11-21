// Layout and theme
// Baseline: Given the page after session.ready · When it renders
import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { AppShell } from "@/chat/components/AppShell";
import { START_LINE } from "@/chat/components/StartScreen";
import { CHAT_WIDTH_KEY, CHAT_WIDTH_STEP, DEFAULT_CHAT_WIDTH, MIN_CHAT_WIDTH, MIN_PANEL_WIDTH, NOTEBOOK_OPEN_KEY } from "@/chat/lib/layout";
import { THEME_KEY } from "@/chat/lib/theme";
import { renderWithChat, startChat } from "@/chat/test/renderChat";
import { readFileSync } from "node:fs";

const chat = () => screen.getByRole("main", { name: "Chat" });
const panel = () => document.querySelector("aside[aria-label='Notebook panel']") as HTMLElement;
const divider = () => screen.getByRole("separator", { name: "Resize the chat and the notebook" });
const chatWidth = () => Number.parseInt(chat().style.getPropertyValue("--chat-width"), 10);
const drag = (fromX: number, toX: number) => {
  fireEvent.pointerDown(divider(), { clientX: fromX, pointerId: 1, button: 0 });
  fireEvent.pointerMove(divider(), { clientX: toX, pointerId: 1 });
  fireEvent.pointerUp(divider(), { clientX: toX, pointerId: 1 });
};
const storedKeys = () => Array.from({ length: localStorage.length }, (_, index) => localStorage.key(index));

beforeEach(() => {
  localStorage.clear();
  document.documentElement.classList.remove("dark");
  startChat();
});

describe("Layout and theme", () => {
  it("notebook open: the panel is the focus", () => {
    // Changed: —
    // Then: the panel region is wide, the chat column narrow; the button says Hide notebook
    // Demonstrates: the notebook gets the room when open
    renderWithChat(<AppShell />);
    expect(chat().dataset.width).toBe("narrow");
    expect(panel().getAttribute("aria-hidden")).toBe("false");
    expect(panel().querySelector("#rc-panel-root")).not.toBeNull();
    expect(screen.getByRole("button", { name: /Hide notebook/ })).toBeTruthy();
  });

  it("notebook closed: a full-width chat, remembered", () => {
    // Changed: click Hide notebook, then Ctrl+\, then reload
    // Then: full chat, then open again; the last choice survives a reload; only that value is stored
    // Demonstrates: the layout follows your choice
    const first = renderWithChat(<AppShell />);
    fireEvent.click(screen.getByRole("button", { name: /Hide notebook/ }));
    expect(chat().dataset.width).toBe("full");
    expect(panel().getAttribute("aria-hidden")).toBe("true");
    expect(panel().hasAttribute("inert")).toBe(true);
    expect(screen.getByRole("button", { name: /^Notebook$/ })).toBeTruthy();
    fireEvent.keyDown(window, { key: "\\", ctrlKey: true });
    expect(chat().dataset.width).toBe("narrow");
    fireEvent.keyDown(window, { key: "\\", ctrlKey: true });
    first.unmount();
    renderWithChat(<AppShell />);
    expect(chat().dataset.width).toBe("full");
    expect(storedKeys()).toEqual([NOTEBOOK_OPEN_KEY]);
  });

  it("the theme toggle switches and is remembered", () => {
    // Changed: click the toggle
    // Then: dark class on the page; kept after a reload
    // Demonstrates: the theme follows your choice
    const first = renderWithChat(<AppShell />);
    fireEvent.click(screen.getByRole("button", { name: "Switch light or dark theme" }));
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(localStorage.getItem(THEME_KEY)).toBe("dark");
    first.unmount();
    document.documentElement.classList.remove("dark");
    renderWithChat(<AppShell />);
    expect(document.documentElement.classList.contains("dark")).toBe(true);
  });

  it("start screen shows only the logo and one line", () => {
    // Changed: no messages yet
    // Then: logo and text; message box at the bottom
    // Demonstrates: a new chat looks calm
    renderWithChat(<AppShell />);
    const main = chat();
    expect(main.textContent).toContain(START_LINE);
    expect(main.querySelectorAll("img[alt='SillyTherin']")).toHaveLength(1);
    const box = screen.getByRole("textbox", { name: "Message SillyTherin" });
    expect(main.lastElementChild?.contains(box)).toBe(true);
    expect(document.querySelector("[data-testid='message-list']")).toBeNull();
  });

  it("dragging the divider sets the chat width, remembered", () => {
    // Changed: drag the divider 150 px right, then reload
    // Then: the chat column is 150 px wider, and still after a reload
    // Demonstrates: you choose how much room each side gets
    const first = renderWithChat(<AppShell />);
    expect(chatWidth()).toBe(DEFAULT_CHAT_WIDTH);
    drag(DEFAULT_CHAT_WIDTH, DEFAULT_CHAT_WIDTH + 150);
    expect(chatWidth()).toBe(DEFAULT_CHAT_WIDTH + 150);
    expect(localStorage.getItem(CHAT_WIDTH_KEY)).toBe(String(DEFAULT_CHAT_WIDTH + 150));
    first.unmount();
    renderWithChat(<AppShell />);
    expect(chatWidth()).toBe(DEFAULT_CHAT_WIDTH + 150);
  });

  it("arrow keys move the divider", () => {
    // Changed: focus the divider, press → twice, then ← once
    // Then: the width grows two steps, then shrinks one; the divider reports its width to screen readers
    // Demonstrates: the divider works without a mouse
    renderWithChat(<AppShell />);
    divider().focus();
    fireEvent.keyDown(divider(), { key: "ArrowRight" });
    fireEvent.keyDown(divider(), { key: "ArrowRight" });
    fireEvent.keyDown(divider(), { key: "ArrowLeft" });
    expect(chatWidth()).toBe(DEFAULT_CHAT_WIDTH + CHAT_WIDTH_STEP);
    expect(divider().getAttribute("aria-valuenow")).toBe(String(DEFAULT_CHAT_WIDTH + CHAT_WIDTH_STEP));
  });

  it("the divider stops at the limits", () => {
    // Changed: drag far left, then far right
    // Then: the chat stays at least 320 px and the panel at least 360 px
    // Demonstrates: neither side can be squeezed away
    renderWithChat(<AppShell />);
    drag(DEFAULT_CHAT_WIDTH, 10);
    expect(chatWidth()).toBe(MIN_CHAT_WIDTH);
    drag(MIN_CHAT_WIDTH, 5000);
    expect(chatWidth()).toBe(window.innerWidth - MIN_PANEL_WIDTH);
  });

  it("motion stops when the system asks for less", () => {
    // Changed: read the page's styles
    // Then: a reduced-motion rule turns animations and transitions off
    // Demonstrates: motion never gets in the way of people who turn it off
    const themeCss = readFileSync("src/styles/theme.css", "utf8"); // tests run from frontend/
    const start = themeCss.indexOf("@media (prefers-reduced-motion: reduce)");
    expect(start).toBeGreaterThan(-1);
    const reduced = themeCss.slice(start);
    expect(reduced).toMatch(/animation-duration:\s*0\.01ms !important/);
    expect(reduced).toMatch(/transition-duration:\s*0\.01ms !important/);
  });
});
