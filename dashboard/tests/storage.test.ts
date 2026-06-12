import assert from "node:assert/strict";
import test from "node:test";

import { blobKeyForPayload, getLatestDashboardData, resolveDashboardPayload, resolveDashboardPayloads } from "../src/lib/storage";

const validPayload = {
  schema_version: "dashboard_payload_v1",
  generated_at: "2026-06-05T08:00:00",
  report_kind: "portfolio",
  total_value_krw: 1000,
  asset_groups: { coin: 200, equity: 700, cash: 100 },
  assets: [],
  trend: {
    start_total_krw: 1000,
    latest_total_krw: 1000,
    change_krw: 0,
    change_pct: null,
    snapshot_count: 1,
  },
  news_impacts: [],
  provider_status: [],
};

test("production dashboard does not fall back to sample data when blob payload is missing", () => {
  const result = resolveDashboardPayload(null, { allowSample: false });

  assert.equal(result.payload, null);
  assert.equal(result.source, "empty");
});

test("development dashboard can use sample data when blob payload is missing", () => {
  const result = resolveDashboardPayload(null, { allowSample: true });

  assert.ok(result.payload);
  assert.equal(result.source, "sample");
});

test("valid blob payload is preferred over sample data", () => {
  const result = resolveDashboardPayload(validPayload, { allowSample: true });

  assert.deepEqual(result.payload, validPayload);
  assert.equal(result.source, "blob");
});

test("v1 and v2 payloads use separate blob keys", () => {
  assert.equal(blobKeyForPayload({ schema_version: "dashboard_payload_v1" }), "dashboard/latest.json");
  assert.equal(blobKeyForPayload({ schema_version: "dashboard_payload_v2" }), "dashboard/v2-latest.json");
});

test("dashboard payload resolver keeps valid v1 and v2 data together", () => {
  const v2 = {
    schema_version: "dashboard_payload_v2",
    generated_at: "2026-06-12T19:28:50+09:00",
    total_value_krw: 1000,
    data_freshness: {},
    performance: {},
    asset_groups: [],
    assets: [],
    provider_status: [],
  };

  const result = resolveDashboardPayloads(validPayload, v2);

  assert.equal(result.v1?.schema_version, "dashboard_payload_v1");
  assert.equal(result.v2?.schema_version, "dashboard_payload_v2");
});

test("production blob read delegates credential resolution to the Blob SDK", async () => {
  const previousNodeEnv = process.env.NODE_ENV;
  const previousReadWriteToken = process.env.BLOB_READ_WRITE_TOKEN;
  const previousOidcToken = process.env.VERCEL_OIDC_TOKEN;
  const previousStoreId = process.env.BLOB_STORE_ID;
  const previousConsoleError = console.error;
  const errors: unknown[][] = [];

  process.env.NODE_ENV = "production";
  delete process.env.BLOB_READ_WRITE_TOKEN;
  delete process.env.VERCEL_OIDC_TOKEN;
  delete process.env.BLOB_STORE_ID;
  console.error = (...args: unknown[]) => errors.push(args);

  try {
    const result = await getLatestDashboardData();

    assert.equal(result.source, "empty");
    assert.match(String(errors[0]?.[1]), /No blob credentials found/);
  } finally {
    restoreEnv("NODE_ENV", previousNodeEnv);
    restoreEnv("BLOB_READ_WRITE_TOKEN", previousReadWriteToken);
    restoreEnv("VERCEL_OIDC_TOKEN", previousOidcToken);
    restoreEnv("BLOB_STORE_ID", previousStoreId);
    console.error = previousConsoleError;
  }
});

function restoreEnv(name: string, value: string | undefined): void {
  if (value === undefined) {
    delete process.env[name];
    return;
  }
  process.env[name] = value;
}
