import { AppShell } from "@/components/app-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

import { TokenForm } from "./token-form";

export const dynamic = "force-dynamic";

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}) {
  const params = await searchParams;
  const reason = params.reason;
  return (
    <AppShell>
      <div className="flex flex-col gap-2">
        <h2 className="font-heading text-xl font-medium">Settings</h2>
        <p className="text-sm text-muted-foreground">
          Bearer token only. SociACL is slice 8. Bind defaults to 127.0.0.1 —
          set <code>AIMMUNE_UI_HOST=0.0.0.0</code> only as an explicit opt-in.
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
            Must match the server env. Never commit the token.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <TokenForm />
        </CardContent>
      </Card>
    </AppShell>
  );
}
