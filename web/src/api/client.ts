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

export type JobSummary = components["schemas"]["JobSummary"];
export type JobView = components["schemas"]["JobView"];
