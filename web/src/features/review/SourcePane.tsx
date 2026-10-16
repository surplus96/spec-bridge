// ① Source: where each value was read. PDF: the page with boxes (fits the pane, zoomable);
// every format: the parsed blocks as readable rows under their section headings, with the
// highlighted cells. When the reviewer adds a value, they click the cell it was read from.
import { FileText, List } from "lucide-react";
import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useBlocks } from "../../api/hooks";
import { blockIndexFor, type Location, pdfMark } from "../../lib/locate";
import { sourceRows } from "../../lib/rows";

const PdfView = lazy(() => import("./PdfView"));

interface Props {
  jobId: string;
  fileName: string;
  highlight: Location[];
  picking: boolean;
  picked: number | null;
  onPick: (index: number) => void;
}

export function SourcePane({ jobId, fileName, highlight, picking, picked, onPick }: Props) {
  const blocks = useBlocks(jobId, true);
  const isPdf = fileName.toLowerCase().endsWith(".pdf");
  const [view, setView] = useState<"page" | "blocks">(isPdf ? "page" : "blocks");
  const list = blocks.data ?? [];
  const marked = new Set(
    highlight.map((l) => blockIndexFor(l, list)).filter((i): i is number => i !== null),
  );
  const firstMarked = [...marked][0];
  const cellRefs = useRef(new Map<number, HTMLElement>());

  useEffect(() => {
    if (firstMarked !== undefined)
      cellRefs.current.get(firstMarked)?.scrollIntoView?.({ block: "center" });
  }, [firstMarked]);

  const showPage = isPdf && view === "page" && !picking;
  let section: string | null | undefined;
  return (
    <section className="flex min-h-0 min-w-0 flex-col rounded-lg border bg-white">
      <header className="flex items-center justify-between border-b px-3 py-2">
        <h2 className="text-sm font-semibold text-gray-700">원문</h2>
        {isPdf && (
          <button
            type="button"
            className="inline-flex items-center gap-1 text-xs text-blue-700"
            onClick={() => setView(view === "page" ? "blocks" : "page")}
          >
            {view === "page" ? <List className="size-4" /> : <FileText className="size-4" />}
            {view === "page" ? "텍스트로 보기" : "페이지로 보기"}
          </button>
        )}
      </header>
      {picking && (
        <p className="m-3 rounded bg-amber-50 p-2 text-sm text-amber-900 ring-1 ring-amber-200">
          값을 읽은 칸을 아래에서 클릭하세요.
        </p>
      )}
      <div className="min-h-0 flex-1 overflow-auto p-3">
        {showPage ? (
          <Suspense fallback={<p className="text-gray-500">PDF 표시 준비 중…</p>}>
            <PdfView
              url={`/api/jobs/${jobId}/source`}
              marks={highlight.map(pdfMark).filter((m) => m !== null)}
            />
          </Suspense>
        ) : blocks.isPending ? (
          <p className="text-gray-500">원문 블록을 불러오는 중…</p>
        ) : blocks.isError ? (
          <p className="text-red-700">{blocks.error.message}</p>
        ) : (
          <div className="space-y-0.5 text-sm leading-relaxed">
            {sourceRows(list).map((row) => {
              const heading = row.section !== section ? row.section : null;
              section = row.section;
              return (
                <div key={row.key}>
                  {heading && (
                    <h3 className="mt-3 mb-1 text-xs font-semibold tracking-wide text-gray-500 uppercase">
                      {heading}
                    </h3>
                  )}
                  <div className="flex flex-wrap gap-x-1">
                    {row.cells.map((cell, i) => {
                      const on = marked.has(cell.index);
                      const chosen = picked === cell.index;
                      const tone = chosen
                        ? "bg-amber-200"
                        : on
                          ? "bg-blue-100 ring-2 ring-blue-500"
                          : picking
                            ? "hover:bg-amber-100"
                            : "";
                      const body = (
                        <>
                          {i > 0 && <span className="mr-1 text-gray-300">|</span>}
                          {cell.text}
                        </>
                      );
                      return (
                        <span
                          key={cell.index}
                          ref={(el) => {
                            if (el) cellRefs.current.set(cell.index, el);
                          }}
                          data-testid={`block-${cell.index}`}
                          data-marked={on || undefined}
                          className={`rounded px-1 ${tone}`}
                        >
                          {picking ? (
                            <button
                              type="button"
                              className="text-left"
                              onClick={() => onPick(cell.index)}
                            >
                              {body}
                            </button>
                          ) : (
                            body
                          )}
                        </span>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
