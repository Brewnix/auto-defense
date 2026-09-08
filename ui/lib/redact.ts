import type { HoldRow, IncidentRow, ReceiptRow, Snapshot } from "@/lib/types";

export function redactHold(hold: HoldRow): HoldRow {
  return {
    ...hold,
    held: hold.held
      ? { tool: hold.held.tool, reason_code: hold.held.reason_code }
      : null,
  };
}

export function redactReceipt(row: ReceiptRow): ReceiptRow {
  return {
    receipt_id: row.receipt_id,
    parent_id: row.parent_id,
    purpose: row.purpose,
    display: row.display,
    actor: row.actor ? { kind: row.actor.kind } : undefined,
  };
}

export function redactIncident(row: IncidentRow): IncidentRow {
  return {
    incident_id: row.incident_id,
    kind: row.kind,
    status: row.status,
    can_close: false,
    grant_active: row.grant_active,
  };
}

export function redactSnapshot(snap: Snapshot): Snapshot {
  return {
    ...snap,
    receipts: snap.receipts.map(redactReceipt),
    holds: snap.holds.map(redactHold),
    incidents: snap.incidents.map(redactIncident),
    preempt: {
      queue: [],
      receipts: snap.preempt.receipts.map(redactReceipt),
    },
  };
}
