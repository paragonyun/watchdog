import assert from "node:assert/strict";
import test from "node:test";

import { createSessionToken, hashPassword, verifyBearerToken, verifyPasswordHash, verifySessionToken } from "../src/lib/auth-core";

test("password hashes are verified with exact matches only", () => {
  const hashed = hashPassword("correct-password");

  assert.equal(verifyPasswordHash("correct-password", hashed), true);
  assert.equal(verifyPasswordHash("wrong-password", hashed), false);
});

test("session tokens expire and reject tampering", () => {
  const token = createSessionToken("secret", 1000);
  const tampered = token.replace(/.$/, "x");
  const extended = `${token}.extra`;

  assert.equal(verifySessionToken(token, "secret", 60_000, 2000), true);
  assert.equal(verifySessionToken(token, "secret", 60_000, 120_000), false);
  assert.equal(verifySessionToken(tampered, "secret", 60_000, 2000), false);
  assert.equal(verifySessionToken(extended, "secret", 60_000, 2000), false);
});

test("bearer token comparison requires exact token", () => {
  assert.equal(verifyBearerToken("upload-token", "upload-token"), true);
  assert.equal(verifyBearerToken("upload-token", "other"), false);
});
