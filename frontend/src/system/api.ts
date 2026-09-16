import { api } from "@/api/client";
import { ApiError } from "@/api/errors";
import type { components } from "@/api/schema";

export type SystemStatus = components["schemas"]["SystemStatusResponse"];
export type SystemConfig = components["schemas"]["SystemConfigResponse"];

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
