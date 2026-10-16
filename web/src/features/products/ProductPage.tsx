// A registered product (W5-7b): every fact with its evidence (NFR-07: a document place, a
// reviewer's edit with its reason, or the seed list), the reviewer's edits, and the events
// (registered, documents linked later — S2 never changes the facts).
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Database, FileText, Link2, Pencil, PlusCircle } from "lucide-react";
import { api } from "../../api/client";
import type { components } from "../../api/schema";
import { attributeName, className, useLabels } from "../../lib/display";
import { contextParts, formatValue } from "../../lib/format";
import { Badge } from "../../ui/Badge";

type Fact = components["schemas"]["ProductFact"];
type Event = components["schemas"]["ProductEvent"];
type Link = components["schemas"]["ProductLink"];

const EVIDENCE = {
  observed: { label: "원문", tone: "ref", Icon: FileText },
  human_edit: { label: "수정됨", tone: "info", Icon: Pencil },
  registry_seed: { label: "기존 목록", tone: "ref", Icon: Database },
} as const;

const EVENTS: Record<string, string> = {
  seed_import: "기존 등록 목록에서 적재",
  registered: "신규 등록",
  linked_document: "문서 연결",
  bom_linked: "BOM 구성품 연결",
};

export function ProductPage({ productId, onBack }: { productId: string; onBack: () => void }) {
  const labels = useLabels();
  const product = useQuery({
    queryKey: ["product", productId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/products/{product_id}", {
        params: { path: { product_id: productId } },
      });
      if (error || !data) throw new Error("제품을 불러오지 못했습니다");
      return data;
    },
  });

  const back = (
    <button
      type="button"
      className="inline-flex items-center gap-1 text-sm text-blue-700"
      onClick={onBack}
    >
      <ArrowLeft className="size-4" /> 목록
    </button>
  );
  if (product.isPending) return <main className="p-6 text-gray-500">불러오는 중…</main>;
  if (product.isError)
    return (
      <main className="space-y-3 p-6">
        {back}
        <p className="text-red-700">{product.error.message}</p>
      </main>
    );
  const p = product.data;
  const counts = p.facts.reduce<Record<string, number>>((acc, f) => {
    acc[f.evidence_kind] = (acc[f.evidence_kind] ?? 0) + 1;
    return acc;
  }, {});
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-5xl space-y-4 p-6">
        {back}
        <header className="rounded-lg border bg-white p-4">
          <div className="flex flex-wrap items-baseline gap-3">
            <h1 className="text-xl font-semibold">{p.model_designation}</h1>
            <span className="text-gray-600">{className(labels, p.class_id)}</span>
            <span className="font-mono text-sm text-gray-500">{p.product_id}</span>
            <Badge tone={p.origin === "user_registered" ? "done" : "ref"}>
              {p.origin === "user_registered" ? "검토 후 등록" : "기존 목록"}
            </Badge>
          </div>
          <p className="mt-1 text-sm text-gray-600">
            제조사 {p.maker_name ?? p.maker_id} · 등록{" "}
            {new Date(p.created_at).toLocaleString("ko-KR")} · 사실 {p.facts.length}개
            {Object.entries(counts).map(([kind, n]) => (
              <span key={kind}>
                {" "}
                · {EVIDENCE[kind as Fact["evidence_kind"]].label} {n}
              </span>
            ))}
          </p>
        </header>

        <section className="rounded-lg border bg-white">
          <h2 className="border-b px-4 py-2 text-sm font-semibold text-gray-700">사실과 근거</h2>
          <ul className="divide-y">
            {p.facts.map((fact) => {
              const evidence = EVIDENCE[fact.evidence_kind];
              const context = contextParts(fact as unknown as Record<string, unknown>, labels);
              return (
                <li
                  key={`${fact.attribute}-${JSON.stringify(fact.value)}-${fact.evidence_ref}`}
                  className="grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_minmax(0,3fr)] gap-3 px-4 py-2 text-sm"
                >
                  <div>
                    <div className="font-medium">{attributeName(labels, fact.attribute)}</div>
                    <div className="font-mono text-[11px] text-gray-400">{fact.attribute}</div>
                  </div>
                  <div>
                    <div className="font-semibold [overflow-wrap:anywhere]">
                      {formatValue(fact.value)}
                      {fact.unit && <span className="font-normal text-gray-500"> {fact.unit}</span>}
                    </div>
                    {context.length > 0 && (
                      <div className="mt-1 flex flex-wrap gap-1">
                        {context.map((c) => (
                          <span
                            key={`${c.name}=${c.value}`}
                            className="rounded bg-gray-100 px-1.5 py-0.5 text-xs"
                          >
                            {c.name}: {c.value}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <div className="flex items-start gap-2">
                    <Badge tone={evidence.tone}>
                      <evidence.Icon className="size-3" /> {evidence.label}
                    </Badge>
                    <span className="text-xs text-gray-600 [overflow-wrap:anywhere]">
                      {fact.evidence_text}
                    </span>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        {p.edits.length > 0 && (
          <section className="rounded-lg border bg-white">
            <h2 className="border-b px-4 py-2 text-sm font-semibold text-gray-700">수정 이력</h2>
            <ul className="divide-y text-sm">
              {p.edits.map((e) => (
                <li key={e.edit_id} className="px-4 py-2">
                  <div>
                    <span className="font-medium">{attributeName(labels, e.attribute)}</span>{" "}
                    {{ set: "수정", add: "추가", remove: "삭제", context: "문맥 수정" }[e.op]} —{" "}
                    <span className="text-gray-700">{e.reason}</span>
                  </div>
                  <div className="text-xs text-gray-500">
                    {e.edit_id} · {e.actor} · {new Date(e.at).toLocaleString("ko-KR")}
                    {e.before &&
                      ` · 이전 ${formatValue((e.before as Record<string, unknown>).value ?? (e.before as Record<string, unknown>).value_text)}`}
                    {e.after &&
                      ` · 이후 ${formatValue((e.after as Record<string, unknown>).value ?? (e.after as Record<string, unknown>).value_text)}`}
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}

        <Links title="구성품" links={p.components ?? []} quantity />
        <Links title="상위 제품" links={p.parents ?? []} />

        <section className="rounded-lg border bg-white">
          <h2 className="border-b px-4 py-2 text-sm font-semibold text-gray-700">이력</h2>
          <ol className="space-y-3 px-4 py-3 text-sm">
            {p.events.map((event) => (
              <EventRow
                key={`${event.event_type}-${event.at}-${JSON.stringify(event.payload.job_id ?? "")}`}
                event={event}
              />
            ))}
          </ol>
        </section>
      </div>
    </main>
  );
}

/** has_component neighbours (D-103): supply-scope inclusion, not compatibility (D-014). */
function Links({ title, links, quantity }: { title: string; links: Link[]; quantity?: boolean }) {
  const labels = useLabels();
  if (links.length === 0) return null;
  return (
    <section aria-label={title} className="rounded-lg border bg-white">
      <h2 className="border-b px-4 py-2 text-sm font-semibold text-gray-700">{title}</h2>
      <ul className="divide-y text-sm">
        {links.map((l) => (
          <li key={l.product_id} className="flex items-baseline gap-3 px-4 py-2">
            <a className="text-blue-700" href={`#/products/${l.product_id}`}>
              {l.model_designation} <span className="font-mono text-xs">({l.product_id})</span>
            </a>
            <span className="text-gray-600">{className(labels, l.class_id)}</span>
            {quantity && l.quantity != null && (
              <span className="text-gray-500">수량 {l.quantity}</span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

function EventRow({ event }: { event: Event }) {
  const payload = event.payload as Record<string, unknown>;
  const Icon =
    event.event_type === "linked_document"
      ? Link2
      : event.event_type === "registered"
        ? PlusCircle
        : Database;
  const differing = (payload.differing_attributes as string[] | undefined) ?? [];
  return (
    <li className="flex gap-3">
      <Icon className="mt-0.5 size-4 shrink-0 text-gray-500" aria-hidden />
      <div>
        <div className="font-medium">{EVENTS[event.event_type] ?? event.event_type}</div>
        <div className="text-xs text-gray-500">
          {new Date(event.at).toLocaleString("ko-KR")} · {event.actor}
          {typeof payload.file_name === "string" && ` · ${payload.file_name}`}
          {typeof payload.job_id === "string" && ` · 작업 ${payload.job_id}`}
          {typeof payload.relation === "string" &&
            ` · 판정 ${payload.relation === "duplicate" ? "동일" : "유사"}`}
        </div>
        {differing.length > 0 && (
          <div className="text-xs">값이 다른 속성: {differing.join(", ")}</div>
        )}
      </div>
    </li>
  );
}
