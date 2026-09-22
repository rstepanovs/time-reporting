import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type SystemStatus = components["schemas"]["SystemStatusResponse"];
export type SystemConfig = components["schemas"]["SystemConfigResponse"];
export type Backup = components["schemas"]["BackupResponse"];
export type BackupList = components["schemas"]["BackupListResponse"];

export async function getSystemStatus(): Promise<SystemStatus> {
  const { data, response } = await api.GET("/api/v1/admin/system/status");
  if (!data) throw new ApiError(response);
  return data;
}

export async function getSystemConfig(): Promise<SystemConfig> {
  const { data, response } = await api.GET("/api/v1/admin/system/config");
  if (!data) throw new ApiError(response);
  return data;
}

/** A backup is already in progress (409) — `BackupService`'s lock file. */
export class BackupInProgressError extends Error {
  constructor() {
    super("A backup is already in progress");
    this.name = "BackupInProgressError";
  }
}

/** `pg_dump` failed (500); the backend's generic detail, never the raw stderr. */
export class BackupFailedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "BackupFailedError";
  }
}

async function backupAwareError(response: Response): Promise<Error> {
  if (response.status === 409) return new BackupInProgressError();
  if (response.status === 500) {
    const body = (await response.clone().json().catch(() => null)) as { detail?: string } | null;
    return new BackupFailedError(body?.detail ?? "Backup failed; see server logs for details");
  }
  return new ApiError(response);
}

export async function listBackups(): Promise<BackupList> {
  const { data, response } = await api.GET("/api/v1/admin/backups");
  if (!data) throw new ApiError(response);
  return data;
}

export async function createBackup(): Promise<Backup> {
  const { data, response } = await api.POST("/api/v1/admin/backups");
  if (!data) throw await backupAwareError(response);
  return data;
}

/** Relative download URL for a backup; used directly as an `<a href>`, not fetched via `api`. */
export function backupDownloadUrl(name: string): string {
  return `/api/v1/admin/backups/${encodeURIComponent(name)}`;
}
