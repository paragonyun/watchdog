import { verifyBearerToken } from "@/lib/auth-core";
import { validateDashboardPayload } from "@/lib/dashboard-payload";
import { saveLatestDashboardPayload } from "@/lib/storage";

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

  if (!validateDashboardPayload(body)) {
    return Response.json({ ok: false, error: "invalid_dashboard_payload" }, { status: 400 });
  }

  await saveLatestDashboardPayload(body);
  return Response.json({ ok: true, generated_at: body.generated_at });
}

function parseBearerToken(value: string | null): string | undefined {
  if (!value?.startsWith("Bearer ")) {
    return undefined;
  }
  return value.slice("Bearer ".length).trim();
}
