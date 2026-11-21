// A thin bar while the link to the app is down.
import type { ConnectionStatus } from "@/chat/connection";

export const RECONNECTING = "Reconnecting…";

export function ConnectionBar({ status }: { status: ConnectionStatus }): JSX.Element | null {
  if (status !== "reconnecting") return null;
  return (
    <div role="status" className="animate-[st-fade-in_200ms_ease-out] bg-amber-100 px-4 py-1 text-center text-xs font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200">
      {RECONNECTING}
    </div>
  );
}
