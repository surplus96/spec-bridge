import type { components } from "../../api/schema";

export type ReviewPrompt = components["schemas"]["ReviewPrompt"];
export type ClassPrompt = components["schemas"]["ClassPrompt"];
export type FactEdit = components["schemas"]["FactEdit"];
export type Finding = components["schemas"]["Finding"];
export type TermNote = components["schemas"]["TermNote"];
export type Fact = Record<string, unknown>;

/** What the reviewer is looking at: the source pane highlights its places. */
export type Selection =
  | { kind: "fact"; index: number }
  | { kind: "unresolved"; index: number }
  | { kind: "finding"; index: number }
  | null;
