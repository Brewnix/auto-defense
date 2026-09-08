/**
 * IR act gates. Re-Check at act time — never cache allow across
 * undelegate / until. break_glass = execute on :ir AND principal ∈ owners.
 */

import { checkDelegate } from "./check";
import { irObject } from "./objects";
import { isOwnerPrincipal } from "./principal";
import type {
  AccessorId,
  ActionMask,
  CheckResult,
  DelegateGraph,
  HandoffHint,
} from "./types";

export type IrAct = "view" | "annotate" | "resolve" | "mint" | "break_glass";

const ACT_MASK: Record<IrAct, ActionMask | "see"> = {
  view: "see",
  annotate: "write",
  resolve: "execute",
  mint: "execute",
  break_glass: "execute",
};

export function checkIrAct(
  graph: DelegateGraph,
  siteId: string,
  principal: AccessorId | null | undefined,
  act: IrAct,
  now: number,
  owners: readonly AccessorId[] = [],
  hint?: HandoffHint,
): CheckResult {
  if (!principal) {
    return { allowed: false, reason: "principal required (SIWE / cottage session)" };
  }
  let object;
  try {
    object = irObject(siteId);
  } catch (err) {
    return {
      allowed: false,
      reason: err instanceof Error ? err.message : "invalid site object",
    };
  }
  const checked = checkDelegate(
    graph,
    object,
    principal,
    ACT_MASK[act],
    now,
    hint,
  );
  if (!checked.allowed) {
    return checked;
  }
  if (act === "break_glass" && !isOwnerPrincipal(principal, owners)) {
    return {
      allowed: false,
      reason: "break_glass requires execute on :ir AND principal ∈ AIMMUNE_OWNER_PRINCIPALS",
    };
  }
  return checked;
}

export type IrCaps = {
  principal: AccessorId | null;
  siteId: string;
  object: string;
  read: boolean;
  write: boolean;
  execute: boolean;
  break_glass: boolean;
  owner: boolean;
};

export function irCaps(
  graph: DelegateGraph,
  siteId: string,
  principal: AccessorId | null,
  now: number,
  owners: readonly AccessorId[] = [],
): IrCaps {
  const object = `site:${siteId}:ir`;
  const owner = isOwnerPrincipal(principal, owners);
  if (!principal) {
    return {
      principal: null,
      siteId,
      object,
      read: false,
      write: false,
      execute: false,
      break_glass: false,
      owner: false,
    };
  }
  return {
    principal,
    siteId,
    object,
    read: checkIrAct(graph, siteId, principal, "view", now, owners).allowed,
    write: checkIrAct(graph, siteId, principal, "annotate", now, owners).allowed,
    execute: checkIrAct(graph, siteId, principal, "resolve", now, owners).allowed,
    break_glass: checkIrAct(graph, siteId, principal, "break_glass", now, owners)
      .allowed,
    owner,
  };
}
