import { NextResponse } from "next/server";

import { NONCE_COOKIE, NONCE_TTL_MS, siweNoncePayload } from "@/lib/siwe";

function cookieOpts() {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    path: "/",
    secure: process.env.NODE_ENV === "production",
    maxAge: Math.floor(NONCE_TTL_MS / 1000),
  };
}

export async function GET() {
  const payload = siweNoncePayload();
  const response = NextResponse.json(payload);
  response.cookies.set({
    name: NONCE_COOKIE,
    value: payload.nonce,
    ...cookieOpts(),
  });
  return response;
}
