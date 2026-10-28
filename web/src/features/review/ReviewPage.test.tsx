import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
    context_axes: [],
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
              reviewed: false,
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

  const axes: ReviewPrompt["context_axes"] = [
    { axis: "basis.rating", kind: "token", values: ["MCR", "maximum"], units: [] },
    { axis: "condition.rating_point", kind: "token", values: ["R1", "R2"], units: [] },
    { axis: "condition.frequency", kind: "quantity", values: [], units: ["Hz"] },
    { axis: "scope", kind: "scope", values: [], units: [] },
  ];

  async function openContextForm(onResume: (body: unknown) => void) {
    serve(job(review({ context_axes: axes })), (body) => {
      onResume(body);
      return undefined;
    });
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "문맥 수정" }));
    return screen.getByRole("form", { name: "문맥 수정" });
  }

  it("edits one context axis, a token from the vocabulary (D-100)", async () => {
    let sent: unknown;
    const form = await openContextForm((body) => {
      sent = body;
    });
    const axis = within(form).getByLabelText("축") as HTMLSelectElement;
    expect(axis.value).toBe("condition.rating_point"); // an axis the fact has comes first
    fireEvent.change(axis, { target: { value: "basis.rating" } }); // 축 추가
    const value = within(form).getByLabelText("값") as HTMLSelectElement;
    expect([...value.options].map((o) => o.value)).toEqual(["", "MCR", "maximum"]);
    fireEvent.change(value, { target: { value: "MCR" } });
    fireEvent.change(within(form).getByLabelText("사유(필수)"), { target: { value: "비고 확인" } });
    fireEvent.click(within(form).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(sent).toBeDefined());
    expect(sent).toMatchObject({
      command: {
        action: "edit",
        revision: 3,
        edit: {
          op: "context",
          target: "fact",
          index: 0,
          axis: "basis.rating",
          value_text: "MCR",
          reason: "비고 확인",
        },
      },
    });
  });

  it("clears an axis and types a scope phrase or a quantity as text", async () => {
    const sent: unknown[] = [];
    const form = await openContextForm((body) => sent.push(body));
    const value = within(form).getByLabelText("값") as HTMLSelectElement;
    expect(value.value).toBe("R1"); // the current value
    fireEvent.change(value, { target: { value: "" } }); // 비우기
    fireEvent.change(within(form).getByLabelText("사유(필수)"), { target: { value: "근거 없음" } });
    fireEvent.click(within(form).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(sent).toHaveLength(1));
    expect(sent[0]).toMatchObject({
      command: { edit: { axis: "condition.rating_point", value_text: null } },
    });

    fireEvent.click(await screen.findByRole("button", { name: "문맥 수정" })); // closed on success
    const again = screen.getByRole("form", { name: "문맥 수정" });
    fireEvent.change(within(again).getByLabelText("축"), { target: { value: "scope" } });
    const scope = within(again).getByLabelText("범위 구절") as HTMLInputElement;
    expect(scope.value).toBe("engine shaft");
    fireEvent.change(within(again).getByLabelText("축"), {
      target: { value: "condition.frequency" },
    });
    expect(within(again).getByText(/단위: Hz/)).toBeInTheDocument();
  });
  it("marks a context hint the reviewer has edited (D-100)", async () => {
    serve(
      job(
        review({
          context_hints: [
            {
              fact_index: 0,
              attribute: "rated_power",
              reasons: ["scope: phrase not in the remarks"],
              messages: ["범위 — 범위 구절이 비고에 없음"],
              reviewed: true,
            },
          ],
          edited: [0],
        }),
      ),
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    expect(await screen.findByRole("button", { name: /문맥 확인함/ })).toBeInTheDocument();
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

// The reviewer's decisions (D-063) and the edits besides "set", driven as a user would.
function capture() {
  const box: { sent?: { command: Record<string, unknown> } } = {};
  const onResume = (body: unknown) => {
    box.sent = body as { command: Record<string, unknown> };
    return undefined;
  };
  return { box, onResume };
}

function linkable(): ReviewPrompt {
  const base = review();
  return review({
    link_targets: ["REG-D-1", "REG-S-1"],
    allowed: ["edit", "link", "cancel"],
    blockers: ["first reason", "second reason"],
    result: {
      ...base.result,
      matches: [
        { registry_id: "REG-D-1", relation: "duplicate", evidence: {} },
        { registry_id: "REG-S-1", relation: "similar", evidence: {} },
      ],
    },
  });
}

describe("ReviewPage decisions", () => {
  it("links to the target the reviewer picked, with the screen's revision", async () => {
    const user = userEvent.setup();
    const { box, onResume } = capture();
    serve(job(linkable()), onResume);
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    await user.selectOptions(await screen.findByLabelText("연결 대상"), "REG-S-1");
    await user.click(screen.getByRole("button", { name: "기존 제품에 연결" }));
    await waitFor(() => expect(box.sent).toBeDefined());
    expect(box.sent?.command).toEqual({ action: "link", revision: 3, target_id: "REG-S-1" });
  });

  it("cancels only after the reviewer confirms, and can step back", async () => {
    const user = userEvent.setup();
    const { box, onResume } = capture();
    serve(job(review()), onResume);
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "취소" }));
    expect(screen.getByText(/작업을 취소할까요/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "아니오" }));
    expect(screen.queryByText(/작업을 취소할까요/)).not.toBeInTheDocument();
    expect(box.sent).toBeUndefined();

    await user.click(screen.getByRole("button", { name: "취소" }));
    await user.click(screen.getByRole("button", { name: "예, 취소" }));
    await waitFor(() => expect(box.sent).toBeDefined());
    expect(box.sent?.command).toMatchObject({ action: "cancel" });
  });

  it("opens the full list of reasons registration is blocked", async () => {
    const user = userEvent.setup();
    serve(job(linkable()));
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    const why = await screen.findByRole("region", { name: "등록할 수 없는 이유" });
    const toggle = within(why).getByRole("button", { name: /2건: first reason/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(within(why).queryByRole("listitem")).not.toBeInTheDocument();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(
      within(why)
        .getAllByRole("listitem")
        .map((li) => li.textContent),
    ).toEqual(["first reason", "second reason"]);
  });
});

describe("ReviewPage class choice", () => {
  const choosing: JobView = {
    ...job(null, "awaiting_class"),
    class_id: null,
    prompt: {
      kind: "choose_class",
      candidates: ["Pump", "FourStrokeEngine"],
      classes: ["FourStrokeEngine", "Pump", "Separator"],
      notice: null,
    },
  };

  it("offers the classifier's candidates first and sends the chosen class", async () => {
    const user = userEvent.setup();
    const { box, onResume } = capture();
    serve(choosing, onResume);
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    const select = await screen.findByLabelText("클래스");
    expect(select).toHaveValue("Pump"); // the top candidate
    const groups = within(select).getAllByRole("group");
    expect(
      within(groups[0])
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Pump", "FourStrokeEngine"]);
    expect(
      within(groups[1])
        .getAllByRole("option")
        .map((o) => o.textContent),
    ).toEqual(["Separator"]);
    await user.selectOptions(select, "FourStrokeEngine");
    await user.click(screen.getByRole("button", { name: "이 클래스로 계속" }));
    await waitFor(() => expect(box.sent).toBeDefined());
    expect(box.sent?.command).toEqual({ action: "choose_class", class_id: "FourStrokeEngine" });
  });

  it("can cancel the job instead of choosing", async () => {
    const user = userEvent.setup();
    const { box, onResume } = capture();
    serve(choosing, onResume);
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "작업 취소" }));
    await waitFor(() => expect(box.sent).toBeDefined());
    expect(box.sent?.command).toMatchObject({ action: "cancel" });
  });
});

