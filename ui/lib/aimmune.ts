import { spawn } from "node:child_process";
import path from "node:path";

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
  if (process.env.AIMMUNE_STATE_DIR) {
    extra.push("--state-dir", process.env.AIMMUNE_STATE_DIR);
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
