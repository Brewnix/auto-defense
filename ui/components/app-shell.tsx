import type { ReactNode } from "react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/receipts", label: "Receipts" },
  { href: "/holds", label: "Holds" },
  { href: "/incidents", label: "Incidents" },
  { href: "/preempt", label: "Preempt" },
  { href: "/settings", label: "Settings" },
];

export function AppShell({
  children,
  siteId,
  planeReachable,
}: {
  children: ReactNode;
  siteId?: string;
  planeReachable?: boolean;
}) {
  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b bg-card">
        <div className="mx-auto flex w-full max-w-6xl flex-col gap-3 px-4 py-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex flex-col gap-0.5">
              <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
                AImmune
              </p>
              <h1 className="font-heading text-lg font-medium">Site operator console</h1>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {siteId ? <Badge variant="secondary">{siteId}</Badge> : null}
              {planeReachable === undefined ? null : (
                <Badge variant={planeReachable ? "default" : "outline"}>
                  {planeReachable ? "plane reachable" : "plane down"}
                </Badge>
              )}
            </div>
          </div>
          <nav className="flex flex-wrap gap-2">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        </div>
      </header>
      <Separator />
      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 px-4 py-6">
        {children}
      </main>
    </div>
  );
}
