// Logo, project name, New chat, Settings, theme and notebook toggles.
import { Folder, Moon, PanelRight, Plus, SlidersHorizontal, Sun } from "lucide-react";
import logoDark from "@/assets/logo_dark.svg";
import logoLight from "@/assets/logo_light.svg";
import type { Theme } from "@/chat/lib/theme";

export interface AppHeaderProps {
  projectName: string | null;
  theme: Theme;
  isNotebookOpen: boolean;
  onNewChat: () => void;
  onOpenSettings: () => void;
  onToggleTheme: () => void;
  onToggleNotebook: () => void;
}

const ICON_BUTTON = "inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent hover:text-foreground";

export function AppHeader({ projectName, theme, isNotebookOpen, onNewChat, onOpenSettings, onToggleTheme, onToggleNotebook }: AppHeaderProps): JSX.Element {
  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b px-4">
      <img src={theme === "dark" ? logoDark : logoLight} alt="SillyTherin" className="h-6 w-auto" />
      {projectName && (
        <>
          <span className="h-5 w-px bg-border" aria-hidden />
          <span className="inline-flex min-w-0 items-center gap-1.5 text-[13px] font-medium">
            <Folder className="size-4 shrink-0" aria-hidden />
            <span className="truncate">{projectName}</span>
          </span>
        </>
      )}
      <span className="flex-1" />
      <button type="button" onClick={onNewChat} className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-[13px] font-medium hover:bg-accent">
        <Plus className="size-4" aria-hidden />
        New chat
      </button>
      <button type="button" aria-label="Settings" onClick={onOpenSettings} className={ICON_BUTTON}>
        <SlidersHorizontal className="size-[18px]" aria-hidden />
      </button>
      <button type="button" aria-label="Switch light or dark theme" onClick={onToggleTheme} className={ICON_BUTTON}>
        {theme === "dark" ? <Sun className="size-[18px]" aria-hidden /> : <Moon className="size-[18px]" aria-hidden />}
      </button>
      {/* fixed width: the label changes, the buttons beside it must not move */}
      <button
        type="button"
        aria-pressed={isNotebookOpen}
        title="Ctrl+\"
        onClick={onToggleNotebook}
        className="inline-flex h-9 w-[9.75rem] items-center justify-center gap-2 whitespace-nowrap rounded-lg border px-3 text-[13px] font-medium hover:bg-accent aria-pressed:border-transparent aria-pressed:bg-muted"
      >
        <PanelRight className="size-4" aria-hidden />
        {isNotebookOpen ? "Hide notebook" : "Notebook"}
      </button>
    </header>
  );
}
