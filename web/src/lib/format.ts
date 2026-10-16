// Display forms for fact values and their context (basis, condition, scope). Values are the
// server's normalized values; the screen only makes them readable (tokens as words, booleans
// as 예/아니오) and never converts units.
import { axisName, humanize, type Labels } from "./display";

function quantity(v: unknown): string | null {
  if (v && typeof v === "object" && "value" in v && "unit" in v) {
    const q = v as { value: unknown; unit: unknown };
    return `${String(q.value)} ${String(q.unit)}`;
  }
  return null;
}

export function formatValue(value: unknown): string {
  if (value == null) return "—";
  if (typeof value === "boolean") return value ? "예" : "아니오";
  if (typeof value === "string") return humanize(value);
  if (Array.isArray(value)) return value.map(formatValue).join(", ");
  if (typeof value === "object") {
    const q = quantity(value);
    if (q) return q;
    const v = value as Record<string, unknown>;
    if ("min" in v && "max" in v) return `${String(v.min)} – ${String(v.max)}`;
    if ("length" in v || "width" in v || "height" in v) {
      // always L × W × H, whatever order the stored JSON has
      const short = { length: "L", width: "W", height: "H" } as const;
      return (["length", "width", "height"] as const)
        .filter((k) => v[k] != null)
        .map((k) => `${short[k]} ${String(v[k])}`)
        .join(" × ");
    }
    return Object.entries(v)
      .filter(([, x]) => x != null)
      .map(([k, x]) => `${k} ${formatValue(x)}`)
      .join(" × ");
  }
  return String(value);
}

/** The raw text a reviewer edits: exactly what the server would read back. */
export function editableValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "object" && !Array.isArray(value)) {
    const v = value as Record<string, unknown>;
    if ("length" in v || "width" in v || "height" in v) {
      return [v.length, v.width, v.height].map((x) => (x == null ? "" : String(x))).join(" × ");
    }
  }
  if (Array.isArray(value)) return value.map(String).join(", ");
  return String(value);
}

const NO_SCOPE = new Set(["main_equipment", "unknown", ""]);
/** Axis values that say "nothing stated" (the extraction schema hides the same tokens). */
const NOTHING = new Set(["unknown", "not_applicable", ""]);

export interface ContextPart {
  name: string;
  value: string;
}

/** Basis, condition and scope as name/value pairs; empty when the fact has none. */
export function contextParts(fact: Record<string, unknown>, labels?: Labels): ContextPart[] {
  const parts: ContextPart[] = [];
  for (const group of ["basis", "condition"] as const) {
    const entries = Object.entries((fact[group] as Record<string, unknown>) ?? {});
    for (const [k, v] of entries) {
      if (v == null || (typeof v === "string" && NOTHING.has(v))) continue; // seed rows store every axis
      parts.push({ name: axisName(labels, group, k), value: formatValue(v) });
    }
  }
  const scope = String(fact.scope ?? "");
  if (!NO_SCOPE.has(scope)) parts.push({ name: "범위", value: humanize(scope) });
  return parts;
}

/** One line for tests and tooltips. */
export function formatContext(fact: Record<string, unknown>, labels?: Labels): string {
  const parts = contextParts(fact, labels);
  return parts.length ? parts.map((p) => `${p.name}: ${p.value}`).join(" · ") : "—";
}
