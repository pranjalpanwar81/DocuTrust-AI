// Port of app/synthesis.py: optional grounded synthesis via an
// OpenAI-compatible chat-completions endpoint, with safe fallbacks.
import type { Evidence } from "./retrieval.js";
import { settings } from "./config.js";

export interface SynthesisResult {
  text: string | null;
  source: "llm" | "fallback";
  error: string | null;
}

export async function synthesize(question: string, evidence: Evidence[]): Promise<SynthesisResult> {
  const { openaiApiKey, openaiBaseUrl, openaiModel } = settings();
  if (!openaiApiKey) {
    console.info("LLM synthesis skipped: OPENAI_API_KEY is not configured.");
    return { text: null, source: "fallback", error: "api_key_missing" };
  }
  const sources = evidence
    .map((item, index) => `[S${index + 1}] ${item.document_name}, page ${item.page}\n${item.text}`)
    .join("\n\n");
  const prompt =
    "Answer only from the sources below. Do not use outside knowledge. " +
    "If the sources do not establish the answer, reply exactly: INSUFFICIENT_EVIDENCE. " +
    "Use concise sentences and cite each claim as [S1], [S2], etc.\n\n" +
    `Question: ${question}\n\nSources:\n${sources}`;
  const payload = {
    model: openaiModel,
    temperature: 0,
    messages: [
      { role: "system", content: "You are a compliance evidence assistant." },
      { role: "user", content: prompt },
    ],
  };
  const url = `${openaiBaseUrl.replace(/\/+$/, "")}/chat/completions`;

  let answer: string;
  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { Authorization: `Bearer ${openaiApiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) {
      const body = (await response.text()).slice(0, 240).replace(/\n/g, " ");
      console.warn(`LLM synthesis HTTP error ${response.status} (model=${openaiModel}): ${body}. Falling back.`);
      return { text: null, source: "fallback", error: `http_${response.status}` };
    }
    try {
      const data = await response.json();
      answer = String(data.choices[0].message.content).trim();
    } catch (error) {
      console.warn(`LLM synthesis returned an unexpected response shape: ${error}. Falling back.`);
      return { text: null, source: "fallback", error: "malformed_response" };
    }
  } catch (error) {
    const name = (error as Error).name;
    if (name === "TimeoutError" || name === "AbortError") {
      console.warn(`LLM synthesis timed out after 20s (model=${openaiModel}). Falling back.`);
      return { text: null, source: "fallback", error: "timeout" };
    }
    console.warn(`LLM synthesis network error (${openaiModel}): ${error}. Falling back.`);
    return { text: null, source: "fallback", error: "network_error" };
  }

  if (answer === "INSUFFICIENT_EVIDENCE") {
    console.info("LLM synthesis abstained: sources did not support the question.");
    return { text: null, source: "fallback", error: "llm_abstained" };
  }
  console.info(`LLM synthesis succeeded (model=${openaiModel}, answer_chars=${answer.length}).`);
  return { text: answer, source: "llm", error: null };
}
