"use client";

import { createSiweMessage } from "viem/siwe";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Field, FieldDescription, FieldGroup } from "@/components/ui/field";
import type { SiweNoncePayload } from "@/lib/siwe";

type InjectedEthereum = {
  request: (args: { method: string; params?: unknown[] }) => Promise<unknown>;
};

function injectedEthereum(): InjectedEthereum | null {
  if (typeof window === "undefined") {
    return null;
  }
  const eth = (window as Window & { ethereum?: InjectedEthereum }).ethereum;
  return eth ?? null;
}

export function SiweConnect() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [ok, setOk] = useState<string | null>(null);

  async function connect() {
    setBusy(true);
    setError(null);
    setOk(null);
    try {
      const ethereum = injectedEthereum();
      if (!ethereum) {
        setError("No injected window.ethereum (MetaMask / Brave). WalletConnect is out of scope.");
        return;
      }
      const accounts = (await ethereum.request({
        method: "eth_requestAccounts",
      })) as string[];
      const address = accounts?.[0];
      if (!address) {
        setError("wallet returned no account");
        return;
      }

      const nonceRes = await fetch("/api/siwe/nonce");
      const noncePayload = (await nonceRes.json()) as SiweNoncePayload & { error?: string };
      if (!nonceRes.ok) {
        setError(noncePayload.error || "could not issue siwe nonce");
        return;
      }

      const message = createSiweMessage({
        address: address as `0x${string}`,
        chainId: noncePayload.chainId,
        domain: noncePayload.domain,
        nonce: noncePayload.nonce,
        uri: noncePayload.uri,
        version: "1",
        statement: noncePayload.statement,
        issuedAt: new Date(noncePayload.issuedAt),
        expirationTime: new Date(noncePayload.expirationTime),
      });

      const signature = (await ethereum.request({
        method: "personal_sign",
        params: [message, address],
      })) as string;

      const verifyRes = await fetch("/api/siwe/verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, signature }),
      });
      const verifyPayload = (await verifyRes.json()) as {
        error?: string;
        principal?: string;
      };
      if (!verifyRes.ok) {
        setError(verifyPayload.error || "siwe verify failed");
        return;
      }
      setOk(verifyPayload.principal || address);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "siwe connect failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <FieldGroup>
      <Field>
        <FieldDescription>
          Injected <code>window.ethereum</code> only (MetaMask / Brave). No
          WalletConnect / Wagmi / Web3Modal. Address becomes the SociACL
          AccessorId after verify.
        </FieldDescription>
      </Field>
      <Button type="button" onClick={connect} disabled={busy}>
        {busy ? "Waiting for signature…" : "Connect wallet"}
      </Button>
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
      {ok ? (
        <p className="font-mono text-sm text-muted-foreground">SIWE {ok}</p>
      ) : null}
    </FieldGroup>
  );
}
