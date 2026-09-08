import { NextResponse } from "next/server";

import { ownerResolve } from "@/lib/aimmune";

export async function POST(request: Request) {
  let body: { receipt_id?: string; action?: string; note?: string } = {};
  try {
    body = (await request.json()) as {
      receipt_id?: string;
      action?: string;
      note?: string;
    };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const receiptId = body.receipt_id?.trim();
  const action = body.action;
  if (!receiptId || (action !== "approve" && action !== "deny")) {
    return NextResponse.json(
      { error: "receipt_id and action=approve|deny required" },
      { status: 400 },
    );
  }
  const result = await ownerResolve(receiptId, action, body.note);
  if (result.code === 2) {
    return NextResponse.json(
      { error: result.stderr.trim() || "waiting on plane" },
      { status: 409 },
    );
  }
  if (result.code !== 0) {
    return NextResponse.json(
      { error: result.stderr.trim() || "owner resolve failed" },
      { status: 400 },
    );
  }
  try {
    return NextResponse.json(JSON.parse(result.stdout));
  } catch {
    return NextResponse.json({ ok: true, raw: result.stdout });
  }
}
