// The "My Kaggle datasets" window opened by /kaggle: loading, the owned list with search, or why there is none.
import { useState } from "react";
import { CircleAlert, Loader2, Lock, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogClose, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useMyKaggleDatasets, type MyDatasetsView } from "@/chat/components/useMyKaggleDatasets";
import {
  datasetsMatching,
  formatDatasetSize,
  formatUpdatedDate,
  LOADING_TEXT,
  MISSING_DETAIL,
  NO_DATASETS_TEXT,
  NOT_CONNECTED_TEXT,
  PRIVACY_NOTE,
  SEARCH_LABEL,
  SEARCH_PLACEHOLDER,
  SIGNED_OUT_TEXT,
  TRUNCATED_TEXT,
  UNREACHABLE_TEXT,
  WINDOW_TITLE,
  type MyDatasetsAnswer,
  type MyDatasetsState,
  type OwnedKaggleDataset,
} from "@/chat/lib/kaggleDatasets";
import type { CallAction } from "@/panel/types";

export interface KaggleDatasetsWindowProps {
  callAction: CallAction;
  /** A Kaggle sign-in has just ended connected */
  hasSignInFinished: boolean;
  /** Starts the same Kaggle sign-in as the Settings switch */
  onConnect: () => void;
  onClose: () => void;
}

const SKELETON_ROWS = 4;
const NOT_CONNECTED_SUBTITLE = "Not connected";

type Recovery = "connect" | "retry";
// What the window says, and which button it offers, when there is no list to show
const NO_LIST: Record<Exclude<MyDatasetsState, "listed">, { text: string; recovery: Recovery }> = {
  not_connected: { text: NOT_CONNECTED_TEXT, recovery: "connect" },
  signed_out: { text: SIGNED_OUT_TEXT, recovery: "connect" },
  unreachable: { text: UNREACHABLE_TEXT, recovery: "retry" },
};
const RECOVERY_LABELS: Record<Recovery, string> = { connect: "Connect", retry: "Try again" };

export function KaggleDatasetsWindow({ callAction, hasSignInFinished, onConnect, onClose }: KaggleDatasetsWindowProps): JSX.Element {
  const datasets = useMyKaggleDatasets(callAction, hasSignInFinished);
  const recoveries: Record<Recovery, () => void> = { connect: onConnect, retry: datasets.retry };
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="flex max-h-[min(700px,calc(100vh-4rem))] w-[780px] max-w-[calc(100vw-2rem)] flex-col overflow-hidden p-0">
        <div className="flex items-start gap-3 border-b px-5 pb-4 pt-5">
          <DialogHeader className="min-w-0 flex-1">
            <DialogTitle>{WINDOW_TITLE}</DialogTitle>
            <DialogDescription>{subtitleOf(datasets.view)}</DialogDescription>
          </DialogHeader>
          <DialogClose aria-label="Close" className="inline-flex size-8 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-accent">
            <X className="size-4" aria-hidden />
          </DialogClose>
        </div>
        {datasets.view.phase === "loading" ? <LoadingRows /> : <AnsweredBody answer={datasets.view.answer} recoveries={recoveries} />}
        <p className="flex items-center gap-2 border-t px-5 py-3 text-xs text-muted-foreground">
          <Lock className="size-3.5" aria-hidden />
          {PRIVACY_NOTE}
        </p>
      </DialogContent>
    </Dialog>
  );
}

function subtitleOf(view: MyDatasetsView): string {
  if (view.phase === "loading") return "";
  const { state, username } = view.answer;
  if (state === "listed") return `Connected as ${username}`;
  return state === "unreachable" ? "" : NOT_CONNECTED_SUBTITLE;
}

