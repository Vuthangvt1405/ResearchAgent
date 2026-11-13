// Project picker in the header (port of ProjectPicker). The list comes from
// useProjects (TanStack Query, D4). Project names are React text only (SEC1).
import { useState } from "react";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useProjects } from "@/lib/actions";

export interface ProjectPickerProps {
  name: string;
  current: string;
  onSwitch: (id: string) => void;
  onCreate: (name: string) => void;
}

export function ProjectPicker({ name, current, onSwitch, onCreate }: ProjectPickerProps) {
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState<string | null>(null);
  const projects = useProjects(current, true).data || [];
  return (
    <DropdownMenu
      modal={false}
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (!o) setNewName(null);
      }}
    >
      <DropdownMenuTrigger asChild>
        <button className="rcnb-titlebtn" title="Switch project" aria-label={`Project ${name}, switch project`}>
          <span className="rcnb-titletext">{name}</span>
          <ChevronsUpDown size={16} className="rcnb-titlechev" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent data-rc-overlay="project" className="rcnb-mcontent rcnb-projects" align="start" sideOffset={4} aria-label="Projects">
        <div className="rcnb-mhead">Projects</div>
        {!projects.length && <DropdownMenuItem disabled className="rcnb-mitem">Loading…</DropdownMenuItem>}
        {projects.map((p) => (
          <DropdownMenuItem key={p.id} data-rc-item={p.id} className="rcnb-mitem" onSelect={() => onSwitch(p.id)}>
            {p.id === current ? <Check /> : <span className="rcnb-mspacer" />}
            <span className="rcnb-mlabel">{p.name}</span>
          </DropdownMenuItem>
        ))}
        <DropdownMenuSeparator />
        {newName === null ? (
          <DropdownMenuItem
            data-rc-item="__new"
            className="rcnb-mitem"
            onSelect={(e) => {
              // Turn the item into a name field in place; the menu stays open
              e.preventDefault();
              setNewName("");
            }}
          >
            <Plus />
            <span>New project…</span>
          </DropdownMenuItem>
        ) : (
          <form
            className="rcnb-mnew"
            onSubmit={(e) => {
              e.preventDefault();
              const n = newName.trim();
              if (!n) return;
              setOpen(false);
              setNewName(null);
              onCreate(n);
            }}
          >
            <Input
              autoFocus
              data-rc-item="__name"
              className="rcnb-mnew-input"
              value={newName}
              maxLength={80}
              placeholder="Project name"
              aria-label="New project name"
              onChange={(e) => setNewName(e.target.value)}
              // Typing must not trigger the menu's type-to-select; Escape still closes it
              onKeyDown={(e) => e.key !== "Escape" && e.stopPropagation()}
            />
            <Button type="submit" size="sm" className="rcnb-mnew-btn" disabled={!newName.trim()}>Create</Button>
          </form>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
