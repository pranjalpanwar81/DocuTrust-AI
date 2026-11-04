// Port of app/database.py onto Netlify Database (managed Postgres).
import { getDatabase } from "@netlify/database";
import { randomUUID } from "node:crypto";

type Row = Record<string, any>;
interface Queryable {
  query(text: string, params?: unknown[]): Promise<{ rows: Row[]; rowCount: number | null }>;
}

let pool: (Queryable & { connect(): Promise<Queryable & { release(): void }> }) | null = null;

function db() {
  if (!pool) {
    // TEST_DATABASE_URL lets the local test harness point at a throwaway Postgres.
    const connectionString = process.env.TEST_DATABASE_URL;
    pool = getDatabase(connectionString ? { connectionString } : undefined).pool as any;
  }
  return pool!;
}

async function q(text: string, params: unknown[] = []): Promise<Row[]> {
  return (await db().query(text, params)).rows;
}

async function affected(text: string, params: unknown[] = []): Promise<number> {
  return (await db().query(text, params)).rowCount ?? 0;
}

function isUniqueViolation(error: unknown): boolean {
  const code = (error as { code?: string })?.code;
  return code === "23505" || code === "23503"; // unique / foreign-key violation
}

const DOC_COLUMNS = `d.id, d.filename, d.media_type, d.uploaded_at, d.page_count, d.extraction_method, d.owner_username, d.is_public, COUNT(c.id)::int AS chunk_count`;

