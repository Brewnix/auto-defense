import { NextResponse } from "next/server";

import { grantPropose } from "@/lib/aimmune";

export async function POST(request: Request) {
  let body: {
    action?: "propose" | "mint-local";
    incident_id?: string;
    profile?: string;
    ttl?: number;
    reason?: string;
    tools?: string[];
    ticket_id?: string;
    notes?: string;
  } = {};
  try {
    body = (await request.json()) as typeof body;
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const incidentId = body.incident_id?.trim();
  const reason = body.reason?.trim();
  if (!incidentId || !reason) {
    return NextResponse.json(
      { error: "incident_id and reason required" },
      { status: 400 },
    );
  }
  const result = await grantPropose({
    action: body.action || "propose",
    incident_id: incidentId,
    profile: body.profile || "ir_elevated",
    ttl: Number(body.ttl) || 1800,
    reason,
    tools: body.tools,
    ticket_id: body.ticket_id,
    notes: body.notes,
  });
  if (result.code === 2) {
    return NextResponse.json(
      { error: result.stderr.trim() || "plane-up mint is plane-resolved" },
      { status: 409 },
    );
  }
  if (result.code !== 0) {
    return NextResponse.json(
      { error: result.stderr.trim() || "grant failed" },
      { status: 400 },
    );
  }
  try {
    return NextResponse.json(JSON.parse(result.stdout));
  } catch {
    return NextResponse.json({ ok: true, raw: result.stdout });
  }
}
