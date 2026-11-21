// Settings
// Baseline: Given the Settings window open on Tools · When Web search is switched off
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SettingsDialog } from "@/chat/components/SettingsDialog";
import type { SettingSwitch } from "@/chat/events";
import { sessionReady } from "@/chat/test/renderChat";

function open(switches: SettingSwitch[] = sessionReady().settings) {
  const onChange = vi.fn();
  render(<SettingsDialog open onOpenChange={vi.fn()} switches={switches} onChange={onChange} theme="light" onThemeChange={vi.fn()} />);
  return onChange;
}

const section = (name: string) => fireEvent.click(screen.getByRole("button", { name }));
const content = () => screen.getByRole("dialog").textContent ?? "";

describe("Settings", () => {
  it("a switch change is sent right away", () => {
    // Changed: —
    // Then: settings.update with web_search false; no Save needed
    // Demonstrates: changes apply at once
    const onChange = open();
    fireEvent.click(screen.getByRole("switch", { name: "Web search" }));
    expect(onChange).toHaveBeenCalledWith("web_search", false);
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("sections list their own settings", () => {
    // Changed: click each section
    // Then: General: theme; Answers: Show thinking; Tools: Web search, Notebook; Account: Kaggle; About: facts
    // Demonstrates: each setting has one home
    open();
    section("General");
    expect(screen.getByRole("radiogroup")).toBeTruthy();
    section("Answers");
    expect(screen.getAllByRole("switch").map((s) => s.getAttribute("aria-labelledby"))).toEqual(["setting-show_thinking"]);
    section("Tools");
    expect(screen.getAllByRole("switch").map((s) => s.getAttribute("aria-labelledby"))).toEqual(["setting-web_search", "setting-notebook"]);
    section("Account");
    expect(content()).toContain("Kaggle account");
    expect(screen.queryAllByRole("switch")).toEqual([]);
    section("About");
    expect(content()).toContain("OpenRouter");
  });

  it("a greyed switch shows why and can't change", () => {
    // Changed: a disabled row
    // Then: its reason is shown; clicking sends nothing
    // Demonstrates: you know why a feature is off
    const greyed = sessionReady().settings.map((row) =>
      row.id === "web_search" ? { ...row, initial: false, disabled: true, description: "This model can't use tools." } : row,
    );
    const onChange = open(greyed);
    expect(content()).toContain("This model can't use tools.");
    fireEvent.click(screen.getByRole("switch", { name: "Web search" }));
    expect(onChange).not.toHaveBeenCalled();
  });

  it("kaggle connect flips the account switch", () => {
    // Changed: click Connect
    // Then: settings.update with kaggle_account true
    // Demonstrates: connecting Kaggle starts from Settings
    const onChange = open();
    section("Account");
    fireEvent.click(screen.getByRole("button", { name: "Connect" }));
    expect(onChange).toHaveBeenCalledWith("kaggle_account", true);
  });
});