export async function addDocument(record: Row, chunks: Row[]): Promise<void> {
  const client = await db().connect();
  try {
    await client.query("BEGIN");
    await client.query(
      "INSERT INTO documents (id, filename, media_type, uploaded_at, page_count, extraction_method, owner_username, is_public) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)",
      [record.id, record.filename, record.media_type, record.uploaded_at, record.page_count, record.extraction_method, record.owner_username, record.is_public],
    );
    // Insert chunks in batches to stay well under Postgres' parameter limit.
    for (let i = 0; i < chunks.length; i += 500) {
      const batch = chunks.slice(i, i + 500);
      const params: unknown[] = [];
      const values = batch.map((chunk, j) => {
        params.push(chunk.id, chunk.document_id, chunk.page_number, chunk.section, chunk.text);
        const base = j * 5;
        return `($${base + 1}, $${base + 2}, $${base + 3}, $${base + 4}, $${base + 5})`;
      });
      await client.query(`INSERT INTO chunks (id, document_id, page_number, section, text) VALUES ${values.join(", ")}`, params);
    }
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
}

export async function listDocuments(): Promise<Row[]> {
  return q(`SELECT ${DOC_COLUMNS} FROM documents d LEFT JOIN chunks c ON c.document_id = d.id GROUP BY d.id ORDER BY d.uploaded_at DESC`);
}

export async function documentCount(): Promise<number> {
  return (await q("SELECT COUNT(*)::int AS n FROM documents"))[0].n;
}

/** Chunks (with filename) restricted to the given document ids. */
export async function chunksForDocuments(documentIds: string[]): Promise<Row[]> {
  if (!documentIds.length) return [];
  return q(
    "SELECT c.id, c.document_id, c.page_number, c.section, c.text, d.filename FROM chunks c JOIN documents d ON c.document_id = d.id WHERE c.document_id = ANY($1::text[]) ORDER BY c.seq",
    [documentIds],
  );
}

export async function addQueryEvent(record: Row): Promise<void> {
  await q("INSERT INTO query_events (id, created_at, question, answer_status, confidence, citation_ids, username) VALUES ($1, $2, $3, $4, $5, $6, $7)", [
    record.id,
    record.created_at,
    record.question,
    record.answer_status,
    record.confidence,
    JSON.stringify(record.citation_ids),
    record.username ?? null,
  ]);
}

export async function deleteDocument(documentId: string): Promise<boolean> {
  if (!(await q("SELECT 1 FROM documents WHERE id = $1", [documentId])).length) return false;
  const client = await db().connect();
  try {
    await client.query("BEGIN");
    await client.query("DELETE FROM document_permissions WHERE document_id = $1", [documentId]);
    await client.query("DELETE FROM chunks WHERE document_id = $1", [documentId]);
    await client.query("DELETE FROM documents WHERE id = $1", [documentId]);
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
  return true;
}

export async function deleteAllDocuments(): Promise<number> {
  const count = await documentCount();
  const client = await db().connect();
  try {
    await client.query("BEGIN");
    await client.query("DELETE FROM document_permissions");
    await client.query("DELETE FROM chunks");
    await client.query("DELETE FROM documents");
    await client.query("COMMIT");
  } catch (error) {
    await client.query("ROLLBACK");
    throw error;
  } finally {
    client.release();
  }
  return count;
}

export async function recentQueryEvents(limit = 8): Promise<Row[]> {
  const rows = await q("SELECT id, created_at, question, answer_status, confidence, citation_ids, username FROM query_events ORDER BY created_at DESC LIMIT $1", [limit]);
  return rows.map((row) => ({ ...row, citation_ids: JSON.parse(row.citation_ids) }));
}

export async function deleteQueryEvent(eventId: string): Promise<boolean> {
  return (await affected("DELETE FROM query_events WHERE id = $1", [eventId])) > 0;
}

function pyRound2(value: number): number {
  return Math.round((value + Number.EPSILON) * 100) / 100;
}

export async function analytics(): Promise<Row> {
  const [counts] = await q(
    `SELECT (SELECT COUNT(*)::int FROM documents) AS document_count,
            (SELECT COUNT(*)::int FROM chunks) AS chunk_count,
            COUNT(*)::int AS query_count,
            AVG(confidence)::float8 AS average_confidence,
            COALESCE(SUM(CASE WHEN answer_status = 'grounded' THEN 1 ELSE 0 END), 0)::int AS grounded_count
       FROM query_events`,
  );
  return {
    document_count: counts.document_count,
    chunk_count: counts.chunk_count,
    query_count: counts.query_count,
    average_confidence: pyRound2(counts.average_confidence || 0),
    grounded_rate: pyRound2(counts.query_count ? counts.grounded_count / counts.query_count : 0),
  };
}

export async function createUser(username: string, email: string, hashedPassword: string, role = "user"): Promise<boolean> {
  try {
    await q("INSERT INTO users (username, email, hashed_password, role, created_at) VALUES ($1, $2, $3, $4, $5)", [username, email, hashedPassword, role, new Date().toISOString()]);
    return true;
  } catch (error) {
    if (isUniqueViolation(error)) return false;
    throw error;
  }
}

export async function getUser(username: string): Promise<Row | null> {
  return (await q("SELECT * FROM users WHERE username = $1", [username]))[0] ?? null;
}

export async function getAllUsers(): Promise<Row[]> {
  return q("SELECT username, email, role, disabled, created_at FROM users");
}

export async function hasUsers(): Promise<boolean> {
  return (await q("SELECT 1 FROM users LIMIT 1")).length > 0;
}

export async function updateUserRole(username: string, role: string): Promise<boolean> {
  return (await affected("UPDATE users SET role = $1 WHERE username = $2", [role, username])) > 0;
}

export async function disableUser(username: string, disabled = true): Promise<boolean> {
  return (await affected("UPDATE users SET disabled = $1 WHERE username = $2", [disabled ? 1 : 0, username])) > 0;
}

export async function grantDocumentPermission(documentId: string, username: string, level = "read"): Promise<boolean> {
  try {
    await q("INSERT INTO document_permissions (id, document_id, username, permission_level, granted_at) VALUES ($1, $2, $3, $4, $5)", [randomUUID(), documentId, username, level, new Date().toISOString()]);
    return true;
  } catch (error) {
    if (isUniqueViolation(error)) return false;
    throw error;
  }
}

export async function revokeDocumentPermission(documentId: string, username: string): Promise<boolean> {
  return (await affected("DELETE FROM document_permissions WHERE document_id = $1 AND username = $2", [documentId, username])) > 0;
}

export async function getUserAccessibleDocuments(username: string, role: string): Promise<Row[]> {
  if (role === "admin") return listDocuments();
  return q(
    `SELECT ${DOC_COLUMNS} FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
      WHERE d.owner_username = $1 OR d.is_public = 1 OR d.id IN (SELECT document_id FROM document_permissions WHERE username = $1)
      GROUP BY d.id ORDER BY d.uploaded_at DESC`,
    [username],
  );
}

export async function checkDocumentAccess(documentId: string, username: string, role: string): Promise<boolean> {
  if (role === "admin") return true;
  const rows = await q(
    `SELECT 1 FROM documents d WHERE d.id = $1 AND (d.owner_username = $2 OR d.is_public = 1 OR d.id IN (SELECT document_id FROM document_permissions WHERE username = $2))`,
    [documentId, username],
  );
  return rows.length > 0;
}

/** Return a stored setting, creating it with `initial()` if it does not exist yet. */
export async function getOrCreateSetting(key: string, initial: () => string): Promise<string> {
  await q("INSERT INTO app_settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING", [key, initial()]);
  return (await q("SELECT value FROM app_settings WHERE key = $1", [key]))[0].value;
}
