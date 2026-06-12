import samplePayload from "@/data/sample-dashboard.json";

import { validateDashboardPayload, type DashboardPayload } from "./dashboard-payload";

const BLOB_KEY = "dashboard/latest.json";

export type DashboardDataSource = "blob" | "sample" | "empty";

export type DashboardDataResult = {
  payload: DashboardPayload | null;
  source: DashboardDataSource;
};

export function resolveDashboardPayload(value: unknown, options: { allowSample: boolean }): DashboardDataResult {
  if (validateDashboardPayload(value)) {
    return { payload: value, source: "blob" };
  }
  if (options.allowSample) {
    return { payload: samplePayload as DashboardPayload, source: "sample" };
  }
  return { payload: null, source: "empty" };
}

export async function getLatestDashboardData(): Promise<DashboardDataResult> {
  const allowSample = process.env.NODE_ENV !== "production";
  try {
    const { get } = await import("@vercel/blob");
    const file = await get(BLOB_KEY, { access: "private", useCache: false });
    if (!file?.stream) {
      return resolveDashboardPayload(null, { allowSample });
    }
    const payload = JSON.parse(await new Response(file.stream).text()) as unknown;
    return resolveDashboardPayload(payload, { allowSample });
  } catch (error) {
    console.error("Failed to load dashboard blob:", error instanceof Error ? error.message : "unknown error");
    return resolveDashboardPayload(null, { allowSample });
  }
}

export async function saveLatestDashboardPayload(payload: DashboardPayload): Promise<void> {
  const { put } = await import("@vercel/blob");
  await put(BLOB_KEY, JSON.stringify(payload), {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json",
  });
}
