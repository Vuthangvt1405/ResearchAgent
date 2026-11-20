// The few icons the page-level buttons draw, built as SVG elements (no HTML strings).
const SVG_NS = "http://www.w3.org/2000/svg";

type Shape = [tag: "path" | "rect" | "circle", attributes: Record<string, string>];

const ICONS = {
  settings: [
    ["path", { d: "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z" }],
    ["circle", { cx: "12", cy: "12", r: "3" }],
  ],
  panelClose: [
    ["rect", { width: "18", height: "18", x: "3", y: "3", rx: "2" }],
    ["path", { d: "M15 3v18" }],
    ["path", { d: "m8 9 3 3-3 3" }],
  ],
  panelOpen: [
    ["rect", { width: "18", height: "18", x: "3", y: "3", rx: "2" }],
    ["path", { d: "M15 3v18" }],
    ["path", { d: "m10 15-3-3 3-3" }],
  ],
} satisfies Record<string, Shape[]>;

export type IconName = keyof typeof ICONS;

export function createIcon(doc: Document, name: IconName, sizePx: number): HTMLSpanElement {
  const span = doc.createElement("span");
  span.style.cssText = "display:inline-flex;flex:none";
  const svg = doc.createElementNS(SVG_NS, "svg");
  const svgAttributes = {
    width: String(sizePx), height: String(sizePx), viewBox: "0 0 24 24", fill: "none", stroke: "currentColor",
    "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round",
  };
  for (const [key, value] of Object.entries(svgAttributes)) svg.setAttribute(key, value);
  for (const [tag, attributes] of ICONS[name] as Shape[]) {
    const shape = doc.createElementNS(SVG_NS, tag);
    for (const [key, value] of Object.entries(attributes)) shape.setAttribute(key, value);
    svg.appendChild(shape);
  }
  span.appendChild(svg);
  return span;
}
