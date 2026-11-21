import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Unmount whatever a test rendered, before the next one clears document.body
afterEach(() => {
  cleanup();
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
const css = (g.CSS ||= {}) as Record<string, unknown>;
css.escape ||= (value: string) => value.replace(/[^a-zA-Z0-9_-]/g, (char) => `\\${char}`);

// Newer Node versions define their own (empty) localStorage/sessionStorage globals, which hide
// jsdom's; tests get a plain in-memory Storage instead
class MemoryStorage implements Storage {
  private items = new Map<string, string>();
  get length() { return this.items.size; }
  clear() { this.items.clear(); }
  getItem(key: string) { return this.items.has(key) ? (this.items.get(key) as string) : null; }
  key(index: number) { return [...this.items.keys()][index] ?? null; }
  removeItem(key: string) { this.items.delete(key); }
  setItem(key: string, value: string) { this.items.set(key, String(value)); }
}
for (const name of ["localStorage", "sessionStorage"]) {
  if (!g[name]) Object.defineProperty(globalThis, name, { value: new MemoryStorage(), configurable: true, writable: true });
}

// jsdom here has no PointerEvent; a MouseEvent with a pointer id is enough for the divider
if (!g.PointerEvent) {
  g.PointerEvent = class PointerEvent extends MouseEvent {
    readonly pointerId: number;
    constructor(type: string, init: PointerEventInit = {}) {
      super(type, init);
      this.pointerId = init.pointerId ?? 1;
    }
  };
}
