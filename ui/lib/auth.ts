import { timingSafeEqual } from "node:crypto";

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

/**
 * Dual auth: UI token still opens the loopback console.
 * Human acts need a SIWE / cottage principal. Loopback smoke may
 * use AIMMUNE_UI_SMOKE_PRINCIPAL when the token is valid.
 */
export function resolvePrincipal(input: {
  cookie?: string | null;
  header?: string | null;
  tokenOk?: boolean;
}): { principal: AccessorId | null; source: "siwe" | "smoke" | null } {
  const session = normalizePrincipal(input.header) || normalizePrincipal(input.cookie);
  if (session) {
    return { principal: session, source: "siwe" };
  }
  if (input.tokenOk && smokePrincipalAllowed()) {
    const smoke = smokePrincipalFromEnv();
    if (smoke) {
      return { principal: smoke, source: "smoke" };
    }
  }
  return { principal: null, source: null };
}