describe("ReviewPage edits", () => {
  it("adds a value read from a block the reviewer picked in the source", async () => {
    const user = userEvent.setup();
    const { box, onResume } = capture();
    serve(job(review()), onResume);
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    await user.click(await screen.findByRole("button", { name: /값 추가/ }));
    const form = screen.getByRole("form", { name: "값 추가" });
    const apply = within(form).getByRole("button", { name: "적용" });
    await user.selectOptions(within(form).getByLabelText("속성"), "rated_power");
    await user.type(within(form).getByLabelText("값"), "2221.25");
    await user.type(within(form).getByLabelText("단위"), "kW");
    await user.type(within(form).getByLabelText("사유(필수)"), "원문 확인");
    expect(apply).toBeDisabled(); // no block picked yet
    await user.click(within(form).getByRole("button", { name: "원문에서 선택" }));
    await user.click(await screen.findByRole("button", { name: /Rated power 2221.25 kW/ }));
    expect(within(form).getByText("Rated power 2221.25 kW (R1)")).toBeInTheDocument();
    await user.click(apply);
    await waitFor(() => expect(box.sent).toBeDefined());
    expect(box.sent?.command).toEqual({
      action: "edit",
      revision: 3,
      edit: {
        op: "add",
        attribute: "rated_power",
        block: 1,
        value_text: "2221.25",
        unit_text: "kW",
        reason: "원문 확인",
      },
    });
  });

  it("removes a value with only a reason", async () => {
    const user = userEvent.setup();
    const { box, onResume } = capture();
    serve(job(review()), onResume);
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "삭제" }));
    const form = screen.getByRole("form", { name: "값 삭제" });
    expect(within(form).queryByLabelText("값")).not.toBeInTheDocument();
    await user.type(within(form).getByLabelText("사유(필수)"), "다른 제품의 값");
    await user.click(within(form).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(box.sent).toBeDefined());
    expect(box.sent?.command).toEqual({
      action: "edit",
      revision: 3,
      edit: { op: "remove", target: "fact", index: 0, reason: "다른 제품의 값" },
    });
  });

  it("sends a cleared unit as no unit, not an empty string", async () => {
    const user = userEvent.setup();
    const { box, onResume } = capture();
    serve(job(review()), onResume);
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    await user.click(await screen.findByRole("button", { name: "수정" }));
    const form = screen.getByRole("form", { name: "값 수정" });
    await user.clear(within(form).getByLabelText("단위"));
    await user.type(within(form).getByLabelText("사유(필수)"), "단위 없는 값");
    await user.click(within(form).getByRole("button", { name: "적용" }));
    await waitFor(() => expect(box.sent).toBeDefined());
    expect(box.sent?.command).toMatchObject({ edit: { op: "set", unit_text: null } });
  });
});

