// The decision (D-063), always in view at the bottom. Which buttons work and why the others
// do not come from the server (allowed, blockers): the screen shows them and decides nothing.
import { Ban, Check, ChevronDown, ChevronUp, Link2, X } from "lucide-react";
import { useState } from "react";
import type { ReviewPrompt } from "./types";

interface Props {
  prompt: ReviewPrompt;
  busy: boolean;
  onRegister: () => void;
  onLink: (target: string) => void;
  onCancel: () => void;
}

export function ActionBar({ prompt, busy, onRegister, onLink, onCancel }: Props) {
  const can = (a: ReviewPrompt["allowed"][number]) => !busy && prompt.allowed.includes(a);
  const [target, setTarget] = useState(prompt.link_targets[0] ?? "");
  const [confirming, setConfirming] = useState(false);
  const [open, setOpen] = useState(false);
  const blockers = prompt.blockers;
  const relationOf = Object.fromEntries(
    prompt.result.matches.map((m) => [m.registry_id, m.relation] as const),
  );
  return (
    <footer className="mt-3 rounded-lg border bg-white px-4 py-3 shadow-sm">
      {blockers.length > 0 && (
        <section aria-label="등록할 수 없는 이유" className="mb-2 text-sm text-red-800">
          <button
            type="button"
            className="flex w-full items-center gap-2 text-left"
            onClick={() => setOpen(!open)}
            aria-expanded={open}
          >
            <Ban className="size-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate">
              등록할 수 없는 이유 {blockers.length}건: {blockers[0]}
            </span>
            {open ? <ChevronUp className="size-4" /> : <ChevronDown className="size-4" />}
          </button>
          {open && (
            <ul className="mt-1 list-disc pl-10">
              {blockers.map((b) => (
                <li key={b}>{b}</li>
              ))}
            </ul>
          )}
        </section>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={!can("register_new")}
          onClick={onRegister}
          className="inline-flex items-center gap-1 rounded-md bg-green-700 px-4 py-1.5 text-sm font-medium text-white disabled:bg-gray-300"
        >
          <Check className="size-4" /> 신규 등록
        </button>
        {prompt.link_targets.length > 0 && (
          <span className="flex items-center gap-1">
            <select
              className="rounded-md border px-2 py-1.5 text-sm"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              aria-label="연결 대상"
            >
              {prompt.link_targets.map((t) => (
                <option key={t} value={t}>
                  {t} ({relationOf[t] === "duplicate" ? "동일 제품" : "유사 제품"})
                </option>
              ))}
            </select>
            <button
              type="button"
              disabled={!can("link") || target === ""}
              onClick={() => onLink(target)}
              className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-40"
            >
              <Link2 className="size-4" /> 기존 제품에 연결
            </button>
          </span>
        )}
        <span className="ml-auto text-sm">
          {confirming ? (
            <>
              작업을 취소할까요?{" "}
              <button
                type="button"
                className="text-red-700"
                disabled={!can("cancel")}
                onClick={onCancel}
              >
                예, 취소
              </button>{" "}
              <button type="button" onClick={() => setConfirming(false)}>
                아니오
              </button>
            </>
          ) : (
            <button
              type="button"
              className="inline-flex items-center gap-1 text-gray-600"
              disabled={!can("cancel")}
              onClick={() => setConfirming(true)}
            >
              <X className="size-4" /> 취소
            </button>
          )}
        </span>
      </div>
    </footer>
  );
}
