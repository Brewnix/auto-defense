import { afterEach, describe, expect, it, vi } from "vitest";

import {
  bearerFromHeader,
  isBlockedStatus,
  resolvePrincipal,
  tokensEqual,
} from "./auth";
import { statusBadgeVariant } from "@/components/status-badge";
import { signSiweSession } from "@/lib/siwe/session";

const MIXED = "0xBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB";
const LOWER = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("status copy guards", () => {
  it("never treats resolve-like statuses as blocked", () => {
    for (const status of [
      "pending_intent",
      "waiting_on_plane",
      "timed_out_waiting",
      "approved_pending_apply",
      "applied_pending_ack",
      "observed",
    ]) {
      expect(isBlockedStatus(status)).toBe(false);
      expect(statusBadgeVariant(status)).not.toBe("destructive");
    }
  });

  it("blocked is only the explicit enum", () => {
    expect(isBlockedStatus("blocked")).toBe(true);
    expect(isBlockedStatus("approved")).toBe(false);
    expect(isBlockedStatus("resolved")).toBe(false);
  });
});

describe("bearer token", () => {
  it("parses Authorization headers", () => {
    expect(bearerFromHeader("Bearer secret")).toBe("secret");
    expect(bearerFromHeader("Basic x")).toBeNull();
    expect(bearerFromHeader(null)).toBeNull();
  });

  it("compares tokens", () => {
    expect(tokensEqual("abc", "abc")).toBe(true);
    expect(tokensEqual("abc", "abd")).toBe(false);
    expect(tokensEqual("", "abc")).toBe(false);
    expect(tokensEqual(null, "abc")).toBe(false);
  });
});

describe("dual principal", () => {
  it("labels a verified SIWE cookie as siwe and normalizes 0x", () => {
    vi.stubEnv("AIMMUNE_UI_TOKEN", "test-token");
    const cookie = signSiweSession(MIXED);
    expect(cookie).toBeTruthy();
    const { principal, source } = resolvePrincipal({
      cookie,
      header: null,
      tokenOk: true,
    });
    expect(principal).toBe(LOWER);
    expect(source).toBe("siwe");
  });

  it("treats unsigned paste as smoke, never siwe", () => {
    const { principal, source } = resolvePrincipal({
      cookie: MIXED,
      header: null,
      tokenOk: true,
    });
    expect(principal).toBe(LOWER);
    expect(source).toBe("smoke");
  });

  it("does not let paste-principal claim siwe in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("AIMMUNE_UI_TOKEN", "prod-token");
    vi.stubEnv("AIMMUNE_UI_ALLOW_SMOKE_PRINCIPAL", "");
    const { principal, source } = resolvePrincipal({
      cookie: MIXED,
      header: MIXED,
      tokenOk: true,
    });
    expect(principal).toBeNull();
    expect(source).toBeNull();
  });
});
