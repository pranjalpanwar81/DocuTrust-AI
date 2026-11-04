// Runtime settings, read from Netlify environment variables (Functions scope).
declare const Netlify: { env: { get(key: string): string | undefined } } | undefined;

function env(key: string): string | undefined {
  try {
    if (typeof Netlify !== "undefined" && Netlify?.env) return Netlify.env.get(key);
  } catch {
    /* fall through to process.env (local tests) */
  }
  return process.env[key];
}

function trimmed(key: string): string | null {
  const value = (env(key) ?? "").trim();
  return value || null;
}

export function settings() {
  return {
    // Netlify buffers request bodies up to 6 MB (binary is base64-encoded),
    // so the effective upload ceiling for a file is about 4.5 MB.
    maxUploadBytes: Number(env("MAX_UPLOAD_BYTES") ?? 4 * 1024 * 1024),
    retrievalThreshold: Number(env("RETRIEVAL_THRESHOLD") ?? "0.12"),
    openaiApiKey: trimmed("OPENAI_API_KEY"),
    openaiBaseUrl: (env("OPENAI_BASE_URL") ?? "https://api.openai.com/v1").trim(),
    openaiModel: (env("OPENAI_MODEL") ?? "gpt-4.1-mini").trim(),
    jwtSecretKey: env("JWT_SECRET_KEY") ?? "",
    accessTokenExpireMinutes: Number(env("ACCESS_TOKEN_EXPIRE_MINUTES") ?? "30"),
    adminUsername: trimmed("ADMIN_USERNAME"),
    adminEmail: trimmed("ADMIN_EMAIL"),
    adminPassword: env("ADMIN_PASSWORD") || null,
  };
}
