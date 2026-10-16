// The classifier could not decide (D-062 stop 1): the reviewer picks the class.
import { useState } from "react";
import type { ClassPrompt } from "./types";

export function ClassChooser(props: {
  prompt: ClassPrompt;
  busy: boolean;
  onChoose: (classId: string) => void;
  onCancel: () => void;
}) {
  const { prompt } = props;
  const others = prompt.classes.filter((c) => !prompt.candidates.includes(c));
  const [choice, setChoice] = useState(prompt.candidates[0] ?? prompt.classes[0] ?? "");
  return (
    <section className="space-y-3">
      <p>분류기가 클래스를 정하지 못했습니다. 문서의 제품 클래스를 골라 주세요.</p>
      <select
        className="border"
        value={choice}
        onChange={(e) => setChoice(e.target.value)}
        aria-label="클래스"
      >
        {prompt.candidates.length > 0 && (
          <optgroup label="분류기 후보 (순위순)">
            {prompt.candidates.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </optgroup>
        )}
        <optgroup label="다른 클래스">
          {others.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </optgroup>
      </select>
      <div className="flex gap-3">
        <button
          type="button"
          disabled={props.busy || choice === ""}
          className="rounded bg-blue-700 px-3 py-1 text-white disabled:opacity-40"
          onClick={() => props.onChoose(choice)}
        >
          이 클래스로 계속
        </button>
        <button type="button" disabled={props.busy} onClick={props.onCancel}>
          작업 취소
        </button>
      </div>
    </section>
  );
}
