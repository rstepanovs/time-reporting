import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { testUser } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
});

describe("navigation", () => {
  it("shows links to Home and Projects", async () => {
    vi.mocked(fetchCurrentUser).mockResolvedValue(testUser);
    renderApp("/");

    await screen.findByRole("heading", { name: "Time Reporting" });

    expect(screen.getByRole("link", { name: "Home" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Projects" })).toBeTruthy();
  });
});
