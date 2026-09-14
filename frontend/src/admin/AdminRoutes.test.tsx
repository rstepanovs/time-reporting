import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { testAdmin, testUser } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
});

describe("/admin routes", () => {
  it("shows the not-found page to a non-admin", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp("/admin/users");

    expect(await screen.findByText("Page not found")).toBeTruthy();
  });

  it("redirects an admin from /admin to /admin/users", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    const { router } = renderApp("/admin");

    await screen.findByRole("heading", { name: "Users" });

    expect(router.state.location.pathname).toBe("/admin/users");
  });

  it("lets an admin open /admin/customers and /admin/projects", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    renderApp("/admin/customers");
    expect(await screen.findByRole("heading", { name: "Customers" })).toBeTruthy();

    vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
    renderApp("/admin/projects");
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeTruthy();
  });
});
