/**
 * Process-local MockCheck with optional durable file at
 * $AIMMUNE_STATE_DIR/sociacl-mock.json (0600).
 * AIMMUNE_SOCIACL_FIXTURE seeds only when that store is empty/missing.
 * Not a cached allow — callers must checkDelegate again at act time.
 */

import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

import { sociaclMockStorePath } from "@/lib/state-dir";

import { isSiteObjectId, undelegate } from "./check";
import { MockCheck } from "./mock-check";
import { irObject, standingObject } from "./objects";
import { normalizePrincipal, ownerPrincipalsFromEnv } from "./principal";
import type { ActionMask, AccessorId, LiveMockGrant, MockCheckRow, SiteObjectId } from "./types";

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

function fixturePopulated(data: SociaclFixture | null | undefined): boolean {
  if (!data) {
    return false;
  }
  return Boolean(data.objects?.length || data.grants?.length);
}

function loadFixtureFile(): SociaclFixture | null {
  const fixturePath = process.env.AIMMUNE_SOCIACL_FIXTURE?.trim();
  if (!fixturePath) {
    return null;
  }
  const raw = readFileSync(fixturePath, "utf8");
  return JSON.parse(raw) as SociaclFixture;
}

function loadStoreFile(): SociaclFixture | null {
  const storePath = sociaclMockStorePath();
  if (!storePath || !existsSync(storePath)) {
    return null;
  }
  const raw = readFileSync(storePath, "utf8").trim();
  if (!raw) {
    return null;
  }
  return JSON.parse(raw) as SociaclFixture;
}

function applyFixture(acl: MockCheck, loaded: SociaclFixture | null): void {
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
}

export function persistAcl(acl: MockCheck): void {
  const storePath = sociaclMockStorePath();
  if (!storePath) {
    return;
  }
  mkdirSync(path.dirname(storePath), { recursive: true, mode: 0o700 });
  writeFileSync(storePath, `${JSON.stringify(acl.exportState(), null, 2)}\n`, {
    encoding: "utf8",
    mode: 0o600,
  });
  chmodSync(storePath, 0o600);
}

function attachPersist(acl: MockCheck): MockCheck {
  acl.setOnMutate(() => persistAcl(acl));
  return acl;
}

/**
 * Build a MockCheck. When `fixture` is omitted, a populated
 * $AIMMUNE_STATE_DIR/sociacl-mock.json wins; AIMMUNE_SOCIACL_FIXTURE
 * seeds only if that store is empty or missing.
 */
export function buildAclFromEnv(siteId: string, fixture?: SociaclFixture | null): MockCheck {
  const acl = new MockCheck();
  let loaded: SociaclFixture | null;
  if (fixture !== undefined) {
    loaded = fixture;
  } else {
    const stored = loadStoreFile();
    loaded = fixturePopulated(stored) ? stored : loadFixtureFile();
  }
  applyFixture(acl, loaded);
  seedOwners(acl, siteId);
  return acl;
}

export function getProcessAcl(siteId: string): MockCheck {
  if (!processAcl) {
    processAcl = attachPersist(buildAclFromEnv(siteId));
  }
  return processAcl;
}

export function resetProcessAcl(acl?: MockCheck): void {
  if (acl) {
    processAcl = attachPersist(acl);
    return;
  }
  processAcl = null;
}

export function listLiveSiteGrants(siteId: string, now: number): LiveMockGrant[] {
  const acl = getProcessAcl(siteId);
  const objects = [standingObject(siteId), irObject(siteId)];
  const out: LiveMockGrant[] = [];
  for (const object of objects) {
    const owner = acl.ownerOf(object);
    for (const grant of acl.liveGrants(object, now)) {
      out.push({
        object: grant.object,
        accessor: grant.accessor,
        mask: grant.mask,
        ...(grant.from !== undefined ? { from: grant.from } : {}),
        ...(grant.until !== undefined ? { until: grant.until } : {}),
        ...(owner ? { owner } : {}),
      });
    }
  }
  return out;
}

export function ownerUndelegateGrant(input: {
  principal: AccessorId | null;
  accessor: string;
  object: string;
  siteId: string;
}): { ok: true } | { ok: false; status: number; error: string } {
  if (!input.principal) {
    return {
      ok: false,
      status: 403,
      error: "principal required (SIWE / cottage session)",
    };
  }
  if (!isSiteObjectId(input.object)) {
    return { ok: false, status: 400, error: "object must be site:{id} or site:{id}:ir" };
  }
  const accessor = normalizePrincipal(input.accessor);
  if (!accessor) {
    return { ok: false, status: 400, error: "accessor required" };
  }
  const acl = getProcessAcl(input.siteId);
  if (acl.ownerOf(input.object) !== input.principal) {
    return { ok: false, status: 403, error: "undelegate is owner-only" };
  }
  try {
    undelegate(acl, input.principal, accessor, input.object);
  } catch (err) {
    return {
      ok: false,
      status: 403,
      error: err instanceof Error ? err.message : "undelegate failed",
    };
  }
  return { ok: true };
}
