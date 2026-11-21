// One message you sent, as a bubble on the right.
export function UserMessage({ text }: { text: string }): JSX.Element {
  return (
    <div className="st-enter flex justify-end">
      <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl bg-muted px-4 py-2.5 text-[15px]">{text}</div>
    </div>
  );
}
