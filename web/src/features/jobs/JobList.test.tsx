import { screen } from "@testing-library/react";
import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";
import type { JobSummary } from "../../api/client";
import { renderWithQuery } from "../../test/render";
import { server } from "../../test/server";
import { JobList } from "./JobList";

const job: JobSummary = {
  job_id: "JOB-1",
  file_name: "SYN-011.docx",
  document_id: "UP-1",
  uploaded_at: "2026-10-14T05:23:34+00:00",
  status: "awaiting_review",
  class_id: "FourStrokeEngine",
  product_id: null,
};

describe("JobList", () => {
  it("shows each job with its status in Korean", async () => {
    server.use(http.get("*/api/jobs", () => HttpResponse.json([job])));
    renderWithQuery(<JobList />);
    expect(await screen.findByText("SYN-011.docx")).toBeInTheDocument();
    expect(screen.getByText("검토 대기")).toBeInTheDocument();
    expect(await screen.findByText(/4행정 엔진/)).toBeInTheDocument(); // display label (D-074)
  });

  it("says so when nothing was uploaded", async () => {
    server.use(http.get("*/api/jobs", () => HttpResponse.json([])));
    renderWithQuery(<JobList />);
    expect(await screen.findByText("아직 올린 문서가 없습니다.")).toBeInTheDocument();
  });

  it("reports a failed request instead of an empty list", async () => {
    server.use(http.get("*/api/jobs", () => HttpResponse.json({ detail: "x" }, { status: 500 })));
    renderWithQuery(<JobList />);
    expect(await screen.findByText("작업 목록을 불러오지 못했습니다")).toBeInTheDocument();
  });
});
