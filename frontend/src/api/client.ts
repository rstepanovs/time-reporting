import createClient from "openapi-fetch";

import type { paths } from "@/api/schema";

/** Typed API client. Paths already include the `/api/v1` prefix from the OpenAPI schema. */
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
});
