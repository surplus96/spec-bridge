// Server state for the review screens (TanStack Query). The server's graph holds the job;
// the screen reads it and sends commands. A running job is polled until it stops again.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type { components } from "./schema";

export type ResumeCommand = components["schemas"]["ResumeRequest"]["command"];

/** The server refused a command (409) or the request failed; `message` is for the reviewer. */
export class CommandError extends Error {}

function detailOf(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : fallback;
}

export function useJob(jobId: string) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/jobs/{job_id}", {
        params: { path: { job_id: jobId } },
      });
      if (error || !data) throw new Error(detailOf(error, "작업을 불러오지 못했습니다"));
      return data;
    },
    refetchInterval: (query) => (query.state.data?.status === "running" ? 1500 : false),
  });
}

export function useBlocks(jobId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["blocks", jobId],
    enabled,
    staleTime: Number.POSITIVE_INFINITY, // the parsed document never changes
    queryFn: async () => {
      const { data, error } = await api.GET("/api/jobs/{job_id}/blocks", {
        params: { path: { job_id: jobId } },
      });
      if (error || !data) throw new Error("원문 블록을 불러오지 못했습니다");
      return data;
    },
  });
}

export function useSupplement(jobId: string, revision: number) {
  return useQuery({
    queryKey: ["supplement", jobId, revision],
    queryFn: async () => {
      const { data, error } = await api.GET("/api/jobs/{job_id}/supplement", {
        params: { path: { job_id: jobId } },
      });
      if (error || !data) throw new Error("보강 요청을 만들지 못했습니다");
      return data;
    },
  });
}

export function useResume(jobId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (command: ResumeCommand) => {
      const { data, error } = await api.POST("/api/jobs/{job_id}/resume", {
        params: { path: { job_id: jobId } },
        // one id per click: a repeated delivery of the same request is applied once
        body: { request_id: crypto.randomUUID(), command },
      });
      if (error || !data) throw new CommandError(detailOf(error, "명령을 보내지 못했습니다"));
      return data;
    },
    onSuccess: (view) => client.setQueryData(["job", jobId], view),
    onSettled: () => {
      void client.invalidateQueries({ queryKey: ["job", jobId] });
      void client.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}
