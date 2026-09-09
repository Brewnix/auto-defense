import { mkdtempSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { applyDelegate, cancelDelegate, checkDelegate, checkIrAct } from "./index";
import { irObject } from "./objects";
import {
  buildAclFromEnv,
  getProcessAcl,
  ownerUndelegateGrant,
  resetProcessAcl,
} from "./store";

const SITE = "net-tn-cottage";
const IR = irObject(SITE);
const OWNER = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const DELEGATE = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const NOW = 1_778_000_000;

function tempStateDir(): string {
  return mkdtempSync(path.join(tmpdir(), "aimmune-sociacl-"));
}

afterEach(() => {
  resetProcessAcl();
  vi.unstubAllEnvs();
});

describe("MockCheck durable store", () => {
  it("persists grants to sociacl-mock.json and reloads them", () => {
    const stateDir = tempStateDir();
    vi.stubEnv("AIMMUNE_STATE_DIR", stateDir);
    vi.stubEnv("AIMMUNE_OWNER_PRINCIPALS", OWNER);
    vi.stubEnv("SITE_ID", SITE);

    const acl = getProcessAcl(SITE);
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "execute" });
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW).allowed).toBe(true);

    const storePath = path.join(stateDir, "sociacl-mock.json");
    const mode = statSync(storePath).mode & 0o777;
    expect(mode).toBe(0o600);
    const stored = JSON.parse(readFileSync(storePath, "utf8")) as {
      grants: Array<{ principal: string }>;
    };
    expect(stored.grants.some((row) => row.principal === DELEGATE)).toBe(true);

    resetProcessAcl();
    const reloaded = getProcessAcl(SITE);
    expect(checkDelegate(reloaded, IR, DELEGATE, "execute", NOW).allowed).toBe(true);
    expect(checkIrAct(reloaded, SITE, DELEGATE, "resolve", NOW, [OWNER]).allowed).toBe(
      true,
    );
  });

  it("does not wipe a populated store with AIMMUNE_SOCIACL_FIXTURE on restart", () => {
    const stateDir = tempStateDir();
    const fixturePath = path.join(stateDir, "fixture.json");
    writeFileSync(
      path.join(stateDir, "sociacl-mock.json"),
      JSON.stringify({
        objects: [{ object: IR, owner: OWNER }],
        grants: [{ principal: DELEGATE, object: IR, mask: "execute" }],
      }),
    );
    writeFileSync(
      fixturePath,
      JSON.stringify({
        objects: [{ object: IR, owner: OWNER }],
        grants: [
          {
            principal: "0xcccccccccccccccccccccccccccccccccccccccc",
            object: IR,
            mask: "write",
          },
        ],
      }),
    );
    vi.stubEnv("AIMMUNE_STATE_DIR", stateDir);
    vi.stubEnv("AIMMUNE_SOCIACL_FIXTURE", fixturePath);
    vi.stubEnv("AIMMUNE_OWNER_PRINCIPALS", OWNER);

    const acl = getProcessAcl(SITE);
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW).allowed).toBe(true);
    expect(
      checkDelegate(acl, IR, "0xcccccccccccccccccccccccccccccccccccccccc", "write", NOW)
        .allowed,
    ).toBe(false);
  });

  it("seeds the fixture only when the store is empty or missing", () => {
    const stateDir = tempStateDir();
    const fixturePath = path.join(stateDir, "fixture.json");
    writeFileSync(
      fixturePath,
      JSON.stringify({
        objects: [{ object: IR, owner: OWNER }],
        grants: [{ principal: DELEGATE, object: IR, mask: "write" }],
      }),
    );
    vi.stubEnv("AIMMUNE_STATE_DIR", stateDir);
    vi.stubEnv("AIMMUNE_SOCIACL_FIXTURE", fixturePath);

    const acl = buildAclFromEnv(SITE);
    expect(checkDelegate(acl, IR, DELEGATE, "write", NOW).allowed).toBe(true);
  });

  it("cancel / undelegate persists and the next Check denies", () => {
    const stateDir = tempStateDir();
    vi.stubEnv("AIMMUNE_STATE_DIR", stateDir);
    vi.stubEnv("AIMMUNE_OWNER_PRINCIPALS", OWNER);

    const acl = getProcessAcl(SITE);
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "execute" });
    cancelDelegate(acl, OWNER, DELEGATE, IR);
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW).allowed).toBe(false);

    resetProcessAcl();
    const reloaded = getProcessAcl(SITE);
    expect(checkDelegate(reloaded, IR, DELEGATE, "execute", NOW).allowed).toBe(false);
    expect(checkIrAct(reloaded, SITE, DELEGATE, "resolve", NOW, [OWNER]).allowed).toBe(
      false,
    );
  });

  it("ownerUndelegateGrant is owner-only and Check-denies after", () => {
    const stateDir = tempStateDir();
    vi.stubEnv("AIMMUNE_STATE_DIR", stateDir);
    vi.stubEnv("AIMMUNE_OWNER_PRINCIPALS", OWNER);

    const acl = getProcessAcl(SITE);
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "execute" });
    expect(
      ownerUndelegateGrant({
        principal: DELEGATE,
        accessor: DELEGATE,
        object: IR,
        siteId: SITE,
      }).ok,
    ).toBe(false);
    expect(
      ownerUndelegateGrant({
        principal: OWNER,
        accessor: DELEGATE,
        object: IR,
        siteId: SITE,
      }),
    ).toEqual({ ok: true });
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW).allowed).toBe(false);
  });
});
