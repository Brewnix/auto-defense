import { createHmac, timingSafeEqual } from "node:crypto";

import { normalizePrincipal } from "@/lib/sociacl-light/principal";
import type { AccessorId } from "@/lib/sociacl-light/types";

const PREFIX_V1 = "v1";
const PREFIX_V2 = "v2";
const ETH = /^0x[a-f0-9]{40}$/;
export const DEFAULT_SIWE_TTL_S = 43_200;

export type SiweSession = {
  principal: AccessorId;
  exp: number | null;
  version: "v1" | "v2";
};

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

/** Seconds. Env AIMMUNE_SIWE_TTL_S; default 12h. */
export function siweSessionTtlS(): number {
  const raw = process.env.AIMMUNE_SIWE_TTL_S?.trim();
  if (raw) {
    const n = Number(raw);
    if (Number.isInteger(n) && n > 0) {
      return n;
    }
  }
  return DEFAULT_SIWE_TTL_S;
}

function hmacV1(secret: string, address: string): string {
  return createHmac("sha256", secret).update(`aimmune-siwe-${PREFIX_V1}:${address}`).digest("hex");
}

function hmacV2(secret: string, address: string, exp: number): string {
  return createHmac("sha256", secret)
    .update(`aimmune-siwe-${PREFIX_V2}:${address}:${exp}`)
    .digest("hex");
}

function macsEqual(left: string, right: string): boolean {
  const a = Buffer.from(left, "hex");
  const b = Buffer.from(right, "hex");
  if (a.length === 0 || a.length !== b.length) {
    return false;
  }
  return timingSafeEqual(a, b);
}

function unixNow(now?: number): number {
  return now ?? Math.floor(Date.now() / 1000);
}

/** Signed httpOnly cookie value. Only /api/siwe/verify may mint this (v2 + exp). */
export function signSiweSession(
  address: string,
  secret = siweSessionSecret(),
  now?: number,
): string | null {
  const principal = normalizePrincipal(address);
  if (!principal || !ETH.test(principal) || !secret) {
    return null;
  }
  const exp = unixNow(now) + siweSessionTtlS();
  return `${PREFIX_V2}.${principal}.${exp}.${hmacV2(secret, principal, exp)}`;
}

function readV2(
  parts: string[],
  secret: string,
  now: number,
): SiweSession | null {
  const principal = normalizePrincipal(parts[1]);
  const exp = Number(parts[2]);
  if (!principal || !ETH.test(principal) || !Number.isInteger(exp) || exp <= 0) {
    return null;
  }
  const expected = hmacV2(secret, principal, exp);
  if (!macsEqual(parts[3] || "", expected)) {
    return null;
  }
  if (!(now < exp)) {
    return null;
  }
  return { principal, exp, version: "v2" };
}

function readV1(parts: string[], secret: string): SiweSession | null {
  const principal = normalizePrincipal(parts[1]);
  if (!principal || !ETH.test(principal)) {
    return null;
  }
  const expected = hmacV1(secret, principal);
  if (!macsEqual(parts[2] || "", expected)) {
    return null;
  }
  return { principal, exp: null, version: "v1" };
}

/**
 * Verified SIWE session only. Unsigned paste cookies are not SIWE.
 * v2 requires now < exp. Expired v2 is logged out (no SIWE principal).
 * v1 (no exp) is still accepted during the cookie-format upgrade.
 */
export function readSiweSession(
  raw: string | null | undefined,
  secret = siweSessionSecret(),
  now?: number,
): SiweSession | null {
  if (!raw || !secret) {
    return null;
  }
  const parts = raw.split(".");
  const at = unixNow(now);
  if (parts[0] === PREFIX_V2 && parts.length === 4) {
    return readV2(parts, secret, at);
  }
  if (parts[0] === PREFIX_V1 && parts.length === 3) {
    return readV1(parts, secret);
  }
  return null;
}

/** Verified SIWE session only. Unsigned paste cookies are not SIWE. */
export function readSiweSessionCookie(
  raw: string | null | undefined,
  secret = siweSessionSecret(),
  now?: number,
): AccessorId | null {
  return readSiweSession(raw, secret, now)?.principal ?? null;
}

export function isSignedSiweCookie(raw: string | null | undefined): boolean {
  return Boolean(raw?.startsWith(`${PREFIX_V1}.`) || raw?.startsWith(`${PREFIX_V2}.`));
}
