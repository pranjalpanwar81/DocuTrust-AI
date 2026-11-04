// HTTP API for DocuTrust AI, ported route-for-route from app/main.py (FastAPI).
// Responses keep the same paths, status codes and JSON shapes so the existing
// frontend (app/static) works unchanged.
import { randomUUID } from "node:crypto";
import * as database from "./db.js";
import { createAccessToken, decodeAccessToken, hashPassword, verifyPassword } from "./auth.js";
import { settings } from "./config.js";
import { ExtractionError, extractPages, sanitizeFilename } from "./extraction.js";
import {
  type ChunkRow,
  chunkPages,
  conciseAnswer,
  confidence,
  correctedQuestion,
  focusedExcerpt,
  isIdentityQuestion,
  pyRound,
  retrieve,
} from "./retrieval.js";
import { type SynthesisResult, synthesize } from "./synthesis.js";

type User = Record<string, any>;

class HttpError extends Error {
  constructor(public status: number, public detail: string, public headers: Record<string, string> = {}) {
    super(detail);
  }
}

const json = (body: unknown, status = 200) => Response.json(body, { status });
const noContent = () => new Response(null, { status: 204 });

// ---------------------------------------------------------------- rate limits
// Best-effort, per function instance (the original slowapi limiter was also
// in-memory on a single server).
const hits = new Map<string, number[]>();
function limit(key: string, ip: string, perMinute: number) {
  const now = Date.now();
  const bucketKey = `${key}:${ip}`;
  const recent = (hits.get(bucketKey) ?? []).filter((t) => now - t < 60_000);
  if (recent.length >= perMinute) {
    throw new HttpError(429, `Rate limit exceeded: ${perMinute} per 1 minute`);
  }
  recent.push(now);
  hits.set(bucketKey, recent);
}

// ------------------------------------------------------------ admin bootstrap
let bootstrapped: Promise<void> | null = null;
function bootstrapAdmin(): Promise<void> {
  if (!bootstrapped) {
    bootstrapped = (async () => {
      const { adminUsername, adminEmail, adminPassword } = settings();
      if (adminUsername && adminEmail && adminPassword && !(await database.hasUsers())) {
        await database.createUser(adminUsername, adminEmail, await hashPassword(adminPassword), "admin");
        console.info(`Created initial admin account "${adminUsername}".`);
      }
    })().catch((error) => {
      bootstrapped = null; // retry on the next request
      throw error;
    });
  }
  return bootstrapped;
}

// ------------------------------------------------------------- auth helpers
async function currentUser(req: Request): Promise<User> {
  const header = req.headers.get("authorization") ?? "";
  const [scheme, token] = header.split(" ");
  if (scheme?.toLowerCase() !== "bearer" || !token) {
    throw new HttpError(401, "Not authenticated", { "WWW-Authenticate": "Bearer" });
  }
  const username = await decodeAccessToken(token);
  const user = username ? await database.getUser(username) : null;
  if (!user) throw new HttpError(401, "Could not validate credentials", { "WWW-Authenticate": "Bearer" });
  if (user.disabled) throw new HttpError(403, "User account is disabled");
  return user;
}

async function requireAdmin(req: Request): Promise<User> {
  const user = await currentUser(req);
  if (user.role !== "admin") throw new HttpError(403, "Admin privileges required");
  return user;
}

async function requireUserOrAdmin(req: Request): Promise<User> {
  const user = await currentUser(req);
  if (!["admin", "user"].includes(user.role)) throw new HttpError(403, "User privileges required");
  return user;
}

// ---------------------------------------------------------- input helpers
async function jsonBody(req: Request): Promise<Record<string, unknown>> {
  try {
    const body = await req.json();
    if (body && typeof body === "object" && !Array.isArray(body)) return body as Record<string, unknown>;
  } catch {
    /* handled below */
  }
  throw new HttpError(422, "Request body must be a JSON object.");
}

function requireString(body: Record<string, unknown>, field: string): string {
  const value = body[field];
  if (typeof value !== "string") throw new HttpError(422, `Field "${field}" is required and must be a string.`);
  return value;
}

