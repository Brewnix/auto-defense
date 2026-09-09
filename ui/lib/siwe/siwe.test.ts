import { createHmac } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NextRequest } from "next/server";
import { privateKeyToAccount } from "viem/accounts";
import { createSiweMessage } from "viem/siwe";

import { GET as getNonce } from "@/app/api/siwe/nonce/route";
import { POST as postVerify } from "@/app/api/siwe/verify/route";
import { DELETE as deleteSession, POST as postSession } from "@/app/api/session/route";
import { resolvePrincipal } from "@/lib/auth";
import { checkIrAct } from "@/lib/sociacl-light/gate";
import { irObject } from "@/lib/sociacl-light/objects";
import { MockCheck } from "@/lib/sociacl-light/mock-check";

import { NONCE_COOKIE, resetNonceStore, siweNoncePayload } from "./index";
import { readSiweSession, signSiweSession, siweSessionTtlS } from "./session";
import { verifySiweLogin } from "./verify";

const ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";
const ACCOUNT = privateKeyToAccount(ANVIL_KEY);
const SITE = "net-tn-cottage";
const OWNER = ACCOUNT.address.toLowerCase();

function cookieFrom(response: Response, name: string): string | undefined {
  return (response as Response & { cookies: { get: (n: string) => { value: string } | undefined } })
    .cookies.get(name)?.value;
}

function setCookieHasHttpOnly(response: Response, name: string): boolean {
  const raw =
    typeof response.headers.getSetCookie === "function"
      ? response.headers.getSetCookie()
      : [response.headers.get("set-cookie") || ""];
  return raw.some((line) => line.startsWith(`${name}=`) && /HttpOnly/i.test(line));
}

async function signedMessage(overrides: Record<string, unknown> = {}) {
  const fields = siweNoncePayload();
  const message = createSiweMessage({
    address: ACCOUNT.address,
    chainId: fields.chainId,
    domain: fields.domain,
    nonce: fields.nonce,
    uri: fields.uri,
    version: "1",
    statement: fields.statement,
    issuedAt: new Date(fields.issuedAt),
    expirationTime: new Date(fields.expirationTime),
    ...overrides,
  });
  const signature = await ACCOUNT.signMessage({ message });
  return { fields, message, signature };
}

beforeEach(() => {
  resetNonceStore();
  vi.stubEnv("AIMMUNE_UI_TOKEN", "test-token");
  vi.stubEnv("AIMMUNE_SIWE_DOMAIN", "127.0.0.1");
  vi.stubEnv("SITE_ID", SITE);
  vi.stubEnv("AIMMUNE_UI_PORT", "3000");
});

afterEach(() => {
  resetNonceStore();
  vi.unstubAllEnvs();
});

