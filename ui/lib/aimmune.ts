import { spawn } from "node:child_process";
import path from "node:path";

import { configuredStateDir } from "@/lib/state-dir";
import type { Snapshot } from "@/lib/types";

function repoRoot(): string {
  if (process.env.AIMMUNE_REPO_ROOT) {
    return path.resolve(process.env.AIMMUNE_REPO_ROOT);
  }
  return path.resolve(process.cwd(), "..");
}

export function runAimmune(
  args: string[],
): Promise<{ code: number; stdout: string; stderr: string }> {
  const python = process.env.AIMMUNE_PYTHON || "python3";
  const root = repoRoot();
  const extra: string[] = [];
  const stateDir = configuredStateDir();
  if (stateDir) {
    extra.push("--state-dir", stateDir);
  }
  const env = { ...process.env };
  const src = path.join(root, "src");
  env.PYTHONPATH = env.PYTHONPATH ? `${src}${path.delimiter}${env.PYTHONPATH}` : src;
  return new Promise((resolve, reject) => {
    const proc = spawn(python, ["-m", "aimmune", ...args, ...extra], {
      env,
      cwd: root,
    });
    let stdout = "";
    let stderr = "";
    proc.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    proc.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    proc.on("error", reject);
    proc.on("close", (code) => {
      resolve({ code: code ?? 1, stdout, stderr });
    });
  });
}

export async function loadSnapshot(limit = 50): Promise<Snapshot> {
  const result = await runAimmune(["ui-snapshot", "--limit", String(limit)]);
  if (result.code !== 0) {
    throw new Error(result.stderr.trim() || "aimmune ui-snapshot failed");
  }
  return JSON.parse(result.stdout) as Snapshot;
}

export async function closeIncident(
  incidentId: string,
): Promise<{ code: number; stdout: string; stderr: string }> {
  return runAimmune(["incident", "close", "--id", incidentId]);
}

export async function grantPropose(body: {
  incident_id: string;
  profile: string;
  ttl: number;
  reason: string;
  tools?: string[];
  ticket_id?: string;
  notes?: string;
  action?: "propose" | "mint-local";
}): Promise<{ code: number; stdout: string; stderr: string }> {
  const action = body.action || "propose";
  const args = [
    "grant",
    action,
    "--incident-id",
    body.incident_id,
    "--profile",
    body.profile,
    "--ttl",
    String(body.ttl),
    "--reason",
    body.reason,
  ];
  for (const tool of body.tools || []) {
    if (tool.trim()) {
      args.push("--tool", tool.trim());
    }
  }
  if (body.ticket_id?.trim()) {
    args.push("--ticket-id", body.ticket_id.trim());
  }
  if (action === "mint-local") {
    args.push("--notes", (body.notes || "").trim() || "ui local mint");
  }
  return runAimmune(args);
}

export async function ownerResolve(
  receiptId: string,
  action: "approve" | "deny",
  note?: string,
): Promise<{ code: number; stdout: string; stderr: string }> {
  const args = ["owner", action, "--receipt-id", receiptId];
  if (note?.trim()) {
    args.push("--note", note.trim().slice(0, 500));
  }
  return runAimmune(args);
}

export async function ownerAnnotate(
  receiptId: string,
  note: string,
): Promise<{ code: number; stdout: string; stderr: string }> {
  return runAimmune([
    "owner",
    "annotate",
    "--receipt-id",
    receiptId,
    "--note",
    note.trim().slice(0, 500),
  ]);
}
