// BOM linking through the browser (D-103, D-108, D-117): upload, preview, a reviewer's pick
// for a pending row, apply, and the components on the product page. No model call.
import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

const repo = join(process.cwd(), "..");

test("a BOM is previewed, a pending row is picked, and the relations are applied", async ({
  page,
}, info) => {
  // BOM-001 under a root that has no components yet, with the pump row's maker misspelt
  const source = readFileSync(join(repo, "data/synth/boms/BOM-001.md"), "utf8");
  const pumpLine = source.split("\n").find((l) => l.includes("| VX013-001 |")) ?? "";
  const bom = source
    .replace("Root model: VX001-001", "Root model: VX001-004")
    .replace(pumpLine, pumpLine.replace("Works", "Wroks"));
  const file = info.outputPath("BOM-E2E.md");
  writeFileSync(file, bom);

  await page.goto("/");
  await page.getByRole("link", { name: "BOM 연결" }).click();
  await page.getByLabel("BOM 파일").setInputFiles(file);

  // the first API request builds the service (KB embeddings with bge-m3): allow a cold start
  const rows = page.getByRole("row");
  await expect(rows.filter({ hasText: "VX021-002" })).toContainText("추가", { timeout: 120_000 });
  const pump = rows.filter({ hasText: "VX013-001" });
  await expect(pump).toContainText("검토 대기");

  const pick = page.getByRole("form", { name: "줄 10 제품 지정" });
  await pick.getByLabel("제품").selectOption("REG-PUMP-001");
  await pick.getByLabel("사유(필수)").fill("E2E: 제조사 철자 차이");
  await pick.getByRole("button", { name: "지정" }).click();
  await expect(pump).toContainText("담당자 지정");

  await page.getByRole("button", { name: "적용" }).click();
  await expect(page.getByRole("status")).toContainText("관계 3개를 추가했습니다");

  await page.getByRole("link", { name: "REG-2S-004" }).click();
  const parts = page.getByRole("region", { name: "구성품" });
  for (const model of ["VX021-002", "VX013-001", "VX017-001"]) {
    await expect(parts).toContainText(model);
  }
});
