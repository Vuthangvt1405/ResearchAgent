// Dataset sort: a shadcn Select (port of DatasetSortSelect). It stays open across
// pushes because nothing remounts it (G1✅2).
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { usePanel } from "@/store";

export const DS_SORTS = { newest: "Newest", name: "Name", size: "Size" } as const;

export function DatasetSortSelect() {
  const sort = usePanel((s) => s.dsSort);
  return (
    <Select value={sort} onValueChange={(v) => usePanel.setState({ dsSort: v as keyof typeof DS_SORTS })}>
      <SelectTrigger className="rcds-sort" title="Sort" aria-label="Sort datasets">
        <SelectValue />
      </SelectTrigger>
      <SelectContent data-rc-overlay="sort" className="rcnb-mcontent">
        {Object.entries(DS_SORTS).map(([k, label]) => (
          <SelectItem key={k} value={k} data-rc-item={k}>{label}</SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
