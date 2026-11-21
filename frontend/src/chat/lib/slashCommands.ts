// The commands the "/" menu offers, and the rules for which box text opens it and which rows match.
// A new command is one more entry in slashCommandsFor; the menu itself never changes.

export interface SlashCommand {
  /** Typed after the slash and shown as "/name"; the prefix match runs on it */
  name: string;
  /** One line telling the user what the command does, so it can be found without knowing its name */
  description: string;
  /** What choosing it does; given by the shell, so the menu never needs to know */
  run: () => void;
}

/** What the shell can do when a command is chosen */
export interface CommandActions {
  showKaggleDatasets: () => void;
}

const COMMAND_PREFIX = "/";
export const KAGGLE_COMMAND_NAME = "kaggle";
export const KAGGLE_COMMAND_DESCRIPTION = "Show my own Kaggle datasets and download them into this project";

/** The chat's commands, wired to the shell's actions */
export function slashCommandsFor(actions: CommandActions): SlashCommand[] {
  return [{ name: KAGGLE_COMMAND_NAME, description: KAGGLE_COMMAND_DESCRIPTION, run: actions.showKaggleDatasets }];
}

/** The text after the leading slash, or null when the box text isn't a command */
export function commandQueryOf(boxText: string): string | null {
  return boxText.startsWith(COMMAND_PREFIX) ? boxText.slice(COMMAND_PREFIX.length) : null;
}

/** The commands whose name starts with the typed text, ignoring case, in list order */
export function commandsMatching(commands: SlashCommand[], query: string): SlashCommand[] {
  const typedName = query.toLowerCase();
  return commands.filter((command) => command.name.toLowerCase().startsWith(typedName));
}

/** The row highlighted after one arrow press, wrapping round at both ends */
export function highlightAfter(index: number, step: 1 | -1, rowCount: number): number {
  if (rowCount === 0) return 0;
  return (index + step + rowCount) % rowCount;
}
