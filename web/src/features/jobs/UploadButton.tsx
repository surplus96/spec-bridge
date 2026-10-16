// Upload a specification (.pdf, .xlsx, .docx); the job starts on the server.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";

export function UploadButton({ onUploaded }: { onUploaded: (jobId: string) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const client = useQueryClient();
  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      const response = await fetch("/api/jobs", { method: "POST", body });
      const data = (await response.json()) as { job_id?: string; detail?: string };
      if (!response.ok || !data.job_id) throw new Error(data.detail ?? "업로드하지 못했습니다");
      return data.job_id;
    },
    onSuccess: (jobId) => {
      void client.invalidateQueries({ queryKey: ["jobs"] });
      onUploaded(jobId);
    },
  });
  return (
    <span>
      <input
        ref={input}
        type="file"
        accept=".pdf,.xlsx,.docx"
        className="hidden"
        aria-label="사양서 파일"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) upload.mutate(file);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        disabled={upload.isPending}
        className="rounded bg-blue-700 px-3 py-1 text-white disabled:opacity-40"
        onClick={() => input.current?.click()}
      >
        {upload.isPending ? "올리는 중…" : "사양서 올리기"}
      </button>
      {upload.isError && <span className="ml-2 text-sm text-red-700">{upload.error.message}</span>}
    </span>
  );
}
