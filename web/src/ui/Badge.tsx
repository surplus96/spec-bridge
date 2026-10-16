// One colour per meaning across the whole UI (D-074):
//   block   red     registration is blocked (E1–E5, duplicate)
//   review  orange  needs the reviewer's acknowledgement (REVIEW)
//   hint    yellow  context worth checking (D-069)
//   ref     grey    for reference (similar products)
//   done    green   registered / linked / ready
//   info    blue    in progress, edited by a person
import type { ReactNode } from "react";

export type Tone = "block" | "review" | "hint" | "ref" | "done" | "info";

const TONES: Record<Tone, string> = {
  block: "bg-red-50 text-red-800 ring-red-200",
  review: "bg-orange-50 text-orange-800 ring-orange-200",
  hint: "bg-yellow-50 text-yellow-900 ring-yellow-300",
  ref: "bg-gray-50 text-gray-700 ring-gray-200",
  done: "bg-green-50 text-green-800 ring-green-200",
  info: "bg-blue-50 text-blue-800 ring-blue-200",
};

export function Badge({
  tone,
  children,
  title,
}: {
  tone: Tone;
  children: ReactNode;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}
