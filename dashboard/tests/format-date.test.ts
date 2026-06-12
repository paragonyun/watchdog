import assert from "node:assert/strict";
import test from "node:test";

import { formatDashboardDate } from "../src/lib/format-date";

test("formats UTC timestamps in Asia/Seoul time", () => {
  assert.equal(
    formatDashboardDate("2026-06-12T21:18:12+00:00"),
    "06. 13. AM 06:18",
  );
});

test("returns an unavailable label when timestamp is missing", () => {
  assert.equal(formatDashboardDate(null), "확인 불가");
});
