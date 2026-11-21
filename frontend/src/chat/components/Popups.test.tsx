// Kaggle pop-up, toasts, connection bar
// Baseline: Given a kaggle.popup waiting event · When it renders
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/chat/components/AppShell";
import { ConnectionBar, RECONNECTING } from "@/chat/components/ConnectionBar";
import { KaggleSignInDialog, SIGN_IN_TITLE } from "@/chat/components/KaggleSignInDialog";
import { Toasts } from "@/chat/components/Toasts";
import { TOAST_HIDE_MS, useChat } from "@/chat/store";
import { renderWithChat, startChat } from "@/chat/test/renderChat";
import { usePanel } from "@/panel/store";
import { props } from "@/panel/test/fixtures";

const KAGGLE_URL = "https://www.kaggle.com/api/v1/oauth2/authorize?client_id=x&state=y";

afterEach(() => vi.useRealTimers());

describe("Kaggle pop-up, toasts, connection bar", () => {
  it("the sign-in pop-up offers to open kaggle", () => {
    // Changed: —
    // Then: Sign in to Kaggle, Open Kaggle sign-in, Close
    // Demonstrates: signing in is guided
    render(<KaggleSignInDialog popup={{ state: "waiting", authorizeUrl: KAGGLE_URL, message: "" }} onClose={vi.fn()} />);
    expect(screen.getByRole("dialog", { name: SIGN_IN_TITLE })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Open Kaggle sign-in" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Waiting for Kaggle sign-in.");
  });

  it("the pop-up becomes one line when it ends", () => {
    // Changed: state connected / failed
    // Then: one line with the message
    // Demonstrates: the outcome is short
    const onClose = vi.fn();
    const { rerender } = render(<KaggleSignInDialog popup={{ state: "connected", authorizeUrl: KAGGLE_URL, message: "Kaggle connected as ana" }} onClose={onClose} />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Kaggle connected as ana");
    rerender(<KaggleSignInDialog popup={{ state: "failed", authorizeUrl: KAGGLE_URL, message: "Kaggle sign-in was cancelled." }} onClose={onClose} />);
    expect(screen.getByRole("status").textContent).toBe("Kaggle sign-in was cancelled.");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("toasts hide or stay by kind", () => {
    // Changed: an info and an error toast, 5 s later
    // Then: the info toast gone, the error toast still there
    // Demonstrates: errors aren't missed
    vi.useFakeTimers();
    startChat([{ type: "toast", kind: "info", text: "Waiting for Kaggle sign-in in your browser…" }, { type: "error", code: "BUSY", message: "Wait for the reply." }]);
    render(<Toasts />);
    expect(screen.getAllByRole("status").map((t) => t.textContent)).toEqual(["Waiting for Kaggle sign-in in your browser…"]);
    act(() => vi.advanceTimersByTime(TOAST_HIDE_MS));
    expect(screen.queryAllByRole("status")).toEqual([]);
    expect(screen.getByRole("alert").textContent).toBe("Wait for the reply.");
  });

  it("the connection bar shows while reconnecting", () => {
    // Changed: the socket drops
    // Then: Reconnecting… until session.ready
    // Demonstrates: you know the link is down
    const { rerender } = render(<ConnectionBar status="open" />);
    expect(screen.queryByText(RECONNECTING)).toBeNull();
    rerender(<ConnectionBar status="reconnecting" />);
    expect(screen.getByRole("status").textContent).toBe(RECONNECTING);
  });

  it("the panel talks through the socket", async () => {
    // Changed: the panel runs a cell
    // Then: a panel.action is sent and its panel.result reaches the panel
    // Demonstrates: the notebook works in the new page
    localStorage.clear();
    startChat();
    const { sender } = renderWithChat(<AppShell />);
    expect(usePanel.getState().nb?.version).toBe(props().version);
    await act(async () => {
      await usePanel.getState().callAction?.({ name: "nb_run_all", payload: { version: props().version } });
    });
    expect(sender.callAction).toHaveBeenCalledWith({ name: "nb_run_all", payload: { version: props().version } });
    act(() => useChat.getState().apply({ type: "panel.props", props: props({ version: props().version + 1 }) }));
    expect(usePanel.getState().nb?.version).toBe(props().version + 1);
  });
});
