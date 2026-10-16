import { screen, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { components } from "../../api/schema";
import { renderWithQuery } from "../../test/render";
import { server } from "../../test/server";
import { ProductPage } from "./ProductPage";

type ProductView = components["schemas"]["ProductView"];

const product: ProductView = {
  product_id: "REG-UP-1",
  class_id: "FourStrokeEngine",
  maker_id: "SG-MAKER-01",
  model_designation: "VX005-111",
  origin: "user_registered",
  created_at: "2026-10-14T05:25:00+00:00",
  facts: [
    {
      attribute: "rated_power",
      value: 2221.25,
      unit: "kW",
      basis: {},
      condition: { rating_point: "R1" },
      scope: "engine_shaft",
      evidence_kind: "observed",
      evidence_ref: "{}",
      evidence_text: "UP-1 · 1쪽 · Specifications · 라벨 Rated power",
    },
    {
      attribute: "maker",
      value: "SGDW Synthetic Works",
      unit: null,
      basis: {},
      condition: {},
      scope: "main_equipment",
      evidence_kind: "human_edit",
      evidence_ref: "JOB-1-E1",
      evidence_text: "사람 수정 JOB-1-E1: 원문 표와 대조",
    },
  ],
  edits: [
    {
      edit_id: "JOB-1-E1",
      job_id: "JOB-1",
      attribute: "maker",
      op: "add",
      before: null,
      after: { value: "SGDW Synthetic Works" },
      outcome: "fact",
      reason: "원문 표와 대조",
      actor: "reviewer",
      at: "2026-10-14T05:24:00+00:00",
    },
  ],
  events: [
    {
      event_type: "registered",
      actor: "reviewer",
      at: "2026-10-14T05:25:00+00:00",
      payload: { job_id: "JOB-1" },
    },
    {
      event_type: "linked_document",
      actor: "reviewer",
      at: "2026-10-14T05:31:00+00:00",
      payload: {
        job_id: "JOB-2",
        file_name: "SYN-011.docx",
        relation: "duplicate",
        differing_attributes: [],
      },
    },
  ],
  components: [],
  parents: [],
};

describe("ProductPage", () => {
  it("shows every fact with its evidence in words", async () => {
    server.use(http.get("*/api/products/REG-UP-1", () => HttpResponse.json(product)));
    renderWithQuery(<ProductPage productId="REG-UP-1" onBack={() => {}} />);
    const facts = await screen.findByRole("heading", { name: "사실과 근거" });
    const list = facts.parentElement as HTMLElement;
    expect(within(list).getByText("정격 출력")).toBeInTheDocument();
    expect(
      within(list).getByText("UP-1 · 1쪽 · Specifications · 라벨 Rated power"),
    ).toBeInTheDocument();
    expect(within(list).getByText("사람 수정 JOB-1-E1: 원문 표와 대조")).toBeInTheDocument();
    expect(screen.getByText(/원문 1/)).toBeInTheDocument();
  });

  it("lists the edits and the history, with the linked document", async () => {
    server.use(http.get("*/api/products/REG-UP-1", () => HttpResponse.json(product)));
    renderWithQuery(<ProductPage productId="REG-UP-1" onBack={() => {}} />);
    expect(await screen.findByText("신규 등록")).toBeInTheDocument();
    expect(screen.getByText("문서 연결")).toBeInTheDocument();
    expect(screen.getByText(/SYN-011\.docx · 작업 JOB-2 · 판정 동일/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "수정 이력" })).toBeInTheDocument();
  });

  it("says so when the product does not exist", async () => {
    server.use(
      http.get("*/api/products/NOPE", () => HttpResponse.json({ detail: "no" }, { status: 404 })),
    );
    renderWithQuery(<ProductPage productId="NOPE" onBack={() => {}} />);
    expect(await screen.findByText("제품을 불러오지 못했습니다")).toBeInTheDocument();
  });

  it("lists the components with their BOM quantity and the parents (D-103)", async () => {
    const withLinks: ProductView = {
      ...product,
      components: [
        {
          product_id: "REG-TC-1",
          class_id: "Turbocharger",
          model_designation: "VX021-1",
          quantity: 2,
        },
      ],
      parents: [
        {
          product_id: "REG-2S-1",
          class_id: "TwoStrokeMainEngine",
          model_designation: "VX001-1",
          quantity: null,
        },
      ],
    };
    server.use(http.get("*/api/products/REG-UP-1", () => HttpResponse.json(withLinks)));
    renderWithQuery(<ProductPage productId="REG-UP-1" onBack={() => {}} />);
    const parts = await screen.findByRole("region", { name: "구성품" });
    expect(within(parts).getByRole("link", { name: /VX021-1/ })).toHaveAttribute(
      "href",
      "#/products/REG-TC-1",
    );
    expect(within(parts).getByText("수량 2")).toBeInTheDocument();
    const up = screen.getByRole("region", { name: "상위 제품" });
    expect(within(up).getByRole("link", { name: /VX001-1/ })).toHaveAttribute(
      "href",
      "#/products/REG-2S-1",
    );
  });
});
