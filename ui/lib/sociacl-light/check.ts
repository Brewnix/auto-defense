/**
 * Light Check implementation. Names match SociACL PR #14
 * docs/aimmune-ir-check.d.ts. Hopcap 1 — do not walk friend edges.
 */

import type {
  AccessorId,
  ActionMask,
  CheckResult,
  DelegateAcl,
  DelegateGrant,
  DelegateGraph,
  HandoffHint,
  SiteObjectId,
} from "./types";

const ACTION_MASKS = new Set<ActionMask>(["read", "write", "execute"]);

/** see → read. Other masks pass through. */
export function mapAction(action: ActionMask | "see"): ActionMask {
  return action === "see" ? "read" : action;
}

/**
 * True for site:{id} and site:{id}:ir only.
 * :host and :incident: fail closed in this cut.
 */
export function isSiteObjectId(id: string): id is SiteObjectId {
  if (typeof id !== "string" || !id.startsWith("site:")) {
    return false;
  }
  if (id.includes(":incident:") || id.endsWith(":incident")) {
    return false;
  }
  if (id.includes(":host")) {
    return false;
  }
  const rest = id.slice("site:".length);
  if (!rest) {
    return false;
  }
  if (!rest.includes(":")) {
    return true;
  }
  const parts = rest.split(":");
  return parts.length === 2 && parts[0] !== "" && parts[1] === "ir";
}

/** Does not verify. Does not mint. Never sets allowed. */
export function acceptHint(hint: HandoffHint): HandoffHint {
  return {
    principal: hint.principal,
    target: hint.target,
    ...(hint.verb !== undefined ? { verb: hint.verb } : {}),
    ...(hint.context !== undefined ? { context: hint.context } : {}),
  };
}

function deny(reason: string): CheckResult {
  return { allowed: false, reason };
}

function allow(reason: string): CheckResult {
  return { allowed: true, reason };
}

type LiveGraph = DelegateGraph & {
  liveGrants?(object: SiteObjectId, now: number): readonly DelegateGrant[];
};

function grantsAt(
  graph: DelegateGraph,
  object: SiteObjectId,
  now: number,
): readonly DelegateGrant[] {
  const live = (graph as LiveGraph).liveGrants;
  if (typeof live === "function") {
    return live.call(graph, object, now);
  }
  return graph.delegateGrants(object);
}

/**
 * CHECK(action, object, accessor) at now.
 * see maps to dest read. Hint is ignored for allowed.
 * Owner of the object is allowed. Else a live DelegateGrant
 * must name this pair, include the mapped action in mask,
 * and now < until (or until omitted). Unknown / :host /
 * :incident: ids fail closed.
 */
export function checkDelegate(
  graph: DelegateGraph,
  object: SiteObjectId,
  accessor: AccessorId,
  action: ActionMask | "see",
  now: number,
  hint?: HandoffHint,
): CheckResult {
  if (hint) {
    acceptHint(hint);
  }
  if (!isSiteObjectId(object)) {
    return deny("unknown or deferred object (:host / :incident: fail closed)");
  }
  if (!graph.hasObject(object)) {
    return deny("unknown object");
  }
  const mapped = mapAction(action);
  const owner = graph.ownerOf(object);
  if (owner && owner === accessor) {
    return allow("owner");
  }
  for (const grant of grantsAt(graph, object, now)) {
    if (grant.accessor !== accessor) {
      continue;
    }
    if (grant.object !== object) {
      continue;
    }
    if (grant.mask !== mapped) {
      continue;
    }
    if (grant.until !== undefined && !(now < grant.until)) {
      continue;
    }
    return allow("delegate");
  }
  return deny("no live grant");
}

function assertOwner(acl: DelegateAcl, owner: AccessorId, object: SiteObjectId): void {
  if (!isSiteObjectId(object)) {
    throw new Error("unknown or deferred object (:host / :incident: fail closed)");
  }
  if (!acl.hasObject(object) || acl.ownerOf(object) !== owner) {
    throw new Error("apply/cancel is owner-only (hopcap 1)");
  }
}

function assertMask(mask: ActionMask | undefined): asserts mask is ActionMask {
  if (!mask || !ACTION_MASKS.has(mask)) {
    throw new Error("empty mask refused");
  }
}

/** Owner-only. hopcap 1. Empty mask refused. */
export function applyDelegate(
  acl: DelegateAcl,
  owner: AccessorId,
  grant: DelegateGrant,
): void {
  assertMask(grant.mask);
  assertOwner(acl, owner, grant.object);
  acl.stateDelegateGrant(owner, grant);
}

/** Privilege-down is immediate. Dest ACL only. Owner-only. */
export function cancelDelegate(
  acl: DelegateAcl,
  owner: AccessorId,
  accessor: AccessorId,
  object: SiteObjectId,
): void {
  assertOwner(acl, owner, object);
  acl.unstateDelegateGrant(owner, accessor, object);
}

/** Same as cancelDelegate. Privilege-down is immediate. */
export function undelegate(
  acl: DelegateAcl,
  owner: AccessorId,
  accessor: AccessorId,
  object: SiteObjectId,
): void {
  cancelDelegate(acl, owner, accessor, object);
}

/**
 * Refresh only if checkDelegate still allows the same action
 * on the same object for this accessor at now. Owner stays
 * owner. Not a mint of a new grant. Signature only on this
 * light path.
 */
export function remintCapability(
  graph: DelegateGraph,
  object: SiteObjectId,
  accessor: AccessorId,
  action: ActionMask | "see",
  now: number,
): { refreshed: true } | { denied: true } {
  const result = checkDelegate(graph, object, accessor, action, now);
  return result.allowed ? { refreshed: true } : { denied: true };
}
