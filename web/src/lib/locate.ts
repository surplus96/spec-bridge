// Where a value was read → what the source pane highlights: a box on a PDF page and/or a
// row in the parsed block list (DOCX, XLSX and PDF all have blocks).
import type { components } from "../api/schema";

export type Location = components["schemas"]["Location"];
export type BlockView = components["schemas"]["BlockView"];

const POSITION = ["pdf_page", "sheet", "cell_ref", "paragraph", "table", "row", "column", "line"];

function sameKeys(a: Location, b: Location, keys: string[]): boolean {
  const left = a as Record<string, unknown>;
  const right = b as Record<string, unknown>;
  return keys.every((k) => (left[k] ?? null) === (right[k] ?? null));
}

function sameBox(a: Location, b: Location): boolean {
  if (!a.bbox || !b.bbox) return !a.bbox && !b.bbox;
  return a.bbox.every((v, i) => Math.abs(v - (b.bbox as number[])[i]) < 0.01);
}

/** The block a value was read from: the same position (and the same box on a PDF page). */
export function blockIndexFor(location: Location, blocks: BlockView[]): number | null {
  const found = blocks.find(
    (b) => sameKeys(location, b.location, POSITION) && sameBox(location, b.location),
  );
  return found ? found.index : null;
}

export interface PdfMark {
  page: number;
  box: [number, number, number, number];
}

/** A box to draw on a PDF page, when the location has one. */
export function pdfMark(location: Location): PdfMark | null {
  if (location.pdf_page == null || !location.bbox) return null;
  const [x0, y0, x1, y1] = location.bbox;
  return { page: location.pdf_page, box: [x0, y0, x1, y1] };
}

/** Occurrence dicts carry their location under "location". */
export function locationsOf(occurrences: unknown): Location[] {
  if (!Array.isArray(occurrences)) return [];
  return occurrences
    .map((o) => (o as { location?: Location }).location)
    .filter((l): l is Location => l != null);
}
