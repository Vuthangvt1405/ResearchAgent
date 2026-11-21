// Mounts the real panel the way the page does (NotebookPanel with props and a callAction);
// each push hands it new props, like a panel.props event from the server.
import { act, render } from "@testing-library/react";
import { createElement } from "react";
import { vi } from "vitest";
import { queryClient } from "@/panel/components/App";
import { NotebookPanel } from "@/panel/NotebookPanel";
import { resetStore } from "@/panel/store";
import type { CallAction, NotebookProps } from "@/panel/types";

export interface Harness {
  /** Hand the panel new props, as a push from the server does */
  push: (props: NotebookProps, callAction?: CallAction) => Promise<HTMLElement>;
  callAction: ReturnType<typeof vi.fn>;
}

export async function mountPanel(first: NotebookProps, callAction?: ReturnType<typeof vi.fn>): Promise<Harness> {
  document.body.innerHTML = "";
  resetStore();
  queryClient.clear();
  const fn = callAction || vi.fn(async (a: { name: string }) => (a.name === "nb_list_projects" ? { projects: [] } : null));
  let rerender: ((ui: ReturnType<typeof createElement>) => void) | null = null;
  const push = async (props: NotebookProps, cb: CallAction = fn as unknown as CallAction) => {
    await act(async () => {
      const ui = createElement(NotebookPanel, { props, callAction: cb });
      if (rerender) rerender(ui);
      else rerender = render(ui).rerender;
      await Promise.resolve();
      await Promise.resolve();
    });
    return panelRoot();
  };
  await push(first);
  return { push, callAction: fn };
}

export const panelRoot = () => document.getElementById("rc-panel-root") as HTMLElement;
