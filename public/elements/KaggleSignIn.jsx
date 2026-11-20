// Kaggle sign-in pop-up, shown inline in a chat message when the user turns on
// "Kaggle account" in Settings.
// props = { authorize_url, state: "waiting" | "connected" | "failed", message }
//
// While waiting it shows a modal dialog ("Sign in to Kaggle", what will happen,
// "Open Kaggle sign-in", "Close"). After Close, or once the server updates `state`,
// it shows one compact line instead.
import { useEffect, useRef, useState } from "react";

const KAGGLE_AUTHORIZE_PREFIX = "https://www.kaggle.com/api/v1/oauth2/authorize?";
const TITLE = "Sign in to Kaggle";
const EXPLAINER =
  "Approve SillyTherin on Kaggle's page. When the tab says Connected, come back here; Settings will show your account.";
const SCOPE_NOTE = "Kaggle only offers full-account access. ResearchChat only reads with it.";

function isKaggleAuthorizeUrl(url) {
  return typeof url === "string" && url.startsWith(KAGGLE_AUTHORIZE_PREFIX);
}

function openSignIn(url) {
  if (!isKaggleAuthorizeUrl(url)) return;
  window.open(url, "_blank", "noopener,noreferrer");
}

const colors = {
  card: "hsl(var(--card))",
  text: "hsl(var(--card-foreground))",
  muted: "hsl(var(--muted-foreground))",
  border: "hsl(var(--border))",
  primary: "hsl(var(--primary))",
  primaryText: "hsl(var(--primary-foreground))",
};

const buttonBase = {
  borderRadius: 6,
  padding: "8px 14px",
  fontSize: 14,
  fontWeight: 500,
  cursor: "pointer",
  border: `1px solid ${colors.border}`,
};

function OpenButton({ url, autoFocus }) {
  const canOpen = isKaggleAuthorizeUrl(url);
  return (
    <button
      type="button"
      autoFocus={autoFocus}
      disabled={!canOpen}
      onClick={() => openSignIn(url)}
      style={{ ...buttonBase, background: colors.primary, color: colors.primaryText, borderColor: colors.primary }}
    >
      Open Kaggle sign-in
    </button>
  );
}

function SignInDialog({ url, message, onClose }) {
  const dialog = useRef(null);
  useEffect(() => {
    const closeOnEscape = (event) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  return (
    <div
      onClick={(event) => event.target === event.currentTarget && onClose()}
      style={{ position: "fixed", inset: 0, zIndex: 60, background: "rgba(0, 0, 0, 0.45)",
               display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
    >
      <div
        ref={dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby="kaggle-sign-in-title"
        style={{ background: colors.card, color: colors.text, border: `1px solid ${colors.border}`,
                 borderRadius: 10, padding: 20, width: "min(420px, 100%)", display: "grid", gap: 12,
                 boxShadow: "0 10px 30px rgba(0, 0, 0, 0.25)" }}
      >
        <div id="kaggle-sign-in-title" style={{ fontSize: 17, fontWeight: 600 }}>{TITLE}</div>
        <div style={{ fontSize: 14 }}>{message}</div>
        <div style={{ fontSize: 14, color: colors.muted }}>{EXPLAINER}</div>
        <div style={{ fontSize: 12, color: colors.muted }}>{SCOPE_NOTE}</div>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", flexWrap: "wrap" }}>
          <button type="button" onClick={onClose} style={{ ...buttonBase, background: "transparent", color: colors.text }}>
            Close
          </button>
          <OpenButton url={url} autoFocus />
        </div>
      </div>
    </div>
  );
}

export default function KaggleSignIn() {
  const [dialogClosed, setDialogClosed] = useState(false);
  const url = props.authorize_url;
  const waiting = props.state === "waiting";

  if (waiting && !dialogClosed) {
    return <SignInDialog url={url} message={props.message} onClose={() => setDialogClosed(true)} />;
  }
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap", fontSize: 14 }}>
      <span style={{ color: props.state === "failed" ? colors.muted : colors.text }}>
        {waiting ? "Waiting for Kaggle sign-in." : props.message}
      </span>
      {waiting && <OpenButton url={url} autoFocus={false} />}
    </div>
  );
}
