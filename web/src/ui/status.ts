import type { components } from "../api/schema";
import type { Tone } from "./Badge";

export type JobStatus = components["schemas"]["JobSummary"]["status"];

export const STATUS: Record<JobStatus, { label: string; tone: Tone }> = {
  running: { label: "처리 중", tone: "info" },
  awaiting_class: { label: "클래스 선택 대기", tone: "review" },
  awaiting_review: { label: "검토 대기", tone: "review" },
  registered: { label: "등록됨", tone: "done" },
  linked: { label: "기존 제품에 연결됨", tone: "done" },
  cancelled: { label: "취소됨", tone: "ref" },
  failed: { label: "실패", tone: "block" },
  stalled: { label: "중단됨", tone: "block" },
};
