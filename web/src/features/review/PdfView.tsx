// PDF page with boxes on the values (D-061: react-pdf, worker bundled, no CDN). The page
// fits the pane's width; zoom multiplies that. Loaded lazily: only PDF jobs pay for pdf.js.
import { ChevronLeft, ChevronRight, ZoomIn, ZoomOut } from "lucide-react";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import { toScreenBox } from "../../lib/bbox";
import type { PdfMark } from "../../lib/locate";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const ZOOMS = [1, 1.25, 1.5, 2];

export default function PdfView({ url, marks }: { url: string; marks: PdfMark[] }) {
  const frame = useRef<HTMLDivElement>(null);
  const [paneWidth, setPaneWidth] = useState(600);
  const [zoom, setZoom] = useState(0);
  const [pages, setPages] = useState(0);
  const [page, setPage] = useState(1);
  const [size, setSize] = useState<{ width: number; height: number } | null>(null);
  const first = marks[0]?.page;

  useEffect(() => {
    if (first) setPage(first); // jump to where the selected value is
  }, [first]);

  useEffect(() => {
    const element = frame.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setPaneWidth(entry.contentRect.width));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const width = Math.max(200, paneWidth - 4) * ZOOMS[zoom];
  const scale = size ? width / size.width : 1;
  const icon = "size-7 rounded p-1 hover:bg-gray-100 disabled:opacity-30";
  return (
    <div ref={frame} className="min-w-0">
      <div className="mb-2 flex items-center gap-1 text-sm text-gray-600">
        <button
          type="button"
          aria-label="이전 쪽"
          className={icon}
          disabled={page <= 1}
          onClick={() => setPage(page - 1)}
        >
          <ChevronLeft className="size-5" />
        </button>
        <span className="tabular-nums">
          {page} / {pages || "…"}
        </span>
        <button
          type="button"
          aria-label="다음 쪽"
          className={icon}
          disabled={page >= pages}
          onClick={() => setPage(page + 1)}
        >
          <ChevronRight className="size-5" />
        </button>
        <span className="mx-2 h-4 w-px bg-gray-300" />
        <button
          type="button"
          aria-label="축소"
          className={icon}
          disabled={zoom === 0}
          onClick={() => setZoom(zoom - 1)}
        >
          <ZoomOut className="size-5" />
        </button>
        <span className="w-12 text-center tabular-nums">{Math.round(ZOOMS[zoom] * 100)}%</span>
        <button
          type="button"
          aria-label="확대"
          className={icon}
          disabled={zoom === ZOOMS.length - 1}
          onClick={() => setZoom(zoom + 1)}
        >
          <ZoomIn className="size-5" />
        </button>
      </div>
      <div className="overflow-auto">
        <Document file={url} onLoadSuccess={(pdf) => setPages(pdf.numPages)}>
          <div className="relative inline-block border bg-white shadow-sm">
            <Page
              pageNumber={page}
              width={width}
              renderTextLayer={false}
              renderAnnotationLayer={false}
              onLoadSuccess={(p) => {
                const view = p.getViewport({ scale: 1 });
                setSize({ width: view.width, height: view.height });
              }}
            />
            {size &&
              marks
                .filter((m) => m.page === page)
                .map((m) => {
                  const b = toScreenBox(m.box, size.height, scale);
                  return (
                    <div
                      key={m.box.join(",")}
                      className="pointer-events-none absolute rounded-sm border-2 border-blue-600 bg-blue-400/20"
                      style={{
                        left: b.left - 2,
                        top: b.top - 2,
                        width: b.width + 4,
                        height: b.height + 4,
                      }}
                    />
                  );
                })}
          </div>
        </Document>
      </div>
    </div>
  );
}
