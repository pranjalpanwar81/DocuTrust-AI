// TypeScript port of app/retrieval.py. Behaviour is kept identical to the
// original Python so answers, scores and corrections match the old backend.
import { getCloseMatches } from "./difflib.js";

export interface ExtractedPage {
  page_number: number;
  text: string;
  section: string | null;
}

export interface ChunkRow {
  id: string;
  document_id: string;
  page_number: number;
  section: string | null;
  text: string;
  filename: string;
}

export interface Evidence {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page: number;
  text: string;
  score: number;
  section: string | null;
}

const TOKEN = /[a-zA-Z0-9]{2,}/g;
const STOPWORDS = new Set(["the", "is", "are", "was", "were", "what", "who", "when", "where", "why", "how", "with", "from", "that", "this", "for", "and", "or", "of", "to", "in", "on", "by", "at", "be", "an", "a"]);
const DATE_RANGE = /(\d{1,2}-[A-Za-z]{3}-\d{4})\s+to\s+(\d{1,2}-[A-Za-z]{3}-\d{4})/i;
const MONEY_SOURCE = String.raw`(?:€|₹|\$)\s?\d+(?:[.,]\d{2})|(?:Rs\.?\s*)\d+(?:[.,]\d{2})?`;
const BILL_TERMS = new Set(["amount", "bill", "total", "due", "invoice", "period", "payment", "price", "cost"]);
const QUERY_ALIASES: Record<string, string> = {
  price: "amount",
  cost: "amount",
  student: "name",
  applicant: "name",
  candidate: "name",
  university: "education",
  college: "education",
  technology: "skills",
  technologies: "skills",
  technologi: "skills",
  tech: "skills",
  job: "experience",
  work: "experience",
};
const LABELED_FIELDS: Array<[string, RegExp]> = [
  ["email", /\b(?:email|e-mail)\s*[:\-]\s*([^|;\n]+)/i],
  ["phone", /\b(?:phone|mobile|contact)\s*[:\-]?\s*([+()\d][^|;\n]+)/i],
  ["skills", /\b(?:skills|technical skills|technologies)\s*[:\-]\s*([^|;\n]+)/i],
  ["education", /\b(?:education|qualification|degree)\s*[:\-]\s*([^|;\n]+)/i],
  ["experience", /\b(?:experience|work experience|employment)\s*[:\-]\s*([^|;\n]+)/i],
  ["projects", /\bprojects?\s*[:\-]\s*([^|;\n]+)/i],
];
const NAME_FIELD = new RegExp(
  String.raw`\b(?:student\s+name|applicant\s+name|candidate\s+name|full\s+name|name)\s*[:\-]\s*` +
    String.raw`([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})` +
    String.raw`(?=\s*(?:\||$|,|;|\n|email\b|e-mail\b|phone\b|mobile\b|contact\b|linkedin\b|github\b))`,
  "i",
);
// Python's `^` without MULTILINE anchors at the start of the string only.
const NAME_HEADER = new RegExp(
  String.raw`^\s*([A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3})` +
    String.raw`(?=\s+(?:email|e-mail|phone|mobile|contact|linkedin|github)\b|\s*\||` +
    String.raw`\s+(?:projects|education|skills|experience|summary|objective|certifications)\b)`,
  "i",
);
const IDENTITY_TERMS = new Set(["name", "named"]);
const FILENAME_NAME_WORDS = new Set(["resume", "cv", "curriculum", "vitae", "profile", "applicant", "candidate", "student", "name"]);

/** Python's str.split() + " ".join(): collapse all whitespace runs. */
function collapse(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(" ");
}

export function chunkPages(documentId: string, pages: ExtractedPage[], chunkSize = 900, overlap = 150) {
  const chunks: Array<{ id: string; document_id: string; page_number: number; section: string | null; text: string }> = [];
  for (const page of pages) {
    const text = collapse(page.text);
    let start = 0;
    let part = 0;
    while (start < text.length) {
      let end = Math.min(text.length, start + chunkSize);
      if (end < text.length) {
        // Python: text.rfind(". ", start, end) + 1 or end
        const idx = end - 2 >= start ? text.lastIndexOf(". ", end - 2) : -1;
        const found = idx >= start ? idx : -1;
        end = found + 1 || end;
      }
      const value = text.slice(start, end).trim();
      if (value) {
        chunks.push({ id: `${documentId}:p${page.page_number}:c${part}`, document_id: documentId, page_number: page.page_number, section: page.section, text: value });
        part++;
      }
      if (end >= text.length) break;
      start = Math.max(end - overlap, start + 1);
    }
  }
  return chunks;
}

function counter(tokens: string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const token of tokens) counts.set(token, (counts.get(token) ?? 0) + 1);
  return counts;
}

