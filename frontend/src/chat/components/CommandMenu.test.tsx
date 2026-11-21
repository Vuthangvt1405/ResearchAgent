// The "/" command menu in the message box
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/chat/components/AppShell";
import { Composer } from "@/chat/components/Composer";
import { KAGGLE_COMMAND_DESCRIPTION, slashCommandsFor, type SlashCommand } from "@/chat/lib/slashCommands";
import { useChat } from "@/chat/store";
import { fakeSender, renderWithChat, startChat } from "@/chat/test/renderChat";

const box = () => screen.getByRole("textbox", { name: "Message SillyTherin" }) as HTMLTextAreaElement;
const type = (text: string) => fireEvent.change(box(), { target: { value: text } });
const press = (key: string, over: Partial<KeyboardEventInit> = {}) => fireEvent.keyDown(box(), { key, ...over });
const menu = () => screen.queryByRole("listbox", { name: "Commands" });
const rows = () => within(menu() as HTMLElement).getAllByRole("option");
const selectedRow = () => rows().findIndex((row) => row.getAttribute("aria-selected") === "true");

function twoCommands(): [SlashCommand, SlashCommand] {
  return [
    { name: "kaggle", description: "Show my Kaggle datasets", run: vi.fn() },
    { name: "kernels", description: "Manage kernels", run: vi.fn() },
  ];
}

function renderBox(commands: SlashCommand[] | undefined, isStreaming = false) {
  const onSend = vi.fn(() => true);
  const onStop = vi.fn();
  render(<Composer isStreaming={isStreaming} onSend={onSend} onStop={onStop} commands={commands} />);
  return { onSend, onStop };
}

const realCommands = () => slashCommandsFor({ showKaggleDatasets: vi.fn() });
const chatSends = (send: ReturnType<typeof vi.fn>) => send.mock.calls.filter(([event]) => event?.type === "chat.send");

beforeEach(() => {
  localStorage.clear();
  startChat();
});

// The menu opens and shows the commands · component
// Baseline: Composer with the real /kaggle entry; empty box; type /
describe("The menu opens and shows the commands", () => {
  it("typing a slash in an empty box shows the commands", () => {
    // Changed: —
    // Then: a Commands listbox with one option: /kaggle and its description, first row selected
    // Demonstrates: the command can be found without knowing its name
    renderBox(realCommands());
    type("/");
    expect(rows().map((row) => row.textContent)).toEqual([`/kaggle${KAGGLE_COMMAND_DESCRIPTION}`]);
    expect(selectedRow()).toBe(0);
  });

  it("typing more letters keeps only matching rows", () => {
    // Changed: two fake commands, type /kag
    // Then: one row left
    // Demonstrates: narrowing works in the real box
    renderBox(twoCommands());
    type("/");
    expect(rows()).toHaveLength(2);
    type("/kag");
    expect(rows().map((row) => row.textContent)).toEqual(["/kaggleShow my Kaggle datasets"]);
  });

  it("a pasted slash command opens the menu too", () => {
    // Changed: /kag set in one change
    // Then: the menu shows /kaggle
    // Demonstrates: paste behaves like typing
    renderBox(realCommands());
    type("/kag");
    expect(rows()).toHaveLength(1);
  });

  it("no menu while the box has no slash", () => {
    // Changed: type hello
    // Then: no listbox
    // Demonstrates: the menu appears only on /
    renderBox(realCommands());
    type("hello");
    expect(menu()).toBeNull();
  });

  it("letters that match no command close the menu", () => {
    // Changed: / then /zzz
    // Then: no listbox; the box keeps /zzz
    // Demonstrates: unknown text stays an ordinary message
    renderBox(realCommands());
    type("/");
    type("/zzz");
    expect(menu()).toBeNull();
    expect(box().value).toBe("/zzz");
  });

  it("a slash after other text shows no menu", () => {
    // Changed: compare train/test
    // Then: no listbox
    // Demonstrates: a slash mid-message is text
    renderBox(realCommands());
    type("compare train/test");
    expect(menu()).toBeNull();
  });

  it("without commands the box never shows a menu", () => {
    // Changed: Composer without commands, type /
    // Then: no listbox
    // Demonstrates: the box is unchanged where no commands are given
    renderBox(undefined);
    type("/");
    expect(menu()).toBeNull();
  });
});

