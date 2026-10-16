// Job list: every upload with its status, newest first. A row opens the review.
import { useQuery } from "@tanstack/react-query";
import { ChevronRight, FileText } from "lucide-react";
import { api } from "../../api/client";
import { className, useLabels } from "../../lib/display";
import { Badge } from "../../ui/Badge";
import { STATUS } from "../../ui/status";

export function JobList({ onOpen }: { onOpen?: (jobId: string) => void }) {
  const labels = useLabels();
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/jobs");
      if (error) throw new Error("작업 목록을 불러오지 못했습니다");
      return data;
    },
    refetchInterval: 2000, // a running job changes status on its own
  });

  if (jobs.isPending) return <p className="text-gray-500">불러오는 중…</p>;
  if (jobs.isError) return <p className="text-red-700">{jobs.error.message}</p>;
  if (jobs.data.length === 0)
    return (
      <div className="rounded-lg border border-dashed p-10 text-center text-gray-500">
        아직 올린 문서가 없습니다.
      </div>
    );
  return (
    <ul className="divide-y rounded-lg border bg-white">
      {jobs.data.map((job) => {
        const status = STATUS[job.status];
        return (
          <li key={job.job_id}>
            <button
              type="button"
              className="flex w-full items-center gap-4 px-4 py-3 text-left hover:bg-gray-50"
              onClick={() => onOpen?.(job.job_id)}
            >
              <FileText className="size-5 shrink-0 text-gray-400" aria-hidden />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">
                  {job.file_name ?? job.document_id}
                </span>
                <span className="block text-xs text-gray-500">
                  {job.class_id ? className(labels, job.class_id) : "분류 전"} ·{" "}
                  {new Date(job.uploaded_at).toLocaleString("ko-KR")}
                  {job.product_id && ` · ${job.product_id}`}
                </span>
              </span>
              <Badge tone={status.tone}>{status.label}</Badge>
              <ChevronRight className="size-4 text-gray-400" aria-hidden />
            </button>
          </li>
        );
      })}
    </ul>
  );
}