describe("SIWE v0", () => {
  it("issues a one-time nonce and httpOnly cookie", async () => {
    const response = await getNonce();
    const body = (await response.json()) as { nonce: string; statement: string };
    expect(body.nonce.length).toBeGreaterThanOrEqual(8);
    expect(body.statement).toContain(`site:${SITE}`);
    expect(cookieFrom(response, NONCE_COOKIE)).toBe(body.nonce);
    expect(setCookieHasHttpOnly(response, NONCE_COOKIE)).toBe(true);
  });

  it("verifies a personal_sign, normalizes address, and sets httpOnly session", async () => {
    const nonceRes = await getNonce();
    const fields = (await nonceRes.json()) as {
      nonce: string;
      domain: string;
      uri: string;
      statement: string;
      chainId: number;
      issuedAt: string;
      expirationTime: string;
    };
    const message = createSiweMessage({
      address: ACCOUNT.address,
      chainId: fields.chainId,
      domain: fields.domain,
      nonce: fields.nonce,
      uri: fields.uri,
      version: "1",
      statement: fields.statement,
      issuedAt: new Date(fields.issuedAt),
      expirationTime: new Date(fields.expirationTime),
    });
    const signature = await ACCOUNT.signMessage({ message });
    const verifyRes = await postVerify(
      new NextRequest("http://127.0.0.1:3000/api/siwe/verify", {
        method: "POST",
        headers: {
          cookie: `${NONCE_COOKIE}=${fields.nonce}`,
          "content-type": "application/json",
        },
        body: JSON.stringify({ message, signature }),
      }),
    );
    expect(verifyRes.status).toBe(200);
    const body = (await verifyRes.json()) as { principal: string; source: string };
    expect(body.principal).toBe(OWNER);
    expect(body.source).toBe("siwe");
    expect(ACCOUNT.address).not.toBe(OWNER);
    expect(setCookieHasHttpOnly(verifyRes, "aimmune_principal")).toBe(true);
    const session = cookieFrom(verifyRes, "aimmune_principal");
    expect(session?.startsWith("v2.")).toBe(true);
    const minted = readSiweSession(session);
    expect(minted?.exp).toBeGreaterThan(Math.floor(Date.now() / 1000));
    const resolved = resolvePrincipal({ cookie: session, tokenOk: true });
    expect(resolved).toEqual({ principal: OWNER, source: "siwe" });
  });

  it("rejects a reused nonce", async () => {
    const { fields, message, signature } = await signedMessage();
    const first = await verifySiweLogin({
      message,
      signature,
      cookieNonce: fields.nonce,
    });
    expect(first.ok).toBe(true);
    const second = await verifySiweLogin({
      message,
      signature,
      cookieNonce: fields.nonce,
    });
    expect(second).toEqual({ ok: false, status: 401, error: "siwe nonce already used" });
  });

  it("returns 401 on a bad signature", async () => {
    const { fields, message } = await signedMessage();
    const signature = await ACCOUNT.signMessage({ message: "not the siwe message" });
    const result = await verifySiweLogin({
      message,
      signature,
      cookieNonce: fields.nonce,
    });
    expect(result).toEqual({ ok: false, status: 401, error: "unauthorized" });
  });

  it("keeps smoke paste off the siwe source and working in non-prod", async () => {
    const response = await postSession(
      new Request("http://127.0.0.1:3000/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          token: "test-token",
          principal: "0xAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        }),
      }),
    );
    expect(response.status).toBe(200);
    const cookie = cookieFrom(response, "aimmune_principal");
    expect(cookie).toBe("0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa");
    expect(resolvePrincipal({ cookie, tokenOk: true }).source).toBe("smoke");
  });

  it("fails closed for paste-principal in production", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL", "");
    const response = await postSession(
      new Request("http://127.0.0.1:3000/api/session", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ principal: OWNER }),
      }),
    );
    expect(response.status).toBe(403);
  });

  it("feeds a verified SIWE address to unchanged MockCheck / requireIrAct consumers", () => {
    const cookie = signSiweSession(ACCOUNT.address);
    const { principal, source } = resolvePrincipal({ cookie, tokenOk: true });
    expect(source).toBe("siwe");
    expect(principal).toBe(OWNER);
    const acl = new MockCheck();
    acl.putObject(`site:${SITE}`, OWNER);
    acl.putObject(irObject(SITE), OWNER);
    expect(checkIrAct(acl, SITE, principal, "resolve", 1_778_000_000, [OWNER]).allowed).toBe(
      true,
    );
    expect(checkIrAct(acl, SITE, principal, "annotate", 1_778_000_000, [OWNER]).allowed).toBe(
      true,
    );
  });

  it("denies an expired v2 cookie (logged out, not SIWE)", () => {
    vi.stubEnv("AIMMUNE_SIWE_TTL_S", "60");
    const cookie = signSiweSession(ACCOUNT.address, "test-token", 1_700_000_000);
    expect(cookie?.startsWith("v2.")).toBe(true);
    expect(readSiweSession(cookie, "test-token", 1_700_000_060)).toBeNull();
    expect(resolvePrincipal({ cookie, tokenOk: true }).source).toBeNull();
    expect(resolvePrincipal({ cookie, tokenOk: true }).principal).toBeNull();
  });

  it("still reads an unexpired-less v1 cookie during the upgrade", () => {
    const mac = createHmac("sha256", "test-token")
      .update(`aimmune-siwe-v1:${OWNER}`)
      .digest("hex");
    const cookie = `v1.${OWNER}.${mac}`;
    expect(resolvePrincipal({ cookie, tokenOk: true })).toEqual({
      principal: OWNER,
      source: "siwe",
    });
  });

  it("mints only v2 with default 12h TTL and keeps verify EOA-only", async () => {
    expect(siweSessionTtlS()).toBe(43_200);
    const cookie = signSiweSession(ACCOUNT.address);
    expect(cookie?.split(".")).toHaveLength(4);
    expect(cookie?.startsWith("v2.")).toBe(true);
    const { fields, message } = await signedMessage();
    const result = await verifySiweLogin({
      message,
      signature: await ACCOUNT.signMessage({ message }),
      cookieNonce: fields.nonce,
    });
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.principal).toBe(OWNER);
    }
  });

  it("DELETE /api/session clears the SIWE principal cookie", async () => {
    const response = await deleteSession();
    expect(response.status).toBe(200);
    const cleared = cookieFrom(response, "aimmune_principal");
    expect(cleared).toBe("");
  });
});
