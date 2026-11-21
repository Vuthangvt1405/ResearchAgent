// The "My Kaggle datasets" window opened by /kaggle
import { act, fireEvent, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/chat/components/AppShell";
import {
  LIST_MY_DATASETS_ACTION,
  LOADING_TEXT,
  NO_DATASETS_TEXT,
  NOT_CONNECTED_TEXT,
  PRIVACY_NOTE,
  SEARCH_LABEL,
  SIGNED_OUT_TEXT,
  TRUNCATED_TEXT,
  UNREACHABLE_TEXT,
  WINDOW_TITLE,
  type MyDatasetsAnswer,
  type MyDatasetsState,
  type OwnedKaggleDataset,
} from "@/chat/lib/kaggleDatasets";
import { useChat } from "@/chat/store";
import { fakeSender, renderWithChat, startChat } from "@/chat/test/renderChat";

const dataset = (number: number, title = `Dataset ${number}`): OwnedKaggleDataset => ({
  title,
  ref: `ana/dataset-${number}`,
  total_bytes: 48_000_000,
  licence: "CC BY 4.0",
  last_updated: "2026-11-12T08:30:00Z",
});
const listed = (datasets: OwnedKaggleDataset[], isTruncated = false): MyDatasetsAnswer => ({ state: "listed", username: "ana", datasets, is_truncated: isTruncated });
const noList = (state: Exclude<MyDatasetsState, "listed">): MyDatasetsAnswer => ({ state, username: null, datasets: [], is_truncated: false });
const manyDatasets = (count: number) => Array.from({ length: count }, (_, index) => dataset(index + 1));

const box = () => screen.getByRole("textbox", { name: "Message SillyTherin", hidden: true });
const windowEl = () => screen.queryByRole("dialog", { name: WINDOW_TITLE });
const shownRows = () => within(windowEl() as HTMLElement).queryAllByRole("listitem");

/** AppShell with a fake socket whose list actions wait until the test answers them */
function openShell() {
  const waiting: Array<(result: unknown) => void> = [];
  // the notebook panel calls other actions too; only the Kaggle list waits for the test
  const callAction = vi.fn(({ name }: { name: string }) =>
    name === LIST_MY_DATASETS_ACTION ? new Promise<unknown>((resolve) => waiting.push(resolve)) : Promise.resolve(null),
  );
  const sender = { ...fakeSender(), callAction };
  renderWithChat(<AppShell />, sender);
  const answerNewest = async (result: unknown) => {
    await act(async () => waiting[waiting.length - 1](result));
  };
  const answerRequest = async (index: number, result: unknown) => {
    await act(async () => waiting[index](result));
  };
  return { sender, waiting, answerNewest, answerRequest };
}

function chooseKaggle() {
  fireEvent.change(box(), { target: { value: "/" } });
  fireEvent.keyDown(box(), { key: "Enter" });
}

function closeWindow() {
  fireEvent.keyDown(windowEl() as HTMLElement, { key: "Escape" });
}

const listCalls = (callAction: ReturnType<typeof vi.fn>) => callAction.mock.calls.filter(([action]) => action?.name === LIST_MY_DATASETS_ACTION);
const chatSends = (send: ReturnType<typeof vi.fn>) => send.mock.calls.filter(([event]) => event?.type === "chat.send");

beforeEach(() => {
  localStorage.clear();
  startChat();
});

// The window's states · component
// Baseline: account connected; type / then Enter; the list action answers two datasets
describe("The window's states", () => {
  it("choosing kaggle opens the window with my datasets", async () => {
    // Changed: —
    // Then: My Kaggle datasets, Connected as ana, two rows with title, owner/name, size, licence, updated, the privacy note; one list action with an empty payload
    // Demonstrates: the window lists the account's own datasets
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed([dataset(1, "Vietnam air quality, daily"), dataset(2)]));

    const view = within(windowEl() as HTMLElement);
    expect(view.getByText("Connected as ana")).toBeTruthy();
    expect(shownRows().map((row) => row.textContent)).toEqual([
      "Vietnam air quality, dailyana/dataset-148 MBCC BY 4.012 Nov 2026",
      "Dataset 2ana/dataset-248 MBCC BY 4.012 Nov 2026",
    ]);
    expect(view.getByText(PRIVACY_NOTE)).toBeTruthy();
    expect(listCalls(shell.sender.callAction)).toHaveLength(1);
    expect(shell.sender.callAction).toHaveBeenCalledWith({ name: LIST_MY_DATASETS_ACTION, payload: {} });
  });

  it("the window shows loading until kaggle answers", () => {
    // Changed: the answer hasn't come
    // Then: Loading your Kaggle datasets…
    // Demonstrates: you see it is working
    openShell();
    chooseKaggle();
    expect(within(windowEl() as HTMLElement).getByRole("status").textContent).toBe(LOADING_TEXT);
    expect(shownRows()).toEqual([]);
  });

  it("the loading window can be closed", () => {
    // Changed: Esc or Close while loading
    // Then: no window
    // Demonstrates: you never have to wait for Kaggle
    openShell();
    chooseKaggle();
    closeWindow();
    expect(windowEl()).toBeNull();
    chooseKaggle();
    fireEvent.click(within(windowEl() as HTMLElement).getByRole("button", { name: "Close" }));
    expect(windowEl()).toBeNull();
  });

  it("an account with no datasets says so", async () => {
    // Changed: listed with no rows
    // Then: You have no datasets on Kaggle yet.; no rows, no search
    // Demonstrates: an empty account is explained
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed([]));
    const view = within(windowEl() as HTMLElement);
    expect(view.getByText(NO_DATASETS_TEXT)).toBeTruthy();
    expect(shownRows()).toEqual([]);
    expect(view.queryByRole("searchbox", { name: SEARCH_LABEL })).toBeNull();
  });

  it("try again loads the list after a failure", async () => {
    // Changed: unreachable, then Try again
    // Then: a second list action, then rows
    // Demonstrates: a passing outage can be retried
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(noList("unreachable"));
    fireEvent.click(within(windowEl() as HTMLElement).getByRole("button", { name: "Try again" }));
    expect(listCalls(shell.sender.callAction)).toHaveLength(2);
    await shell.answerNewest(listed([dataset(1)]));
    expect(shownRows()).toHaveLength(1);
  });

  it("connect shows the list once the account is connected", async () => {
    // Changed: not connected, Connect, then Settings says connected
    // Then: settings.update turns the Kaggle switch on; a second list action; rows
    // Demonstrates: connecting from the window leads straight to the list
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(noList("not_connected"));
    fireEvent.click(within(windowEl() as HTMLElement).getByRole("button", { name: "Connect" }));
    expect(shell.sender.send).toHaveBeenCalledWith({ type: "settings.update", values: { kaggle_account: true } });
    expect(listCalls(shell.sender.callAction)).toHaveLength(1);

    // the sign-in pop-up reports the account connected once Kaggle says yes
    act(() => useChat.getState().apply({ type: "kaggle.popup", state: "connected", authorize_url: "", message: "Kaggle connected as ana" }));
    expect(listCalls(shell.sender.callAction)).toHaveLength(2);
    await shell.answerNewest(listed([dataset(1)]));
    expect(shownRows()).toHaveLength(1);
  });

  it("no account shows the connect message and no rows", async () => {
    // Changed: not connected
    // Then: Connect your Kaggle account to see your datasets, Connect, subtitle Not connected; no rows
    // Demonstrates: the window says why there's no list
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(noList("not_connected"));
    const view = within(windowEl() as HTMLElement);
    expect(view.getByText(NOT_CONNECTED_TEXT)).toBeTruthy();
    expect(view.getByRole("button", { name: "Connect" })).toBeTruthy();
    expect(view.getByText("Not connected")).toBeTruthy();
    expect(shownRows()).toEqual([]);
  });

  it("kaggle unreachable shows the reason with try again and no rows", async () => {
    // Changed: unreachable
    // Then: Couldn't reach Kaggle. Try again. and Try again; no rows
    // Demonstrates: an outage never shows an old list
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(noList("unreachable"));
    const view = within(windowEl() as HTMLElement);
    expect(view.getByText(UNREACHABLE_TEXT)).toBeTruthy();
    expect(view.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(shownRows()).toEqual([]);
  });

  it("a refused sign-in shows the reason with connect and no rows", async () => {
    // Changed: signed out
    // Then: Kaggle signed you out. Connect again. and Connect; no rows
    // Demonstrates: a refused sign-in never shows an old list
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(noList("signed_out"));
    const view = within(windowEl() as HTMLElement);
    expect(view.getByText(SIGNED_OUT_TEXT)).toBeTruthy();
    expect(view.getByRole("button", { name: "Connect" })).toBeTruthy();
    expect(shownRows()).toEqual([]);
  });

  it("an answer that arrives after closing is ignored", async () => {
    // Changed: close while loading, then the answer comes
    // Then: no window; reopening shows loading, then only the new answer
    // Demonstrates: no surprise pop-up or old data
    const shell = openShell();
    chooseKaggle();
    closeWindow();
    await shell.answerRequest(0, listed([dataset(1, "Old answer")]));
    expect(windowEl()).toBeNull();

    chooseKaggle();
    expect(within(windowEl() as HTMLElement).getByRole("status").textContent).toBe(LOADING_TEXT);
    await shell.answerRequest(1, listed([dataset(2, "New answer")]));
    expect(shownRows().map((row) => within(row).getByText(/answer/).textContent)).toEqual(["New answer"]);
  });
});

