/**
 * fyber.privilege_grant/v0 body — Brewnix, not a SociACL delegate.
 * SociACL Check authorizes minting. The stored object is not a
 * DelegateGrant and does not by itself allow ticket resolve.
 */

export const PRIVILEGE_GRANT_SCHEMA = "fyber.privilege_grant/v0";

export type PrivilegeAsk =
  | { kind: "tool_allowlist_add"; tools: string[] }
  | { kind: "rate_limit_raise"; metric: "blocks_per_hour"; limit: number }
  | { kind: "budget_tokens"; max_tokens: number }
  | {
      kind: "model_tier";
      tier: "local_small" | "local_large" | "plane_ir" | "host_leased";
    }
  | { kind: "prompt_route"; template_ids: string[] };

export type PrivilegeGrantBody = {
  schema: typeof PRIVILEGE_GRANT_SCHEMA;
  grant_id: string;
  site_id: string;
  incident_id: string;
  trace_id: string;
  requested_at: string;
  requested_by: { kind: "human"; id: string };
  reason_redacted: string;
  asks: PrivilegeAsk[];
  rails_profile_requested: "strict" | "ir_elevated" | "break_glass" | null;
  ttl_s_requested: number;
  blast_radius: "site";
  status: "proposed" | "approved" | "denied";
  resolution: {
    resolved_by: string;
    resolved_at: string;
    ttl_s: number;
    rails_profile: "ir_elevated" | "break_glass";
    notes_redacted?: string;
  } | null;
  active_until: string | null;
  parent_grant_id: null;
  ticket_id: string | null;
};

const ASK_KINDS = new Set([
  "tool_allowlist_add",
  "rate_limit_raise",
  "budget_tokens",
  "model_tier",
  "prompt_route",
]);

export class GrantBodyError extends Error {}

export function assertGrantNotDelegate(body: unknown): PrivilegeGrantBody {
  if (!body || typeof body !== "object") {
    throw new GrantBodyError("grant body required");
  }
  const rec = body as Record<string, unknown>;
  if (rec.schema !== PRIVILEGE_GRANT_SCHEMA) {
    throw new GrantBodyError("schema must be fyber.privilege_grant/v0");
  }
  if ("mask" in rec || "accessor" in rec) {
    throw new GrantBodyError("privilege_grant body is not a SociACL delegate");
  }
  if (!rec.asks || !rec.incident_id) {
    throw new GrantBodyError("fyber.privilege_grant/v0 requires asks and incident_id");
  }
  return rec as PrivilegeGrantBody;
}

export function validateMintAsks(asks: unknown): PrivilegeAsk[] {
  if (!Array.isArray(asks) || asks.length === 0) {
    throw new GrantBodyError("asks: [] refused — use a ticket for one-shot approve");
  }
  const seen = new Set<string>();
  const out: PrivilegeAsk[] = [];
  for (const ask of asks) {
    if (!ask || typeof ask !== "object" || !("kind" in ask)) {
      throw new GrantBodyError("invalid ask");
    }
    const kind = String((ask as { kind: string }).kind);
    if (!ASK_KINDS.has(kind)) {
      throw new GrantBodyError(`unknown ask kind ${kind}`);
    }
    if (seen.has(kind)) {
      throw new GrantBodyError(`duplicate ask kind ${kind}`);
    }
    seen.add(kind);
    out.push(ask as PrivilegeAsk);
  }
  if (seen.has("budget_tokens") && !seen.has("model_tier")) {
    throw new GrantBodyError("budget_tokens requires sibling model_tier");
  }
  return out;
}

export function clampTtl(
  profile: "ir_elevated" | "break_glass",
  ttl: number,
): number {
  if (!Number.isFinite(ttl) || ttl <= 0) {
    throw new GrantBodyError("ttl_s_requested must be a positive int");
  }
  if (profile === "break_glass") {
    return Math.min(Math.floor(ttl), 1800);
  }
  return Math.min(Math.floor(ttl), 28800);
}
