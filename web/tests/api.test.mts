// End-to-end API test: runs every route against a throwaway local Postgres.
// Run with `npm test` from web/.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { NetlifyDB } from "@netlify/database-dev";

const here = fileURLToPath(new URL(".", import.meta.url));
const dir = `${here}fixtures`;
const pg = new NetlifyDB();
const url = await pg.start();
const applied = await pg.applyMigrations(`${here}../netlify/database/migrations`);
console.log("migrations applied:", applied);
process.env.TEST_DATABASE_URL = url;
delete process.env.JWT_SECRET_KEY;
process.env.ADMIN_USERNAME = "admin";
process.env.ADMIN_EMAIL = "admin@example.com";
process.env.ADMIN_PASSWORD = "AdminPass123!";

const { handle } = await import("../lib/app.ts");
const base = "https://docutrust-ai.netlify.app";
let failures = 0;
async function call(method: string, path: string, opts: { token?: string; json?: unknown; form?: FormData } = {}) {
  const headers: Record<string, string> = {};
  if (opts.token) headers.Authorization = `Bearer ${opts.token}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.json); }
  if (opts.form) body = opts.form;
  const res = await handle(new Request(base + path, { method, headers, body }), "1.2.3.4");
  const text = await res.text();
  let data: any = text;
  try { data = text ? JSON.parse(text) : null; } catch {}
  return { status: res.status, data };
}
function check(label: string, cond: boolean, extra?: unknown) {
  console.log(`${cond ? "PASS" : "FAIL"} ${label}${cond ? "" : " -> " + JSON.stringify(extra)}`);
  if (!cond) failures++;
}
function fileForm(name: string, type: string) {
  const form = new FormData();
  form.append("file", new Blob([readFileSync(`${dir}/${name}`)], { type }), name);
  return form;
}

let r = await call("GET", "/health");
check("health", r.status === 200 && r.data.status === "ok" && r.data.documents === 0, r);
r = await call("GET", "/api/v1/documents");
check("documents requires auth (401)", r.status === 401 && r.data.detail === "Not authenticated", r);

r = await call("POST", "/api/v1/auth/register", { json: { username: "alice", email: "alice@example.com", password: "pw12345", role: "admin" } });
check("register alice (role ignored)", r.status === 201 && r.data.username === "alice", r);
r = await call("POST", "/api/v1/auth/register", { json: { username: "alice", email: "x@example.com", password: "pw" } });
check("duplicate username rejected", r.status === 400 && r.data.detail === "Username already registered", r);
r = await call("POST", "/api/v1/auth/register", { json: { username: "bob", email: "alice@example.com", password: "pw" } });
check("duplicate email rejected", r.status === 400 && r.data.detail === "Email already registered", r);
await call("POST", "/api/v1/auth/register", { json: { username: "bob", email: "bob@example.com", password: "bobpw123" } });

r = await call("POST", "/api/v1/auth/login", { json: { username: "alice", password: "wrong" } });
check("bad password 401", r.status === 401 && r.data.detail === "Invalid username or password", r);
r = await call("POST", "/api/v1/auth/login", { json: { username: "alice", password: "pw12345" } });
check("login alice", r.status === 200 && r.data.token_type === "bearer" && r.data.user.role === "user" && r.data.expires_in === 1800, r);
const alice = r.data.access_token;
r = await call("POST", "/api/v1/auth/login", { json: { username: "admin", password: "AdminPass123!" } });
check("bootstrapped admin can log in", r.status === 200 && r.data.user.role === "admin", r);
const admin = r.data.access_token;
const bob = (await call("POST", "/api/v1/auth/login", { json: { username: "bob", password: "bobpw123" } })).data.access_token;

r = await call("GET", "/api/v1/auth/me", { token: alice });
check("me", r.status === 200 && r.data.username === "alice" && r.data.disabled === 0, r);
r = await call("GET", "/api/v1/auth/me", { token: "garbage.token.value" });
check("invalid token 401", r.status === 401, r);

const uploads: Record<string, any> = {};
for (const [name, type, method] of [["bill.pdf", "application/pdf", "native_pdf"], ["resume.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "native_docx"], ["policy.txt", "text/plain", "plain_text"], ["warranty.png", "image/png", "tesseract_ocr"]]) {
  const t0 = Date.now();
  r = await call("POST", "/api/v1/documents", { token: alice, form: fileForm(name, type) });
  check(`upload ${name} (${Date.now() - t0}ms)`, r.status === 201 && r.data.extraction_method === method && r.data.chunk_count >= 1 && r.data.owner_username === "alice", r);
  uploads[name] = r.data;
}
check("pdf has 2 pages", uploads["bill.pdf"]?.page_count === 2, uploads["bill.pdf"]);
r = await call("POST", "/api/v1/documents", { token: alice, form: (() => { const f = new FormData(); f.append("file", new Blob(["x"]), "a.exe"); return f; })() });
check("unsupported type 422", r.status === 422 && r.data.detail.startsWith("Supported file types"), r);

r = await call("GET", "/api/v1/documents", { token: alice });
check("alice sees 4 docs", r.status === 200 && r.data.length === 4 && typeof r.data[0].chunk_count === "number", r);
r = await call("GET", "/api/v1/documents", { token: bob });
check("bob sees none", r.status === 200 && r.data.length === 0, r);
r = await call("GET", "/api/v1/documents", { token: admin });
check("admin sees all", r.data.length === 4, r);

r = await call("POST", "/api/v1/query", { token: alice, json: { question: "What is the total amount due on the bill?" } });
check("bill query grounded", r.status === 200 && r.data.answer_status === "grounded" && r.data.answer_source === "deterministic" && r.data.answer.includes("INV-2026-0042") && r.data.citations[0].document_name === "bill.pdf", r);
console.log("   answer:", JSON.stringify(r.data.answer), "conf:", r.data.confidence, "synthesis_error:", r.data.synthesis_error);
r = await call("POST", "/api/v1/query", { token: alice, json: { question: "What is the nmae of the student?" } });
check("name query with typo", r.data.answer === "Student name: Pranjal Panwar." && r.data.corrections.length >= 0, r);
console.log("   corrections:", JSON.stringify(r.data.corrections), "interpreted:", r.data.interpreted_question);
r = await call("POST", "/api/v1/query", { token: alice, json: { question: "How long is the warranty valid?" } });
check("OCR'd image is searchable", r.data.answer_status === "grounded" && r.data.citations[0]?.document_name === "warranty.png", r);
r = await call("POST", "/api/v1/query", { token: alice, json: { question: "Explain quantum chromodynamics", document_ids: [uploads["policy.txt"].id] } });
check("abstains with no evidence", r.data.answer_status === "insufficient_evidence" && r.data.answer_source === "abstained", r);
r = await call("POST", "/api/v1/query", { token: bob, json: { question: "What is the total amount?" , document_ids: [uploads["bill.pdf"].id] } });
check("bob forbidden on alice doc", r.status === 403, r);
r = await call("POST", "/api/v1/query", { token: alice, json: { question: "hey" } });
check("short question 422", r.status === 422, r);

r = await call("POST", `/api/v1/documents/${uploads["policy.txt"].id}/permissions?username=bob&permission_level=read`, { token: alice });
check("grant bob read", r.status === 201, r);
r = await call("POST", `/api/v1/documents/${uploads["policy.txt"].id}/permissions?username=bob`, { token: alice });
check("duplicate grant 400", r.status === 400, r);
r = await call("POST", `/api/v1/documents/${uploads["policy.txt"].id}/permissions?username=ghost`, { token: alice });
check("grant to unknown user 400", r.status === 400, r);
r = await call("POST", "/api/v1/query", { token: bob, json: { question: "How many days can employees work remotely?" } });
check("bob can now query shared doc", r.data.answer_status === "grounded" && r.data.citations.every((c: any) => c.document_name === "policy.txt"), r);
r = await call("DELETE", `/api/v1/documents/${uploads["policy.txt"].id}/permissions/bob`, { token: alice });
check("revoke bob", r.status === 200, r);

r = await call("GET", "/api/v1/analytics", { token: alice });
check("analytics", r.status === 200 && r.data.document_count === 4 && r.data.query_count >= 5 && typeof r.data.average_confidence === "number", r);
console.log("   analytics:", JSON.stringify(r.data));
r = await call("GET", "/api/v1/query-history?limit=3", { token: alice });
check("history limit 3", r.status === 200 && r.data.length === 3 && Array.isArray(r.data[0].citation_ids), r);
const eventId = r.data[0].id;
r = await call("DELETE", `/api/v1/query-history/${eventId}`, { token: alice });
check("delete history event 204", r.status === 204, r);
r = await call("DELETE", `/api/v1/query-history/${eventId}`, { token: alice });
check("delete again 404", r.status === 404, r);

r = await call("GET", "/api/v1/users", { token: alice });
check("non-admin users list 403", r.status === 403, r);
r = await call("GET", "/api/v1/users", { token: admin });
check("admin users list", r.status === 200 && r.data.length === 3 && !("hashed_password" in r.data[0]), r);
r = await call("PUT", "/api/v1/users/bob/role?new_role=viewer", { token: admin });
check("set bob viewer", r.status === 200, r);
r = await call("POST", "/api/v1/documents", { token: bob, form: fileForm("policy.txt", "text/plain") });
check("viewer cannot upload 403", r.status === 403 && r.data.detail === "User privileges required", r);
r = await call("PUT", "/api/v1/users/bob/disable?disabled=true", { token: admin });
check("disable bob", r.status === 200, r);
r = await call("GET", "/api/v1/documents", { token: bob });
check("disabled user 403", r.status === 403 && r.data.detail === "User account is disabled", r);

r = await call("DELETE", `/api/v1/documents/${uploads["bill.pdf"].id}`, { token: bob });
check("disabled bob can't delete", r.status === 403, r);
r = await call("DELETE", `/api/v1/documents/${uploads["bill.pdf"].id}`, { token: alice });
check("alice deletes bill 204", r.status === 204, r);
r = await call("DELETE", "/api/v1/documents", { token: alice });
check("non-admin delete-all 403", r.status === 403, r);
r = await call("DELETE", "/api/v1/documents", { token: admin });
check("admin delete-all", r.status === 200 && r.data.deleted_count === 3, r);
r = await call("GET", "/api/v1/nope", { token: admin });
check("unknown route 404", r.status === 404 && r.data.detail === "Not Found", r);

for (let i = 0; i < 9; i++) await call("POST", "/api/v1/auth/login", { json: { username: "x", password: "y" } });
r = await call("POST", "/api/v1/auth/login", { json: { username: "x", password: "y" } });
check("login rate limit kicks in", r.status === 429, r);

await pg.stop();
console.log(failures ? `\n${failures} FAILURE(S)` : "\nALL PASSED");
process.exit(failures ? 1 : 0);
