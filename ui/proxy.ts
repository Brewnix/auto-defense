import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  COOKIE_NAME,
  bearerFromHeader,
  configuredUiToken,
  tokensEqual,
} from "@/lib/auth";

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (
    pathname.startsWith("/settings") ||
    pathname.startsWith("/api/session") ||
    pathname.startsWith("/api/siwe")
  ) {
    return NextResponse.next();
  }

  const expected = configuredUiToken();
  if (!expected) {
    if (pathname.startsWith("/api")) {
      return NextResponse.json(
        { error: "AIMMUNE_UI_TOKEN is required to serve" },
        { status: 503 },
      );
    }
    return NextResponse.redirect(new URL("/settings?reason=unset", request.url));
  }

  const provided =
    bearerFromHeader(request.headers.get("authorization")) ||
    request.cookies.get(COOKIE_NAME)?.value ||
    null;
  if (tokensEqual(provided, expected)) {
    return NextResponse.next();
  }

  if (pathname.startsWith("/api")) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return NextResponse.redirect(new URL("/settings?reason=auth", request.url));
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
