// One context edit (D-100): pick one axis of the fact's basis, condition or scope and set,
// change or clear it, with a reason. Tokens come from the ontology vocabulary the server
// sends (context_axes); quantities and scope phrases are typed, and the server reads them
// with the same normalizer as extraction (a scope phrase must be in the document).
import { type FormEvent, useState } from "react";
import { axisName, humanize, type Labels, useLabels } from "../../lib/display";
import type { ContextAxis, Fact, FactEdit } from "./types";

const NO_SCOPE = new Set(["main_equipment", "unknown", ""]);

interface Props {
  fact: Fact;
  index: number;
  axes: ContextAxis[];
  onSubmit: (edit: FactEdit) => void;
  onClose: () => void;
  busy: boolean;
}

interface Quantity {
  value: unknown;
  unit: unknown;
  reference_temperature?: { value: unknown; unit: unknown };
}

/** The fact's current value on an axis as the form shows it; "" when the axis is unset. */
export function currentText(fact: Fact, axis: string): string {
  if (axis === "scope") {
    const scope = String(fact.scope ?? "");
    return NO_SCOPE.has(scope) ? "" : humanize(scope);
  }
  const [group, key] = axis.split(".");
  const value = ((fact[group] as Record<string, unknown>) ?? {})[key];
  if (value == null || value === "unknown") return "";
  if (typeof value !== "object") return String(value);
  const q = value as Quantity;
  const main = `${String(q.value)} ${String(q.unit)}`;
  const t = q.reference_temperature;
  return t ? `${main} at ${String(t.value)} ${String(t.unit)}` : main;
}

/** "정격 기준 (basis.rating)": the Korean name already says what it is, the id says where. */
function axisLabel(labels: Labels | undefined, axis: string): string {
  if (axis === "scope") return "범위 (scope)";
  const [group, key] = axis.split(".");
  return `${axisName(labels, group as "basis" | "condition", key)} (${axis})`;
}

export function ContextForm({ fact, index, axes, onSubmit, onClose, busy }: Props) {
  const labels = useLabels();
  const present = axes.filter((a) => currentText(fact, a.axis) !== "");
  const others = axes.filter((a) => currentText(fact, a.axis) === "");
  const [axis, setAxis] = useState(present[0]?.axis ?? "");
  const [value, setValue] = useState(axis ? currentText(fact, axis) : "");
  const [reason, setReason] = useState("");
  const chosen = axes.find((a) => a.axis === axis);

  function choose(next: string) {
    setAxis(next);
    setValue(next ? currentText(fact, next) : "");
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!chosen || reason.trim() === "") return;
    const text = value.trim();
    onSubmit({
      op: "context",
      target: "fact",
      index,
      axis: chosen.axis,
      value_text: text === "" ? null : text,
      reason,
    });
  }

  const option = (a: ContextAxis) => (
    <option key={a.axis} value={a.axis}>
      {axisLabel(labels, a.axis)}
    </option>
  );
  const quantity = chosen?.kind === "quantity" || chosen?.kind === "reference_quantity";
  return (
    <form
      onSubmit={submit}
      className="mt-2 space-y-2 rounded border bg-gray-50 p-3 text-sm"
      aria-label="문맥 수정"
    >
      <p className="font-semibold">문맥 수정</p>
      <p className="text-xs text-gray-500">한 번에 축 하나를 고칩니다. 비우면 그 축을 지웁니다.</p>
      <label className="block">
        축
        <select className="ml-2 border" value={axis} onChange={(e) => choose(e.target.value)}>
          <option value="">선택</option>
          {present.length > 0 && (
            <optgroup label="현재 값이 있는 축">{present.map(option)}</optgroup>
          )}
          <optgroup label="축 추가">{others.map(option)}</optgroup>
        </select>
      </label>
      {chosen?.kind === "token" && (
        <label className="block">
          값
          <select className="ml-2 border" value={value} onChange={(e) => setValue(e.target.value)}>
            <option value="">(비우기)</option>
            {(chosen.values ?? []).map((v) => (
              <option key={v} value={v}>
                {humanize(v)}
              </option>
            ))}
          </select>
        </label>
      )}
      {quantity && (
        <label className="block">
          값
          <input
            className="ml-1 w-48 border px-1"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder={chosen?.kind === "quantity" ? "숫자 단위" : "숫자 단위 at 숫자 단위"}
          />
          <span className="ml-2 text-xs text-gray-500">
            단위: {(chosen?.units ?? []).join(", ")}
          </span>
        </label>
      )}
      {chosen?.kind === "scope" && (
        <label className="block">
          범위 구절
          <input
            className="ml-1 w-full border px-1"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="문서에 적힌 구절 (비우면 범위 없음)"
          />
        </label>
      )}
      <label className="block">
        사유(필수)
        <input
          className="ml-1 w-full border px-1"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="예: 비고의 정격 조건과 대조"
        />
      </label>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={!chosen || reason.trim() === "" || busy}
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
