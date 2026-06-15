import samplePayload from "@/data/sample-dashboard.json";

import {
  validateDashboardPayloadV1,
  validateDashboardPayloadV2,
  type AnyDashboardPayload,
  type DashboardPayload,
  type DashboardPayloadV2,
} from "./dashboard-payload";
import { validateNewsRiskPayload, type NewsRiskPayload } from "./news-risk-payload";
import { validateOpinionPayload, type OpinionPayload } from "./opinion-payload";
import {
  toReportIndexItem,
  validReportId,
  validateReportIndexItem,
  validateReportPayload,
  type ReportIndexItem,
  type ReportPayload,
} from "./report-payload";

const BLOB_KEY = "dashboard/latest.json";
const V2_BLOB_KEY = "dashboard/v2-latest.json";
export const NEWS_RISK_BLOB_KEY = "dashboard/news-risk-latest.json";
export const OPINION_BLOB_KEY = "dashboard/opinion-latest.json";
export const REPORT_INDEX_BLOB_KEY = "dashboard/reports/index.json";

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

export async function getLatestNewsRiskPayload(): Promise<NewsRiskPayload | null> {
  const value = await readBlobPayload(NEWS_RISK_BLOB_KEY);
  return validateNewsRiskPayload(value) ? value : null;
}

export async function saveLatestNewsRiskPayload(payload: NewsRiskPayload): Promise<void> {
  const { put } = await import("@vercel/blob");
  await put(NEWS_RISK_BLOB_KEY, JSON.stringify(payload), {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json",
  });
}

export async function getLatestOpinionPayload(): Promise<OpinionPayload | null> {
  const value = await readBlobPayload(OPINION_BLOB_KEY);
  return validateOpinionPayload(value) ? value : null;
}

export async function saveLatestOpinionPayload(payload: OpinionPayload): Promise<void> {
  const { put } = await import("@vercel/blob");
  await put(OPINION_BLOB_KEY, JSON.stringify(payload), {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json",
  });
}

export function reportBlobKey(reportId: string): string {
  if (!validReportId(reportId)) throw new Error("invalid report id");
  return `dashboard/reports/${reportId}.json`;
}

export async function getReportIndex(): Promise<ReportIndexItem[]> {
  const value = await readBlobPayload(REPORT_INDEX_BLOB_KEY);
  return Array.isArray(value) ? value.filter(validateReportIndexItem) : [];
}

export async function getReportPayload(reportId: string): Promise<ReportPayload | null> {
  const value = await readBlobPayload(reportBlobKey(reportId));
  return validateReportPayload(value) ? value : null;
}

export async function saveReportPayload(payload: ReportPayload): Promise<void> {
  const { put } = await import("@vercel/blob");
  await put(reportBlobKey(payload.report_id), JSON.stringify(payload), {
    access: "private",
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: "application/json",
  });
  const existing = await getReportIndex();
  const index = [
    toReportIndexItem(payload),
    ...existing.filter((item) => item.report_id !== payload.report_id),
  ]
    .sort((left, right) => Date.parse(right.generated_at) - Date.parse(left.generated_at))
    .slice(0, 50);
  await put(REPORT_INDEX_BLOB_KEY, JSON.stringify(index), {
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
