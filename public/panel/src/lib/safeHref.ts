/** Port of safeHref(): only http(s) URLs become links (SEC1) */
export function safeHref(url: string | null | undefined): string | null {
  return url && /^https?:\/\//i.test(url) ? url : null;
}
