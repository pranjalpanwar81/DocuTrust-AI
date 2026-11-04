// Port of app/auth.py: password hashing and HS256 JWT access tokens.
import bcrypt from "bcryptjs";
import { SignJWT, jwtVerify } from "jose";
import { randomBytes } from "node:crypto";
import { settings } from "./config.js";
import { getOrCreateSetting } from "./db.js";

let cachedSecret: Uint8Array | null = null;

/**
 * JWT signing secret: the JWT_SECRET_KEY env var if set, otherwise a random
 * 256-bit key generated once and stored in the database, so every function
 * instance signs and verifies with the same key and nothing has to be
 * configured by hand.
 */
async function secret(): Promise<Uint8Array> {
  if (cachedSecret) return cachedSecret;
  const fromEnv = settings().jwtSecretKey;
  const key = fromEnv || (await getOrCreateSetting("jwt_secret_key", () => randomBytes(32).toString("hex")));
  cachedSecret = new TextEncoder().encode(key);
  return cachedSecret;
}

export async function hashPassword(password: string): Promise<string> {
  return bcrypt.hash(password, 10);
}

export async function verifyPassword(password: string, hashed: string): Promise<boolean> {
  try {
    return await bcrypt.compare(password, hashed);
  } catch {
    return false;
  }
}

export async function createAccessToken(username: string): Promise<string> {
  const minutes = settings().accessTokenExpireMinutes;
  return new SignJWT({ sub: username })
    .setProtectedHeader({ alg: "HS256", typ: "JWT" })
    .setExpirationTime(Math.floor(Date.now() / 1000) + minutes * 60)
    .sign(await secret());
}

export async function decodeAccessToken(token: string): Promise<string | null> {
  try {
    const { payload } = await jwtVerify(token, await secret(), { algorithms: ["HS256"] });
    return typeof payload.sub === "string" ? payload.sub : null;
  } catch {
    return null;
  }
}
