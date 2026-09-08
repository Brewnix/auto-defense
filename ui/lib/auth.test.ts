import { describe, expect, it } from "vitest";

import {
  bearerFromHeader,
  isBlockedStatus,
  tokensEqual,
} from "./auth";
import { statusBadgeVariant } from "@/components/status-badge";

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
