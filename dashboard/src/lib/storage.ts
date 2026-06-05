import samplePayload from "@/data/sample-dashboard.json";

import { validateDashboardPayload, type DashboardPayload } from "./dashboard-payload";

const BLOB_KEY = "dashboard/latest.json";

export async function getLatestDashboardPayload(): Promise<DashboardPayload> {
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    return samplePayload as DashboardPayload;
  }
  try {
    const { get } = await import("@vercel/blob");
    const file = await get(BLOB_KEY, { access: "private", useCache: false });
    if (!file?.stream) {
      return samplePayload as DashboardPayload;
    }
    const payload = JSON.parse(await new Response(file.stream).text()) as unknown;
    return validateDashboardPayload(payload) ? payload : (samplePayload as DashboardPayload);
  } catch {
    return samplePayload as DashboardPayload;
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
