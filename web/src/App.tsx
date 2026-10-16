// Two screens, addressed by the URL hash so a reload keeps the place:
//   #/              job list and upload
//   #/jobs/<id>     the review of one job
//   #/products/<id> a registered product: facts, evidence, edits, events, components
//   #/boms[/<id>]   BOM linking: upload, preview, apply (D-103)
import { useEffect, useState } from "react";
import { BomPage } from "./features/boms/BomPage";
import { JobList } from "./features/jobs/JobList";
import { UploadButton } from "./features/jobs/UploadButton";
import { ProductPage } from "./features/products/ProductPage";
import { ReviewPage } from "./features/review/ReviewPage";

function idOf(hash: string, kind: "jobs" | "products" | "boms"): string | null {
  const match = new RegExp(`^#/${kind}/([\\w-]+)$`).exec(hash);
  return match ? match[1] : null;
}

export function App() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  const open = (jobId: string | null) => {
    window.location.hash = jobId ? `#/jobs/${jobId}` : "#/";
  };
  const productId = idOf(hash, "products");
  if (productId) return <ProductPage productId={productId} onBack={() => open(null)} />;
  if (hash === "#/boms" || idOf(hash, "boms"))
    return (
      <BomPage
        bomId={idOf(hash, "boms")}
        onOpen={(bomId) => {
          window.location.hash = `#/boms/${bomId}`;
        }}
        onBack={() => open(null)}
      />
    );
  const jobId = idOf(hash, "jobs");
  if (jobId) return <ReviewPage jobId={jobId} onBack={() => open(null)} />;
  return (
    <main className="min-h-screen bg-gray-50">
      <div className="mx-auto max-w-5xl p-6">
        <header className="mb-4 flex items-center justify-between">
          <h1 className="text-xl font-semibold">spec-bridge 검토</h1>
          <span className="flex items-center gap-3">
            <a className="text-sm text-blue-700" href="#/boms">
              BOM 연결
            </a>
            <UploadButton onUploaded={open} />
          </span>
        </header>
        <JobList onOpen={open} />
      </div>
    </main>
  );
}
