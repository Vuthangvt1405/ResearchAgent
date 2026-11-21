// The page opens only Kaggle's own sign-in page, whatever URL an event carries.
export const KAGGLE_AUTHORIZE_PREFIX = "https://www.kaggle.com/api/v1/oauth2/authorize?";

export type OpenWindow = (url: string, target: string, features: string) => unknown;

export function isKaggleAuthorizeUrl(url: string): boolean {
  return typeof url === "string" && url.startsWith(KAGGLE_AUTHORIZE_PREFIX);
}

export function openKaggleSignIn(url: string, open: OpenWindow): void {
  if (!isKaggleAuthorizeUrl(url)) return;
  open(url, "_blank", "noopener,noreferrer");
}
