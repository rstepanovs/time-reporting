import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { getSystemConfig, getSystemStatus } from "@/system/api";
import { testAdmin, testSystemConfig, testSystemStatus } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/system/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/system/api")>()),
  getSystemStatus: vi.fn(),
  getSystemConfig: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(getSystemStatus).mockResolvedValue(testSystemStatus);
  vi.mocked(getSystemConfig).mockResolvedValue(testSystemConfig);
});

describe("AdminSystemStatusPage", () => {
  it("renders the backend and frontend versions", async () => {
    renderApp("/admin/status");

    await screen.findByText(`${testSystemStatus.backend_version} (abc123def456)`);
    // No VITE_GIT_SHA is set while running tests, so the frontend SHA falls back to "unknown".
    expect(screen.getByText(`${__APP_VERSION__} (unknown)`)).toBeTruthy();
  });

  it("renders the database and table stats", async () => {
    renderApp("/admin/status");

    await screen.findByText(testSystemStatus.database.server_version);
    expect(screen.getByText(testSystemStatus.database.current_revision!)).toBeTruthy();
    expect(screen.getByText("users")).toBeTruthy();
    expect(screen.getByText("customers")).toBeTruthy();
    expect(screen.queryByText(/does not match the running code's migrations/)).toBeNull();
  });

  it("shows a mismatch alert when migrations are pending", async () => {
    vi.mocked(getSystemStatus).mockResolvedValue({
      ...testSystemStatus,
      database: {
        ...testSystemStatus.database,
        current_revision: "0009_earlier_revision",
        migrations_pending: true,
      },
    });

    renderApp("/admin/status");

    await screen.findByText(/does not match the running code's migrations/);
  });

  it("renders the read-only configuration", async () => {
    renderApp("/admin/status");

    await screen.findByText(testSystemConfig.app_name);
    expect(screen.getByText("DE / BE")).toBeTruthy();
  });
});
