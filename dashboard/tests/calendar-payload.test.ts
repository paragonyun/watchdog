import assert from "node:assert/strict";
import test from "node:test";

import { validateCalendarPayload } from "../src/lib/calendar-payload";

const payload = {
  schema_version: "dashboard_calendar_v1",
  generated_at: "2026-06-18T08:00:00+09:00",
  source: "codex",
  timezone: "Asia/Seoul",
  events: [
    {
      id: "us-fomc-20260619",
      title: "미국 FOMC 의사록",
      starts_at: "2026-06-19T03:00:00+09:00",
      country: "미국",
      category: "금리",
      importance: "high",
      asset_groups: ["isa", "coin"],
      expected_impact: "금리 경로 재평가로 위험자산 변동성이 커질 수 있습니다.",
      watch_note: "점도표와 기자회견의 물가 표현을 확인합니다.",
      source_url: "https://example.com/calendar",
    },
  ],
};

test("accepts privacy-safe economic calendar payloads", () => {
  assert.equal(validateCalendarPayload(payload), true);
});

test("rejects malformed calendar events and sensitive fields", () => {
  assert.equal(validateCalendarPayload({ ...payload, account_no: "123" }), false);
  assert.equal(validateCalendarPayload({ ...payload, events: [{ ...payload.events[0], importance: "critical" }] }), false);
  assert.equal(validateCalendarPayload({ ...payload, events: [{ ...payload.events[0], source_url: "http://localhost:3000" }] }), false);
  assert.equal(validateCalendarPayload({ ...payload, events: [{ ...payload.events[0], asset_groups: ["real_estate"] }] }), false);
});
