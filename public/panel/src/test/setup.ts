import { afterEach } from "vitest";
import { act } from "@testing-library/react";
import { teardown } from "@/main";

// Unmount the panel after every test, before the next one clears document.body
afterEach(() => {
  act(() => teardown(window));
  document.body.innerHTML = "";
});

// jsdom lacks a few browser APIs Radix uses (test-only polyfills)
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
const g = globalThis as unknown as Record<string, unknown>;
if (!g.ResizeObserver) g.ResizeObserver = RO;
const proto = Element.prototype as unknown as Record<string, unknown>;
proto.scrollIntoView ||= function () {};
proto.hasPointerCapture ||= function () { return false; };
proto.setPointerCapture ||= function () {};
proto.releasePointerCapture ||= function () {};
