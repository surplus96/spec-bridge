// One job: waits while the model works, then the three panes (source / attributes /
// findings·matches·supplement) and the decision bar. Every command carries the revision
// of the screen it was made on; the server refuses an out-of-date one (409) and the
// screen reloads.
import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { type ResumeCommand, useBlocks, useJob, useResume } from "../../api/hooks";
import { className, useLabels } from "../../lib/display";
import { type Location, locationsOf } from "../../lib/locate";
import { Badge } from "../../ui/Badge";
import { STATUS } from "../../ui/status";
import { ActionBar } from "./ActionBar";
import { ClassChooser } from "./ClassChooser";
import type { EditTarget } from "./EditForm";
import { FactsPane } from "./FactsPane";
import { IssuesPane } from "./IssuesPane";
import { SourcePane } from "./SourcePane";
import type { Fact, FactEdit, ReviewPrompt, Selection } from "./types";

const STATUS_TEXT: Record<string, string> = {
  running: "처리 중입니다. 모델이 문서를 읽고 있습니다(로컬 모델은 문서당 1~2분).",
  registered: "신규 제품으로 등록되었습니다.",
  linked: "기존 제품에 연결되었습니다. 기존 제품의 값은 바뀌지 않았습니다.",
  cancelled: "취소된 작업입니다.",
  failed: "처리 중 오류가 났습니다.",
  stalled: "서버가 처리 도중 멈췄습니다. 문서를 다시 올려 주세요.",
};

function highlightOf(prompt: ReviewPrompt, selection: Selection): Location[] {
  if (!selection) return [];
  if (selection.kind === "fact") {
    return locationsOf((prompt.result.facts[selection.index] as Fact | undefined)?.occurrences);
  }
  if (selection.kind === "unresolved") {
    const row = prompt.result.unresolved[selection.index] as Fact | undefined;
    return locationsOf(row ? [row.occurrence] : []);
  }
  return locationsOf(prompt.result.validation.findings[selection.index]?.occurrences);
}

function summaryOf(prompt: ReviewPrompt) {
  const findings = prompt.result.validation.findings;
  return {
    block:
      findings.filter((f) => f.code !== "REVIEW").length +
      prompt.result.matches.filter((m) => m.relation === "duplicate").length,
    review: [...prompt.review_keys, ...(prompt.term_notes ?? []).map((t) => t.key)].filter(
      (k) => !prompt.acknowledged.includes(k),
    ).length,
    hints: (prompt.context_hints ?? []).length,
    similar: prompt.result.matches.filter((m) => m.relation !== "duplicate").length,
  };
}

