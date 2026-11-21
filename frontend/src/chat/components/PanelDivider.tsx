// The line between the chat and the notebook: drag it, or focus it and use the arrow keys.
import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { CHAT_WIDTH_STEP, MIN_CHAT_WIDTH } from "@/chat/lib/layout";

export interface PanelDividerProps {
  width: number;
  maxWidth: number;
  /** Where the row the chat sits in starts, so a pointer position becomes a width */
  rowLeft: () => number;
  onResize: (width: number) => void;
  onResizeDone: () => void;
  onDraggingChange: (isDragging: boolean) => void;
}

const KEY_STEPS: Record<string, number> = { ArrowRight: CHAT_WIDTH_STEP, ArrowLeft: -CHAT_WIDTH_STEP };

export function PanelDivider({ width, maxWidth, rowLeft, onResize, onResizeDone, onDraggingChange }: PanelDividerProps): JSX.Element {
  const isDragging = useRef(false);
  const [isActive, setIsActive] = useState(false);

  const setDragging = (value: boolean) => {
    isDragging.current = value;
    setIsActive(value);
    onDraggingChange(value);
  };
  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();
    try {
      event.currentTarget.setPointerCapture?.(event.pointerId); // keeps the drag when the pointer leaves the line
    } catch {
      // a pointer the browser no longer tracks: the drag still works while over the line
    }
    setDragging(true);
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    if (isDragging.current) onResize(event.clientX - rowLeft());
  };
  const onPointerUp = (event: PointerEvent<HTMLDivElement>) => {
    if (!isDragging.current) return;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    setDragging(false);
    onResizeDone();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = KEY_STEPS[event.key];
    const target = step !== undefined ? width + step : event.key === "Home" ? MIN_CHAT_WIDTH : event.key === "End" ? maxWidth : null;
    if (target === null) return;
    event.preventDefault();
    onResize(target);
    onResizeDone();
  };

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the chat and the notebook"
      aria-valuenow={width}
      aria-valuemin={MIN_CHAT_WIDTH}
      aria-valuemax={maxWidth}
      tabIndex={0}
      data-active={isActive || undefined}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
      onKeyDown={onKeyDown}
      className="group relative z-10 -mx-1 w-2 shrink-0 cursor-col-resize touch-none outline-none max-md:hidden"
    >
      <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border transition-[background-color,width] duration-150 group-hover:w-0.5 group-hover:bg-primary/60 group-focus-visible:w-0.5 group-focus-visible:bg-primary group-data-[active]:w-0.5 group-data-[active]:bg-primary" />
      <span className="absolute left-1/2 top-1/2 h-8 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-muted-foreground/30 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-data-[active]:opacity-100" />
    </div>
  );
}