// Choosing a command · component
// Baseline: commands kaggle and kernels with run spies; box /; menu open
describe("Choosing a command", () => {
  let commands: [SlashCommand, SlashCommand];
  beforeEach(() => {
    commands = twoCommands();
  });

  it("enter runs the highlighted command and empties the box", () => {
    // Changed: —
    // Then: kaggle runs once, the box is empty, nothing is sent, the menu is gone
    // Demonstrates: choosing runs the action without a chat message
    const { onSend } = renderBox(commands);
    type("/");
    press("Enter");
    expect(commands[0].run).toHaveBeenCalledTimes(1);
    expect(box().value).toBe("");
    expect(onSend).not.toHaveBeenCalled();
    expect(menu()).toBeNull();
  });

  it("tab runs the highlighted command", () => {
    // Changed: Tab instead of Enter
    // Then: kaggle runs once, the box is empty
    // Demonstrates: Tab chooses too
    renderBox(commands);
    type("/");
    press("Tab");
    expect(commands[0].run).toHaveBeenCalledTimes(1);
    expect(box().value).toBe("");
  });

  it("down arrow then enter runs the second command", () => {
    // Changed: ↓ then Enter
    // Then: kernels runs, kaggle doesn't
    // Demonstrates: the arrows pick the row
    renderBox(commands);
    type("/");
    press("ArrowDown");
    press("Enter");
    expect(commands[1].run).toHaveBeenCalledTimes(1);
    expect(commands[0].run).not.toHaveBeenCalled();
  });

  it("up arrow on the first row wraps to the last", () => {
    // Changed: ↑
    // Then: the second row is selected
    // Demonstrates: the highlight wraps at the top
    renderBox(commands);
    type("/");
    press("ArrowUp");
    expect(selectedRow()).toBe(1);
  });

  it("down arrow on the last row wraps to the first", () => {
    // Changed: ↓ ↓
    // Then: the first row is selected
    // Demonstrates: the highlight wraps at the bottom
    renderBox(commands);
    type("/");
    press("ArrowDown");
    press("ArrowDown");
    expect(selectedRow()).toBe(0);
  });

  it("clicking a row runs that command", () => {
    // Changed: mouse down and click on row 2
    // Then: kernels runs; the box is empty
    // Demonstrates: the click isn't lost to the outside-click close
    renderBox(commands);
    type("/");
    const second = rows()[1];
    fireEvent.mouseDown(second);
    fireEvent.click(second);
    expect(commands[1].run).toHaveBeenCalledTimes(1);
    expect(box().value).toBe("");
  });

  it("hovering a row highlights it", () => {
    // Changed: mouse over row 2
    // Then: row 2 is selected
    // Demonstrates: the mouse and keys agree on the row
    renderBox(commands);
    type("/");
    fireEvent.mouseEnter(rows()[1]);
    expect(selectedRow()).toBe(1);
  });

  it("a command can be chosen while an answer streams", () => {
    // Changed: an answer is streaming
    // Then: the command runs; Stop isn't pressed
    // Demonstrates: commands don't wait for the assistant
    const { onStop } = renderBox(commands, true);
    type("/");
    press("Enter");
    expect(commands[0].run).toHaveBeenCalledTimes(1);
    expect(onStop).not.toHaveBeenCalled();
  });

  it("enter while composing text in an input method does not run a command", () => {
    // Changed: Enter while composing
    // Then: nothing runs; the box is unchanged
    // Demonstrates: input-method users can finish a word
    renderBox(commands);
    type("/");
    press("Enter", { isComposing: true });
    expect(commands[0].run).not.toHaveBeenCalled();
    expect(box().value).toBe("/");
  });

  it("shift enter with the menu open adds a line instead of running", () => {
    // Changed: Shift+Enter
    // Then: nothing runs; the menu closes
    // Demonstrates: Shift+Enter keeps its meaning
    const { onSend } = renderBox(commands);
    type("/");
    const isLeftToTheBox = press("Enter", { shiftKey: true });
    type("/\n");
    expect(isLeftToTheBox).toBe(true);
    expect(commands[0].run).not.toHaveBeenCalled();
    expect(onSend).not.toHaveBeenCalled();
    expect(menu()).toBeNull();
  });
});

