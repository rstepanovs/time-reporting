import type { Location } from "react-router";

/** Navigation state carried to the sign-in page: where to return after signing in. */
export interface SignInRedirectState {
  from: Location;
}

export function signInRedirectState(from: Location): SignInRedirectState {
  return { from };
}

/** The in-app path to open after signing in, taken from `SignInRedirectState` when present. */
export function redirectTarget(state: unknown): string {
  if (typeof state === "object" && state !== null && "from" in state) {
    const from = (state as { from: Partial<Location> | null }).from;
    if (typeof from?.pathname === "string" && from.pathname.startsWith("/") && from.pathname !== "/login") {
      return `${from.pathname}${from.search ?? ""}${from.hash ?? ""}`;
    }
  }
  return "/";
}