export function retrieve(question: string, rows: ChunkRow[], limit = 5): Evidence[] {
  const query = expandedQueryTokens(question, rows);
  if (!query.length || !rows.length) return [];
  const identityQuestion = isIdentityQuestion(question, query);
  const billQuestion = query.some((token) => BILL_TERMS.has(token));
  const docCount = rows.length;
  const rowTokens = rows.map((row) => tokens(row.text));
  const rowTokenSets = rowTokens.map((list) => new Set(list));
  const documentFrequency = new Map<string, number>();
  for (const token of query) {
    documentFrequency.set(token, rowTokenSets.reduce((sum, set) => sum + (set.has(token) ? 1 : 0), 0));
  }
  const results: Evidence[] = [];
  const filenameFallbackDocuments = new Set<string>();
  rows.forEach((row, index) => {
    const rowTokenList = rowTokens[index];
    let personName: string | null = null;
    if (identityQuestion) {
      personName = extractPersonName(row.text);
      if (!personName && !filenameFallbackDocuments.has(row.document_id)) {
        personName = extractPersonNameFromFilename(row.filename);
        if (personName) filenameFallbackDocuments.add(row.document_id);
      }
    }
    if (identityQuestion && !personName) return;
    const frequencies = counter(rowTokenList);
    // The +1 inside log preserves useful scores for a one-document demo corpus.
    let score = 0;
    for (const token of query) {
      score += ((frequencies.get(token) ?? 0) / Math.max(1, rowTokenList.length)) * Math.log(1 + docCount / ((documentFrequency.get(token) ?? 0) + 1));
    }
    if (billQuestion && billFields(row.text).length) score = Math.max(score, 0.02);
    if (score > 0 || personName) {
      if (personName) score = Math.max(score, 0.2);
      results.push({
        chunk_id: row.id,
        document_id: row.document_id,
        document_name: row.filename,
        page: row.page_number,
        text: row.text,
        score,
        section: row.section,
      });
    }
  });
  // Array.prototype.sort is stable, like Python's sorted().
  return results.sort((a, b) => b.score - a.score).slice(0, limit);
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function correctedQuestion(question: string, rows: ChunkRow[]): [string, Array<{ original: string; corrected: string }>] {
  const [, corrections] = correctedTokens(question, rows);
  let updated = question;
  for (const correction of corrections) {
    updated = updated.replace(new RegExp(String.raw`\b${escapeRegExp(correction.original)}\b`, "i"), () => correction.corrected);
  }
  return [updated, corrections];
}

export function correctedTokens(question: string, rows: ChunkRow[]): [string[], Array<{ original: string; corrected: string }>] {
  const query = tokens(question);
  if (!query.length || !rows.length) return [query, []];
  const vocabulary = new Set<string>();
  for (const row of rows) for (const token of tokens(row.text)) vocabulary.add(token);
  const corrected: string[] = [];
  const corrections: Array<{ original: string; corrected: string }> = [];
  for (const token of query) {
    if (vocabulary.has(token) || token.length < 4 || /^\d+$/.test(token)) {
      corrected.push(token);
      continue;
    }
    const candidate = getCloseMatches(token, vocabulary, 1, 0.82);
    if (candidate.length) {
      corrected.push(candidate[0]);
      corrections.push({ original: token, corrected: candidate[0] });
    } else {
      corrected.push(token);
    }
  }
  return [corrected, corrections];
}

/** Python round() uses banker's rounding; mirror it for stable confidence values. */
export function pyRound(value: number, digits: number): number {
  const factor = 10 ** digits;
  const scaled = value * factor;
  const floor = Math.floor(scaled);
  const diff = scaled - floor;
  const EPS = 1e-9;
  let rounded: number;
  if (Math.abs(diff - 0.5) < EPS) rounded = floor % 2 === 0 ? floor : floor + 1;
  else rounded = Math.round(scaled);
  return rounded / factor;
}

export function confidence(evidence: Evidence[]): number {
  if (!evidence.length) return 0.0;
  return pyRound(Math.min(1.0, evidence[0].score * 9), 2);
}

export function focusedExcerpt(question: string, text: string, maxLength = 300): string {
  const normalized = collapse(text);
  const fields = billFields(normalized);
  const queryWords = new Set(tokens(question));
  if (fields.length && [...queryWords].some((word) => BILL_TERMS.has(word))) return formatFields(fields);
  const dateMatch = DATE_RANGE.exec(normalized);
  if (dateMatch && tokens(question).some((word) => ["date", "valid", "validity", "period", "until", "tax"].includes(word))) {
    return `Tax period: ${dateMatch[1]} to ${dateMatch[2]}.`;
  }
  const fragments = normalized.split(/(?<=[.!?])\s+|(?<=;)\s+/);
  let best = normalized;
  let bestScore = -1;
  for (const fragment of fragments) {
    const fragmentTokens = new Set(tokens(fragment));
    let overlap = 0;
    for (const word of queryWords) if (fragmentTokens.has(word)) overlap++;
    if (overlap > bestScore) {
      best = fragment;
      bestScore = overlap;
    }
  }
  if (best.length <= maxLength) return best;
  const cut = best.slice(0, maxLength);
  const space = cut.lastIndexOf(" ");
  return (space >= 0 ? cut.slice(0, space) : cut) + "…";
}

export function conciseAnswer(question: string, evidence: Evidence[]): string {
  const top = evidence[0];
  if (isIdentityQuestion(question, tokens(question))) {
    const personName = extractPersonName(top.text) ?? extractPersonNameFromFilename(top.document_name);
    if (personName) return `Student name: ${personName}.`;
  }
  const labeled = extractLabeledAnswer(question, top.text);
  if (labeled) return labeled;
  const fields = billFields(collapse(top.text));
  const questionWords = new Set(tokens(question));
  if (fields.length && [...questionWords].some((word) => BILL_TERMS.has(word))) return `Bill details\n${formatFields(fields)}`;
  const dateMatch = DATE_RANGE.exec(collapse(top.text));
  if (dateMatch && ["date", "valid", "validity", "period", "until", "tax"].some((word) => questionWords.has(word))) {
    return `The tax is valid until ${dateMatch[2]}.\n\nValidity period: ${dateMatch[1]} to ${dateMatch[2]}.`;
  }
  return `Most relevant information:\n${focusedExcerpt(question, top.text)}`;
}

export function billFields(text: string): Array<[string, string]> {
  const fields: Array<[string, string]> = [];
  const invoice = /Invoice Number\s+([A-Za-z0-9-]+)/i.exec(text);
  const period = /Billing Period\s+(.+?)(?=\s+Invoice Date|$)/i.exec(text);
  const due = /Payment Due Date\s+(\d{1,2}[/-]\d{1,2}[/-]\d{4})/i.exec(text);
  const totals: string[] = [];
  for (const match of text.matchAll(/Total Amount/gi)) {
    const end = match.index! + match[0].length;
    const values = text.slice(end, end + 110).match(new RegExp(MONEY_SOURCE, "gi"));
    if (values && values.length) totals.push(values[values.length - 1]);
  }
  if (invoice) fields.push(["Invoice number", invoice[1]]);
  if (period) fields.push(["Billing period", period[1].trim()]);
  if (due) fields.push(["Payment due date", due[1]]);
  if (totals.length) fields.push(["Total amount", totals[totals.length - 1]]);
  return fields;
}

function formatFields(fields: Array<[string, string]>): string {
  return fields.map(([label, value]) => `${label}: ${value}`).join("\n");
}

export function extractPersonName(text: string): string | null {
  const match = NAME_FIELD.exec(text) ?? NAME_HEADER.exec(text);
  return match ? collapse(match[1]) : null;
}

export function extractPersonNameFromFilename(filename: string): string | null {
  const stem = (filename || "").replace(/\.[A-Za-z0-9]+$/, "");
  const words = stem.split(/[_\-\s]+/).filter(Boolean);
  const nameWords = words.filter((word) => !FILENAME_NAME_WORDS.has(word.toLowerCase()));
  if (nameWords.length < 2 || nameWords.length > 4) return null;
  if (!nameWords.every((word) => /^[A-Za-z][A-Za-z.' ]*$/.test(word))) return null;
  // Python str.capitalize(): first char upper, rest lower.
  return nameWords.map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()).join(" ");
}

function expandedQueryTokens(question: string, rows: ChunkRow[]): string[] {
  const corrected = correctedTokens(question, rows)[0];
  const expanded = [...corrected];
  for (const token of corrected) {
    const alias = QUERY_ALIASES[token];
    const normalizedAlias = alias ? normalize(alias) : null;
    if (normalizedAlias && !expanded.includes(normalizedAlias)) expanded.push(normalizedAlias);
  }
  return expanded;
}

function extractLabeledAnswer(question: string, text: string): string | null {
  const questionTokens = new Set(tokens(question));
  for (const [field, pattern] of LABELED_FIELDS) {
    if (!questionTokens.has(field) && ![...questionTokens].some((token) => QUERY_ALIASES[token] === field)) continue;
    const match = pattern.exec(text);
    if (match) {
      const value = collapse(match[1]).replace(/^[ .,;|]+|[ .,;|]+$/g, "");
      if (value) return `${field.charAt(0).toUpperCase()}${field.slice(1)}: ${value}.`;
    }
  }
  return null;
}

export function isIdentityQuestion(question: string, _queryTokens: string[]): boolean {
  const originalTokens = tokens(question);
  if (originalTokens.some((token) => IDENTITY_TERMS.has(token))) return true;
  for (const token of originalTokens) {
    if (getCloseMatches(token, IDENTITY_TERMS, 1, 0.72).length) return true;
  }
  return false;
}

export function tokens(text: string): string[] {
  const out: string[] = [];
  for (const match of text.matchAll(TOKEN)) {
    const normalized = normalize(match[0]);
    if (!STOPWORDS.has(normalized)) out.push(normalized);
  }
  return out;
}

function normalize(token: string): string {
  const value = token.toLowerCase();
  for (const suffix of ["ing", "ed", "es", "s"]) {
    if (value.endsWith(suffix) && value.length > suffix.length + 3) return value.slice(0, -suffix.length);
  }
  return value;
}
