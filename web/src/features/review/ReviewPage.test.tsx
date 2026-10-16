import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { components } from "../../api/schema";
import { renderWithQuery } from "../../test/render";
import { server } from "../../test/server";
import { ReviewPage } from "./ReviewPage";

type JobView = components["schemas"]["JobView"];
type ReviewPrompt = components["schemas"]["ReviewPrompt"];

const fact = {
  attribute: "rated_power",
  value: 2221.25,
  unit: "kW",
  basis: {},
  condition: { rating_point: "R1" },
  scope: "engine_shaft",
  occurrences: [
    {
      source_document_id: "UP-1",
      raw_text: "2221.25",
      label_text: null,
      unit_text: "kW",
      location: { paragraph: 2 },
    },
  ],
};

function review(overrides: Partial<ReviewPrompt> = {}): ReviewPrompt {
  return {
    kind: "review",
    revision: 3,
    result: {
      schema_version: 1,
      document_id: "UP-1",
      file_name: "SYN-011.docx",
      class_id: "FourStrokeEngine",
      class_candidates: ["FourStrokeEngine"],
      facts: [fact],
      unresolved: [],
      validation: {
        findings: [
          {
            code: "E1",
            attribute_ids: ["maker"],
            occurrences: [],
            rule_ref: "ontology/ontology.yaml#classes/FourStrokeEngine/required_all",
            reason: "required attribute not found in the document",
          },
        ],
        missing_required: ["maker"],
        presence: "missing",
        status: "needs_review",
      },
      matches: [],
      status: "needs_review",
      failure: null,
      provenance: {},
    },
    allowed: ["edit", "cancel"],
    blockers: ["E1 ['maker']: required attribute not found in the document"],
    link_targets: [],
    review_keys: [],
    acknowledged: [],
    context_hints: [],
    term_notes: [],
    finding_notes: ["E1 maker — 필수 값이 문서에 없음"],
    unresolved_notes: [],
    edits: [],
    edited: [],
    attributes: ["maker", "model_designation", "rated_power"],
    notice: null,
    ...overrides,
  };
}

function job(prompt: ReviewPrompt | null, status: JobView["status"] = "awaiting_review"): JobView {
  return {
    job_id: "JOB-1",
    file_name: "SYN-011.docx",
    document_id: "UP-1",
    uploaded_at: "2026-10-14T05:23:34+00:00",
    status,
    class_id: "FourStrokeEngine",
    product_id: null,
    prompt,
    error: null,
  };
}

const blocks = [
  {
    index: 0,
    kind: "title",
    text: "Engine specification",
    section: null,
    location: { paragraph: 1 },
  },
  {
    index: 1,
    kind: "paragraph",
    text: "Rated power 2221.25 kW (R1)",
    section: null,
    location: { paragraph: 2 },
  },
];

function serve(
  view: JobView | (() => JobView),
  onResume?: (body: unknown) => Response | undefined,
) {
  server.use(
    http.get("*/api/jobs/JOB-1", () =>
      HttpResponse.json(typeof view === "function" ? view() : view),
    ),
    http.get("*/api/jobs/JOB-1/blocks", () => HttpResponse.json(blocks)),
    http.get("*/api/jobs/JOB-1/supplement", () =>
      HttpResponse.json({
        document_id: "UP-1",
        file_name: "SYN-011.docx",
        class_id: "FourStrokeEngine",
        missing: [],
        unreadable: [],
        text: "Nothing to supplement.\n",
      }),
    ),
    http.post("*/api/jobs/JOB-1/resume", async ({ request }) => {
      const body = await request.json();
      return onResume?.(body) ?? HttpResponse.json(job(review({ revision: 4 })), { status: 202 });
    }),
  );
}

