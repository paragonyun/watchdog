import { verifyBearerToken } from "@/lib/auth-core";
import { validateCalendarPayload } from "@/lib/calendar-payload";
import { validateDashboardPayload } from "@/lib/dashboard-payload";
import { validateNewsRiskPayload } from "@/lib/news-risk-payload";
import { validateOpinionPayload } from "@/lib/opinion-payload";
import { validateReportPayload } from "@/lib/report-payload";
import { saveLatestCalendarPayload, saveLatestDashboardPayload, saveLatestNewsRiskPayload, saveLatestOpinionPayload, saveReportPayload } from "@/lib/storage";

export const runtime = "nodejs";

export async function POST(request: Request) {
  const token = parseBearerToken(request.headers.get("authorization"));
  if (!verifyBearerToken(token, process.env.WATCHDOG_UPLOAD_TOKEN)) {
    return Response.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return Response.json({ ok: false, error: "invalid_json" }, { status: 400 });
  }

  if (validateDashboardPayload(body)) {
    await saveLatestDashboardPayload(body);
    return Response.json({ ok: true, generated_at: body.generated_at });
  }

  if (validateNewsRiskPayload(body)) {
    await saveLatestNewsRiskPayload(body);
    return Response.json({ ok: true, generated_at: body.generated_at });
  }

  if (validateCalendarPayload(body)) {
    await saveLatestCalendarPayload(body);
    return Response.json({ ok: true, generated_at: body.generated_at, event_count: body.events.length });
  }

  if (validateOpinionPayload(body)) {
    await saveLatestOpinionPayload(body);
    return Response.json({ ok: true, generated_at: body.generated_at, opinion_id: body.opinion_id });
  }

  if (validateReportPayload(body)) {
    await saveReportPayload(body);
    return Response.json({ ok: true, generated_at: body.generated_at, report_id: body.report_id });
  }

  return Response.json({ ok: false, error: "invalid_upload_payload" }, { status: 400 });
}

function parseBearerToken(value: string | null): string | undefined {
  if (!value?.startsWith("Bearer ")) {
    return undefined;
  }
  return value.slice("Bearer ".length).trim();
}
