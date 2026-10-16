import { describe, expect, it } from "vitest";
import { type BlockView, blockIndexFor, locationsOf, pdfMark } from "./locate";

const block = (index: number, location: BlockView["location"]): BlockView => ({
  index,
  kind: "table_cell",
  text: "x",
  section: null,
  location,
});

describe("highlight targets", () => {
  const blocks = [
    block(0, { paragraph: 3, section: "Specs" }),
    block(1, { table: 1, row: 2, column: 2 }),
    block(2, { sheet: "Spec", cell_ref: "B13" }),
    block(3, { pdf_page: 1, bbox: [10, 700, 90, 712] }),
  ];

  it("finds a DOCX paragraph, a DOCX table cell and an XLSX cell by position", () => {
    expect(blockIndexFor({ paragraph: 3, section: "Specs" }, blocks)).toBe(0);
    expect(blockIndexFor({ table: 1, row: 2, column: 2 }, blocks)).toBe(1);
    expect(blockIndexFor({ sheet: "Spec", cell_ref: "B13" }, blocks)).toBe(2);
  });

  it("does not match a different cell of the same table", () => {
    expect(blockIndexFor({ table: 1, row: 2, column: 3 }, blocks)).toBeNull();
  });

  it("matches a PDF block by page and box, and gives a box to draw", () => {
    const location = { pdf_page: 1, bbox: [10, 700, 90, 712] };
    expect(blockIndexFor(location, blocks)).toBe(3);
    expect(pdfMark(location)).toEqual({ page: 1, box: [10, 700, 90, 712] });
    expect(pdfMark({ paragraph: 3 })).toBeNull();
  });

  it("reads the locations out of occurrence rows", () => {
    expect(locationsOf([{ location: { paragraph: 1 } }, { raw_text: "no place" }])).toEqual([
      { paragraph: 1 },
    ]);
  });
});
