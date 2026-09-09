import { AppShell } from "@/components/app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { smokePrincipalAllowed } from "@/lib/auth";
import { loadIrSession } from "@/lib/ir";
import { listLiveSiteGrants } from "@/lib/sociacl-light/store";

import { MockGrants } from "./mock-grants";
import { SessionStatus } from "./session-status";
import { SiweConnect } from "./siwe-connect";
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
  const smokeAllowed = smokePrincipalAllowed();
  const grants = listLiveSiteGrants(session.siteId, session.now);
  return (
    <AppShell principal={session.principal}>
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Settings</h2>
        <p className="text-sm text-muted-foreground">
          Dual auth: <code>AIMMUNE_UI_TOKEN</code> is required to serve;
          production human path is EIP-4361 SIWE → Check. Machine doors stay{" "}
          <code>hm_site_</code>. Bind defaults to 127.0.0.1.
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
          <CardTitle>UI token</CardTitle>
          <CardDescription>
            Token must match the server env. Required to serve (proxy). Never
            commit secrets.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TokenForm smokeAllowed={smokeAllowed} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>SIWE v0</CardTitle>
          <CardDescription>
            Connect → personal_sign EIP-4361 → verify. Sets the httpOnly{" "}
            <code>aimmune_principal</code> cookie only after a valid signature.
            Address is the SociACL AccessorId.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-6">
          <SessionStatus
            source={session.source}
            principal={session.principal}
            exp={session.exp}
          />
          <SiweConnect />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>MockCheck grants</CardTitle>
          <CardDescription>
            Live rows on <code>site:{session.siteId}</code> and{" "}
            <code>site:{session.siteId}:ir</code>. Owner undelegate is
            immediate — the next Check denies. Re-Check at act is unchanged.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MockGrants grants={grants} principal={session.principal} />
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