// Closing without choosing · component
// Baseline: box /ka; menu open; run spy
describe("Closing without choosing", () => {
  let commands: SlashCommand[];
  let onSend: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    commands = realCommands();
    ({ onSend } = renderBox(commands));
    type("/ka");
  });

  it("escape closes the menu and keeps the text", () => {
    // Changed: Esc
    // Then: no listbox; the box keeps /ka; nothing runs
    // Demonstrates: you can back out without losing what you typed
    press("Escape");
    expect(menu()).toBeNull();
    expect(box().value).toBe("/ka");
    expect(commands[0].run).not.toHaveBeenCalled();
  });

  it("deleting the slash closes the menu", () => {
    // Changed: the box is emptied
    // Then: no listbox
    // Demonstrates: the menu follows the text
    type("");
    expect(menu()).toBeNull();
  });

  it("a click outside the menu closes it and keeps the text", () => {
    // Changed: mouse down on the page body
    // Then: no listbox; the box keeps /ka
    // Demonstrates: clicking away closes it
    fireEvent.mouseDown(document.body);
    expect(menu()).toBeNull();
    expect(box().value).toBe("/ka");
  });

  it("enter after escape sends the text as a message", () => {
    // Changed: Esc then Enter
    // Then: the text /ka is sent once
    // Demonstrates: a dismissed menu doesn't block sending
    press("Escape");
    press("Enter");
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("/ka");
  });

  it("typing more after escape keeps the menu closed", () => {
    // Changed: Esc, then /kag
    // Then: no listbox
    // Demonstrates: the menu doesn't pop back while you finish your text
    press("Escape");
    type("/kag");
    expect(menu()).toBeNull();
  });

  it("typing a new slash after clearing opens it again", () => {
    // Changed: Esc, clear, /
    // Then: the listbox shows
    // Demonstrates: dismissal lasts only for that draft
    press("Escape");
    type("");
    type("/");
    expect(menu()).not.toBeNull();
  });

  it("clicking inside the message box keeps the menu open", () => {
    // Changed: mouse down on the text box
    // Then: the listbox stays
    // Demonstrates: placing the cursor isn't clicking away
    fireEvent.mouseDown(box());
    expect(menu()).not.toBeNull();
  });
});

// Keys with the menu closed · component
// Baseline: box hello; no menu
describe("Keys with the menu closed", () => {
  let commands: SlashCommand[];
  let onSend: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    commands = realCommands();
    ({ onSend } = renderBox(commands));
    type("hello");
  });

  it("enter on a normal message still sends it", () => {
    // Changed: —
    // Then: hello is sent once; the box is empty
    // Demonstrates: sending works as before
    press("Enter");
    expect(onSend).toHaveBeenCalledTimes(1);
    expect(onSend).toHaveBeenCalledWith("hello");
    expect(box().value).toBe("");
  });

  it("enter on an unknown slash command sends it as text", () => {
    // Changed: /zzz
    // Then: /zzz is sent
    // Demonstrates: an unknown command is just a message
    type("/zzz");
    press("Enter");
    expect(onSend).toHaveBeenCalledWith("/zzz");
  });

  it("tab with the menu closed is left to the browser", () => {
    // Changed: Tab
    // Then: the key isn't prevented; nothing runs
    // Demonstrates: Tab still moves focus
    expect(press("Tab")).toBe(true);
    expect(commands[0].run).not.toHaveBeenCalled();
  });

  it("arrow keys with the menu closed are left to the text box", () => {
    // Changed: ↑ and ↓
    // Then: the keys aren't prevented
    // Demonstrates: the cursor still moves through a long message
    expect(press("ArrowUp")).toBe(true);
    expect(press("ArrowDown")).toBe(true);
  });
});

