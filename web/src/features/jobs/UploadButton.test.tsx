import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HttpResponse, http } from "msw";
import { describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "../../test/render";
import { server } from "../../test/server";
import { UploadButton } from "./UploadButton";

const spec = () => new File(["spec"], "SYN-011.docx");

describe("UploadButton", () => {
  it("sends the file and opens the new job", async () => {
    const user = userEvent.setup();
    const onUploaded = vi.fn();
    let type: string | null = null;
    server.use(
      // the body is not read: a jsdom File does not stream through Node's fetch
      http.post("*/api/jobs", ({ request }) => {
        type = request.headers.get("content-type");
        return HttpResponse.json({ job_id: "JOB-9", status: "running" }, { status: 202 });
      }),
    );
    renderWithQuery(<UploadButton onUploaded={onUploaded} />);
    await user.upload(screen.getByLabelText("사양서 파일"), spec());
    await waitFor(() => expect(onUploaded).toHaveBeenCalledWith("JOB-9"));
    expect(type).toMatch(/^multipart\/form-data; boundary=/);
  });

  it.each([
    [413, "the file is larger than 52428800 bytes"],
    [415, "unsupported file type .txt"],
  ])("shows the server's reason for a %i and stays put", async (status, detail) => {
    const user = userEvent.setup();
    const onUploaded = vi.fn();
    server.use(http.post("*/api/jobs", () => HttpResponse.json({ detail }, { status })));
    renderWithQuery(<UploadButton onUploaded={onUploaded} />);
    await user.upload(screen.getByLabelText("사양서 파일"), spec());
    expect(await screen.findByText(detail)).toBeInTheDocument();
    expect(onUploaded).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "사양서 올리기" })).toBeEnabled(); // can retry
  });
});
