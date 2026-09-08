import { AppShell } from "@/components/app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { loadIrSession } from "@/lib/ir";

import { TokenForm } from "./token-form";

export const dynamic = "force-dynamic";

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}) {
  const params = await searchParams;
  const reason = params.reason;
  const session = await loadIrSession();
  return (
    <AppShell principal={session.principal}>
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Settings</h2>
        <p className="text-sm text-muted-foreground">
          Dual auth: <code>AIMMUNE_UI_TOKEN</code> for loopback smoke;
          production human path requires Check (SIWE / cottage principal).
          Machine doors stay <code>hm_site_</code>. Bind defaults to 127.0.0.1.
        </p>
      </div>
      {reason === "unset" ? (
        <Alert variant="destructive">
          <AlertTitle>Token unset</AlertTitle>
          <AlertDescription>
            Export AIMMUNE_UI_TOKEN before serving. Production fails closed when
            it is missing.
          </AlertDescription>
        </Alert>
      ) : null}
      {reason === "auth" ? (
        <Alert>
          <AlertTitle>Authorization required</AlertTitle>
          <AlertDescription>
            Enter the same value as AIMMUNE_UI_TOKEN. It is stored in an httpOnly
            cookie for this browser.
          </AlertDescription>
        </Alert>
      ) : null}
      <Card>
        <CardHeader>
          <CardTitle>UI token + principal</CardTitle>
          <CardDescription>
            Token must match the server env. Principal is the cottage SIWE
            address used at Check time. Never commit secrets.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TokenForm />
        </CardContent>
      </Card>
      <Alert>
        <AlertTitle>Check caps</AlertTitle>
        <AlertDescription>
          object {session.caps.object} · read {String(session.caps.read)} · write{" "}
          {String(session.caps.write)} · execute {String(session.caps.execute)} ·
          break_glass {String(session.caps.break_glass)} · source{" "}
          {session.source || "none"}
        </AlertDescription>
      </Alert>
    </AppShell>
  );
}
