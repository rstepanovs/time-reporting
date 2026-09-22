import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { fetchCurrentUser } from "@/auth/api";
import { BackupInProgressError, createBackup, listBackups } from "@/system/api";
import { testAdmin, testBackup, testBackupList } from "@/test/fixtures";
import { renderApp } from "@/test/renderApp";

vi.mock("@/auth/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/auth/api")>()),
  fetchCurrentUser: vi.fn(),
}));

vi.mock("@/system/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/system/api")>()),
  listBackups: vi.fn(),
  createBackup: vi.fn(),
}));

beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(fetchCurrentUser).mockResolvedValue(testAdmin);
  vi.mocked(listBackups).mockResolvedValue(testBackupList);
});

describe("AdminBackupsPage", () => {
  it("renders the backup list", async () => {
    renderApp("/admin/backups");

    await screen.findByText(testBackup.name);
    expect(screen.getByText(testBackup.revision!)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Download" }).getAttribute("href")).toBe(
      `/api/v1/admin/backups/${testBackup.name}`,
    );
  });

  it("shows an empty state when there are no backups", async () => {
    vi.mocked(listBackups).mockResolvedValue({ backups: [], last_backup_at: null });

    renderApp("/admin/backups");

    await screen.findByText("No backups yet.");
  });

  it("creates a backup and shows a confirmation", async () => {
    vi.mocked(createBackup).mockResolvedValue(testBackup);
    renderApp("/admin/backups");
    await screen.findByText(testBackup.name);

    screen.getByRole("button", { name: "Create backup now" }).click();

    await waitFor(() => expect(createBackup).toHaveBeenCalled());
    await screen.findByText("Backup created");
  });

  it("shows a notification when a backup is already in progress", async () => {
    vi.mocked(createBackup).mockRejectedValue(new BackupInProgressError());
    renderApp("/admin/backups");
    await screen.findByText(testBackup.name);

    screen.getByRole("button", { name: "Create backup now" }).click();

    await screen.findByText("Backup already running");
  });
});
