// Mounts the real bundle (bootstrap + overlay + App) and plays the part of Chainlit:
// each push unmounts the old shim slot and mounts a new one, like the sidebar does.
import { act } from "@testing-library/react";
import { vi } from "vitest";
import { bootstrap, teardown, type RcPanelApi } from "@/main";
import { connectShim } from "@/shim";
import { queryClient } from "@/components/App";
import { resetStore } from "@/store";
import type { CallAction, NotebookProps } from "@/types";

export interface Harness {
  api: RcPanelApi;
  sidebar: HTMLElement;
  /** Like a Chainlit push: old slot unmounted, new slot mounted with these props */
  push: (props: NotebookProps, callAction?: CallAction) => Promise<HTMLElement>;
  callAction: ReturnType<typeof vi.fn>;
}

export async function mountPanel(first: NotebookProps, callAction?: ReturnType<typeof vi.fn>): Promise<Harness> {
  act(() => teardown(window));
  document.body.innerHTML = "";
  resetStore();
  queryClient.clear();
  const fn = callAction || vi.fn(async (a: { name: string }) => (a.name === "nb_list_projects" ? { projects: [] } : null));
  const sidebar = document.createElement("div");
  sidebar.id = "side-view-content";
  document.body.appendChild(sidebar);
  let api!: RcPanelApi;
  await act(async () => {
    api = bootstrap(window);
  });
  let cleanup: (() => void) | null = null;
  let slot: HTMLElement | null = null;
  const push = async (props: NotebookProps, cb: CallAction = fn as unknown as CallAction) => {
    await act(async () => {
      if (cleanup) cleanup();
      if (slot) slot.remove();
      slot = document.createElement("div");
      slot.setAttribute("data-rc-panel-slot", "");
      sidebar.appendChild(slot);
      cleanup = connectShim({ slot, props, callAction: cb });
      await Promise.resolve();
      await Promise.resolve();
    });
    return slot!;
  };
  await push(first);
  return { api, sidebar, push, callAction: fn };
}

export const panelRoot = () => document.getElementById("rc-panel-root") as HTMLElement;
