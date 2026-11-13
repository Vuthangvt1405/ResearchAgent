// Calls to the Python nb_* / ds_* actions (AC4). Payloads are the same as the old
// Notebook.jsx sent. Busy and error state come from TanStack Query (AC8, D4).
import { useRef } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { usePanel } from "@/store";
import type { ActionName, ActionResult, ProjectRef } from "@/types";

/** Call one action with the current callAction; unwraps r.response like the old call() */
export async function call(name: ActionName, payload: Record<string, unknown>): Promise<ActionResult> {
  const callAction = usePanel.getState().callAction;
  if (!callAction) throw new Error("The panel is not connected yet");
  const r = (await callAction({ name, payload })) as { response?: unknown } | null | undefined;
  return (r && r.response !== undefined ? r.response : r) as ActionResult;
}

type Payload = Record<string, unknown> | (() => Record<string, unknown>);

export interface Runner {
  /**
   * Run one action; ignored while another runs (one at a time, as before). payload may be
   * a function: it is read after `before` runs, because a flush bumps the version.
   */
  run: (name: ActionName, payload?: Payload, before?: () => Promise<unknown>) => Promise<ActionResult>;
  /** Name (or "run:<cell id>") of the action in flight */
  busy: string | null;
  error: string | null;
  clearError: () => void;
}

/**
 * One mutation for the panel's buttons. A second click while one is pending is
 * dropped (G5❌2), and a rejected call clears the busy state and shows the error (G5❌1).
 */
export function useRunner(): Runner {
  const inFlight = useRef(false);
  const m = useMutation({
    mutationFn: async ({ name, payload, before }: { name: ActionName; payload: Payload; tag: string; before?: () => Promise<unknown> }) => {
      if (before) await before();
      return call(name, typeof payload === "function" ? payload() : payload);
    },
    onSuccess: (result) => {
      usePanel.getState().apply(result);
    },
    onSettled: () => {
      inFlight.current = false;
    },
  });
  return {
    run: async (name, payload = {}, before) => {
      if (inFlight.current) return null;
      inFlight.current = true;
      const tag = name === "nb_run_cell" && typeof payload === "object" ? `run:${payload.cell_id}` : name;
      try {
        return await m.mutateAsync({ name, payload, tag, before });
      } catch {
        return null;
      }
    },
    busy: m.isPending ? m.variables?.tag ?? null : null,
    error: m.error ? m.error.message || "The action failed" : null,
    clearError: m.reset,
  };
}

/** nb_list_projects as a query, refetched when the project changes (D4) */
export function useProjects(projectId: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["projects", projectId],
    enabled: !!projectId && enabled,
    queryFn: async () => {
      const r = await call("nb_list_projects", {});
      return ((r && r.projects) || []) as ProjectRef[];
    },
    staleTime: 30_000,
  });
}