describe("ReviewPage", () => {
  it("waits while the model works, then shows the three panes", async () => {
    let calls = 0;
    serve(() => (calls++ === 0 ? job(null, "running") : job(review())));
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    expect(await screen.findByText(/처리 중입니다/)).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "원문" }, { timeout: 4000 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "추출 속성 1" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "오류 (1)" })).toBeInTheDocument();
  });

  it("keeps register disabled and says why when the server blocks it", async () => {
    serve(job(review()));
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    expect(await screen.findByRole("button", { name: "신규 등록" })).toBeDisabled();
    const why = screen.getByRole("region", { name: "등록할 수 없는 이유" });
    expect(within(why).getByText(/E1 \['maker'\]/)).toBeInTheDocument();
  });

  it("sends register_new with the screen's revision when the server allows it", async () => {
    let sent: unknown;
    serve(job(review({ allowed: ["edit", "register_new", "cancel"], blockers: [] })), (body) => {
      sent = body;
      return undefined;
    });
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "신규 등록" }));
    await waitFor(() => expect(sent).toBeDefined());
    expect(sent).toMatchObject({ command: { action: "register_new", revision: 3 } });
    expect((sent as { request_id: string }).request_id).not.toBe("");
  });

  it("highlights the block a selected value was read from", async () => {
    serve(job(review()));
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    fireEvent.click(await screen.findByText("rated_power"));
    await waitFor(() =>
      expect(screen.getByTestId("block-1")).toHaveAttribute("data-marked", "true"),
    );
    expect(screen.getByTestId("block-0")).not.toHaveAttribute("data-marked");
  });

  it("sends an edit with its reason, revision and a request id", async () => {
    let sent: unknown;
    serve(job(review()), (body) => {
      sent = body;
      return undefined;
    });
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "수정" }));
    const form = screen.getByRole("form", { name: "값 수정" });
    const apply = within(form).getByRole("button", { name: "적용" });
    expect(apply).toBeDisabled(); // no reason yet
    fireEvent.change(within(form).getByLabelText("값"), { target: { value: "2221.3" } });
    fireEvent.change(within(form).getByLabelText("사유(필수)"), { target: { value: "표와 대조" } });
    fireEvent.click(apply);
    await waitFor(() => expect(sent).toBeDefined());
    expect(sent).toMatchObject({
      command: {
        action: "edit",
        revision: 3,
        edit: {
          op: "set",
          target: "fact",
          index: 0,
          value_text: "2221.3",
          unit_text: "kW",
          reason: "표와 대조",
        },
      },
    });
  });

  it("shows the server's refusal instead of failing silently", async () => {
    serve(job(review({ allowed: ["edit", "register_new", "cancel"], blockers: [] })), () =>
      HttpResponse.json(
        { detail: "the screen is out of date (revision 3, now 4)" },
        { status: 409 },
      ),
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "신규 등록" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("out of date");
  });

  it("marks a fact whose context verification refused (D-069)", async () => {
    serve(
      job(
        review({
          context_hints: [
            {
              fact_index: 0,
              attribute: "rated_power",
              reasons: ["basis.rating: evidence not in the line"],
              messages: ["기준 rating — 모델의 근거 구절이 원문 줄에 없음"],
            },
          ],
          edited: [0],
        }),
      ),
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    const chip = await screen.findByRole("button", { name: /문맥 확인 1/ });
    expect(screen.queryByText("기준 rating — 모델의 근거 구절이 원문 줄에 없음")).toBeNull(); // folded
    fireEvent.click(chip);
    expect(screen.getByText("기준 rating — 모델의 근거 구절이 원문 줄에 없음")).toBeInTheDocument();
    expect(screen.getByTitle("사람 수정")).toBeInTheDocument();
  });

  it("explains findings and unread values in words, unit once", async () => {
    const base = review();
    serve(
      job(
        review({
          result: {
            ...base.result,
            unresolved: [
              {
                attribute: "rated_throughput",
                value_text: "5230.4 kg",
                unit_text: "kg",
                reason: "dimension",
                occurrence: { location: { pdf_page: 1 } },
              },
            ],
          },
          unresolved_notes: [
            {
              shown: "5230.4 kg",
              explanation:
                "단위 차원 불일치: kg는 질량 단위인데, 이 속성은 부피 유량(l/h)이어야 함",
              place: "1쪽 · Specifications · 라벨 Throughput",
            },
          ],
        }),
      ),
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    expect(await screen.findByText(/단위 차원 불일치/)).toBeInTheDocument();
    expect(screen.getByText("1쪽 · Specifications · 라벨 Throughput")).toBeInTheDocument();
    expect(screen.queryByText(/kg kg/)).toBeNull();
    expect(screen.getByText(/필수 값이 문서에 없음/)).toBeInTheDocument();
  });

  it("puts a duplicate first and folds similar products as reference", async () => {
    const base = review();
    const match = (id: string, relation: "duplicate" | "similar") => ({
      registry_id: id,
      relation,
      evidence: { same_maker: true, model_key: "VX1", registered_model_key: "VX1" },
    });
    serve(
      job(
        review({
          result: {
            ...base.result,
            matches: [
              match("REG-S-1", "similar"),
              match("REG-D-1", "duplicate"),
              match("REG-S-2", "similar"),
            ],
          },
        }),
      ),
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    fireEvent.click(await screen.findByRole("tab", { name: "중복 1 · 유사 2" }));
    expect(screen.getByText("REG-D-1")).toBeVisible();
    expect(screen.getByText(/참고: 유사 제품 2건/)).toBeInTheDocument();
    expect(screen.getByText("REG-S-1").closest("details")).not.toHaveAttribute("open");
  });

  it("does not repeat the finding code next to its badge", async () => {
    serve(job(review()));
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    const note = await screen.findByText(/필수 값이 문서에 없음/);
    expect(note.textContent).not.toMatch(/E1 E1/);
    expect(note.textContent?.startsWith("E1")).toBe(true); // the badge, then the note
  });

  it("shows Korean names with the id below, and a summary of what blocks registration", async () => {
    serve(job(review()));
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    expect(await screen.findByText("정격 출력")).toBeInTheDocument();
    expect(screen.getByText("rated_power")).toBeInTheDocument();
    expect(screen.getByText("정격점: R1")).toBeInTheDocument(); // condition chip
    const summary = screen.getByLabelText("검토 요약");
    expect(within(summary).getByText("등록 차단 1")).toBeInTheDocument();
  });

  it("names the relation of each link target", async () => {
    const base = review();
    serve(
      job(
        review({
          link_targets: ["REG-D-1", "REG-S-1"],
          allowed: ["edit", "link", "cancel"],
          result: {
            ...base.result,
            matches: [
              { registry_id: "REG-S-1", relation: "similar", evidence: {} },
              { registry_id: "REG-D-1", relation: "duplicate", evidence: {} },
            ],
          },
        }),
      ),
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    const select = await screen.findByLabelText("연결 대상");
    expect(select).toHaveValue("REG-D-1");
    expect(within(select).getByText("REG-D-1 (동일 제품)")).toBeInTheDocument();
    expect(within(select).getByText("REG-S-1 (유사 제품)")).toBeInTheDocument();
  });

  it("asks to confirm a value the dictionary did not turn into a term (D-091)", async () => {
    const note = {
      key: "TERM|fuel_types|MDO / MGO",
      fact_index: 0,
      attribute: "fuel_types",
      value: "MDO / MGO",
      known: ["MDO", "MGO"],
      message: "fuel_types 'MDO / MGO' — 표준 용어로 바뀌지 않은 값. 사전 용어: MDO, MGO",
    };
    let sent: unknown;
    serve(
      job(review({ term_notes: [note], allowed: ["edit", "acknowledge", "cancel"] })),
      (body) => {
        sent = body;
        return undefined;
      },
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    expect(await screen.findByText(note.message)).toBeInTheDocument();
    expect(screen.getByText(/확인 필요 1/)).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "오류 (1) · 용어 1" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "적힌 그대로 확인" }));
    await waitFor(() => expect(sent).toBeDefined());
    expect(sent).toMatchObject({
      command: { action: "acknowledge", revision: 3, keys: [note.key] },
    });
  });
});
