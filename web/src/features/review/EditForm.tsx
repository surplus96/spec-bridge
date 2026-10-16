// One edit: change a value, add a value read from a block, or remove a value. A reason is
// always required (HumanEdit). The server normalizes and re-validates the value; the form
// does not judge units or numbers (D-063).
import { type FormEvent, useState } from "react";
import { attributeName, useLabels } from "../../lib/display";
import type { FactEdit } from "./types";

export type EditTarget =
  | { op: "set"; target: "fact" | "unresolved"; index: number; valueText: string; unitText: string }
  | { op: "remove"; target: "fact" | "unresolved"; index: number }
  | { op: "add" };

interface Props {
  target: EditTarget;
  attributes: string[];
  pickedBlock: { index: number; text: string } | null;
  onStartPick: () => void;
  onSubmit: (edit: FactEdit) => void;
  onClose: () => void;
  busy: boolean;
}

export function EditForm({
  target,
  attributes,
  pickedBlock,
  onStartPick,
  onSubmit,
  onClose,
  busy,
}: Props) {
  const labels = useLabels();
  const [value, setValue] = useState(target.op === "set" ? target.valueText : "");
  const [unit, setUnit] = useState(target.op === "set" ? target.unitText : "");
  const [attribute, setAttribute] = useState("");
  const [reason, setReason] = useState("");

  const ready =
    reason.trim() !== "" &&
    (target.op === "remove" ||
      (value.trim() !== "" && (target.op === "set" || (attribute !== "" && pickedBlock !== null))));

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!ready) return;
    const unitText = unit.trim() === "" ? null : unit.trim();
    if (target.op === "remove") {
      onSubmit({ op: "remove", target: target.target, index: target.index, reason });
    } else if (target.op === "set") {
      onSubmit({
        op: "set",
        target: target.target,
        index: target.index,
        value_text: value.trim(),
        unit_text: unitText,
        reason,
      });
    } else if (pickedBlock) {
      onSubmit({
        op: "add",
        attribute,
        block: pickedBlock.index,
        value_text: value.trim(),
        unit_text: unitText,
        reason,
      });
    }
  }

  const title = { set: "값 수정", add: "값 추가", remove: "값 삭제" }[target.op];
  return (
    <form
      onSubmit={submit}
      className="mt-2 space-y-2 rounded border bg-gray-50 p-3 text-sm"
      aria-label={title}
    >
      <p className="font-semibold">{title}</p>
      {target.op === "add" && (
        <>
          <label className="block">
            속성
            <select
              className="ml-2 border"
              value={attribute}
              onChange={(e) => setAttribute(e.target.value)}
            >
              <option value="">선택</option>
              {attributes.map((a) => (
                <option key={a} value={a}>
                  {attributeName(labels, a)} ({a})
                </option>
              ))}
            </select>
          </label>
          <div>
            원문 블록:{" "}
            {pickedBlock ? <span className="bg-amber-100 px-1">{pickedBlock.text}</span> : "없음"}
            <button type="button" className="ml-2 text-blue-700" onClick={onStartPick}>
              원문에서 선택
            </button>
          </div>
        </>
      )}
      {target.op !== "remove" && (
        <div className="flex gap-2">
          <label>
            값
            <input
              className="ml-1 w-32 border px-1"
              value={value}
              onChange={(e) => setValue(e.target.value)}
            />
          </label>
          <label>
            단위
            <input
              className="ml-1 w-20 border px-1"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            />
          </label>
        </div>
      )}
      <label className="block">
        사유(필수)
        <input
          className="ml-1 w-full border px-1"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="예: 원문 표와 대조해 확인"
        />
      </label>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!ready || busy}
          className="rounded bg-blue-700 px-3 py-1 text-white disabled:opacity-40"
        >
          적용
        </button>
        <button type="button" onClick={onClose}>
          닫기
        </button>
      </div>
    </form>
  );
}
