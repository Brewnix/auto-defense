/**
 * In-memory MockCheck. Rows: principal, object, mask, from?, until?, owner?.
 * Owner → allow. Else a live grant with now ∈ [from, until).
 * cancel / undelegate deletes the row — next check denies.
 * hopcap 1: no friend-edge walk.
 */

import type {
  AccessorId,
  ActionMask,
  DelegateAcl,
  DelegateGrant,
  MockCheckRow,
  SiteObjectId,
} from "./types";
import { isSiteObjectId } from "./check";

type StoredGrant = DelegateGrant & { from?: number };

export class MockCheck implements DelegateAcl {
  private owners = new Map<SiteObjectId, AccessorId>();
  private grants: StoredGrant[] = [];

  constructor(rows: readonly MockCheckRow[] = []) {
    for (const row of rows) {
      this.addRow(row);
    }
  }

  addRow(row: MockCheckRow): void {
    if (!isSiteObjectId(row.object)) {
      throw new Error(`MockCheck refuses ${row.object} (:host / :incident: fail closed)`);
    }
    if (row.owner) {
      this.owners.set(row.object, row.owner);
    }
    if (row.principal && row.mask) {
      this.grants.push({
        object: row.object,
        accessor: row.principal,
        mask: row.mask,
        ...(row.until !== undefined ? { until: row.until } : {}),
        ...(row.from !== undefined ? { from: row.from } : {}),
      });
    }
  }

  hasObject(object: SiteObjectId): boolean {
    return this.owners.has(object);
  }

  ownerOf(object: SiteObjectId): AccessorId | undefined {
    return this.owners.get(object);
  }

  delegateGrants(object: SiteObjectId): readonly DelegateGrant[] {
    return this.grants
      .filter((row) => row.object === object)
      .map((row) => {
        const grant: DelegateGrant = {
          object: row.object,
          accessor: row.accessor,
          mask: row.mask,
        };
        if (row.until !== undefined) {
          grant.until = row.until;
        }
        return grant;
      });
  }

  /** Live grants including MockCheck `from` (inclusive). */
  liveGrants(object: SiteObjectId, now: number): readonly StoredGrant[] {
    return this.grants.filter((row) => {
      if (row.object !== object) {
        return false;
      }
      if (row.from !== undefined && now < row.from) {
        return false;
      }
      if (row.until !== undefined && !(now < row.until)) {
        return false;
      }
      return true;
    });
  }

  putObject(object: SiteObjectId, owner: AccessorId): void {
    if (!isSiteObjectId(object)) {
      throw new Error("putObject: :host / :incident: fail closed");
    }
    this.owners.set(object, owner);
  }

  stateDelegateGrant(owner: AccessorId, grant: DelegateGrant): void {
    if (this.ownerOf(grant.object) !== owner) {
      throw new Error("stateDelegateGrant is owner-only");
    }
    this.grants.push({ ...grant });
  }

  unstateDelegateGrant(
    owner: AccessorId,
    accessor: AccessorId,
    object: SiteObjectId,
  ): void {
    if (this.ownerOf(object) !== owner) {
      throw new Error("unstateDelegateGrant is owner-only");
    }
    this.grants = this.grants.filter(
      (row) => !(row.accessor === accessor && row.object === object),
    );
  }

  rows(): MockCheckRow[] {
    const out: MockCheckRow[] = [];
    for (const [object, owner] of this.owners) {
      out.push({
        principal: owner,
        object,
        mask: "execute",
        owner,
      });
    }
    for (const grant of this.grants) {
      out.push({
        principal: grant.accessor,
        object: grant.object,
        mask: grant.mask,
        ...(grant.from !== undefined ? { from: grant.from } : {}),
        ...(grant.until !== undefined ? { until: grant.until } : {}),
      });
    }
    return out;
  }
}

/** checkDelegate against MockCheck, honoring optional inclusive `from`. */
export function mockLiveMask(
  acl: MockCheck,
  object: SiteObjectId,
  accessor: AccessorId,
  mask: ActionMask,
  now: number,
): boolean {
  if (acl.ownerOf(object) === accessor) {
    return true;
  }
  return acl
    .liveGrants(object, now)
    .some((row) => row.accessor === accessor && row.mask === mask);
}
