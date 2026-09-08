import { NextRequest, NextResponse } from "next/server";

import { PRINCIPAL_COOKIE } from "@/lib/auth";
import { NONCE_COOKIE, signSiweSession, verifySiweLogin } from "@/lib/siwe";

function cookieOpts() {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    path: "/",
    secure: process.env.NODE_ENV === "production",
  };
}

export async function POST(request: NextRequest) {
  let body: { message?: unknown; signature?: unknown } = {};
  try {
    body = (await request.json()) as { message?: unknown; signature?: unknown };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const result = await verifySiweLogin({
    message: body.message,
    signature: body.signature,
    cookieNonce: request.cookies.get(NONCE_COOKIE)?.value || null,
  });
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: result.status });
  }

  const session = signSiweSession(result.principal);
  if (!session) {
    return NextResponse.json({ error: "could not mint siwe session" }, { status: 503 });
  }

  const response = NextResponse.json({
    ok: true,
    principal: result.principal,
    source: "siwe" as const,
  });
  response.cookies.set({
    name: PRINCIPAL_COOKIE,
    value: session,
    ...cookieOpts(),
  });
  response.cookies.set({
    name: NONCE_COOKIE,
    value: "",
    ...cookieOpts(),
    maxAge: 0,
  });
  return response;
}
