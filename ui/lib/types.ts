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
  actor?: { kind?: string; id?: string; purpose?: string };
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

export type IncidentSubject = {
  kind?: string;
  value?: string;
  node?: string;
  unit?: string;
};

export type IncidentRow = {
  schema?: string;
  incident_id?: string;
  site_id?: string;
  kind?: string;
  status?: string;
  opened_at?: string;
  opened_by?: { kind?: string; id?: string };
  severity?: string;
  summary_redacted?: string;
  primary_subjects?: IncidentSubject[];
  closed_at?: string | null;
  close_reason?: string | null;
  flags?: { contain_applied?: boolean; grant_active?: boolean };
  links?: { opening_trace_id?: string; opening_receipt_id?: string | null };
  index?: {
    receipt_ids?: string[];
    ticket_ids?: string[];
    grant_ids?: string[];
    receipt_count?: number;
    ticket_count?: number;
    grant_count?: number;
  };
  can_close?: boolean;
  grant_active?: boolean;
};

export type PreemptQueueRow = {
  queue_id?: string;
  queued_at?: string;
  device_id?: string;
  reason_code?: string;
  tools?: string[];
  done?: boolean;
};

export type GrantAsk = {
  kind?: string;
  tools?: string[];
  metric?: string;
  limit?: number;
  tier?: string;
  max_tokens?: number;
  template_ids?: string[];
};

export type GrantRow = {
  schema?: string;
  grant_id?: string;
  incident_id?: string;
  site_id?: string;
  status?: string;
  rails_profile_requested?: string | null;
  rails_profile?: string | null;
  ttl_s_requested?: number | null;
  ttl_s?: number | null;
  active_until?: string | null;
  ticket_id?: string | null;
  trace_id?: string | null;
  requested_at?: string;
  requested_by?: { kind?: string; id?: string };
  reason_redacted?: string;
  asks?: GrantAsk[];
  notes_redacted?: string;
  resolved_by?: string;
  resolved_at?: string;
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
  grants: GrantRow[];
};
