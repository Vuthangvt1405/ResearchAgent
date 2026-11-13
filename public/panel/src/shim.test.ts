// Group 6 — Bundle load fallback (AC7 · shim unit)
// Plan: docs/plans/done/panel-react-build-plan.md §7
// Baseline: Given the shim mounts · When __rcPanelReady never resolves
import { describe, it, expect, vi, afterEach } from "vitest";
import { connectShim, FALLBACK_TEXT, READY_TIMEOUT_MS } from "@/shim";
import { props } from "@/test/fixtures";
import type { RcPanelApi } from "@/main";

function fakeApi(over: Partial<RcPanelApi> = {}): RcPanelApi {
  return { attach: vi.fn(), detach: vi.fn(), setProps: vi.fn(), setCallAction: vi.fn(), ...over };
}

function setup() {
  const win = { document } as unknown as Window;
  const slot = document.createElement("div");
  document.body.appendChild(slot);
  return { win, slot, callAction: vi.fn() };
}

afterEach(() => vi.useRealTimers());

describe("Group 6 — Bundle load fallback", () => {
  it("shows_fallback_after_timeout", () => {
    // ✅1 · changed: —
    // Then: Panel failed to load after 10 s (fake timers) · Demonstrates: no blank sidebar
    vi.useFakeTimers();
    const { win, slot, callAction } = setup();
    win.__rcPanelReady = new Promise(() => {});
    connectShim({ slot, props: props(), callAction, win });
    vi.advanceTimersByTime(READY_TIMEOUT_MS - 1);
    expect(slot.textContent).toBe("");
    vi.advanceTimersByTime(1);
    expect(slot.textContent).toBe(FALLBACK_TEXT);
    expect(slot.querySelector('[role="alert"]')).not.toBeNull();
  });

  it("late_bundle_replaces_fallback", async () => {
    // ✅2 · changed: it resolves at 3 s
    // Then: the app is attached, no fallback · Demonstrates: slow networks are fine
    vi.useFakeTimers();
    const { win, slot, callAction } = setup();
    const p = props();
    connectShim({ slot, props: p, callAction, win }); // no promise yet: the shim creates it
    expect(win.__rcPanelResolve).toBeTypeOf("function");
    vi.advanceTimersByTime(3000);
    const api = fakeApi();
    win.__rcPanelResolve!(api);
    await vi.advanceTimersByTimeAsync(0);
    expect(api.setCallAction).toHaveBeenCalledWith(callAction);
    expect(api.setProps).toHaveBeenCalledWith(p);
    expect(api.attach).toHaveBeenCalledWith(slot);
    vi.advanceTimersByTime(READY_TIMEOUT_MS);
    expect(slot.textContent).toBe("");
  });

  it("bundle_throws_shows_fallback", async () => {
    // ❌1 · changed: attach throws
    // Then: fallback shown, error logged · Demonstrates: a crash stays inside the panel
    const { win, slot, callAction } = setup();
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    win.__rcPanelReady = Promise.resolve(fakeApi({ attach: () => { throw new Error("boom"); } }));
    connectShim({ slot, props: props(), callAction, win });
    await Promise.resolve();
    await Promise.resolve();
    expect(slot.textContent).toBe(FALLBACK_TEXT);
    expect(log).toHaveBeenCalled();
    log.mockRestore();
  });

  it("cleanup_detaches_the_slot", async () => {
    // extra: unmounting the shim detaches its slot (what each Chainlit push does)
    const { win, slot, callAction } = setup();
    const api = fakeApi();
    win.__rcPanelReady = Promise.resolve(api);
    const cleanup = connectShim({ slot, props: props(), callAction, win });
    await Promise.resolve();
    cleanup();
    expect(api.detach).toHaveBeenCalledWith(slot);
  });
});
