import { NextResponse } from "next/server";

import { COOKIE_NAME, configuredUiToken, tokensEqual } from "@/lib/auth";

export async function POST(request: Request) {
  const expected = configuredUiToken();
  if (!expected) {
    return NextResponse.json(
      { error: "AIMMUNE_UI_TOKEN is required to serve" },
      { status: 503 },
    );
  }
  let body: { token?: string } = {};
  try {
    body = (await request.json()) as { token?: string };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  if (!tokensEqual(body.token, expected)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: COOKIE_NAME,
    value: expected,
    httpOnly: true,
    sameSite: "strict",
    path: "/",
    secure: process.env.NODE_ENV === "production",
  });
  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: COOKIE_NAME,
    value: "",
    httpOnly: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  });
  return response;
}
