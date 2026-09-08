import { createHmac, timingSafeEqual } from "node:crypto";

import { normalizePrincipal } from "@/lib/sociacl-light/principal";
import type { AccessorId } from "@/lib/sociacl-light/types";

const PREFIX = "v1";
const ETH = /^0x[a-f0-9]{40}$/;

export function siweSessionSecret(): string | null {
  const dedicated = process.env.AIMMUNE_SIWE_SECRET?.trim();
  if (dedicated) {
    return dedicated;
  }
  const token = process.env.AIMMUNE_UI_TOKEN?.trim();
  if (token) {
    return token;
  }
  if (
    process.env.NODE_ENV === "test" ||
    process.env.AIMMUNE_UI_ALLOW_TEST_TOKEN === "1"
  ) {
    return process.env.AIMMUNE_UI_TEST_TOKEN?.trim() || "test-token";
  }
  return null;
}

function hmacHex(secret: string, address: string): string {
  return createHmac("sha256", secret).update(`aimmune-siwe-${PREFIX}:${address}`).digest("hex");
}

function macsEqual(left: string, right: string): boolean {
  const a = Buffer.from(left, "hex");
  const b = Buffer.from(right, "hex");
  if (a.length === 0 || a.length !== b.length) {
    return false;
  }
  return timingSafeEqual(a, b);
}

/** Signed httpOnly cookie value. Only /api/siwe/verify may mint this. */
export function signSiweSession(address: string, secret = siweSessionSecret()): string | null {
  const principal = normalizePrincipal(address);
  if (!principal || !ETH.test(principal) || !secret) {
    return null;
  }
  return `${PREFIX}.${principal}.${hmacHex(secret, principal)}`;
}

/** Verified SIWE session only. Unsigned paste cookies are not SIWE. */
export function readSiweSessionCookie(
  raw: string | null | undefined,
  secret = siweSessionSecret(),
): AccessorId | null {
  if (!raw || !secret) {
    return null;
  }
  const parts = raw.split(".");
  if (parts.length !== 3 || parts[0] !== PREFIX) {
    return null;
  }
  const principal = normalizePrincipal(parts[1]);
  if (!principal || !ETH.test(principal)) {
    return null;
  }
  const expected = hmacHex(secret, principal);
  if (!macsEqual(parts[2] || "", expected)) {
    return null;
  }
  return principal;
}

export function isSignedSiweCookie(raw: string | null | undefined): boolean {
  return Boolean(raw?.startsWith(`${PREFIX}.`));
}