function AnsweredBody({ answer, recoveries }: { answer: MyDatasetsAnswer; recoveries: Record<Recovery, () => void> }): JSX.Element {
  if (answer.state !== "listed") {
    const { text, recovery } = NO_LIST[answer.state];
    return <WindowMessage text={text} action={{ label: RECOVERY_LABELS[recovery], onClick: recoveries[recovery] }} />;
  }
  if (answer.datasets.length === 0) return <WindowMessage text={NO_DATASETS_TEXT} />;
  return <DatasetList datasets={answer.datasets} isTruncated={answer.is_truncated} />;
}

function LoadingRows(): JSX.Element {
  return (
    <div className="flex flex-1 flex-col gap-2.5 p-5">
      <p role="status" className="mb-1.5 flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin motion-reduce:animate-none" aria-hidden />
        {LOADING_TEXT}
      </p>
      {Array.from({ length: SKELETON_ROWS }, (_, index) => (
        <div key={index} aria-hidden className="h-12 rounded-lg bg-muted" style={{ opacity: 1 - index * 0.2 }} />
      ))}
    </div>
  );
}

function WindowMessage({ text, action }: { text: string; action?: { label: string; onClick: () => void } }): JSX.Element {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3.5 p-10 text-center">
      <span className="inline-flex size-11 items-center justify-center rounded-full bg-muted text-muted-foreground">
        <CircleAlert className="size-5" aria-hidden />
      </span>
      <p className="max-w-[380px] text-[15px] leading-[22px]">{text}</p>
      {action && <Button onClick={action.onClick}>{action.label}</Button>}
    </div>
  );
}

function countLabel(count: number): string {
  return count === 1 ? "1 dataset" : `${count} datasets`;
}

function DatasetList({ datasets, isTruncated }: { datasets: OwnedKaggleDataset[]; isTruncated: boolean }): JSX.Element {
  const [searchText, setSearchText] = useState("");
  const shown = datasetsMatching(datasets, searchText);
  return (
    <>
      <div className="px-5 py-3">
        <div className="flex h-9 items-center gap-2 rounded-lg border px-2.5 text-muted-foreground">
          <Search className="size-4 shrink-0" aria-hidden />
          <input
            type="search"
            aria-label={SEARCH_LABEL}
            placeholder={SEARCH_PLACEHOLDER}
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
            className="min-w-0 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
          />
          <span className="shrink-0 text-xs">{countLabel(shown.length)}</span>
        </div>
        {isTruncated && <p className="mt-2 text-xs text-muted-foreground">{TRUNCATED_TEXT}</p>}
      </div>
      <div aria-hidden className="grid grid-cols-[minmax(0,1fr)_6rem_8rem_6.5rem] gap-3 border-b px-5 pb-2 text-xs font-medium text-muted-foreground max-sm:hidden">
        <span>Dataset</span>
        <span>Size</span>
        <span>Licence</span>
        <span>Updated</span>
      </div>
      <ul aria-label="My datasets" className="min-h-0 flex-1 overflow-y-auto">
        {shown.map((dataset) => (
          <DatasetRow key={dataset.ref} dataset={dataset} />
        ))}
      </ul>
      {shown.length === 0 && <p className="px-5 py-6 text-sm text-muted-foreground">No dataset matches “{searchText.trim()}”.</p>}
    </>
  );
}

function DatasetRow({ dataset }: { dataset: OwnedKaggleDataset }): JSX.Element {
  return (
    <li className="grid grid-cols-[minmax(0,1fr)_6rem_8rem_6.5rem] items-center gap-3 border-b px-5 py-3 text-sm max-sm:grid-cols-1 max-sm:gap-1">
      <div className="min-w-0">
        <div className="truncate font-medium">{dataset.title}</div>
        <div className="truncate font-mono text-xs text-muted-foreground">{dataset.ref}</div>
      </div>
      <span>{formatDatasetSize(dataset.total_bytes)}</span>
      <span className="truncate text-muted-foreground">{dataset.licence ?? MISSING_DETAIL}</span>
      <span className="text-muted-foreground">{formatUpdatedDate(dataset.last_updated)}</span>
    </li>
  );
}
