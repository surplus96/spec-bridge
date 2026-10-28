// Typed API client (D-061): the types come from the server's OpenAPI contract
// (`npm run gen:api` after `uv run python -m spec_bridge.api.openapi`), so a changed
// response model breaks `tsc`, not the screen.
import createClient from "openapi-fetch";
import type { components, paths } from "./schema";

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  // Look fetch up per request, not once at import: test mocks (MSW) replace it later.
  fetch: (request) => globalThis.fetch(request),
});

/** POST one file as multipart (the typed client does not build multipart bodies). A refusal
 * reads as the server's `detail`; a reply that is not JSON (a proxy's HTML error page) reads
 * as the fallback with the HTTP status, never as a JSON parse error. */
export async function postFile(url: string, file: File, fallback: string): Promise<unknown> {
  const body = new FormData();
  body.append("file", file);
  const response = await fetch(url, { method: "POST", body });
  const data: unknown = await response.json().catch(() => null);
  const detail = (data as { detail?: unknown } | null)?.detail;
  if (!response.ok || data === null) {
    throw new Error(typeof detail === "string" ? detail : `${fallback} (HTTP ${response.status})`);
  }
  return data;
}

export type JobSummary = components["schemas"]["JobSummary"];
export type JobView = components["schemas"]["JobView"];