function queryParam(url: URL, name: string, required = false): string | null {
  const value = url.searchParams.get(name);
  if (required && value === null) throw new HttpError(422, `Query parameter "${name}" is required.`);
  return value;
}

function parseBool(value: string | null, fallback: boolean): boolean {
  if (value === null) return fallback;
  const v = value.toLowerCase();
  if (["true", "1", "yes", "on", "t", "y"].includes(v)) return true;
  if (["false", "0", "no", "off", "f", "n"].includes(v)) return false;
  throw new HttpError(422, "Input should be a valid boolean.");
}

// ------------------------------------------------------------------ routes
async function health(ip: string) {
  limit("health", ip, 60);
  return json({ status: "ok", llm_enabled: Boolean(settings().openaiApiKey), documents: await database.documentCount() });
}

async function register(req: Request, ip: string) {
  limit("register", ip, 5);
  const body = await jsonBody(req);
  const username = requireString(body, "username");
  const email = requireString(body, "email");
  const password = requireString(body, "password");
  if (await database.getUser(username)) throw new HttpError(400, "Username already registered");
  // Public registration always creates a regular user, whatever role is sent.
  const ok = await database.createUser(username, email, await hashPassword(password), "user");
  if (!ok) throw new HttpError(400, "Email already registered");
  return json({ message: "User registered successfully", username }, 201);
}

async function login(req: Request, ip: string) {
  limit("login", ip, 10);
  const body = await jsonBody(req);
  const username = requireString(body, "username");
  const password = requireString(body, "password");
  const user = await database.getUser(username);
  if (!user || !(await verifyPassword(password, user.hashed_password))) {
    throw new HttpError(401, "Invalid username or password");
  }
  const minutes = settings().accessTokenExpireMinutes;
  return json({
    access_token: await createAccessToken(user.username),
    token_type: "bearer",
    expires_in: minutes * 60,
    user: { username: user.username, email: user.email, role: user.role },
  });
}

async function uploadDocument(req: Request, ip: string) {
  limit("upload", ip, 10);
  const user = await requireUserOrAdmin(req);
  let form: FormData;
  try {
    form = await req.formData();
  } catch {
    throw new HttpError(422, "Expected a multipart form upload with a \"file\" field.");
  }
  const file = form.get("file");
  if (!file || typeof file === "string") throw new HttpError(422, "Field \"file\" is required.");
  const { maxUploadBytes } = settings();
  if (file.size > maxUploadBytes) throw new HttpError(413, "File exceeds the configured upload-size limit.");
  const filename = sanitizeFilename(file.name || "upload");
  const data = new Uint8Array(await file.arrayBuffer());
  let pages, extractionMethod;
  try {
    [pages, extractionMethod] = await extractPages(filename, data);
  } catch (error) {
    if (error instanceof ExtractionError) throw new HttpError(422, error.message);
    throw error;
  }
  const documentId = randomUUID();
  const chunks = chunkPages(documentId, pages);
  if (!chunks.length) throw new HttpError(422, "The document did not produce usable chunks.");
  const record = {
    id: documentId,
    filename,
    media_type: file.type || "application/octet-stream",
    uploaded_at: new Date().toISOString(),
    page_count: pages.length,
    extraction_method: extractionMethod,
    owner_username: user.username,
    is_public: 0,
  };
  await database.addDocument(record, chunks);
  return json({ ...record, chunk_count: chunks.length }, 201);
}

