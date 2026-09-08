export type StatusView = {
  status: string;
  label: string;
  blocked: boolean;
  can_local_resolve?: boolean;
};

export type ReceiptRow = {
  receipt_id: string;
  parent_id: string | null;
  site_id?: string;
  ts?: string;
  purpose?: string;
  posture?: Record<string, unknown>;
  policy?: { decision?: string; rule_ids?: string[] };
  human?: {
    required?: boolean;
    resolution?: string | null;
    resolved_by?: string | null;
    resolved_at?: string | null;
  };
  tools?: string[];
  effects?: Array<{
    tool?: string;
    status?: string;
    executor?: string;
    effect?: Record<string, unknown>;
    error?: string | null;
  }>;
  input?: { features_digest?: string; window_s?: number; sources?: string[] };
  display?: StatusView;
};

export type HoldRow = StatusView & {
  receipt_id: string;
  ticket_id?: string | null;
  incident_id?: string | null;
  queued_at?: string | null;
  drained?: boolean;
  watch_status?: string | null;
  resolution?: string | null;
  apply_receipt_id?: string | null;
  held?: {
    tool?: string;
    subject?: { kind?: string; value?: string };
    reason_code?: string;
  } | null;
};

export type IncidentRow = {
  incident_id?: string;
  status?: string;
  severity?: string;
  summary_redacted?: string;
  opened_at?: string;
  primary_subjects?: Array<{ kind?: string; value?: string }>;
};

export type PreemptQueueRow = {
  queue_id?: string;
  queued_at?: string;
  device_id?: string;
  reason_code?: string;
  tools?: string[];
  done?: boolean;
};

export type Snapshot = {
  site_id: string;
  plane_reachable: boolean;
  sell_state: {
    value: string;
    stale: boolean;
    source: string | null;
    ts: string | null;
    receipt_id: string | null;
  };
  status_catalog: StatusView[];
  receipts: ReceiptRow[];
  holds: HoldRow[];
  incidents: IncidentRow[];
  preempt: {
    queue: PreemptQueueRow[];
    receipts: ReceiptRow[];
  };
};
