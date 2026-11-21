// The Kaggle sign-in pop-up while waiting, then one line once the sign-in ends.
import { useState } from "react";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { openKaggleSignIn, type OpenWindow } from "@/chat/lib/kaggleUrl";
import type { KagglePopupView } from "@/chat/store";

export const SIGN_IN_TITLE = "Sign in to Kaggle";
export const SIGN_IN_EXPLAINER =
  "Approve SillyTherin on Kaggle's page. When the tab says Connected, come back here; Settings will show your account.";
export const SIGN_IN_SCOPE_NOTE = "Kaggle only offers full-account access. SillyTherin only reads with it.";
export const WAITING_LINE = "Waiting for Kaggle sign-in.";

export interface KaggleSignInDialogProps {
  popup: KagglePopupView;
  onClose: () => void;
  openWindow?: OpenWindow;
}

export function KaggleSignInDialog({ popup, onClose, openWindow = window.open.bind(window) }: KaggleSignInDialogProps): JSX.Element {
  const [isDialogClosed, setIsDialogClosed] = useState(false);
  const isWaiting = popup.state === "waiting";
  if (isWaiting && !isDialogClosed) {
    return (
      <Dialog open onOpenChange={(open) => !open && setIsDialogClosed(true)}>
        <DialogContent className="p-6">
          <DialogHeader>
            <DialogTitle>{SIGN_IN_TITLE}</DialogTitle>
            <DialogDescription>{SIGN_IN_EXPLAINER}</DialogDescription>
          </DialogHeader>
          <p className="mt-3 text-[13px] text-muted-foreground">{SIGN_IN_SCOPE_NOTE}</p>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setIsDialogClosed(true)}>Close</Button>
            <Button onClick={() => openKaggleSignIn(popup.authorizeUrl, openWindow)}>Open Kaggle sign-in</Button>
          </div>
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <div role="status" className="st-enter mx-4 mt-3 flex items-center gap-3 rounded-lg border bg-card px-3.5 py-2 text-sm">
      <span className="flex-1">{isWaiting ? WAITING_LINE : popup.message}</span>
      <button type="button" aria-label="Close" onClick={onClose} className="inline-flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-accent">
        <X className="size-3.5" aria-hidden />
      </button>
    </div>
  );
}
