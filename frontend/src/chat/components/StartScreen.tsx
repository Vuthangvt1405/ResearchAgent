// A new chat: only the logo and one line of text.
import logoDark from "@/assets/logo_dark.svg";
import logoLight from "@/assets/logo_light.svg";
import type { Theme } from "@/chat/lib/theme";

export const START_LINE = "Ask anything, or paste a dataset link to get started.";

export function StartScreen({ theme }: { theme: Theme }): JSX.Element {
  return (
    <div className="st-enter flex min-h-0 flex-1 flex-col items-center justify-center gap-3.5 px-6 py-12 text-center">
      <img src={theme === "dark" ? logoDark : logoLight} alt="SillyTherin" className="h-16 w-auto max-w-full" />
      <p className="text-[15px] text-muted-foreground">{START_LINE}</p>
    </div>
  );
}