// The menu is readable by screen readers · component
// Baseline: box /; menu open
describe("The menu is readable by screen readers", () => {
  beforeEach(() => {
    renderBox(twoCommands());
    type("/");
  });

  it("the text box points at the highlighted row", () => {
    // Changed: ↓ after opening
    // Then: expanded, controls the listbox, active row is row 1 then row 2
    // Demonstrates: screen readers announce the row the arrows move to
    expect(box().getAttribute("aria-expanded")).toBe("true");
    expect(box().getAttribute("aria-controls")).toBe((menu() as HTMLElement).id);
    expect(box().getAttribute("aria-activedescendant")).toBe(rows()[0].id);
    press("ArrowDown");
    expect(box().getAttribute("aria-activedescendant")).toBe(rows()[1].id);
  });

  it("a closed menu leaves no pointer on the text box", () => {
    // Changed: Esc
    // Then: no active row; not expanded
    // Demonstrates: no announcement for a menu that isn't there
    press("Escape");
    expect(box().hasAttribute("aria-activedescendant")).toBe(false);
    expect(box().getAttribute("aria-expanded")).toBe("false");
  });
});

// A chosen command never reaches the assistant · security
// Baseline: AppShell with the fake socket; box /; menu open
describe("A chosen command never reaches the assistant", () => {
  let sender: ReturnType<typeof fakeSender>;
  beforeEach(() => {
    sender = { ...fakeSender(), callAction: vi.fn(() => new Promise<unknown>(() => {})) };
    renderWithChat(<AppShell />, sender);
    type("/");
  });

  it("choosing kaggle sends nothing over the chat connection", () => {
    // Changed: Enter
    // Then: no chat.send; no user line; the box is empty
    // Demonstrates: the command text never becomes a chat message
    press("Enter");
    expect(chatSends(sender.send)).toEqual([]);
    expect(useChat.getState().messages).toEqual([]);
    // the Kaggle window is open now, so the box sits behind it
    const boxBehindWindow = screen.getByRole("textbox", { name: "Message SillyTherin", hidden: true }) as HTMLTextAreaElement;
    expect(boxBehindWindow.value).toBe("");
  });

  it("tab choice sends nothing over the chat connection", () => {
    // Changed: Tab
    // Then: no chat.send
    // Demonstrates: every way of choosing is local
    press("Tab");
    expect(chatSends(sender.send)).toEqual([]);
  });

  it("row click sends nothing over the chat connection", () => {
    // Changed: click the row
    // Then: no chat.send
    // Demonstrates: every way of choosing is local
    const row = rows()[0];
    fireEvent.mouseDown(row);
    fireEvent.click(row);
    expect(chatSends(sender.send)).toEqual([]);
  });

  it("the full command typed and entered sends nothing", () => {
    // Changed: /kaggle then Enter
    // Then: no chat.send with /kaggle
    // Demonstrates: typing the whole name doesn't fall through to sending
    type("/kaggle");
    press("Enter");
    expect(chatSends(sender.send)).toEqual([]);
  });
});

// Command text is shown as text · security
// Baseline: a fake command whose description is markup; box /
describe("Command text is shown as text", () => {
  it("markup in a command description stays text", () => {
    // Changed: description <img src=x onerror=alert(1)>
    // Then: no img element in the menu; the text shows literally
    // Demonstrates: a command entry can't run script in the page
    const markup = "<img src=x onerror=alert(1)>";
    renderBox([{ name: "kaggle", description: markup, run: vi.fn() }]);
    type("/");
    expect((menu() as HTMLElement).querySelector("img")).toBeNull();
    expect((menu() as HTMLElement).textContent).toContain(markup);
  });
});
