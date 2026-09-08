import { ReceiptIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { loadSnapshot } from "@/lib/aimmune";
import { loadIrSession } from "@/lib/ir";
import { redactReceipt } from "@/lib/redact";

export const dynamic = "force-dynamic";

export default async function ReceiptsPage() {
  const session = await loadIrSession();
  let error: string | null = null;
  let snap = null;
  try {
    snap = await loadSnapshot();
  } catch (err) {
    error = err instanceof Error ? err.message : "snapshot failed";
  }
  const receipts = (snap?.receipts || []).map((row) =>
    session.caps.read ? row : redactReceipt(row),
  );

  return (
    <AppShell
      siteId={snap?.site_id}
      planeReachable={snap?.plane_reachable}
      principal={session.principal}
    >
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load receipts</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Receipts</h2>
        <p className="text-sm text-muted-foreground">
          Last N from receipts.jsonl. Digests, tools, effects, and policy only —
          prompts and EVE payloads are stripped.
        </p>
      </div>
      {!receipts.length ? (
        <EmptyState
          icon={ReceiptIcon}
          title="No receipts"
          description="Run a cycle against a state dir to populate receipts.jsonl."
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>receipt_id</TableHead>
              <TableHead>actor</TableHead>
              <TableHead>purpose</TableHead>
              <TableHead>decision</TableHead>
              <TableHead>tools</TableHead>
              <TableHead>effects</TableHead>
              <TableHead>human</TableHead>
              <TableHead>parent_id</TableHead>
              <TableHead>copy</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {receipts.map((row) => (
              <TableRow key={row.receipt_id}>
                <TableCell className="font-mono text-xs">{row.receipt_id}</TableCell>
                <TableCell className="font-mono text-xs">
                  {row.actor?.kind || "—"}
                  {row.actor?.id ? (
                    <span className="block truncate text-muted-foreground">
                      {row.actor.id}
                    </span>
                  ) : null}
                </TableCell>
                <TableCell>{row.purpose}</TableCell>
                <TableCell>{row.policy?.decision}</TableCell>
                <TableCell>{(row.tools || []).join(", ") || "—"}</TableCell>
                <TableCell className="max-w-56 truncate font-mono text-xs">
                  {(row.effects || [])
                    .map((effect) => `${effect.tool}:${effect.status}`)
                    .join(" · ") || "—"}
                </TableCell>
                <TableCell>
                  {row.human?.required ? "required" : "no"}
                  {row.human?.resolution ? ` / ${row.human.resolution}` : ""}
                </TableCell>
                <TableCell className="font-mono text-xs">
                  {row.parent_id || "—"}
                </TableCell>
                <TableCell>
                  {row.display ? (
                    <StatusBadge
                      status={row.display.status}
                      label={row.display.label}
                    />
                  ) : null}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </AppShell>
  );
}
