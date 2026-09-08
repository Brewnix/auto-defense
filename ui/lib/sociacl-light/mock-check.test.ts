import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  acceptHint,
  applyDelegate,
  assertGrantNotDelegate,
  cancelDelegate,
  checkDelegate,
  checkIrAct,
  irCaps,
  irObject,
  isSiteObjectId,
  mapAction,
  MockCheck,
  PRIVILEGE_GRANT_SCHEMA,
  remintCapability,
  undelegate,
  validateMintAsks,
} from "./index";

const SITE = "net-tn-cottage";
const IR = irObject(SITE);
const STANDING = `site:${SITE}` as const;
const OWNER = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
const DELEGATE = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";
const STRANGER = "0xcccccccccccccccccccccccccccccccccccccccc";
const NOW = 1_778_000_000;

function cottageAcl(): MockCheck {
  const acl = new MockCheck();
  acl.putObject(STANDING, OWNER);
  acl.putObject(IR, OWNER);
  return acl;
}

describe("consume contract names", () => {
  it("maps see → read and keeps dest masks", () => {
    expect(mapAction("see")).toBe("read");
    expect(mapAction("read")).toBe("read");
    expect(mapAction("write")).toBe("write");
    expect(mapAction("execute")).toBe("execute");
  });

  it("accepts only site:{id} and site:{id}:ir", () => {
    expect(isSiteObjectId(STANDING)).toBe(true);
    expect(isSiteObjectId(IR)).toBe(true);
    expect(isSiteObjectId(`site:${SITE}:host`)).toBe(false);
    expect(isSiteObjectId(`site:${SITE}:incident:abc`)).toBe(false);
    expect(isSiteObjectId("site:")).toBe(false);
  });

  it("acceptHint never sets allowed", () => {
    const hint = acceptHint({
      principal: DELEGATE,
      target: IR,
      verb: "execute",
    });
    expect(hint.principal).toBe(DELEGATE);
    expect(hint).not.toHaveProperty("allowed");
    const acl = cottageAcl();
    const denied = checkDelegate(acl, IR, STRANGER, "execute", NOW, hint);
    expect(denied.allowed).toBe(false);
    expect(denied.reason).not.toMatch(/hint/);
  });
});

describe("binding 1 — execute for resolve/mint; owner gate for break_glass", () => {
  it("owner execute on :ir can resolve and mint", () => {
    const acl = cottageAcl();
    expect(checkIrAct(acl, SITE, OWNER, "resolve", NOW, [OWNER]).allowed).toBe(true);
    expect(checkIrAct(acl, SITE, OWNER, "mint", NOW, [OWNER]).allowed).toBe(true);
    expect(checkIrAct(acl, SITE, OWNER, "break_glass", NOW, [OWNER]).allowed).toBe(
      true,
    );
  });

  it("delegated execute can resolve/mint but cannot break_glass", () => {
    const acl = cottageAcl();
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "execute" });
    expect(checkIrAct(acl, SITE, DELEGATE, "resolve", NOW, [OWNER]).allowed).toBe(
      true,
    );
    expect(checkIrAct(acl, SITE, DELEGATE, "mint", NOW, [OWNER]).allowed).toBe(true);
    const glass = checkIrAct(acl, SITE, DELEGATE, "break_glass", NOW, [OWNER]);
    expect(glass.allowed).toBe(false);
    expect(glass.reason).toMatch(/AIMMUNE_OWNER_PRINCIPALS/);
  });
});

describe("binding 2 — write ≠ resolve / mint", () => {
  it("write-only may annotate and must not resolve or mint", () => {
    const acl = cottageAcl();
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "write" });
    expect(checkIrAct(acl, SITE, DELEGATE, "annotate", NOW, [OWNER]).allowed).toBe(
      true,
    );
    expect(checkIrAct(acl, SITE, DELEGATE, "resolve", NOW, [OWNER]).allowed).toBe(
      false,
    );
    expect(checkIrAct(acl, SITE, DELEGATE, "mint", NOW, [OWNER]).allowed).toBe(
      false,
    );
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW).allowed).toBe(false);
  });
});

describe("binding 3 — re-Check at act time", () => {
  it("a prior allow is not reused after undelegate", () => {
    const acl = cottageAcl();
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "execute" });
    const first = checkIrAct(acl, SITE, DELEGATE, "resolve", NOW, [OWNER]);
    expect(first.allowed).toBe(true);
    undelegate(acl, OWNER, DELEGATE, IR);
    const second = checkIrAct(acl, SITE, DELEGATE, "resolve", NOW, [OWNER]);
    expect(second.allowed).toBe(false);
    expect(second.reason).toBe("no live grant");
  });

  it("until is exclusive; from is inclusive", () => {
    const acl = cottageAcl();
    acl.addRow({
      principal: DELEGATE,
      object: IR,
      mask: "execute",
      from: NOW,
      until: NOW + 60,
    });
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW).allowed).toBe(true);
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW + 59).allowed).toBe(
      true,
    );
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW + 60).allowed).toBe(
      false,
    );
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW - 1).allowed).toBe(
      false,
    );
  });
});

