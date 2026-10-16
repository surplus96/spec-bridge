// Parsed blocks → what the source pane lists: one heading per section, and the cells of
// one table row (DOCX table / XLSX row) on one line, so a specification reads as rows.
import type { BlockView } from "./locate";

export interface SourceRow {
  key: string;
  section: string | null;
  cells: BlockView[];
}

function rowKey(b: BlockView): string | null {
  const l = b.location as Record<string, unknown>;
  if (l.table != null && l.row != null) return `t${String(l.table)}r${String(l.row)}`;
  if (l.sheet != null && typeof l.cell_ref === "string") {
    const row = /\d+$/.exec(l.cell_ref)?.[0];
    if (row) return `s${String(l.sheet)}r${row}`;
  }
  return null;
}

export function sourceRows(blocks: BlockView[]): SourceRow[] {
  const rows: SourceRow[] = [];
  for (const block of blocks) {
    const key = rowKey(block);
    const last = rows[rows.length - 1];
    if (key && last && last.key === key) {
      last.cells.push(block);
    } else {
      rows.push({ key: key ?? `b${block.index}`, section: block.section ?? null, cells: [block] });
    }
  }
  return rows;
}
