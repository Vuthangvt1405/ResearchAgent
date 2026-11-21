// Answer text as Markdown: tables, lists, code blocks with Copy; raw HTML stays text.
import { useState, type ReactNode } from "react";
import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";
import { highlightPython } from "@/chat/lib/highlight";
import { safeHref } from "@/panel/lib/safeHref";

const PYTHON = new Set(["python", "py", "python3", "ipython"]);

function CopyButton({ text, label = "Copy" }: { text: string; label?: string }): JSX.Element {
  const [isCopied, setIsCopied] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setIsCopied(true);
    setTimeout(() => setIsCopied(false), 1500);
  };
  return (
    <button type="button" onClick={copy} className="inline-flex h-7 items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground hover:bg-accent hover:text-foreground">
      {isCopied ? <Check className="size-3.5" aria-hidden /> : <Copy className="size-3.5" aria-hidden />}
      {isCopied ? "Copied" : label}
    </button>
  );
}

function CodeBlock({ language, code }: { language: string; code: string }): JSX.Element {
  const body: ReactNode = PYTHON.has(language) ? highlightPython(code) : code;
  return (
    <div className="my-3 overflow-hidden rounded-lg border">
      <div className="flex items-center justify-between border-b bg-muted/50 py-1 pl-3 pr-1 text-xs text-muted-foreground">
        <span>{language || "code"}</span>
        <CopyButton text={code} />
      </div>
      <pre className="st-code overflow-x-auto bg-muted/30 px-3.5 py-3 font-mono text-[13px] leading-relaxed">
        <code>{body}</code>
      </pre>
    </div>
  );
}

const COMPONENTS: Components = {
  a: ({ href, children }) => {
    const safe = safeHref(href);
    if (!safe) return <span>{children}</span>;
    return (
      <a href={safe} target="_blank" rel="noopener noreferrer" className="text-primary underline-offset-2 hover:underline">
        {children}
      </a>
    );
  },
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children }) => {
    const language = /language-(\w+)/.exec(className ?? "")?.[1];
    const text = String(children ?? "");
    const isBlock = language !== undefined || text.includes("\n");
    if (!isBlock) return <code className="rounded-md bg-muted px-1.5 py-0.5 font-mono text-[0.85em]">{children}</code>;
    return <CodeBlock language={language ?? ""} code={text.replace(/\n$/, "")} />;
  },
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border">
      <table className="w-full border-collapse text-sm">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b bg-muted/50 px-3 py-2 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b px-3 py-2 align-top">{children}</td>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-6">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-6">{children}</ol>,
  p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
  h1: ({ children }) => <h3 className="mb-2 mt-4 text-lg font-semibold">{children}</h3>,
  h2: ({ children }) => <h3 className="mb-2 mt-4 text-base font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="mb-1 mt-3 font-semibold">{children}</h4>,
  blockquote: ({ children }) => <blockquote className="my-2 border-l-2 pl-3 text-muted-foreground">{children}</blockquote>,
};

interface MarkdownNode {
  type: string;
  children?: MarkdownNode[];
}

/** Raw HTML in model output becomes plain text: shown as written, never rendered */
function htmlAsText() {
  const walk = (node: MarkdownNode): void => {
    if (node.type === "html") node.type = "text";
    node.children?.forEach(walk);
  };
  return (tree: MarkdownNode) => walk(tree);
}

export function Answer({ text }: { text: string }): JSX.Element {
  return (
    <div className="text-[15px] leading-relaxed break-words">
      <Markdown remarkPlugins={[remarkGfm, htmlAsText]} components={COMPONENTS}>
        {text}
      </Markdown>
    </div>
  );
}

export { CopyButton };
