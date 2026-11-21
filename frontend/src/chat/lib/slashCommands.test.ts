// Which box text opens the "/" menu and which commands match
import { describe, expect, it, vi } from "vitest";
import { commandQueryOf, commandsMatching, type SlashCommand } from "@/chat/lib/slashCommands";

const KAGGLE: SlashCommand = { name: "kaggle", description: "Kaggle", run: vi.fn() };
const KERNELS: SlashCommand = { name: "kernels", description: "Kernels", run: vi.fn() };
const COMMANDS = [KAGGLE, KERNELS];

const namesFor = (boxText: string) => {
  const query = commandQueryOf(boxText);
  return query === null ? null : commandsMatching(COMMANDS, query).map((c) => c.name);
};

// Which text opens the menu and which commands match · unit
// Baseline: commands kaggle and kernels; text /
describe("Which text opens the menu and which commands match", () => {
  it("the slash alone matches every command", () => {
    // Changed: —
    // Then: query "", matches kaggle and kernels
    // Demonstrates: an empty box plus / shows the whole list
    expect(commandQueryOf("/")).toBe("");
    expect(namesFor("/")).toEqual(["kaggle", "kernels"]);
  });

  it("the typed letters keep only names that start with them", () => {
    // Changed: /kag
    // Then: matches kaggle
    // Demonstrates: typing narrows the list
    expect(namesFor("/kag")).toEqual(["kaggle"]);
  });

  it("matching ignores letter case", () => {
    // Changed: /KAG
    // Then: matches kaggle
    // Demonstrates: Caps Lock doesn't hide a command
    expect(namesFor("/KAG")).toEqual(["kaggle"]);
  });

  it("the full name still matches", () => {
    // Changed: /kaggle
    // Then: matches kaggle
    // Demonstrates: typing the whole name still lets you run it
    expect(namesFor("/kaggle")).toEqual(["kaggle"]);
  });

  it("a name that only contains the letters does not match", () => {
    // Changed: /ggle
    // Then: no matches
    // Demonstrates: it is starts-with, not contains
    expect(namesFor("/ggle")).toEqual([]);
  });

  it("unknown letters match nothing", () => {
    // Changed: /zzz
    // Then: no matches
    // Demonstrates: an unknown command closes the menu
    expect(namesFor("/zzz")).toEqual([]);
  });

  it("text before the slash is not a command", () => {
    // Changed: compare train/test
    // Then: query null
    // Demonstrates: a slash mid-message is text
    expect(commandQueryOf("compare train/test")).toBeNull();
  });

  it("a space before the slash is not a command", () => {
    // Changed:  /
    // Then: query null
    // Demonstrates: only a box that starts with / opens it
    expect(commandQueryOf(" /")).toBeNull();
  });

  it("a slash after a line break is not a command", () => {
    // Changed: hello + line break + /
    // Then: query null
    // Demonstrates: only the first character counts
    expect(commandQueryOf("hello\n/")).toBeNull();
  });

  it("words after the name match nothing", () => {
    // Changed: /kaggle air
    // Then: no matches
    // Demonstrates: extra words make it an ordinary message
    expect(namesFor("/kaggle air")).toEqual([]);
  });

  it("an empty box is not a command", () => {
    // Changed: empty text
    // Then: query null
    // Demonstrates: no menu before / is typed
    expect(commandQueryOf("")).toBeNull();
  });
});
