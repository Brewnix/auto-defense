import { FolderOpenIcon } from "lucide-react";

import { AppShell } from "@/components/app-shell";
import { EmptyState } from "@/components/empty-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { loadSnapshot } from "@/lib/aimmune";

export const dynamic = "force-dynamic";

export default async function IncidentsPage() {
  let error: string | null = null;
  let snap = null;
  try {
    snap = await loadSnapshot();
  } catch (err) {
    error = err instanceof Error ? err.message : "snapshot failed";
  }

  return (
    <AppShell siteId={snap?.site_id} planeReachable={snap?.plane_reachable}>
      {error ? (
        <Alert variant="destructive">
          <AlertTitle>Could not load incidents</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Incidents</h2>
        <p className="text-sm text-muted-foreground">
          Minimal local fyber.incident/v0 side-records. Contain is not gated on
          this list.
        </p>
      </div>
      {!snap?.incidents.length ? (
        <EmptyState
          icon={FolderOpenIcon}
          title="No incidents"
          description="Propose/hold/contain cycles open or join a security side-record."
        />
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>incident_id</TableHead>
              <TableHead>status</TableHead>
              <TableHead>severity</TableHead>
              <TableHead>summary</TableHead>
              <TableHead>opened</TableHead>
              <TableHead>subjects</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {snap.incidents.map((row) => (
              <TableRow key={row.incident_id}>
                <TableCell className="font-mono text-xs">{row.incident_id}</TableCell>
                <TableCell>
                  <Badge variant="outline">{row.status}</Badge>
                </TableCell>
                <TableCell>{row.severity}</TableCell>
                <TableCell>{row.summary_redacted}</TableCell>
                <TableCell className="text-xs">{row.opened_at}</TableCell>
                <TableCell className="text-xs">
                  {(row.primary_subjects || [])
                    .map((subject) => `${subject.kind}:${subject.value}`)
                    .join(", ")}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </AppShell>
  );
}
