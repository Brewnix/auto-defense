import { generateSiweNonce } from "viem/siwe";

import { NONCE_TTL_MS } from "./config";

const store = new Map<string, number>();

function sweep(now = Date.now()): void {
  for (const [nonce, expiresAt] of store) {
    if (expiresAt <= now) {
      store.delete(nonce);
    }
  }
}

export function issueNonce(now = Date.now()): string {
  sweep(now);
  const nonce = generateSiweNonce();
  store.set(nonce, now + NONCE_TTL_MS);
  return nonce;
}

/** One-time consume. Returns false when missing, already used, or expired. */
export function consumeNonce(nonce: string | null | undefined, now = Date.now()): boolean {
  if (!nonce) {
    return false;
  }
  const expiresAt = store.get(nonce);
  if (expiresAt === undefined) {
    return false;
  }
  store.delete(nonce);
  return expiresAt > now;
}

export function resetNonceStore(): void {
  store.clear();
}

export function nonceStoreSize(): number {
  sweep();
  return store.size;
}
