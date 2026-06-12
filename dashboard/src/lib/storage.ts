import samplePayload from "@/data/sample-dashboard.json";

import {
  validateDashboardPayloadV1,
  validateDashboardPayloadV2,
  type AnyDashboardPayload,
  type DashboardPayload,
  type DashboardPayloadV2,
} from "./dashboard-payload";

const BLOB_KEY = "dashboard/latest.json";
const V2_BLOB_KEY = "dashboard/v2-latest.json";

export type DashboardDataSource = "blob" | "sample" | "empty";

export type DashboardDataResult = {
  payload: DashboardPayload | null;
  source: DashboardDataSource;
};

export type DashboardPayloads = {
  v1: DashboardPayload | null;
  v2: DashboardPayloadV2 | null;
};

export function resolveDashboardPayload(value: unknown, options: { allowSample: boolean }): DashboardDataResult {
  if (validateDashboardPayloadV1(value)) {
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

export function resolveDashboardPayloads(v1: unknown, v2: unknown): DashboardPayloads {
  return {
    v1: validateDashboardPayloadV1(v1) ? v1 : null,
    v2: validateDashboardPayloadV2(v2) ? v2 : null,
  };
}

export async function getLatestDashboardPayloads(): Promise<DashboardPayloads> {
  const [v1, v2] = await Promise.all([readBlobPayload(BLOB_KEY), readBlobPayload(V2_BLOB_KEY)]);
  const resolved = resolveDashboardPayloads(v1, v2);
  if (!resolved.v1 && process.env.NODE_ENV !== "production") {
    resolved.v1 = samplePayload as DashboardPayload;
  }
  return resolved;
}

export function blobKeyForPayload(payload: Pick<AnyDashboardPayload, "schema_version">): string {
  return payload.schema_version === "dashboard_payload_v2" ? V2_BLOB_KEY : BLOB_KEY;
}

export async function saveLatestDashboardPayload(payload: AnyDashboardPayload): Promise<void> {
  const { put } = await import("@vercel/blob");
  await put(blobKeyForPayload(payload), JSON.stringify(payload), {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json",
  });
}

async function readBlobPayload(key: string): Promise<unknown> {
  try {
    const { get } = await import("@vercel/blob");
    const file = await get(key, { access: "private", useCache: false });
    if (!file?.stream) {
      return null;
    }
    return JSON.parse(await new Response(file.stream).text()) as unknown;
  } catch (error) {
    console.error(`Failed to load dashboard blob ${key}:`, error instanceof Error ? error.message : "unknown error");
    return null;
  }
}
