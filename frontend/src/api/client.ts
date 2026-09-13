import createClient, { type Middleware } from "openapi-fetch";

import { queryClient } from "@/api/queryClient";
import type { paths } from "@/api/schema";

/** Query key of the signed-in user; its data is `null` while signed out. */
export const currentUserQueryKey = ["auth", "currentUser"] as const;

const sessionMiddleware: Middleware = {
  onRequest({ request }) {
    // The backend rejects cookie-authenticated unsafe requests without this header (CSRF defense).
    request.headers.set("X-Requested-With", "fetch");
    return request;
  },
  onResponse({ response }) {
    // The session cookie expired or was revoked: from now on the app is signed out.
    if (response.status === 401) {
      queryClient.setQueryData(currentUserQueryKey, null);
    }
  },
};

/**
 * Typed API client. Paths already include the `/api/v1` prefix from the OpenAPI schema.
 * Authentication is an httpOnly session cookie, sent along with every request.
 */
export const api = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE_URL ?? "",
  credentials: "include",
});
api.use(sessionMiddleware);
