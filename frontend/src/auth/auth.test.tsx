import { fireEvent, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  changePassword,
  fetchCurrentUser,
  InvalidCredentialsError,
  InvalidCurrentPasswordError,
  signIn,
  signOut,
} from "@/auth/api";
import { testManager } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
  signIn: vi.fn(),
  signOut: vi.fn(),
  changePassword: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
});

function typeInto(label: RegExp, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("signing in", () => {
  it("sends a signed-out visitor to the sign-in page and back after signing in", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(null);
    vi.mocked(signIn).mockImplementation(async () => {
      vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    });
    const { router } = renderApp("/account/password");

    await screen.findByRole("heading", { name: "Sign in" });
    typeInto(/^email/i, "ada@example.com");
    typeInto(/^password/i, "secret-password");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await screen.findByRole("heading", { name: "Change password" });
    expect(signIn).toHaveBeenCalledWith({ email: "ada@example.com", password: "secret-password" });
    expect(router.state.location.pathname).toBe("/account/password");
  });

  it("shows an error for incorrect credentials", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(null);
    vi.mocked(signIn).mockRejectedValue(new InvalidCredentialsError());
    const { router } = renderApp("/login");

    await screen.findByRole("heading", { name: "Sign in" });
    typeInto(/^email/i, "ada@example.com");
    typeInto(/^password/i, "wrong-password");
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Incorrect email or password")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("requires email and password", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(null);
    renderApp("/login");

    await screen.findByRole("heading", { name: "Sign in" });
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect(await screen.findByText("Enter your email")).toBeTruthy();
    expect(screen.getByText("Enter your password")).toBeTruthy();
    expect(signIn).not.toHaveBeenCalled();
  });
});

describe("account menu", () => {
  it("shows the signed-in user and signs out", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(signOut).mockResolvedValue();
    const { router } = renderApp("/account/password");

    await screen.findByRole("heading", { name: "Time Reporting" });
    fireEvent.click(screen.getByRole("button", { name: "Account menu" }));
    expect(await screen.findByText("ada@example.com")).toBeTruthy();
    expect(screen.getByText("Manager")).toBeTruthy();
    fireEvent.click(screen.getByRole("menuitem", { name: "Sign out" }));

    await screen.findByRole("heading", { name: "Sign in" });
    expect(signOut).toHaveBeenCalled();
    expect(router.state.location.pathname).toBe("/login");
    // An explicit sign-out does not bring the next user back to the page left behind.
    expect(router.state.location.state).toBeNull();
  });
});

describe("changing the password", () => {
  it("signs out and asks to sign in with the new password", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(changePassword).mockResolvedValue();
    vi.mocked(signOut).mockResolvedValue();
    const { router } = renderApp("/account/password");

    await screen.findByRole("heading", { name: "Change password" });
    typeInto(/^current password/i, "old-password");
    typeInto(/^new password/i, "new-password-1");
    typeInto(/^confirm new password/i, "new-password-1");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    await screen.findByRole("heading", { name: "Sign in" });
    expect(changePassword).toHaveBeenCalledWith({
      currentPassword: "old-password",
      newPassword: "new-password-1",
    });
    expect(signOut).toHaveBeenCalled();
    expect(await screen.findByText("Password changed")).toBeTruthy();
    expect(router.state.location.state).toBeNull();
  });

  it("reports a wrong current password on its field", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    vi.mocked(changePassword).mockRejectedValue(new InvalidCurrentPasswordError());
    renderApp("/account/password");

    await screen.findByRole("heading", { name: "Change password" });
    typeInto(/^current password/i, "wrong-password");
    typeInto(/^new password/i, "new-password-1");
    typeInto(/^confirm new password/i, "new-password-1");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByText("Current password is incorrect")).toBeTruthy();
    expect(signOut).not.toHaveBeenCalled();
  });

  it("validates the new password before submitting", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testManager);
    renderApp("/account/password");

    await screen.findByRole("heading", { name: "Change password" });
    typeInto(/^current password/i, "old-password");
    typeInto(/^new password/i, "short");
    typeInto(/^confirm new password/i, "different");
    fireEvent.click(screen.getByRole("button", { name: "Change password" }));

    expect(await screen.findByText("Use 8 to 128 characters")).toBeTruthy();
    expect(screen.getByText("Passwords do not match")).toBeTruthy();
    expect(changePassword).not.toHaveBeenCalled();
  });
});
