import { timingSafeEqual } from "node:crypto";

export const COOKIE_NAME = "aimmune_ui";

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
