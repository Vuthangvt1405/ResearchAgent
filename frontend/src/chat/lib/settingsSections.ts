// Which Settings rows each section of the Settings window shows.
export type SectionId = "general" | "answers" | "tools" | "account" | "about";

export interface SettingsSection {
  id: SectionId;
  title: string;
  detail: string;
  switchIds: string[]; // Settings rows from the server shown in this section
}

export const SECTIONS: SettingsSection[] = [
  { id: "general", title: "General", detail: "How SillyTherin looks on this PC.", switchIds: [] },
  { id: "answers", title: "Answers", detail: "How replies are shown in this chat.", switchIds: ["show_thinking"] },
  { id: "tools", title: "Tools", detail: "What the model may use in this chat. Greyed out when the picked model can't use tools.", switchIds: ["web_search", "notebook"] },
  { id: "account", title: "Account", detail: "Shared by every chat on this PC.", switchIds: ["kaggle_account"] },
  { id: "about", title: "About", detail: "This copy of SillyTherin.", switchIds: [] },
];
