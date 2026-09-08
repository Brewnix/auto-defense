import { NextResponse } from "next/server";

import { loadSnapshot } from "@/lib/aimmune";
import { loadIrSession } from "@/lib/ir";
import { redactSnapshot } from "@/lib/redact";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const limit = Number(url.searchParams.get("limit") || "50");
  try {
    const session = await loadIrSession();
    const snap = await loadSnapshot(Number.isFinite(limit) ? limit : 50);
    const payload = session.caps.read ? snap : redactSnapshot(snap);
    return NextResponse.json({
      ...payload,
      ir: {
        principal: session.principal,
        source: session.source,
        caps: session.caps,
      },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "snapshot failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
