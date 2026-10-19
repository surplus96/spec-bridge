// BOM linking (D-103): upload an Excel / Markdown BOM, read each row's outcome (추가, 이미
// 있음, 검토 대기 and why), pick a product for a pending row with a reason, then apply. The
// server plans again on apply and refuses an out-of-date preview (409). A product that is
// not registered is never created here: it comes in through its spec sheet. A pending row
// can ask for a suggestion (D-112): the model chooses, code verifies, and the suggestion only
// fills the pick form; the reviewer confirms it with "지정".
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Upload, UserCheck } from "lucide-react";
import { type FormEvent, useRef, useState } from "react";
import { api } from "../../api/client";
import type { components } from "../../api/schema";
import { className, useLabels } from "../../lib/display";
import { Badge, type Tone } from "../../ui/Badge";

type BomView = components["schemas"]["BomView"];
type BomRow = components["schemas"]["BomRowView"];
type Pick = components["schemas"]["Pick"];
type Suggestion = components["schemas"]["Suggestion"];

const STATUS: Record<BomRow["status"], { label: string; tone: Tone }> = {
  new: { label: "추가", tone: "info" },
  existing: { label: "이미 있음", tone: "ref" },
  pending: { label: "검토 대기", tone: "review" },
};

function detailOf(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : fallback;
}

interface Props {
  bomId: string | null;
  onOpen: (bomId: string) => void;
  onBack: () => void;
}

export function BomPage({ bomId, onOpen, onBack }: Props) {
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-5xl space-y-4 p-6">
        <header className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="inline-flex items-center gap-1 text-sm text-blue-700"
            onClick={onBack}
          >
            <ArrowLeft className="size-4" /> 목록
          </button>
          <h1 className="text-xl font-semibold">BOM 연결</h1>
          <BomUpload onUploaded={onOpen} />
        </header>
        <p className="text-sm text-gray-600">
          BOM 표의 행을 등록된 제품에 연결해 구성품 관계를 만듭니다. 미리보기를 확인한 뒤
          적용하세요. 등록되지 않은 제품은 여기서 만들지 않습니다.
        </p>
        {bomId ? <BomPreview bomId={bomId} /> : null}
      </div>
    </main>
  );
}

function BomUpload({ onUploaded }: { onUploaded: (bomId: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/boms", { method: "POST", body });
      const data = (await response.json()) as { bom_id?: string; detail?: string };
      if (!response.ok || !data.bom_id) throw new Error(data.detail ?? "올리지 못했습니다");
      return data.bom_id;
    },
    onSuccess: onUploaded,
  });
  return (
    <span className="ml-auto">
      <input
        ref={input}
        type="file"
        accept=".xlsx,.md"
        className="hidden"
        aria-label="BOM 파일"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload.mutate(file);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={upload.isPending}
        className="inline-flex items-center gap-1 rounded bg-blue-700 px-3 py-1 text-white disabled:opacity-40"
        onClick={() => input.current?.click()}
      >
        <Upload className="size-4" /> {upload.isPending ? "올리는 중…" : "BOM 올리기"}
      </button>
      {upload.isError && <span className="ml-2 text-sm text-red-700">{upload.error.message}</span>}
    </span>
  );
}

