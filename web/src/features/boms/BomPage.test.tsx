import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
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

describe("BomPage upload", () => {
  const md = () => new File(["| a |"], "BOM-001.md");

  it("opens the uploaded BOM", async () => {
    const user = userEvent.setup();
    const onOpen = vi.fn();
    server.use(http.post("*/api/boms", () => HttpResponse.json({ bom_id: "BOM-UP-9" })));
    renderWithQuery(<BomPage bomId={null} onOpen={onOpen} onBack={() => {}} />);
    await user.upload(screen.getByLabelText("BOM 파일"), md());
    await waitFor(() => expect(onOpen).toHaveBeenCalledOnce());
    expect(onOpen.mock.calls[0][0]).toBe("BOM-UP-9");
  });

  it("shows the server's reason for a refusal", async () => {
    const user = userEvent.setup();
    const detail = "the file is larger than 52428800 bytes";
    server.use(http.post("*/api/boms", () => HttpResponse.json({ detail }, { status: 413 })));
    renderWithQuery(<BomPage bomId={null} onOpen={vi.fn()} onBack={() => {}} />);
    await user.upload(screen.getByLabelText("BOM 파일"), md());
    expect(await screen.findByText(detail)).toBeInTheDocument();
  });

  it("says the upload failed, with the status, when the reply is not JSON", async () => {
    const user = userEvent.setup();
    server.use(
      http.post("*/api/boms", () =>
        HttpResponse.text("<html>Bad Gateway</html>", {
          status: 502,
          headers: { "content-type": "text/html" },
        }),
      ),
    );
    renderWithQuery(<BomPage bomId={null} onOpen={vi.fn()} onBack={() => {}} />);
    await user.upload(screen.getByLabelText("BOM 파일"), md());
    expect(await screen.findByText("올리지 못했습니다 (HTTP 502)")).toBeInTheDocument();
  });
});

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

  it("starts a different BOM with no picks: a pick belongs to the BOM it was made on", async () => {
    const user = userEvent.setup();
    const toFirst: unknown[] = [];
    serve((_url, body) => {
      toFirst.push(body);
      return undefined;
    });
    const toOther: unknown[] = [];
    server.use(
      http.post("*/api/boms/BOM-UP-2/preview", async ({ request }) => {
        toOther.push(await request.json());
        return HttpResponse.json(bom({ bom_id: "BOM-UP-2" }));
      }),
    );
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const page = (bomId: string) => (
      <QueryClientProvider client={client}>
        <BomPage bomId={bomId} onOpen={() => {}} onBack={() => {}} />
      </QueryClientProvider>
    );
    const { rerender } = render(page("BOM-UP-1"));
    const pick = await screen.findByRole("form", { name: "줄 10 제품 지정" });
    await user.selectOptions(within(pick).getByLabelText("제품"), "REG-PUMP-001");
    await user.type(within(pick).getByLabelText("사유(필수)"), "BOM 오타");
    await user.click(within(pick).getByRole("button", { name: "지정" }));
    const picked = { line: 10, product_id: "REG-PUMP-001", reason: "BOM 오타" };
    await waitFor(() => expect(toFirst).toContainEqual({ picks: [picked] }));

    rerender(page("BOM-UP-2"));
    await waitFor(() => expect(toOther).not.toHaveLength(0));
    expect(toOther).toEqual([{ picks: [] }]);
  });

  it("keeps what the reviewer typed in another row while the preview updates", async () => {
    const user = userEvent.setup();
    const base = bom();
    const second = { ...base.rows[1], component: "Valve", model: "VX998-998", line: 11 };
    serve(() => HttpResponse.json(bom({ rows: [...base.rows, second] })));
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    const other = await screen.findByRole("form", { name: "줄 11 제품 지정" });
    await user.type(within(other).getByLabelText("사유(필수)"), "작성 중인 사유");

    const pick = screen.getByRole("form", { name: "줄 10 제품 지정" });
    await user.selectOptions(within(pick).getByLabelText("제품"), "REG-PUMP-001");
    await user.type(within(pick).getByLabelText("사유(필수)"), "BOM 오타");
    await user.click(within(pick).getByRole("button", { name: "지정" }));

    await waitFor(() => expect(screen.getByRole("button", { name: "적용" })).toBeEnabled());
    const kept = screen.getByRole("form", { name: "줄 11 제품 지정" });
    expect(within(kept).getByLabelText("사유(필수)")).toHaveValue("작성 중인 사유");
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

  it("keeps a reason the reviewer already typed when a suggestion arrives", async () => {
    const user = userEvent.setup();
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
    await user.type(within(pick).getByLabelText("사유(필수)"), "도면과 대조함");
    await user.click(within(pick).getByRole("button", { name: "제안 받기" }));
    expect(await within(pick).findByText(/제안: VX013-001/)).toBeInTheDocument();
    expect(within(pick).getByLabelText("제품")).toHaveValue("REG-PUMP-001"); // was empty
    expect(within(pick).getByLabelText("사유(필수)")).toHaveValue("도면과 대조함");
  });

  it("names the row on each undo button", async () => {
    const mine = { ...bom().rows[1], status: "new" as const, decided_by: "reviewer" as const };
    serve(() => HttpResponse.json(bom({ rows: [bom().rows[0], mine] })));
    renderWithQuery(<BomPage bomId="BOM-UP-1" onOpen={() => {}} onBack={() => {}} />);
    expect(await screen.findByRole("button", { name: "줄 10 지정 취소" })).toBeInTheDocument();
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
