import { NextResponse } from "next/server";

import { ownerAnnotate } from "@/lib/aimmune";
import { requireIrAct } from "@/lib/ir";

export async function POST(request: Request) {
  const gate = await requireIrAct("annotate");
  if (!gate.ok) {
    return NextResponse.json(
      { error: gate.error, check: gate.check },
      { status: gate.status },
    );
  }
  let body: { receipt_id?: string; note?: string } = {};
  try {
    body = (await request.json()) as { receipt_id?: string; note?: string };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const receiptId = body.receipt_id?.trim();
  const note = body.note?.trim();
  if (!receiptId || !note) {
    return NextResponse.json(
      { error: "receipt_id and note required" },
      { status: 400 },
    );
  }
  const result = await ownerAnnotate(receiptId, note);
  if (result.code !== 0) {
    return NextResponse.json(
      { error: result.stderr.trim() || "annotate failed" },
      { status: 400 },
    );
  }
  try {
    return NextResponse.json(JSON.parse(result.stdout));
  } catch {
    return NextResponse.json({ ok: true, raw: result.stdout });
  }
}
