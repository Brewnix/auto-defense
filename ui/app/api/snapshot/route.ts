import { NextResponse } from "next/server";

import { loadSnapshot } from "@/lib/aimmune";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const limit = Number(url.searchParams.get("limit") || "50");
  try {
    const snap = await loadSnapshot(Number.isFinite(limit) ? limit : 50);
    return NextResponse.json(snap);
  } catch (error) {
    const message = error instanceof Error ? error.message : "snapshot failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
