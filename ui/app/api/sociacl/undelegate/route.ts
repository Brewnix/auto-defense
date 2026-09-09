import { NextResponse } from "next/server";

import { loadIrSession } from "@/lib/ir";
import { ownerUndelegateGrant } from "@/lib/sociacl-light/store";

export async function POST(request: Request) {
  let body: { accessor?: string; object?: string } = {};
  try {
    body = (await request.json()) as { accessor?: string; object?: string };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const session = await loadIrSession();
  const result = ownerUndelegateGrant({
    principal: session.principal,
    accessor: body.accessor || "",
    object: body.object || "",
    siteId: session.siteId,
  });
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }
  return NextResponse.json({ ok: true });
}