// Long lists · component
// Baseline: the list action answers 60 datasets
describe("Long lists", () => {
  it("typing in search narrows the rows by title or name", async () => {
    // Changed: a search matching one dataset
    // Then: 60 datasets becomes 1 dataset
    // Demonstrates: a long list is quick to search
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed(manyDatasets(60)));
    const view = within(windowEl() as HTMLElement);
    expect(view.getByText("60 datasets")).toBeTruthy();
    fireEvent.change(view.getByRole("searchbox", { name: SEARCH_LABEL }), { target: { value: "dataset-17" } });
    expect(view.getByText("1 dataset")).toBeTruthy();
    expect(shownRows()).toHaveLength(1);
  });

  it("every row can be reached by scrolling", async () => {
    // Changed: —
    // Then: all 60 rows inside a scrolling list
    // Demonstrates: nothing is out of reach
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed(manyDatasets(60)));
    const list = within(windowEl() as HTMLElement).getByRole("list", { name: "My datasets" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(60);
    expect(list.className).toContain("overflow-y-auto");
  });

  it("a capped list says only the newest are shown", async () => {
    // Changed: is_truncated
    // Then: Showing your 1000 most recently updated datasets
    // Demonstrates: a cut list never pretends to be complete
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed(manyDatasets(60), true));
    expect(within(windowEl() as HTMLElement).getByText(TRUNCATED_TEXT)).toBeTruthy();
  });

  it("a search with no match says so", async () => {
    // Changed: zzz
    // Then: No dataset matches “zzz”.; no rows
    // Demonstrates: an empty search isn't mistaken for an empty account
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed(manyDatasets(60)));
    const view = within(windowEl() as HTMLElement);
    fireEvent.change(view.getByRole("searchbox", { name: SEARCH_LABEL }), { target: { value: "zzz" } });
    expect(view.getByText("No dataset matches “zzz”.")).toBeTruthy();
    expect(shownRows()).toEqual([]);
  });
});

