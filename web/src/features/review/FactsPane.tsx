// ② Extracted attributes: what would be registered. Each row: the Korean name (the id small
// below), the value, the context as chips, and status chips — 원문 (read from the document),
// 수정됨 (a reviewer's edit, NFR-07), 문맥 확인 n (verification refused a context the model
// proposed, D-069; folded until opened; 문맥 확인함 once the reviewer edited that context,
// D-100). Edit/context/remove show on the selected or hovered row.
import {
  AlertTriangle,
  CheckCircle2,
  FileText,
  Pencil,
  Plus,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { attributeName, useLabels } from "../../lib/display";
import { contextParts, editableValue, formatContext, formatValue } from "../../lib/format";
import { Badge } from "../../ui/Badge";
import { ContextForm } from "./ContextForm";
import { EditForm, type EditTarget } from "./EditForm";
import type { Fact, FactEdit, ReviewPrompt, Selection } from "./types";

/** Facts are merged on attribute, value and context, so these name one fact. */
const factKey = (f: Fact) =>
  JSON.stringify([f.attribute, f.value, f.unit, f.basis, f.condition, f.scope]);
const rowKey = (r: Fact) =>
  JSON.stringify([r.attribute, r.value_text, r.unit_text, (r.occurrence as Fact)?.location]);

interface Props {
  prompt: ReviewPrompt;
  selection: Selection;
  onSelect: (s: Selection) => void;
  editing: EditTarget | null;
  onEdit: (t: EditTarget | null) => void;
  pickedBlock: { index: number; text: string } | null;
  onStartPick: () => void;
  onSubmit: (edit: FactEdit) => void;
  busy: boolean;
}

export function FactsPane(props: Props) {
  const { prompt, selection, onSelect, editing, onEdit } = props;
  const labels = useLabels();
  const [openHints, setOpenHints] = useState<Set<number>>(new Set());
  const canEdit = prompt.allowed.includes("edit");
  const facts = prompt.result.facts as Fact[];
  const unresolved = prompt.result.unresolved as Fact[];
  const hints = new Map((prompt.context_hints ?? []).map((h) => [h.fact_index, h]));
  const edited = new Set(prompt.edited ?? []);
  const form = (here: (t: EditTarget) => boolean) => {
    if (!editing || !here(editing)) return null;
    if (editing.op === "context") {
      return (
        <ContextForm
          fact={facts[editing.index]}
          index={editing.index}
          axes={prompt.context_axes ?? []}
          onSubmit={props.onSubmit}
          onClose={() => onEdit(null)}
          busy={props.busy}
        />
      );
    }
    return (
      <EditForm
        target={editing}
        attributes={prompt.attributes ?? []}
        pickedBlock={props.pickedBlock}
        onStartPick={props.onStartPick}
        onSubmit={props.onSubmit}
        onClose={() => onEdit(null)}
        busy={props.busy}
      />
    );
  };
  const toggle = (i: number) => {
    const next = new Set(openHints);
    if (next.has(i)) next.delete(i);
    else next.add(i);
    setOpenHints(next);
  };
  const iconButton = "rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-900";

  return (
    <section className="flex min-h-0 min-w-0 flex-col rounded-lg border bg-white">
      <header className="flex items-center justify-between border-b px-3 py-2">
        <h2 className="text-sm font-semibold text-gray-700">
          추출 속성 <span className="font-normal text-gray-400">{facts.length}</span>
        </h2>
        {canEdit && (
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-blue-700"
            onClick={() => onEdit({ op: "add" })}
          >
            <Plus className="size-4" /> 값 추가
          </button>
        )}
      </header>
      <div className="min-h-0 flex-1 overflow-auto">
        <p className="px-3 pt-2 text-xs text-gray-500">
          문맥 확인 표시가 없어도 기준·조건·범위가 완전하다는 뜻은 아닙니다. 값마다 원문과
          대조하세요.
        </p>
        <div className="px-3">{form((t) => t.op === "add")}</div>
        <ul className="divide-y">
          {facts.map((fact, i) => {
            const hint = hints.get(i);
            const selected = selection?.kind === "fact" && selection.index === i;
            const context = contextParts(fact, labels);
            const unit = fact.unit ? ` ${String(fact.unit)}` : "";
            return (
              <li
                key={factKey(fact)}
                className={`group px-3 py-2 ${selected ? "bg-blue-50" : "hover:bg-gray-50"}`}
              >
                <div className="flex items-start gap-2">
                  <button
                    type="button"
                    className="min-w-0 flex-1 text-left"
                    onClick={() => onSelect({ kind: "fact", index: i })}
                  >
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="font-medium text-gray-900">
                        {attributeName(labels, String(fact.attribute))}
                      </span>
                      <span className="text-right font-semibold tabular-nums [overflow-wrap:anywhere]">
                        {formatValue(fact.value)}
                        <span className="font-normal text-gray-500">{unit}</span>
                      </span>
                    </div>
                    <div className="font-mono text-[11px] text-gray-400">
                      {String(fact.attribute)}
                    </div>
                    {context.length > 0 && (
                      <div
                        className="mt-1 flex flex-wrap gap-1"
                        title={formatContext(fact, labels)}
                      >
                        {context.map((c) => (
                          <span
                            key={`${c.name}=${c.value}`}
                            className="max-w-full truncate rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700"
                          >
                            {c.name}: {c.value}
                          </span>
                        ))}
                      </div>
                    )}
                  </button>
                </div>
                <div className="mt-1 flex items-center gap-1">
                  {edited.has(i) ? (
                    <Badge tone="info" title="사람 수정">
                      <Pencil className="size-3" /> 수정됨
                    </Badge>
                  ) : (
                    <Badge tone="ref" title="원문">
                      <FileText className="size-3" /> 원문
                    </Badge>
                  )}
                  {hint && (
                    <button
                      type="button"
                      onClick={() => toggle(i)}
                      aria-expanded={openHints.has(i)}
                    >
                      {hint.reviewed ? (
                        <Badge tone="info" title="담당자가 문맥을 수정함">
                          <CheckCircle2 className="size-3" /> 문맥 확인함
                        </Badge>
                      ) : (
                        <Badge tone="hint">
                          <AlertTriangle className="size-3" /> 문맥 확인{" "}
                          {(hint.messages ?? hint.reasons).length}
                        </Badge>
                      )}
                    </button>
                  )}
                  {canEdit && (
                    <span
                      className={`ml-auto flex gap-1 ${selected ? "" : "opacity-0 group-focus-within:opacity-100 group-hover:opacity-100"}`}
                    >
                      <button
                        type="button"
                        aria-label="수정"
                        className={iconButton}
                        onClick={() =>
                          onEdit({
                            op: "set",
                            target: "fact",
                            index: i,
                            valueText: editableValue(fact.value),
                            unitText: fact.unit ? String(fact.unit) : "",
                          })
                        }
                      >
                        <Pencil className="size-4" />
                      </button>
                      <button
                        type="button"
                        aria-label="문맥 수정"
                        className={iconButton}
                        onClick={() => onEdit({ op: "context", target: "fact", index: i })}
                      >
                        <SlidersHorizontal className="size-4" />
                      </button>
                      <button
                        type="button"
                        aria-label="삭제"
                        className={iconButton}
                        onClick={() => onEdit({ op: "remove", target: "fact", index: i })}
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </span>
                  )}
                </div>
                {hint && openHints.has(i) && (
                  <ul className="mt-1 list-disc rounded bg-yellow-50 py-1 pr-2 pl-6 text-xs text-yellow-900">
                    {(hint.messages ?? hint.reasons).map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                )}
                {form((t) => t.op !== "add" && t.target === "fact" && t.index === i)}
              </li>
            );
          })}
        </ul>
        {unresolved.length > 0 && (
          <div className="border-t px-3 py-2">
            <h3 className="mb-1 text-sm font-semibold text-red-800">
              판독하지 못한 값 <span className="font-normal">{unresolved.length}</span>
            </h3>
            <ul className="space-y-2 text-sm">
              {unresolved.map((row, i) => {
                const selected = selection?.kind === "unresolved" && selection.index === i;
                const note = prompt.unresolved_notes?.[i];
                return (
                  <li
                    key={rowKey(row)}
                    className={`group rounded p-2 ring-1 ring-red-100 ${selected ? "bg-blue-50" : "bg-red-50/40"}`}
                  >
                    <div className="flex items-start gap-2">
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        onClick={() => onSelect({ kind: "unresolved", index: i })}
                      >
                        <span className="font-medium">
                          {attributeName(labels, String(row.attribute))}
                        </span>{" "}
                        <span className="font-semibold">
                          "{note?.shown ?? String(row.value_text)}"
                        </span>
                        <div className="text-xs text-red-800">
                          {note?.explanation ?? String(row.reason)}
                        </div>
                        {note && <div className="text-xs text-gray-500">{note.place}</div>}
                      </button>
                      {canEdit && (
                        <button
                          type="button"
                          aria-label="수정"
                          className={iconButton}
                          onClick={() =>
                            onEdit({
                              op: "set",
                              target: "unresolved",
                              index: i,
                              valueText: String(row.value_text),
                              unitText: row.unit_text ? String(row.unit_text) : "",
                            })
                          }
                        >
                          <Pencil className="size-4" />
                        </button>
                      )}
                    </div>
                    {form((t) => t.op !== "add" && t.target === "unresolved" && t.index === i)}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
        {(prompt.edits ?? []).length > 0 && (
          <div className="border-t px-3 py-2">
            <h3 className="mb-1 text-sm font-semibold text-gray-700">수정 이력</h3>
            <ol className="space-y-1 text-xs text-gray-700">
              {(prompt.edits ?? []).map((e) => (
                <li key={String(e.edit_id)}>
                  <span className="font-medium">{attributeName(labels, String(e.attribute))}</span>{" "}
                  {{ set: "수정", add: "추가", remove: "삭제", context: "문맥 수정" }[
                    String(e.op)
                  ] ?? String(e.op)}
                  {e.axis ? ` (${String(e.axis)})` : ""} — {String(e.reason)}
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    </section>
  );
}
