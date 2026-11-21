// Toasts in the bottom-right corner: info and success hide by themselves, warnings and errors stay.
import { useEffect } from "react";
import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from "lucide-react";
import { TOAST_HIDE_MS, useChat, type ToastView } from "@/chat/store";

const ICONS = { info: Info, success: CircleCheck, warning: TriangleAlert, error: CircleAlert };
const COLOURS = { info: "text-primary", success: "text-emerald-600 dark:text-emerald-400", warning: "text-amber-600 dark:text-amber-400", error: "text-destructive dark:text-red-400" };

function ToastItem({ toast, onClose }: { toast: ToastView; onClose: () => void }): JSX.Element {
  const hidesItself = toast.kind === "info" || toast.kind === "success";
  useEffect(() => {
    if (!hidesItself) return;
    const timer = setTimeout(onClose, TOAST_HIDE_MS);
    return () => clearTimeout(timer);
  }, [hidesItself, onClose]);
  const Icon = ICONS[toast.kind];
  return (
    <div role={toast.kind === "error" ? "alert" : "status"} className="st-toast flex w-[22rem] max-w-full items-start gap-3 rounded-xl border bg-background p-3.5 shadow-lg">
      <Icon className={`mt-0.5 size-4 shrink-0 ${COLOURS[toast.kind]}`} aria-hidden />
      <span className="flex-1 text-sm">{toast.text}</span>
      <button type="button" aria-label="Close" onClick={onClose} className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-accent">
        <X className="size-3.5" aria-hidden />
      </button>
    </div>
  );
}

export function Toasts(): JSX.Element {
  const toasts = useChat((s) => s.toasts);
  const dismiss = useChat((s) => s.dismissToast);
  return (
    <div className="pointer-events-none fixed bottom-6 right-6 z-50 flex max-w-[calc(100vw-3rem)] flex-col gap-2 [&>*]:pointer-events-auto">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onClose={() => dismiss(toast.id)} />
      ))}
    </div>
  );
}
