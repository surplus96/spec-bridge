import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { components } from "../../api/schema";
import { renderWithQuery } from "../../test/render";
import { server } from "../../test/server";
import { BomPage } from "./BomPage";

type BomView = components["schemas"]["BomView"];

const row = {
  component: "Turbocharger",
  model: "VX021-002",
  maker: "Synthetic Works A",
  quantity: 1,
  line: 9,
  status: "new" as const,
  product_id: "REG-TC-002",
  reason: null,
  decided_by: "rule" as const,
  candidates: [],
};

function bom(overrides: Partial<BomView> = {}): BomView {
  return {
    bom_id: "BOM-UP-1",
    file_name: "BOM-001.md",
    sha256: "ab",
    root_id: "REG-2S-001",
    rows: [
      row,
      {
        ...row,
        component: "Pump",
        model: "VX999-999",
        line: 10,
        status: "pending",
        product_id: null,
        reason: "Synthetic Works A VX999-999 is not in the registry",
        candidates: [
          {
            product_id: "REG-PUMP-001",
            class_id: "Pump",
            model_designation: "VX013-001",
            maker_name: "Synthetic Works A",
          },
        ],
      },
    ],
    not_in_bom: [],
    plan_key: "k1",
    added: null,
    ...overrides,
  };
}

function serve(onPost: (url: string, body: unknown) => Response | undefined = () => undefined) {
  server.use(
    http.post("*/api/boms/BOM-UP-1/preview", async ({ request }) => {
      const body = await request.json();
      return onPost(request.url, body) ?? HttpResponse.json(bom());
    }),
    http.post("*/api/boms/BOM-UP-1/apply", async ({ request }) => {
      const body = await request.json();
      return onPost(request.url, body) ?? HttpResponse.json(bom({ added: 1 }));
    }),
  );
}

describe("BomPage", () => {
  it("shows each row's outcome and why a row waits (D-103)", async () => {
    serve();
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    const rows = await screen.findAllByRole("row");
    expect(within(rows[1]).getByText("추가")).toBeInTheDocument();
    expect(within(rows[2]).getByText("검토 대기")).toBeInTheDocument();
    expect(within(rows[2]).getByText(/not in the registry/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "REG-2S-001" })).toHaveAttribute(
      "href",
      "#/products/REG-2S-001",
    );
  });

  it("sends a reviewer's pick with its reason, then applies with the preview's key", async () => {
    const sent: { url: string; body: unknown }[] = [];
    serve((url, body) => {
      sent.push({ url, body });
      return undefined;
    });
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    const pick = await screen.findByRole("form", { name: "줄 10 제품 지정" });
    fireEvent.change(within(pick).getByLabelText("제품"), { target: { value: "REG-PUMP-001" } });
    fireEvent.change(within(pick).getByLabelText("사유(필수)"), { target: { value: "BOM 오타" } });
    fireEvent.click(within(pick).getByRole("button", { name: "지정" }));
    const picked = { line: 10, product_id: "REG-PUMP-001", reason: "BOM 오타" };
    await waitFor(() =>
      expect(sent.some((s) => JSON.stringify(s.body) === JSON.stringify({ picks: [picked] }))).toBe(
        true,
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "적용" }));
    await waitFor(() => expect(sent.some((s) => s.url.endsWith("/apply"))).toBe(true));
    const applied = sent.find((s) => s.url.endsWith("/apply"));
    expect(applied?.body).toEqual({ plan_key: "k1", picks: [picked] });
    expect(await screen.findByRole("status")).toHaveTextContent("관계 1개를 추가했습니다");
  });

  it("says when the preview is out of date instead of applying", async () => {
    serve((url) =>
      url.endsWith("/apply")
        ? HttpResponse.json({ detail: "the preview is out of date" }, { status: 409 })
        : undefined,
    );
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "적용" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("out of date");
  });

  it("disables apply when nothing would be added", async () => {
    server.use(
      http.post("*/api/boms/BOM-UP-1/preview", () =>
        HttpResponse.json(bom({ rows: [{ ...row, status: "existing" }] })),
      ),
    );
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    expect(await screen.findByRole("button", { name: "적용" })).toBeDisabled();
  });

  function serveSuggestion(reply: () => Response) {
    serve();
    server.use(http.post("*/api/boms/BOM-UP-1/suggest", reply));
  }

  it("fills the pick form with a verified suggestion for the reviewer to confirm (D-112)", async () => {
    serveSuggestion(() =>
      HttpResponse.json({
        line: 10,
        product_id: "REG-PUMP-001",
        model_answer: "REG-PUMP-001",
        reason: "same maker, letters swapped",
        rejected: null,
        unavailable: null,
      }),
    );
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    const pick = await screen.findByRole("form", { name: "줄 10 제품 지정" });
    fireEvent.click(within(pick).getByRole("button", { name: "제안 받기" }));
    expect(await within(pick).findByText(/제안: VX013-001/)).toBeInTheDocument();
    expect((within(pick).getByLabelText("제품") as HTMLSelectElement).value).toBe("REG-PUMP-001");
    expect((within(pick).getByLabelText("사유(필수)") as HTMLInputElement).value).toMatch(
      /모델 제안 확인/,
    );
  });

  it("says when there is no suggestion and why", async () => {
    serveSuggestion(() =>
      HttpResponse.json({
        line: 10,
        product_id: null,
        model_answer: "REG-PUMP-001",
        reason: "closest",
        rejected: "the row's model cell does not hold VX013-001",
        unavailable: null,
      }),
    );
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    const pick = await screen.findByRole("form", { name: "줄 10 제품 지정" });
    fireEvent.click(within(pick).getByRole("button", { name: "제안 받기" }));
    expect(await within(pick).findByText(/제안 없음/)).toHaveTextContent("does not hold");
    expect((within(pick).getByLabelText("제품") as HTMLSelectElement).value).toBe("");
  });

  it("says when the model server cannot be reached", async () => {
    serveSuggestion(() =>
      HttpResponse.json({ detail: "the model server cannot be reached: down" }, { status: 503 }),
    );
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    const pick = await screen.findByRole("form", { name: "줄 10 제품 지정" });
    fireEvent.click(within(pick).getByRole("button", { name: "제안 받기" }));
    expect(await within(pick).findByRole("alert")).toHaveTextContent("cannot be reached");
  });
});