describe("binding 4 — cancel clears; next check denies", () => {
  it("cancelDelegate deletes the row", () => {
    const acl = cottageAcl();
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "execute" });
    cancelDelegate(acl, OWNER, DELEGATE, IR);
    expect(checkDelegate(acl, IR, DELEGATE, "execute", NOW).allowed).toBe(false);
    expect(remintCapability(acl, IR, DELEGATE, "execute", NOW)).toEqual({
      denied: true,
    });
  });
});

describe("binding 5 — contain path never imports Check", () => {
  const root = path.resolve(__dirname, "../../..");

  it("Python contain / expiry / alias do not import sociacl or Check", () => {
    const files = [
      "src/aimmune/exec/opnsense_alias.py",
      "src/aimmune/rules/expiry.py",
      "src/aimmune/rules/engine.py",
      "src/aimmune/cycle.py",
      "src/aimmune/policy.py",
      "src/aimmune/ledger/ttl.py",
    ];
    for (const rel of files) {
      const text = readFileSync(path.join(root, rel), "utf8").toLowerCase();
      expect(text, rel).not.toMatch(/sociacl|checkdelegate|mockcheck/);
    }
  });

  it("this module is the only Check surface and is not imported by contain", () => {
    const cycle = readFileSync(path.join(root, "src/aimmune/cycle.py"), "utf8");
    expect(cycle).not.toContain("sociacl-light");
    expect(cycle).not.toContain("checkDelegate");
  });
});

describe("binding 6 — privilege_grant body ≠ delegate", () => {
  it("rejects a DelegateGrant shaped object as a grant body", () => {
    expect(() =>
      assertGrantNotDelegate({
        object: IR,
        accessor: DELEGATE,
        mask: "execute",
      }),
    ).toThrow(/fyber.privilege_grant\/v0/);
    expect(() =>
      assertGrantNotDelegate({
        schema: PRIVILEGE_GRANT_SCHEMA,
        mask: "execute",
        accessor: DELEGATE,
        asks: [{ kind: "tool_allowlist_add", tools: ["notify.operator"] }],
        incident_id: "inc-1",
      }),
    ).toThrow(/not a SociACL delegate/);
  });

  it("accepts a Brewnix grant body and refuses empty asks", () => {
    const body = assertGrantNotDelegate({
      schema: PRIVILEGE_GRANT_SCHEMA,
      grant_id: "g1",
      site_id: SITE,
      incident_id: "inc-1",
      asks: [{ kind: "tool_allowlist_add", tools: ["notify.operator"] }],
    });
    expect(body.schema).toBe(PRIVILEGE_GRANT_SCHEMA);
    expect(body).not.toHaveProperty("mask");
    expect(() => validateMintAsks([])).toThrow(/ticket/);
  });
});

describe("hopcap 1 / remint stub / see", () => {
  it("delegate cannot applyDelegate (owner-only, hopcap 1)", () => {
    const acl = cottageAcl();
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "execute" });
    expect(() =>
      applyDelegate(acl, DELEGATE, {
        object: IR,
        accessor: STRANGER,
        mask: "read",
      }),
    ).toThrow(/owner-only/);
  });

  it("remint refreshes only while Check still allows", () => {
    const acl = cottageAcl();
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "read" });
    expect(remintCapability(acl, IR, DELEGATE, "see", NOW)).toEqual({
      refreshed: true,
    });
    expect(checkDelegate(acl, IR, DELEGATE, "see", NOW).allowed).toBe(true);
  });

  it("unknown object and :host fail closed", () => {
    const acl = cottageAcl();
    expect(checkDelegate(acl, "site:other:ir", OWNER, "execute", NOW).allowed).toBe(
      false,
    );
    expect(isSiteObjectId(`site:${SITE}:host`)).toBe(false);
  });

  it("irCaps expose see/read for redacted view", () => {
    const acl = cottageAcl();
    applyDelegate(acl, OWNER, { object: IR, accessor: DELEGATE, mask: "read" });
    const caps = irCaps(acl, SITE, DELEGATE, NOW, [OWNER]);
    expect(caps.read).toBe(true);
    expect(caps.write).toBe(false);
    expect(caps.execute).toBe(false);
  });
});