async function ask(req: Request, ip: string) {
  limit("query", ip, 30);
  const user = await currentUser(req);
  const body = await jsonBody(req);
  const question = requireString(body, "question");
  if (question.length < 5 || question.length > 1000) {
    throw new HttpError(422, "Question must be between 5 and 1000 characters.");
  }
  let documentIds: string[] | null = null;
  if (body.document_ids !== undefined && body.document_ids !== null) {
    if (!Array.isArray(body.document_ids) || !body.document_ids.every((id) => typeof id === "string")) {
      throw new HttpError(422, "document_ids must be a list of strings.");
    }
    documentIds = body.document_ids as string[];
  }

  let scope: string[];
  if (documentIds && documentIds.length) {
    for (const docId of documentIds) {
      if (!(await database.checkDocumentAccess(docId, user.username, user.role))) {
        throw new HttpError(403, `You do not have access to document ${docId}`);
      }
    }
    scope = documentIds;
  } else {
    scope = (await database.getUserAccessibleDocuments(user.username, user.role)).map((doc) => doc.id);
  }
  const rows = (await database.chunksForDocuments(scope)) as ChunkRow[];

  const [interpretedQuestion, corrections] = correctedQuestion(question, rows);
  const evidence = retrieve(interpretedQuestion, rows);
  const score = confidence(evidence);
  const status = score >= settings().retrievalThreshold && evidence.length ? "grounded" : "insufficient_evidence";
  // Identity fields are copied deterministically from the retrieved resume.
  const synthesis: SynthesisResult =
    status === "grounded" && !isIdentityQuestion(interpretedQuestion, interpretedQuestion.split(/\s+/))
      ? await synthesize(interpretedQuestion, evidence)
      : { text: null, source: "fallback", error: null };
  const generated = synthesis.text;
  const answer =
    generated ||
    (status === "grounded"
      ? conciseAnswer(interpretedQuestion, evidence)
      : "I do not have enough supporting evidence in the indexed documents to answer this reliably.");
  const answerSource = status === "grounded" ? (synthesis.source === "llm" && generated ? "llm" : "deterministic") : "abstained";
  if (synthesis.error && synthesis.source === "fallback" && status === "grounded") {
    console.info(`Query used deterministic fallback after synthesis issue: ${synthesis.error}`);
  }
  const event = {
    id: randomUUID(),
    created_at: new Date().toISOString(),
    question,
    answer_status: status,
    confidence: score,
    citation_ids: evidence.map((item) => item.chunk_id),
    username: user.username,
  };
  await database.addQueryEvent(event);
  return json({
    answer,
    answer_status: status,
    answer_source: answerSource,
    synthesis_error: synthesis.error,
    confidence: score,
    interpreted_question: interpretedQuestion,
    corrections,
    citations: evidence.map((item) => ({
      chunk_id: item.chunk_id,
      document_id: item.document_id,
      document_name: item.document_name,
      page: item.page,
      section: item.section,
      relevance_score: pyRound(item.score, 4),
      supporting_quote: focusedExcerpt(interpretedQuestion, item.text),
    })),
    audit_event_id: event.id,
  });
}

type Handler = (req: Request, params: Record<string, string>, url: URL, ip: string) => Promise<Response>;
const routes: Array<[string, RegExp, Handler]> = [];
function route(method: string, pattern: string, handler: Handler) {
  const regex = new RegExp("^" + pattern.replace(/:(\w+)/g, "(?<$1>[^/]+)") + "/?$");
  routes.push([method, regex, handler]);
}

