// Settings: sections on the left, their rows on the right; changes apply right away.
import { useState } from "react";
import { Info, Lightbulb, SlidersHorizontal, UserRound, Wrench, X } from "lucide-react";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { SECTIONS, type SectionId } from "@/chat/lib/settingsSections";
import type { Theme } from "@/chat/lib/theme";
import type { SettingSwitch } from "@/chat/events";

export const KAGGLE_SWITCH_ID = "kaggle_account";
const ICONS: Record<SectionId, typeof Info> = { general: SlidersHorizontal, answers: Lightbulb, tools: Wrench, account: UserRound, about: Info };
const ABOUT_FACTS: [string, string, string][] = [
  ["Version", "The build you are running.", "Development build"],
  ["Runs on", "Only this PC can open the app.", "127.0.0.1"],
  ["Models from", "Every model in the picker comes from here.", "OpenRouter"],
];
const TOOL_FACTS: [string, string, string][] = [["Risky code", "Code the app flags as risky asks Run or Skip before it runs.", "Always asks"]];
const GENERAL_FACTS: [string, string, string][] = [["Notebook panel", "Show or hide the notebook next to the chat.", "Ctrl+\\"]];

export interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  switches: SettingSwitch[];
  onChange: (switchId: string, value: boolean) => void;
  theme: Theme;
  onThemeChange: (theme: Theme) => void;
}

function Row({ title, detail, id, children }: { title: string; detail: string; id?: string; children: JSX.Element | string }): JSX.Element {
  return (
    <div className="flex items-center gap-5 border-b py-4 last:border-b-0">
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span id={id} className="text-sm font-medium">{title}</span>
        <span className="text-[13px] text-muted-foreground">{detail}</span>
      </div>
      {typeof children === "string" ? <span className="max-w-[45%] text-right text-[13px] text-muted-foreground">{children}</span> : children}
    </div>
  );
}

function SwitchRow({ row, onChange }: { row: SettingSwitch; onChange: (switchId: string, value: boolean) => void }): JSX.Element {
  const labelId = `setting-${row.id}`;
  return (
    <Row title={row.label} detail={row.description} id={labelId}>
      <Switch aria-labelledby={labelId} checked={row.initial} disabled={row.disabled} onCheckedChange={(value) => onChange(row.id, value)} />
    </Row>
  );
}

function KaggleRow({ row, onChange }: { row: SettingSwitch; onChange: (switchId: string, value: boolean) => void }): JSX.Element {
  return (
    <Row title={row.label} detail={row.description}>
      <Button variant="outline" size="sm" onClick={() => onChange(row.id, !row.initial)}>
        {row.initial ? "Disconnect" : "Connect"}
      </Button>
    </Row>
  );
}

function ThemeRow({ theme, onThemeChange }: { theme: Theme; onThemeChange: (theme: Theme) => void }): JSX.Element {
  return (
    <Row title="Theme" detail="Light or dark, for the chat and the notebook." id="setting-theme">
      <div role="radiogroup" aria-labelledby="setting-theme" className="inline-flex gap-0.5 rounded-lg bg-muted p-0.5">
        {(["light", "dark"] as const).map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={theme === option}
            onClick={() => onThemeChange(option)}
            className="h-7 rounded-md px-3.5 text-[13px] font-medium capitalize text-muted-foreground aria-checked:bg-background aria-checked:text-foreground aria-checked:shadow-sm"
          >
            {option}
          </button>
        ))}
      </div>
    </Row>
  );
}

const facts = (rows: [string, string, string][]) => rows.map(([title, detail, value]) => <Row key={title} title={title} detail={detail}>{value}</Row>);

export function SettingsDialog({ open, onOpenChange, switches, onChange, theme, onThemeChange }: SettingsDialogProps): JSX.Element {
  const [sectionId, setSectionId] = useState<SectionId>("tools");
  const section = SECTIONS.find((s) => s.id === sectionId) ?? SECTIONS[0];
  const rows = section.switchIds.map((id) => switches.find((s) => s.id === id)).filter((s): s is SettingSwitch => Boolean(s));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex h-[min(620px,calc(100vh-3rem))] max-w-[940px] flex-wrap overflow-hidden p-0" aria-describedby={undefined}>
        <nav aria-label="Settings sections" className="flex min-h-0 basis-56 flex-col gap-1 overflow-y-auto border-r bg-muted/40 px-3 py-4 max-sm:basis-full">
          <DialogTitle className="mx-2 mb-3 text-base">Settings</DialogTitle>
          {SECTIONS.map((s) => {
            const Icon = ICONS[s.id];
            return (
              <button
                key={s.id}
                type="button"
                aria-current={s.id === sectionId ? "page" : undefined}
                onClick={() => setSectionId(s.id)}
                className="flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-left text-[13.5px] font-medium text-muted-foreground hover:bg-accent aria-[current=page]:bg-muted aria-[current=page]:text-foreground"
              >
                <Icon className="size-4" aria-hidden />
                {s.title}
              </button>
            );
          })}
          <span className="flex-1" />
          <span className="mx-2.5 mt-2 text-[11.5px] text-muted-foreground">Changes apply right away</span>
        </nav>
        <section className="flex min-h-0 min-w-0 flex-1 basis-[420px] flex-col">
          <div className="flex items-start gap-3 border-b px-7 pb-3.5 pt-5">
            <div className="flex flex-1 flex-col gap-1">
              <h3 className="text-xl font-semibold tracking-tight">{section.title}</h3>
              <DialogDescription>{section.detail}</DialogDescription>
            </div>
            <DialogClose aria-label="Close settings" className="inline-flex size-8 items-center justify-center rounded-lg text-muted-foreground hover:bg-accent">
              <X className="size-4" aria-hidden />
            </DialogClose>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto px-7 pb-6 pt-2">
            {sectionId === "general" && (
              <>
                <ThemeRow theme={theme} onThemeChange={onThemeChange} />
                {facts(GENERAL_FACTS)}
              </>
            )}
            {rows.map((row) =>
              row.id === KAGGLE_SWITCH_ID ? <KaggleRow key={row.id} row={row} onChange={onChange} /> : <SwitchRow key={row.id} row={row} onChange={onChange} />,
            )}
            {sectionId === "tools" && facts(TOOL_FACTS)}
            {sectionId === "about" && facts(ABOUT_FACTS)}
          </div>
        </section>
      </DialogContent>
    </Dialog>
  );
}
