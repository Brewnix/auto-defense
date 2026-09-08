import { describe, expect, it } from "vitest";

import { formatSubject } from "./incident";

describe("formatSubject", () => {
  it("formats ip, node_unit, and health_class", () => {
    expect(formatSubject({ kind: "ip", value: "203.0.113.50" })).toBe(
      "ip:203.0.113.50",
    );
    expect(
      formatSubject({ kind: "node_unit", node: "opnsense-cottage", unit: "suricata" }),
    ).toBe("node_unit:opnsense-cottage/suricata");
    expect(formatSubject({ kind: "health_class", value: "health_disk" })).toBe(
      "health_class:health_disk",
    );
  });
});
