/**
 * Light Check consume contract for AImmune / Brewnix IR site console.
 *
 * Re-typed from FyberLabs/SociACL master docs/aimmune-ir-check.d.ts
 * (https://github.com/FyberLabs/SociACL/blob/master/docs/aimmune-ir-check.d.ts).
 * Landed via PR #14. Copy / re-type — do not `npm install sociacl`.
 * No Rust / NAPI / WASM on the Next light path.
 *
 * Binding (objects + masks, do not fork):
 *   Brewnix/inference-iface docs/sociacl-ir-binding-v0.md
 * Primitives: SociACL PR #11 (delegate), PR #13 / docs/s3rch-check.d.ts
 * (light see), docs/verbs.md.
 *
 * CHECK(action, object, accessor) at now.
 *   object   = site:{site_id} | site:{site_id}:ir
 *   accessor = human / agent id (not a site-token type)
 *   action   = read | write | execute; see maps to read
 *   hopcap 1, jointly stated grants, revoke immediate
 *
 * break_glass is a Brewnix owner gate, not a SociACL verb.
 * privilege_grant body is Brewnix; SociACL authorizes minting.
 * contain never calls Check.
 * write without execute is annotate-only.
 * :host is later (when Host exists). Do not mint per-incident
 * ACL objects. No owner-console type. No site-token type.
 */

/**
 * Standing site object or IR keep-operating object.
 * site_id is the envelope / grant / auditor scope token.
 * :host is later — not this cut. Do not invent
 * site:{site_id}:incident:{incident_id}.
 */
export type SiteObjectId = `site:${string}` | `site:${string}:ir`;

/** Human or agent. Not a machine site-token type. */
export type AccessorId = string;

/**
 * Same shape as docs/s3rch-check.d.ts CheckResult.
 * A present hint never makes this a grant.
 */
export type CheckResult = {
  allowed: boolean;
  /** Predicate / deny reason. A present hint never makes this a grant. */
  reason: string;
};

/**
 * Untrusted edge handoff (auditor URL / hop / ingest).
 * Same shape as docs/s3rch-check.d.ts HandoffHint.
 * Decode does not verify. A hint never sets allowed.
 */
export type HandoffHint = {
  principal: string;
  target: string;
  verb?: string;
  context?: string;
};

/** dest Check action bits. see maps to read (alias). */
export type ActionMask = "read" | "write" | "execute";

/**
 * Jointly stated keep-operating grant. hopcap 1.
 * Privilege-down is immediate. Owner stays owner.
 * `until` exclusive unix seconds. Omit = open.
 */
export type DelegateGrant = {
  object: SiteObjectId;
  accessor: AccessorId;
  mask: ActionMask;
  until?: number;
};

/**
 * Live graph the browser reads. Only in-graph site objects
 * and jointly stated delegate grants. Do not walk friend
 * edges (hopcap 1).
 */
export type DelegateGraph = {
  hasObject(object: SiteObjectId): boolean;
  ownerOf(object: SiteObjectId): AccessorId | undefined;
  delegateGrants(object: SiteObjectId): readonly DelegateGrant[];
};

/** Writable dest ACL. Cancel and apply land here, not on a URL. */
export type DelegateAcl = DelegateGraph & {
  putObject(object: SiteObjectId, owner: AccessorId): void;
  stateDelegateGrant(owner: AccessorId, grant: DelegateGrant): void;
  unstateDelegateGrant(
    owner: AccessorId,
    accessor: AccessorId,
    object: SiteObjectId,
  ): void;
};

/** In-memory MockCheck row. `from` is inclusive; `until` exclusive. */
export type MockCheckRow = {
  principal: AccessorId;
  object: SiteObjectId;
  mask: ActionMask;
  from?: number;
  until?: number;
  owner?: AccessorId;
};

/** Live grant row for Settings / ACL UI. */
export type LiveMockGrant = {
  object: SiteObjectId;
  accessor: AccessorId;
  mask: ActionMask;
  from?: number;
  until?: number;
  owner?: AccessorId;
};
