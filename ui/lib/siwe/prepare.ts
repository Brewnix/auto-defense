import { configuredSiteId } from "@/lib/sociacl-light/objects";

import {
  NONCE_TTL_MS,
  SIWE_VERSION,
  defaultClientChainId,
  siweDomain,
  siweStatement,
  siweUri,
} from "./config";
import { issueNonce } from "./nonce";

export type SiweNoncePayload = {
  nonce: string;
  domain: string;
  uri: string;
  statement: string;
  version: typeof SIWE_VERSION;
  chainId: number;
  issuedAt: string;
  expirationTime: string;
  site_id: string;
};

export function siweNoncePayload(now = Date.now()): SiweNoncePayload {
  const nonce = issueNonce(now);
  const siteId = configuredSiteId();
  const issuedAt = new Date(now);
  const expirationTime = new Date(now + NONCE_TTL_MS);
  return {
    nonce,
    domain: siweDomain(),
    uri: siweUri(),
    statement: siweStatement(siteId),
    version: SIWE_VERSION,
    chainId: defaultClientChainId(),
    issuedAt: issuedAt.toISOString(),
    expirationTime: expirationTime.toISOString(),
    site_id: siteId,
  };
}
