import { NextResponse } from "next/server";

import { closeIncident } from "@/lib/aimmune";

export async function POST(request: Request) {
  let body: { incident_id?: string } = {};
  try {
    body = (await request.json()) as { incident_id?: string };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const incidentId = body.incident_id?.trim();
  if (!incidentId) {
    return NextResponse.json({ error: "incident_id required" }, { status: 400 });
  }
  const result = await closeIncident(incidentId);
  if (result.code === 2) {
    return NextResponse.json(
      { error: result.stderr.trim() || "close refused: grant_active" },
      { status: 409 },
    );
  }
  if (result.code !== 0) {
    return NextResponse.json(
      { error: result.stderr.trim() || "incident close failed" },
      { status: 400 },
    );
  }
  try {
    return NextResponse.json(JSON.parse(result.stdout));
  } catch {
    return NextResponse.json({ ok: true, raw: result.stdout });
  }
}
