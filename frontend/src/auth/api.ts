import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type CurrentUser = components["schemas"]["UserResponse"];
export type UserRole = components["schemas"]["UserRole"];

export class InvalidCredentialsError extends Error {
  constructor() {
    super("Incorrect email or password");
    this.name = "InvalidCredentialsError";
  }
}

export class InvalidCurrentPasswordError extends Error {
  constructor() {
    super("Current password is incorrect");
    this.name = "InvalidCurrentPasswordError";
  }
}

/** The signed-in user, or `null` when there is no valid session. */
export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  const { data, response } = await api.GET("/api/v1/users/me");
  if (data) return data;
  if (response.status === 401) return null;
  throw new ApiError(response);
}

/** Start a session; the backend sets it as an httpOnly cookie. */
export async function signIn(credentials: { email: string; password: string }): Promise<void> {
  const { response } = await api.POST("/api/v1/auth/session", { body: credentials });
  if (response.ok) return;
  if (response.status === 401) throw new InvalidCredentialsError();
  throw new ApiError(response);
}

export async function signOut(): Promise<void> {
  const { response } = await api.DELETE("/api/v1/auth/session");
  if (!response.ok) throw new ApiError(response);
}

/** Change the signed-in user's password. The backend revokes the current session on success. */
export async function changePassword(passwords: {
  currentPassword: string;
  newPassword: string;
}): Promise<void> {
  const { response } = await api.POST("/api/v1/users/me/password", {
    body: {
      current_password: passwords.currentPassword,
      new_password: passwords.newPassword,
    },
  });
  if (response.ok) return;
  if (response.status === 400) throw new InvalidCurrentPasswordError();
  throw new ApiError(response);
}

/** Sign-in succeeded but the browser did not keep the session cookie (e.g. `Secure` over HTTP). */
export class SessionNotStoredError extends Error {
  constructor() {
    super("Signed in, but the browser did not store the session. Contact your administrator.");
    this.name = "SessionNotStoredError";
  }
}