// The assistant is never sent the list · security
// Baseline: the window lists two datasets
describe("The assistant is never sent the list", () => {
  it("the window never sends the list over the chat", async () => {
    // Changed: open, list, search, close
    // Then: no chat.send; only the list action was used
    // Demonstrates: the list stays out of the conversation
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed([dataset(1), dataset(2)]));
    fireEvent.change(within(windowEl() as HTMLElement).getByRole("searchbox", { name: SEARCH_LABEL }), { target: { value: "1" } });
    closeWindow();
    expect(chatSends(shell.sender.send)).toEqual([]);
    expect(shell.sender.send).not.toHaveBeenCalled();
    expect(listCalls(shell.sender.callAction)).toHaveLength(1);
  });
});

// No stale list after sign-out · security
// Baseline: the window listed two datasets and was closed
describe("No stale list after sign-out", () => {
  it("a sign-out after a list clears the old rows", async () => {
    // Changed: reopen and the answer is signed out
    // Then: no old rows at any moment, not even while loading
    // Demonstrates: a private list never outlives the sign-in
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed([dataset(1), dataset(2)]));
    closeWindow();

    chooseKaggle();
    expect(shownRows()).toEqual([]);
    await shell.answerNewest(noList("signed_out"));
    expect(shownRows()).toEqual([]);
    expect(within(windowEl() as HTMLElement).getByText(SIGNED_OUT_TEXT)).toBeTruthy();
  });
});

// Kaggle text is shown as text · security
// Baseline: a dataset whose title is markup
describe("Kaggle text is shown as text", () => {
  it("markup in a dataset title stays text", async () => {
    // Changed: title <img src=x onerror=alert(1)>
    // Then: no img element in the window; the text shows literally
    // Demonstrates: another site's data can't run in the page
    const markup = "<img src=x onerror=alert(1)>";
    const shell = openShell();
    chooseKaggle();
    await shell.answerNewest(listed([dataset(1, markup)]));
    expect((windowEl() as HTMLElement).querySelector("img")).toBeNull();
    expect(shownRows()[0].textContent).toContain(markup);
  });
});
