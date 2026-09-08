import { verifyMessage } from "viem";
import { parseSiweMessage, validateSiweMessage } from "viem/siwe";

import type { AccessorId } from "@/lib/sociacl-light/types";
import { normalizePrincipal } from "@/lib/sociacl-light/principal";
import { configuredSiteId } from "@/lib/sociacl-light/objects";

import { SIWE_VERSION, siweChainId, siweDomain, siteBindToken } from "./config";
import { consumeNonce } from "./nonce";

export type SiweVerifyInput = {
  message: unknown;
  signature: unknown;
  cookieNonce: string | null;
};

export type SiweVerifyOk = { ok: true; principal: AccessorId };
export type SiweVerifyErr = { ok: false; status: 400 | 401; error: string };
export type SiweVerifyResult = SiweVerifyOk | SiweVerifyErr;

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export async function verifySiweLogin(input: SiweVerifyInput): Promise<SiweVerifyResult> {
  const message = asString(input.message);
  const signature = asString(input.signature);
  if (!message || !signature) {
    return { ok: false, status: 400, error: "message and signature required" };
  }
  if (!input.cookieNonce) {
    return { ok: false, status: 401, error: "siwe nonce required" };
  }

  let parsed;
  try {
    parsed = parseSiweMessage(message);
  } catch {
    return { ok: false, status: 401, error: "invalid siwe message" };
  }

  const address = normalizePrincipal(parsed.address);
  if (!address || !address.startsWith("0x") || address.length !== 42) {
    return { ok: false, status: 401, error: "invalid siwe address" };
  }
  const hexAddress = address as `0x${string}`;
  if (parsed.version !== SIWE_VERSION) {
    return { ok: false, status: 401, error: "invalid siwe version" };
  }
  if (parsed.nonce !== input.cookieNonce) {
    return { ok: false, status: 401, error: "siwe nonce mismatch" };
  }

  const siteId = configuredSiteId();
  const bind = siteBindToken(siteId);
  if (!parsed.statement || !parsed.statement.includes(bind)) {
    return { ok: false, status: 401, error: `siwe statement must bind ${bind}` };
  }

  const fieldsOk = validateSiweMessage({
    message: parsed,
    address: hexAddress,
    domain: siweDomain(),
    nonce: input.cookieNonce,
  });
  if (!fieldsOk) {
    return { ok: false, status: 401, error: "invalid siwe fields" };
  }
  const expectedChain = siweChainId();
  if (expectedChain !== undefined && parsed.chainId !== expectedChain) {
    return { ok: false, status: 401, error: "siwe chain mismatch" };
  }

  if (!consumeNonce(input.cookieNonce)) {
    return { ok: false, status: 401, error: "siwe nonce already used" };
  }

  let valid = false;
  try {
    valid = await verifyMessage({
      address: hexAddress,
      message,
      signature: signature as `0x${string}`,
    });
  } catch {
    valid = false;
  }
  if (!valid) {
    return { ok: false, status: 401, error: "unauthorized" };
  }

  return { ok: true, principal: address };
}
