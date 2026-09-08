import { PauseIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { StatusBadge } from "@/components/status-badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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

export const dynamic = "force-dynamic";

export default async function PreemptPage() {
  const session = await loadIrSession();
  let error: string | null = null;
  let snap = null;
  try {
    snap = await loadSnapshot();
  } catch (err) {
    error = err instanceof Error ? err.message : "snapshot failed";
  }

  const queue = snap?.preempt.queue || [];
  const receipts = snap?.preempt.receipts || [];

  return (
    <AppShell
      siteId={snap?.site_id}
      planeReachable={snap?.plane_reachable}
      principal={session.principal}
    >
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load preempt state</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Preempt</h2>
        <p className="text-sm text-muted-foreground">
          Recent hypermesh.* receipts and the pending preempt queue. Execute
          stays in <code>aimmune preempt run</code>.
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Pending queue</CardTitle>
          <CardDescription>preempt_queue.jsonl rows not yet done</CardDescription>
        </CardHeader>
        <CardContent>
          {!queue.length ? (
            <EmptyState
              icon={PauseIcon}
              title="Queue empty"
              description="Auditor-approved hypermesh.* work lands here after slice 2 apply."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>device</TableHead>
                  <TableHead>reason</TableHead>
                  <TableHead>tools</TableHead>
                  <TableHead>queued</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {queue.map((row) => (
                  <TableRow key={row.queue_id}>
                    <TableCell>{row.device_id}</TableCell>
                    <TableCell>
                      <Badge variant="outline">{row.reason_code}</Badge>
                    </TableCell>
                    <TableCell>{(row.tools || []).join(", ")}</TableCell>
                    <TableCell className="text-xs">{row.queued_at}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>hypermesh.* receipts</CardTitle>
          <CardDescription>Filtered from the site chain</CardDescription>
        </CardHeader>
        <CardContent>
          {!receipts.length ? (
            <p className="text-sm text-muted-foreground">None yet.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>receipt_id</TableHead>
                  <TableHead>decision</TableHead>
                  <TableHead>tools</TableHead>
                  <TableHead>copy</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {receipts.map((row) => (
                  <TableRow key={row.receipt_id}>
                    <TableCell className="font-mono text-xs">{row.receipt_id}</TableCell>
                    <TableCell>{row.policy?.decision}</TableCell>
                    <TableCell>{(row.tools || []).join(", ")}</TableCell>
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
        </CardContent>
      </Card>
    </AppShell>
  );
}
