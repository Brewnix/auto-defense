"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { LiveMockGrant } from "@/lib/sociacl-light/types";

export function MockGrants({
  grants,
  principal,
}: {
  grants: LiveMockGrant[];
  principal: string | null;
}) {
  const router = useRouter();
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function undelegate(grant: LiveMockGrant) {
    const key = `${grant.object}:${grant.accessor}:${grant.mask}`;
    setBusyKey(key);
    setError(null);
    try {
      const response = await fetch("/api/sociacl/undelegate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ accessor: grant.accessor, object: grant.object }),
      });
      const payload = (await response.json()) as { error?: string };
      if (!response.ok) {
        setError(payload.error || "undelegate failed");
        return;
      }
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "undelegate failed");
    } finally {
      setBusyKey(null);
    }
  }

  if (!grants.length) {
    return (
      <p className="text-sm text-muted-foreground">
        No live MockCheck grants on <code>site:{"{id}"}</code> / <code>:ir</code>.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Object</TableHead>
            <TableHead>Accessor</TableHead>
            <TableHead>Mask</TableHead>
            <TableHead>Until</TableHead>
            <TableHead />
          </TableRow>
        </TableHeader>
        <TableBody>
          {grants.map((grant) => {
            const key = `${grant.object}:${grant.accessor}:${grant.mask}`;
            const canUndelegate = Boolean(principal && grant.owner === principal);
            return (
              <TableRow key={key}>
                <TableCell className="font-mono text-xs">{grant.object}</TableCell>
                <TableCell className="font-mono text-xs">{grant.accessor}</TableCell>
                <TableCell>{grant.mask}</TableCell>
                <TableCell className="font-mono text-xs">
                  {grant.until === undefined ? "open" : String(grant.until)}
                </TableCell>
                <TableCell>
                  {canUndelegate ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={busyKey === key}
                      onClick={() => undelegate(grant)}
                    >
                      {busyKey === key ? "Removing…" : "Undelegate"}
                    </Button>
                  ) : null}
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  );
}
