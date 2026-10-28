// The spec-sheet path through the browser (W5, D-117): upload, the local model works, the
// review screen opens with extracted facts, and a reviewer's edit is kept with its reason.
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const repo = join(process.cwd(), "..");

test("an uploaded spec sheet reaches review and a reviewer's edit is recorded", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("사양서 파일").setInputFiles(join(repo, "data/synth/inputs/SYN-011.docx"));

  // the local model classifies and extracts: wait for the facts pane (minutes when cold)
  const facts = page.getByRole("heading", { name: /추출 속성/ });
  await expect(facts).toBeVisible({ timeout: 5 * 60_000 });

  await page.getByRole("button", { name: "수정", exact: true }).first().click();
  const form = page.getByRole("form", { name: "값 수정" });
  await form.getByLabel("사유(필수)").fill("E2E: 원문 표와 대조");
  await form.getByRole("button", { name: "적용" }).click();

  await expect(page.getByText("E2E: 원문 표와 대조")).toBeVisible({ timeout: 60_000 });
  await expect(page.getByTitle("사람 수정").first()).toBeVisible();
});
