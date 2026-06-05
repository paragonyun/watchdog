import { createHash, createHmac, timingSafeEqual } from "node:crypto";

type SessionPayload = {
  sub: "owner";
  iat: number;
};

export function hashPassword(password: string): string {
  return createHash("sha256").update(password, "utf8").digest("hex");
}

export function verifyPasswordHash(password: string, expectedHash: string | undefined): boolean {
  if (!expectedHash) {
    return false;
  }
  return safeEqual(hashPassword(password), expectedHash.trim().toLowerCase());
}

export function createSessionToken(secret: string, now: number = Date.now()): string {
  const payload: SessionPayload = { sub: "owner", iat: now };
  const encoded = Buffer.from(JSON.stringify(payload), "utf8").toString("base64url");
  return `${encoded}.${sign(encoded, secret)}`;
}

export function verifySessionToken(token: string | undefined, secret: string | undefined, maxAgeMs: number, now: number = Date.now()): boolean {
  if (!token || !secret) {
    return false;
  }
  const parts = token.split(".");
  if (parts.length !== 2) {
    return false;
  }
  const [encoded, signature] = parts;
  if (!encoded || !signature || !safeEqual(sign(encoded, secret), signature)) {
    return false;
  }
  try {
    const payload = JSON.parse(Buffer.from(encoded, "base64url").toString("utf8")) as SessionPayload;
    return payload.sub === "owner" && Number.isFinite(payload.iat) && now - payload.iat <= maxAgeMs;
  } catch {
    return false;
  }
}

export function verifyBearerToken(value: string | undefined, expected: string | undefined): boolean {
  if (!value || !expected) {
    return false;
  }
  return safeEqual(value, expected);
}

function sign(value: string, secret: string): string {
  return createHmac("sha256", secret).update(value, "utf8").digest("base64url");
}

function safeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a);
  const right = Buffer.from(b);
  return left.length === right.length && timingSafeEqual(left, right);
}
