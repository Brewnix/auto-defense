import { NextResponse } from "next/server";

import {
  COOKIE_NAME,
  PRINCIPAL_COOKIE,
  configuredUiToken,
  smokePrincipalAllowed,
  tokensEqual,
} from "@/lib/auth";
import { loadIrSession } from "@/lib/ir";
import { NONCE_COOKIE } from "@/lib/siwe";
import { normalizePrincipal } from "@/lib/sociacl-light/principal";

function cookieOpts(secure: boolean) {
  return {
    httpOnly: true,
    sameSite: "strict" as const,
    path: "/",
    secure,
  };
}

export async function GET() {
  const session = await loadIrSession();
  return NextResponse.json({
    ok: true,
    principal: session.principal,
    source: session.source,
    exp: session.exp,
    site_id: session.siteId,
    caps: session.caps,
    dual: {
      ui_token: "AIMMUNE_UI_TOKEN still required to serve (loopback smoke)",
      human: "production human path requires Check (SIWE / cottage principal)",
      machine: "hm_site_ unchanged",
    },
  });
}

export async function POST(request: Request) {
  const expected = configuredUiToken();
  if (!expected) {
    return NextResponse.json(
      { error: "AIMMUNE_UI_TOKEN is required to serve" },
      { status: 503 },
    );
  }
  let body: { token?: string; principal?: string } = {};
  try {
    body = (await request.json()) as { token?: string; principal?: string };
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }
  const response = NextResponse.json({ ok: true });
  const secure = process.env.NODE_ENV === "production";
  if (body.token !== undefined) {
    if (!tokensEqual(body.token, expected)) {
      return NextResponse.json({ error: "unauthorized" }, { status: 401 });
    }
    response.cookies.set({
      name: COOKIE_NAME,
      value: expected,
      ...cookieOpts(secure),
    });
  }
  if (body.principal !== undefined) {
    if (!smokePrincipalAllowed()) {
      return NextResponse.json(
        {
          error:
            "production requires SIWE (POST /api/siwe/verify); paste principal is smoke-only",
        },
        { status: 403 },
      );
    }
    const principal = normalizePrincipal(body.principal);
    if (!principal) {
      return NextResponse.json({ error: "principal required" }, { status: 400 });
    }
    response.cookies.set({
      name: PRINCIPAL_COOKIE,
      value: principal,
      ...cookieOpts(secure),
    });
  }
  if (body.token === undefined && body.principal === undefined) {
    return NextResponse.json({ error: "token or principal required" }, { status: 400 });
  }
  return response;
}

/** Clears UI token + SIWE signed principal (v2 / leftover v1) + nonce. */
export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  const secure = process.env.NODE_ENV === "production";
  for (const name of [COOKIE_NAME, PRINCIPAL_COOKIE, NONCE_COOKIE]) {
    response.cookies.set({
      name,
      value: "",
      ...cookieOpts(secure),
      maxAge: 0,
    });
  }
  return response;
}
