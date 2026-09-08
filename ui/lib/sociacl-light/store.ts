/**
 * Process-local MockCheck. Seeded from AIMMUNE_OWNER_PRINCIPALS and
 * optional AIMMUNE_SOCIACL_FIXTURE JSON. Not a cached allow — callers
 * must checkDelegate again at act time.
 */

import { readFileSync } from "node:fs";

import { MockCheck } from "./mock-check";
import { irObject, standingObject } from "./objects";
import { ownerPrincipalsFromEnv } from "./principal";
import type { ActionMask, MockCheckRow, SiteObjectId } from "./types";
import { isSiteObjectId } from "./check";

export type SociaclFixture = {
  objects?: Array<{ object: string; owner: string }>;
  grants?: Array<{
    principal: string;
    object: string;
    mask: ActionMask;
    from?: number;
    until?: number;
    owner?: string;
  }>;
};

let processAcl: MockCheck | null = null;

function seedOwners(acl: MockCheck, siteId: string): void {
  const owners = ownerPrincipalsFromEnv();
  if (!owners.length) {
    return;
  }
  const owner = owners[0];
  const standing = standingObject(siteId);
  const ir = irObject(siteId);
  if (!acl.hasObject(standing)) {
    acl.putObject(standing, owner);
  }
  if (!acl.hasObject(ir)) {
    acl.putObject(ir, owner);
  }
}

function loadFixtureFile(): SociaclFixture | null {
  const path = process.env.AIMMUNE_SOCIACL_FIXTURE?.trim();
  if (!path) {
    return null;
  }
  const raw = readFileSync(path, "utf8");
  return JSON.parse(raw) as SociaclFixture;
}

export function buildAclFromEnv(siteId: string, fixture?: SociaclFixture | null): MockCheck {
  const acl = new MockCheck();
  const loaded = fixture === undefined ? loadFixtureFile() : fixture;
  if (loaded?.objects) {
    for (const row of loaded.objects) {
      if (!isSiteObjectId(row.object)) {
        throw new Error(`fixture object refused: ${row.object}`);
      }
      acl.putObject(row.object as SiteObjectId, row.owner);
    }
  }
  if (loaded?.grants) {
    for (const row of loaded.grants) {
      const item: MockCheckRow = {
        principal: row.principal,
        object: row.object as SiteObjectId,
        mask: row.mask,
        ...(row.from !== undefined ? { from: row.from } : {}),
        ...(row.until !== undefined ? { until: row.until } : {}),
        ...(row.owner ? { owner: row.owner } : {}),
      };
      acl.addRow(item);
    }
  }
  seedOwners(acl, siteId);
  return acl;
}

export function getProcessAcl(siteId: string): MockCheck {
  if (!processAcl) {
    processAcl = buildAclFromEnv(siteId);
  }
  return processAcl;
}

export function resetProcessAcl(acl?: MockCheck): void {
  processAcl = acl ?? null;
}
