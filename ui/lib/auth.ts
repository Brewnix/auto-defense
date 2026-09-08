import { timingSafeEqual } from "node:crypto";

import { isSignedSiweCookie, readSiweSessionCookie } from "@/lib/siwe/session";
import {
  normalizePrincipal,
  smokePrincipalFromEnv,
} from "@/lib/sociacl-light/principal";
import type { AccessorId } from "@/lib/sociacl-light/types";

export const COOKIE_NAME = "aimmune_ui";
export const PRINCIPAL_COOKIE = "aimmune_principal";
export const PRINCIPAL_HEADER = "x-aimmune-principal";

export function configuredUiToken(): string | null {
  const env = process.env.AIMMUNE_UI_TOKEN?.trim();
  if (env) {
    return env;
  }
  if (
    process.env.NODE_ENV === "test" ||
    process.env.AIMMUNE_UI_ALLOW_TEST_TOKEN === "1"
  ) {
    return process.env.AIMMUNE_UI_TEST_TOKEN?.trim() || "test-token";
  }
  return null;
}

export function tokensEqual(provided: string | null | undefined, expected: string): boolean {
  if (!provided) {
    return false;
  }
  const left = Buffer.from(provided);
  const right = Buffer.from(expected);
  if (left.length !== right.length) {
    return false;
  }
  return timingSafeEqual(left, right);
}

export function bearerFromHeader(header: string | null): string | null {
  if (!header) {
    return null;
  }
  const prefix = "Bearer ";
  if (!header.startsWith(prefix)) {
    return null;
  }
  const token = header.slice(prefix.length).trim();
  return token || null;
}

export function isBlockedStatus(status: string): boolean {
  return status === "blocked";
}

export function smokePrincipalAllowed(): boolean {
  if (process.env.AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL === "1") {
    return true;
  }
  return process.env.NODE_ENV !== "production";
}

function smokePastedPrincipal(
  cookie?: string | null,
  header?: string | null,
): AccessorId | null {
  const fromHeader = normalizePrincipal(header);
  if (fromHeader) {
    return fromHeader;
  }
  if (isSignedSiweCookie(cookie)) {
    return null;
  }
  return normalizePrincipal(cookie);
}

/**
 * Dual auth: UI token still opens the loopback console.
 * source "siwe" is only a verified (HMAC) cookie from POST /api/siwe/verify.
 * Paste-principal and X-AImmune-Principal are smoke-only, and fail closed
 * in production unless AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL=1.
 */
export function resolvePrincipal(input: {
  cookie?: string | null;
  header?: string | null;
  tokenOk?: boolean;
}): { principal: AccessorId | null; source: "siwe" | "smoke" | null } {
  const verified = readSiweSessionCookie(input.cookie);
  if (verified) {
    return { principal: verified, source: "siwe" };
  }
  if (smokePrincipalAllowed()) {
    const pasted = smokePastedPrincipal(input.cookie, input.header);
    if (pasted) {
      return { principal: pasted, source: "smoke" };
    }
    if (input.tokenOk) {
      const smoke = smokePrincipalFromEnv();
      if (smoke) {
        return { principal: smoke, source: "smoke" };
      }
    }
  }
  return { principal: null, source: null };
}
