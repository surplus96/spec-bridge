import { describe, expect, it } from "vitest";
import type { BlockView } from "./locate";
import { sourceRows } from "./rows";

const block = (
  index: number,
  text: string,
  location: BlockView["location"],
  section = "Specs",
): BlockView => ({
  index,
  kind: "table_cell",
  text,
  section,
  location,
});

describe("sourceRows", () => {
  it("puts the cells of one DOCX table row on one line", () => {
    const rows = sourceRows([
      block(0, "Bore", { table: 1, row: 2, column: 1 }),
      block(1, "210", { table: 1, row: 2, column: 2 }),
      block(2, "mm", { table: 1, row: 2, column: 3 }),
      block(3, "Stroke", { table: 1, row: 3, column: 1 }),
    ]);
    expect(rows.map((r) => r.cells.map((c) => c.text))).toEqual([
      ["Bore", "210", "mm"],
      ["Stroke"],
    ]);
  });

  it("groups an XLSX row by its sheet and row number", () => {
    const rows = sourceRows([
      block(0, "Bore", { sheet: "Spec", cell_ref: "A13" }),
      block(1, "210", { sheet: "Spec", cell_ref: "B13" }),
      block(2, "Stroke", { sheet: "Spec", cell_ref: "A14" }),
    ]);
    expect(rows.map((r) => r.cells.length)).toEqual([2, 1]);
  });

  it("keeps paragraphs one per line", () => {
    const rows = sourceRows([block(0, "a", { paragraph: 1 }), block(1, "b", { paragraph: 2 })]);
    expect(rows).toHaveLength(2);
  });
});