route("GET", "/health", (_req, _p, _u, ip) => health(ip));
route("POST", "/api/v1/auth/register", (req, _p, _u, ip) => register(req, ip));
route("POST", "/api/v1/auth/login", (req, _p, _u, ip) => login(req, ip));
route("GET", "/api/v1/auth/me", async (req) => {
  const user = await currentUser(req);
  return json({ username: user.username, email: user.email, role: user.role, disabled: user.disabled });
});
route("GET", "/api/v1/users", async (req) => {
  await requireAdmin(req);
  return json(await database.getAllUsers());
});
route("PUT", "/api/v1/users/:username/role", async (req, params, url) => {
  await requireAdmin(req);
  const newRole = queryParam(url, "new_role", true)!;
  if (!["admin", "user", "viewer"].includes(newRole)) throw new HttpError(400, "Invalid role. Must be admin, user, or viewer");
  if (!(await database.updateUserRole(params.username, newRole))) throw new HttpError(404, "User not found");
  return json({ message: `User role updated to ${newRole}` });
});
route("PUT", "/api/v1/users/:username/disable", async (req, params, url) => {
  await requireAdmin(req);
  const disabled = parseBool(queryParam(url, "disabled"), true);
  if (!(await database.disableUser(params.username, disabled))) throw new HttpError(404, "User not found");
  return json({ message: `User account ${disabled ? "disabled" : "enabled"}` });
});
route("POST", "/api/v1/documents", (req, _p, _u, ip) => uploadDocument(req, ip));
route("GET", "/api/v1/documents", async (req) => {
  const user = await currentUser(req);
  return json(await database.getUserAccessibleDocuments(user.username, user.role));
});
route("DELETE", "/api/v1/documents", async (req) => {
  await requireAdmin(req);
  return json({ deleted_count: await database.deleteAllDocuments() });
});
route("DELETE", "/api/v1/documents/:documentId", async (req, params) => {
  const user = await requireUserOrAdmin(req);
  if (!(await database.checkDocumentAccess(params.documentId, user.username, user.role))) {
    throw new HttpError(403, "You do not have permission to delete this document.");
  }
  if (!(await database.deleteDocument(params.documentId))) throw new HttpError(404, "Document not found.");
  return noContent();
});
route("GET", "/api/v1/analytics", async (req) => {
  await currentUser(req);
  return json(await database.analytics());
});
route("GET", "/api/v1/query-history", async (req, _p, url) => {
  await currentUser(req);
  const raw = queryParam(url, "limit") ?? "8";
  if (!/^-?\d+$/.test(raw)) throw new HttpError(422, "limit must be an integer.");
  return json(await database.recentQueryEvents(Math.max(1, Math.min(Number(raw), 50))));
});
route("DELETE", "/api/v1/query-history/:eventId", async (req, params) => {
  await currentUser(req);
  if (!(await database.deleteQueryEvent(params.eventId))) throw new HttpError(404, "Audit event not found.");
  return noContent();
});
route("POST", "/api/v1/query", (req, _p, _u, ip) => ask(req, ip));
route("POST", "/api/v1/documents/:documentId/permissions", async (req, params, url) => {
  const user = await requireUserOrAdmin(req);
  const username = queryParam(url, "username", true)!;
  const level = queryParam(url, "permission_level") ?? "read";
  if (!(await database.checkDocumentAccess(params.documentId, user.username, user.role))) {
    throw new HttpError(403, "You do not have permission to grant access to this document.");
  }
  if (!["read", "write", "admin"].includes(level)) throw new HttpError(400, "Invalid permission level. Must be read, write, or admin");
  if (!(await database.grantDocumentPermission(params.documentId, username, level))) {
    throw new HttpError(400, "Permission already exists or user not found");
  }
  return json({ message: `Permission granted to ${username} with level ${level}` }, 201);
});
route("DELETE", "/api/v1/documents/:documentId/permissions/:username", async (req, params) => {
  const user = await requireUserOrAdmin(req);
  if (!(await database.checkDocumentAccess(params.documentId, user.username, user.role))) {
    throw new HttpError(403, "You do not have permission to revoke access to this document.");
  }
  if (!(await database.revokeDocumentPermission(params.documentId, params.username))) throw new HttpError(404, "Permission not found");
  return json({ message: `Permission revoked from ${params.username}` });
});

export async function handle(req: Request, ip = "unknown"): Promise<Response> {
  const url = new URL(req.url);
  try {
    await bootstrapAdmin();
    let pathMatched = false;
    for (const [method, regex, handler] of routes) {
      const match = regex.exec(url.pathname);
      if (!match) continue;
      pathMatched = true;
      if (method !== req.method) continue;
      const params = Object.fromEntries(Object.entries(match.groups ?? {}).map(([k, v]) => [k, decodeURIComponent(v)]));
      return await handler(req, params, url, ip);
    }
    return pathMatched ? json({ detail: "Method Not Allowed" }, 405) : json({ detail: "Not Found" }, 404);
  } catch (error) {
    if (error instanceof HttpError) {
      const response = json({ detail: error.detail }, error.status);
      for (const [k, v] of Object.entries(error.headers)) response.headers.set(k, v);
      return response;
    }
    console.error("Unhandled API error", error);
    return json({ detail: "Internal Server Error" }, 500);
  }
}
