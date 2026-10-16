// ③ Findings, duplicates and the supplement request. Colours have one meaning each:
// red blocks registration (E1–E5, duplicate), orange needs acknowledging (REVIEW, and a
// value that did not become a dictionary term, D-091), grey is for reference (similar).
import { useState } from "react";
import { useSupplement } from "../../api/hooks";
import type { Finding, ReviewPrompt, Selection, TermNote } from "./types";

type Tab = "findings" | "matches" | "supplement";

interface Props {
  jobId: string;
  prompt: ReviewPrompt;
  selection: Selection;
  onSelect: (s: Selection) => void;
  onAcknowledge: (keys: string[]) => void;
  busy: boolean;
}

function codeStyle(code: string): string {
  return code === "REVIEW" ? "bg-orange-100 text-orange-900" : "bg-red-100 text-red-900";
}

export function IssuesPane({ jobId, prompt, selection, onSelect, onAcknowledge, busy }: Props) {
  const [tab, setTab] = useState<Tab>("findings");
  const findings = prompt.result.validation.findings;
  const matches = prompt.result.matches;
  const terms = prompt.term_notes ?? [];
  const tabs: [Tab, string][] = [
    ["findings", `오류 (${findings.length})${terms.length ? ` · 용어 ${terms.length}` : ""}`],
    [
      "matches",
      `중복 ${matches.filter((m) => m.relation === "duplicate").length} · 유사 ${
        matches.filter((m) => m.relation !== "duplicate").length
      }`,
    ],
    ["supplement", "보강 요청"],
  ];
  return (
    <section className="flex min-h-0 min-w-0 flex-col rounded-lg border bg-white [overflow-wrap:anywhere]">
      <div role="tablist" className="flex gap-3 border-b px-3 pt-2 text-sm">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            className={`pb-1 ${tab === id ? "border-b-2 border-blue-700 font-semibold" : "text-gray-500"}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-3 text-sm">
        {tab === "findings" && (
          <>
            <Findings
              findings={findings}
              prompt={prompt}
              selection={selection}
              onSelect={onSelect}
              onAcknowledge={onAcknowledge}
              busy={busy}
            />
            <Terms
              terms={terms}
              prompt={prompt}
              onSelect={onSelect}
              onAcknowledge={onAcknowledge}
              busy={busy}
            />
          </>
        )}
        {tab === "matches" && <Matches prompt={prompt} />}
        {tab === "supplement" && <Supplement jobId={jobId} revision={prompt.revision} />}
      </div>
    </section>
  );
}

function Findings(props: {
  findings: Finding[];
  prompt: ReviewPrompt;
  selection: Selection;
  onSelect: (s: Selection) => void;
  onAcknowledge: (keys: string[]) => void;
  busy: boolean;
}) {
  const { findings, prompt } = props;
  if (findings.length === 0)
    return <p className="text-gray-500">검증 규칙에 걸린 값이 없습니다.</p>;
  // REVIEW findings come in the same order as the server's review_keys.
  let reviewSeen = 0;
  return (
    <ul className="space-y-2">
      {findings.map((f, i) => {
        const key = f.code === "REVIEW" ? prompt.review_keys[reviewSeen++] : undefined;
        const done = key !== undefined && prompt.acknowledged.includes(key);
        const selected = props.selection?.kind === "finding" && props.selection.index === i;
        return (
          <li
            key={`${f.code}-${f.rule_ref}-${f.attribute_ids.join(",")}`}
            className={selected ? "bg-blue-50" : ""}
          >
            <button
              type="button"
              className="text-left"
              onClick={() => props.onSelect({ kind: "finding", index: i })}
            >
              <span className={`mr-2 rounded px-1 text-xs font-semibold ${codeStyle(f.code)}`}>
                {f.code}
              </span>
              {/* the badge already shows the code */}
              {(prompt.finding_notes?.[i] ?? `${f.attribute_ids.join(", ")} — ${f.reason}`).replace(
                `${f.code} `,
                "",
              )}
            </button>
            <div className="text-xs text-gray-400">{f.rule_ref}</div>
            {key !== undefined &&
              (done ? (
                <span className="text-xs text-gray-500">확인함</span>
              ) : (
                <button
                  type="button"
                  disabled={props.busy || !prompt.allowed.includes("acknowledge")}
                  className="text-xs text-orange-800"
                  onClick={() => props.onAcknowledge([key])}
                >
                  확인함으로 표시
                </button>
              ))}
          </li>
        );
      })}
    </ul>
  );
}

interface TermsProps {
  terms: TermNote[];
  prompt: ReviewPrompt;
  onSelect: (s: Selection) => void;
  onAcknowledge: (keys: string[]) => void;
  busy: boolean;
}

// Values kept as written because the dictionary has no such term: correct them to a term
// in the facts pane, or confirm them as written.
function Terms({ terms, prompt, onSelect, onAcknowledge, busy }: TermsProps) {
  if (terms.length === 0) return null;
  return (
    <ul className="mt-3 space-y-2 border-t pt-3">
      {terms.map((t) => (
        <li key={t.key}>
          <button
            type="button"
            className="text-left"
            onClick={() => onSelect({ kind: "fact", index: t.fact_index })}
          >
            <span className="mr-2 rounded bg-orange-100 px-1 text-xs font-semibold text-orange-900">
              용어
            </span>
            {t.message}
          </button>
          <div>
            {prompt.acknowledged.includes(t.key) ? (
              <span className="text-xs text-gray-500">확인함</span>
            ) : (
              <button
                type="button"
                disabled={busy || !prompt.allowed.includes("acknowledge")}
                className="text-xs text-orange-800"
                onClick={() => onAcknowledge([t.key])}
              >
                적힌 그대로 확인
              </button>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

type Match = ReviewPrompt["result"]["matches"][number];

function MatchCard({ m }: { m: Match }) {
  const evidence = m.evidence as Record<string, unknown>;
  const differing = (evidence.differing_attributes as string[] | undefined) ?? [];
  const duplicate = m.relation === "duplicate";
  return (
    <li
      className={`rounded p-2 ${duplicate ? "border-2 border-red-600" : "border border-gray-300 text-gray-700"}`}
    >
      <div>
        <span className="font-semibold">{duplicate ? "동일 제품" : "유사 제품"}</span>{" "}
        <span className="font-mono">{m.registry_id}</span>
      </div>
      <div className="text-xs">
        같은 제조사: {evidence.same_maker ? "예" : "아니오"} · 모델 키 {String(evidence.model_key)}{" "}
        / {String(evidence.registered_model_key)}
        {evidence.name_score !== undefined &&
          ` · 이름 유사도 ${Number(evidence.name_score).toFixed(1)}`}
      </div>
      {differing.length > 0 && (
        <div className="text-xs">값이 다른 속성: {differing.join(", ")}</div>
      )}
    </li>
  );
}

function Matches({ prompt }: { prompt: ReviewPrompt }) {
  const duplicates = prompt.result.matches.filter((m) => m.relation === "duplicate");
  const similar = prompt.result.matches.filter((m) => m.relation !== "duplicate");
  if (duplicates.length + similar.length === 0)
    return <p className="text-gray-500">같거나 비슷한 등록 제품이 없습니다.</p>;
  return (
    <div className="space-y-3">
      {duplicates.length > 0 ? (
        <ul className="space-y-2">
          {duplicates.map((m) => (
            <MatchCard key={m.registry_id} m={m} />
          ))}
        </ul>
      ) : (
        <p>동일 제품은 없습니다.</p>
      )}
      {similar.length > 0 && (
        <details>
          <summary className="cursor-pointer text-gray-600">
            참고: 유사 제품 {similar.length}건 (같은 제조사 · 모델명 유사, 등록을 막지 않음)
          </summary>
          <ul className="mt-2 space-y-2">
            {similar.map((m) => (
              <MatchCard key={m.registry_id} m={m} />
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function Supplement({ jobId, revision }: { jobId: string; revision: number }) {
  const request = useSupplement(jobId, revision);
  if (request.isPending) return <p className="text-gray-500">만드는 중…</p>;
  if (request.isError) return <p className="text-red-700">{request.error.message}</p>;
  const { missing, unreadable, text } = request.data;
  const download = () => {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `supplement-${jobId}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <div className="space-y-2">
      <p className="text-xs text-gray-500">
        시스템은 빠진 값을 채우지 않습니다. 이 목록을 문서 전달자에게 보내 보완 문서를 받으세요.
      </p>
      {missing.length === 0 && unreadable.length === 0 ? (
        <p>보강할 내용이 없습니다.</p>
      ) : (
        <>
          {missing.length > 0 && (
            <ul className="list-disc pl-5">
              {missing.map((m) => (
                <li key={m.attribute}>
                  <span className="font-mono text-xs">{m.attribute}</span> —{" "}
                  {m.expected.datatype.join("/")}
                  {m.expected.unit && `, 단위 ${m.expected.unit}`}
                  {(m.expected.allowed_values ?? []).length > 0 &&
                    `, 허용값 ${(m.expected.allowed_values ?? []).join(", ")}`}
                </li>
              ))}
            </ul>
          )}
          {unreadable.length > 0 && (
            <ul className="list-disc pl-5">
              {unreadable.map((u) => (
                <li key={`${u.attribute}-${u.value_text}`}>
                  <span className="font-mono text-xs">{u.attribute}</span> "{u.shown}" ({u.place})
                  <div className="text-xs">{u.explanation}</div>
                </li>
              ))}
            </ul>
          )}
        </>
      )}
      <button type="button" className="text-blue-700" onClick={download}>
        텍스트로 내려받기
      </button>
    </div>
  );
}