describe("ReviewPage supplement request", () => {
  it("lists what the document lacks, with the expected form of each value", async () => {
    const user = userEvent.setup();
    serve(job(review()));
    server.use(
      http.get("*/api/jobs/JOB-1/supplement", () =>
        HttpResponse.json({
          document_id: "UP-1",
          file_name: "SYN-011.docx",
          class_id: "FourStrokeEngine",
          missing: [
            {
              attribute: "maker",
              expected: { datatype: ["string"], dimension: "", unit: null, allowed_values: [] },
              rule_ref: "ontology/ontology.yaml#classes/FourStrokeEngine/required_all",
            },
            {
              attribute: "rated_power",
              expected: {
                datatype: ["quantity"],
                dimension: "power",
                unit: "kW",
                allowed_values: [],
              },
              rule_ref: "ontology/ontology.yaml#classes/FourStrokeEngine/required_all",
            },
          ],
          unreadable: [],
          text: "maker\nrated_power\n",
        }),
      ),
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    await user.click(await screen.findByRole("tab", { name: "보강 요청" }));
    const items = await screen.findAllByRole("listitem");
    const texts = items.map((li) => li.textContent);
    expect(texts).toContain("maker — string");
    expect(texts).toContain("rated_power — quantity, 단위 kW");
  });

  it("says when the request could not be made", async () => {
    const user = userEvent.setup();
    serve(job(review()));
    server.use(
      http.get("*/api/jobs/JOB-1/supplement", () => new HttpResponse(null, { status: 500 })),
    );
    renderWithQuery(<ReviewPage jobId="JOB-1" onBack={() => {}} />);
    await user.click(await screen.findByRole("tab", { name: "보강 요청" }));
    expect(await screen.findByText("보강 요청을 만들지 못했습니다")).toBeInTheDocument();
  });
});