function BomPreview({ bomId }: { bomId: string }) {
  const labels = useLabels();
  const client = useQueryClient();
  const [picks, setPicks] = useState<Pick[]>([]);
  const preview = useQuery({
    queryKey: ["bom", bomId, picks],
    queryFn: async () => {
      const { data, error } = await api.POST("/api/boms/{bom_id}/preview", {
        params: { path: { bom_id: bomId } },
        body: { picks },
      });
      if (error || !data) throw new Error(detailOf(error, "미리보기를 만들지 못했습니다"));
      return data;
    },
  });
  const applying = useMutation({
    mutationFn: async (view: BomView) => {
      const { data, error } = await api.POST("/api/boms/{bom_id}/apply", {
        params: { path: { bom_id: bomId } },
        body: { plan_key: view.plan_key, picks },
      });
      if (error || !data) throw new Error(detailOf(error, "적용하지 못했습니다"));
      return data;
    },
    onSuccess: (view) => client.setQueryData(["bom", bomId, picks], view),
    onError: () => void client.invalidateQueries({ queryKey: ["bom", bomId] }),
  });
  const choose = (pick: Pick) => setPicks([...picks.filter((p) => p.line !== pick.line), pick]);
  const unpick = (line: number) => setPicks(picks.filter((p) => p.line !== line));

  if (preview.isPending) return <p className="text-gray-500">미리보기를 만드는 중…</p>;
  if (preview.isError) return <p className="text-red-700">{preview.error.message}</p>;
  const view = preview.data;
  const adding = view.rows.filter((r) => r.status === "new").length;
  return (
    <section className="space-y-3 rounded-lg border bg-white p-4">
      <div className="flex flex-wrap items-baseline gap-3 text-sm">
        <span className="font-medium">{view.file_name}</span>
        <span>
          상위 제품{" "}
          <a className="font-mono text-blue-700" href={`#/products/${view.root_id}`}>
            {view.root_id}
          </a>
        </span>
        <span className="text-gray-500">추가 {adding}개</span>
      </div>
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-gray-500">
          <tr>
            <th className="py-1">줄</th>
            <th>구성품</th>
            <th>모델</th>
            <th>제조사</th>
            <th>수량</th>
            <th>상태</th>
            <th>연결 제품</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {view.rows.map((row) => (
            <tr key={row.line} className="align-top">
              <td className="py-2 text-gray-500">{row.line}</td>
              <td>{className(labels, row.component)}</td>
              <td className="font-mono">{row.model}</td>
              <td>{row.maker}</td>
              <td>{row.quantity}</td>
              <td>
                <Badge tone={STATUS[row.status].tone}>{STATUS[row.status].label}</Badge>
                {row.decided_by === "reviewer" && (
                  <Badge tone="info" title={row.reason ?? undefined}>
                    <UserCheck className="size-3" /> 담당자 지정
                  </Badge>
                )}
              </td>
              <td className="space-y-1">
                {row.product_id && (
                  <a className="font-mono text-blue-700" href={`#/products/${row.product_id}`}>
                    {row.product_id}
                  </a>
                )}
                {row.decided_by === "reviewer" && (
                  <button
                    type="button"
                    className="ml-2 text-xs text-gray-600"
                    onClick={() => unpick(row.line)}
                  >
                    지정 취소
                  </button>
                )}
                {row.status === "pending" && (
                  <>
                    <p className="text-xs text-yellow-900">{row.reason}</p>
                    <PickForm bomId={bomId} picks={picks} row={row} onPick={choose} />
                  </>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {view.not_in_bom.length > 0 && (
        <p className="text-xs text-gray-600">
          BOM에 없는 기존 구성품(지우지 않음): {view.not_in_bom.join(", ")}
        </p>
      )}
      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={adding === 0 || applying.isPending}
          className="rounded bg-blue-700 px-3 py-1 text-white disabled:opacity-40"
          onClick={() => applying.mutate(view)}
        >
          적용
        </button>
        {applying.isSuccess && (
          <span role="status" className="text-sm text-green-800">
            관계 {applying.data.added ?? 0}개를 추가했습니다
          </span>
        )}
        {applying.isError && (
          <span role="alert" className="text-sm text-red-700">
            {applying.error.message}
          </span>
        )}
      </div>
    </section>
  );
}

interface PickProps {
  bomId: string;
  picks: Pick[];
  row: BomRow;
  onPick: (pick: Pick) => void;
}

function PickForm({ bomId, picks, row, onPick }: PickProps) {
  const [productId, setProductId] = useState("");
  const [reason, setReason] = useState("");
  const options = row.candidates ?? [];
  const asking = useMutation({
    mutationFn: async (): Promise<Suggestion> => {
      const { data, error } = await api.POST("/api/boms/{bom_id}/suggest", {
        params: { path: { bom_id: bomId } },
        body: { line: row.line, picks },
      });
      if (error || !data) throw new Error(detailOf(error, "제안을 받지 못했습니다"));
      return data;
    },
    onSuccess: (s) => {
      if (s.product_id) {
        setProductId(s.product_id);
        setReason(`모델 제안 확인: ${s.reason}`);
      }
    },
  });
  const suggested = asking.data;
  const named = options.find((c) => c.product_id === suggested?.product_id);
  if (options.length === 0) {
    return (
      <p className="text-xs text-gray-600">
        같은 종류의 등록 제품이 없습니다. <a href="#/">사양서를 먼저 등록</a>한 뒤 다시 미리보세요.
      </p>
    );
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    if (productId && reason.trim()) onPick({ line: row.line, product_id: productId, reason });
  }
  return (
    <form
      onSubmit={submit}
      aria-label={`줄 ${row.line} 제품 지정`}
      className="space-y-1 rounded bg-gray-50 p-2 text-xs"
    >
      <label className="block">
        제품
        <select
          className="ml-1 border"
          value={productId}
          onChange={(e) => setProductId(e.target.value)}
        >
          <option value="">선택</option>
          {options.map((c) => (
            <option key={c.product_id} value={c.product_id}>
              {c.model_designation} · {c.maker_name ?? ""} ({c.product_id})
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        사유(필수)
        <input
          className="ml-1 w-48 border px-1"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="예: BOM의 모델명 오타"
        />
      </label>
      <div className="flex items-center gap-2">
        <button
          type="submit"
          disabled={!productId || !reason.trim()}
          className="rounded bg-gray-700 px-2 py-0.5 text-white disabled:opacity-40"
        >
          지정
        </button>
        <button
          type="button"
          disabled={asking.isPending}
          className="rounded border px-2 py-0.5 disabled:opacity-40"
          onClick={() => asking.mutate()}
        >
          {asking.isPending ? "묻는 중…" : "제안 받기"}
        </button>
      </div>
      {suggested?.product_id && (
        <p className="text-blue-900">
          제안: {named?.model_designation ?? suggested.product_id} ({suggested.product_id}) —{" "}
          {suggested.reason}. 맞으면 "지정"을 누르세요.
        </p>
      )}
      {suggested && !suggested.product_id && (
        <p className="text-gray-700">
          제안 없음 —{" "}
          {suggested.rejected ??
            (suggested.model_answer ? suggested.reason : "모델이 후보를 고르지 않았습니다")}
        </p>
      )}
      {asking.isError && (
        <p role="alert" className="text-red-700">
          {asking.error.message}
        </p>
      )}
      <p className="text-gray-500">목록에 없으면 사양서로 먼저 등록합니다.</p>
    </form>
  );
}
