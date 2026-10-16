// Screen names (D-074): Korean labels for ontology ids from /api/display, and readable forms
// for tokens. Every function falls back to the id, so a missing label never hides a value.
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import type { components } from "../api/schema";

export type Labels = components["schemas"]["DisplayLabels"];

export function useLabels(): Labels | undefined {
  const query = useQuery({
    queryKey: ["display"],
    staleTime: Number.POSITIVE_INFINITY,
    queryFn: async () => {
      const { data, error } = await api.GET("/api/display");
      if (error || !data) throw new Error("표시명을 불러오지 못했습니다");
      return data;
    },
  });
  return query.data;
}

/** "heavy_fuel_oil" → "heavy fuel oil": tokens read as words, nothing translated. */
export function humanize(token: string): string {
  return token.replaceAll("_", " ");
}

export function attributeName(labels: Labels | undefined, id: string): string {
  return labels?.attributes[id] ?? humanize(id);
}

export function className(labels: Labels | undefined, id: string): string {
  return labels?.classes[id] ?? id;
}

export function axisName(labels: Labels | undefined, group: "basis" | "condition", id: string) {
  return labels?.[group][id] ?? humanize(id);
}