export function ReviewPage({ jobId, onBack }: { jobId: string; onBack: () => void }) {
  const labels = useLabels();
  const job = useJob(jobId);
  const resume = useResume(jobId);
  const [selection, setSelection] = useState<Selection>(null);
  const [editing, setEditing] = useState<EditTarget | null>(null);
  const [picking, setPicking] = useState(false);
  const [picked, setPicked] = useState<number | null>(null);
  const blocks = useBlocks(jobId, picked !== null);

  if (job.isPending) return <p className="p-6 text-gray-500">불러오는 중…</p>;
  if (job.isError) return <p className="p-6 text-red-700">{job.error.message}</p>;
  const view = job.data;
  const prompt = view.prompt;
  const busy = resume.isPending || view.status === "running";
  const send = (command: ResumeCommand, after?: () => void) =>
    resume.mutate(command, {
      onSuccess: () => {
        setSelection(null);
        after?.();
      },
    });
  const pickedBlock =
    picked === null
      ? null
      : { index: picked, text: blocks.data?.[picked]?.text ?? `블록 ${picked}` };
  const notice =
    resume.error?.message ?? (prompt?.kind === "review" ? prompt.notice : prompt?.notice);

  const summary = prompt?.kind === "review" ? summaryOf(prompt) : null;
  const status = STATUS[view.status];
  return (
    <div className="flex h-screen flex-col bg-gray-50 p-4">
      <header className="mb-3 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="inline-flex items-center gap-1 text-sm text-blue-700"
          onClick={onBack}
        >
          <ArrowLeft className="size-4" /> 목록
        </button>
        <h1 className="text-lg font-semibold">{view.file_name ?? view.document_id}</h1>
        {view.class_id && (
          <span className="text-sm text-gray-600">{className(labels, view.class_id)}</span>
        )}
        <Badge tone={status.tone}>{status.label}</Badge>
        {prompt?.kind === "review" && (
          <span className="text-xs text-gray-400">판본 {prompt.revision}</span>
        )}
        {summary && (
          <section className="ml-auto flex flex-wrap gap-2" aria-label="검토 요약">
            <Badge tone={summary.block ? "block" : "done"}>등록 차단 {summary.block}</Badge>
            <Badge tone={summary.review ? "review" : "ref"}>확인 필요 {summary.review}</Badge>
            <Badge tone={summary.hints ? "hint" : "ref"}>문맥 확인 {summary.hints}</Badge>
            <Badge tone="ref">유사 {summary.similar}</Badge>
          </section>
        )}
      </header>
      {notice && (
        <p
          role="alert"
          className="mb-2 rounded-md bg-amber-50 p-2 text-sm text-amber-900 ring-1 ring-amber-200"
        >
          {notice}
        </p>
      )}
      {!prompt && (
        <div className="mx-auto mt-10 w-full max-w-xl rounded-lg border bg-white p-6 text-center">
          <p className="text-base">{STATUS_TEXT[view.status] ?? view.status}</p>
          {view.error && <p className="mt-2 text-sm text-red-700">{view.error}</p>}
          {view.product_id && (
            <p className="mt-3 text-sm">
              제품{" "}
              <a
                className="font-mono text-blue-700 underline"
                href={`#/products/${view.product_id}`}
              >
                {view.product_id}
              </a>
            </p>
          )}
        </div>
      )}
      {prompt?.kind === "choose_class" && (
        <ClassChooser
          prompt={prompt}
          busy={busy}
          onChoose={(classId) => send({ action: "choose_class", class_id: classId })}
          onCancel={() => send({ action: "cancel", reason: "" })}
        />
      )}
      {prompt?.kind === "review" && (
        <>
          <div
            className={`grid min-h-0 flex-1 grid-cols-[minmax(0,9fr)_minmax(0,7fr)_minmax(0,4fr)] gap-3 ${busy ? "opacity-60" : ""}`}
          >
            <SourcePane
              jobId={jobId}
              fileName={view.file_name ?? ""}
              highlight={highlightOf(prompt, selection)}
              picking={picking}
              picked={picked}
              onPick={(index) => {
                setPicked(index);
                setPicking(false);
              }}
            />
            <FactsPane
              prompt={prompt}
              selection={selection}
              onSelect={setSelection}
              editing={editing}
              onEdit={(t) => {
                setEditing(t);
                setPicked(null);
                setPicking(false);
              }}
              pickedBlock={pickedBlock}
              onStartPick={() => setPicking(true)}
              onSubmit={(edit: FactEdit) =>
                send({ action: "edit", revision: prompt.revision, edit }, () => {
                  setEditing(null);
                  setPicked(null);
                })
              }
              busy={busy}
            />
            <IssuesPane
              jobId={jobId}
              prompt={prompt}
              selection={selection}
              onSelect={setSelection}
              onAcknowledge={(keys) =>
                send({ action: "acknowledge", revision: prompt.revision, keys })
              }
              busy={busy}
            />
          </div>
          <ActionBar
            prompt={prompt}
            busy={busy}
            onRegister={() => send({ action: "register_new", revision: prompt.revision })}
            onLink={(target) =>
              send({ action: "link", revision: prompt.revision, target_id: target })
            }
            onCancel={() => send({ action: "cancel", reason: "" })}
          />
        </>
      )}
    </div>
  );
}
