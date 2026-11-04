// Port of app/extraction.py: PDF, DOCX, TXT/MD and image OCR text extraction.
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import type { ExtractedPage } from "./retrieval.js";

export class ExtractionError extends Error {}

function ocrLanguagePath(): string {
  const require = createRequire(import.meta.url);
  return join(dirname(require.resolve("@tesseract.js-data/eng/package.json")), "4.0.0_best_int");
}

export function sanitizeFilename(filename: string): string {
  const name = (filename || "upload").split(/[\\/]/).pop() || "upload";
  return name.replace(/[^A-Za-z0-9._ -]/g, "_").slice(0, 120);
}

function suffixOf(filename: string): string {
  const match = /(\.[^./\\]*)$/.exec(filename);
  return match ? match[1].toLowerCase() : "";
}

export async function extractPages(filename: string, data: Uint8Array): Promise<[ExtractedPage[], string]> {
  const suffix = suffixOf(filename);
  if (suffix === ".pdf") {
    const { extractText, getDocumentProxy } = await import("unpdf");
    let pageTexts: string[];
    try {
      const pdf = await getDocumentProxy(new Uint8Array(data));
      const result = await extractText(pdf, { mergePages: false });
      pageTexts = result.text as string[];
    } catch (error) {
      throw new ExtractionError(`The PDF could not be read: ${(error as Error).message}`);
    }
    return [nonempty(pageTexts.map((text, index) => ({ page_number: index + 1, text: text || "", section: null }))), "native_pdf"];
  }
  if (suffix === ".docx") {
    const mammoth = (await import("mammoth")).default;
    let raw: string;
    try {
      raw = (await mammoth.extractRawText({ buffer: Buffer.from(data) })).value;
    } catch (error) {
      throw new ExtractionError(`The DOCX file could not be read: ${(error as Error).message}`);
    }
    const text = raw.split("\n").filter((line) => line.trim()).join("\n");
    return [nonempty([{ page_number: 1, text, section: null }]), "native_docx"];
  }
  if (suffix === ".txt" || suffix === ".md") {
    return [nonempty([{ page_number: 1, text: new TextDecoder("utf-8").decode(data), section: null }]), "plain_text"];
  }
  if ([".png", ".jpg", ".jpeg", ".tiff", ".bmp"].includes(suffix)) {
    let text: string;
    try {
      const { createWorker } = await import("tesseract.js");
      const worker = await createWorker("eng", 1, {
        // English model ships with the function (no CDN download at runtime).
        langPath: ocrLanguagePath(),
        cacheMethod: "none",
        // Without this, worker errors are re-thrown as uncaught exceptions and
        // crash the whole function instead of rejecting this promise.
        errorHandler: () => {},
      });
      try {
        text = (await worker.recognize(Buffer.from(data))).data.text;
      } finally {
        await worker.terminate();
      }
    } catch (error) {
      throw new ExtractionError(`Image OCR failed: ${(error as Error)?.message ?? String(error)}`);
    }
    return [nonempty([{ page_number: 1, text, section: null }]), "tesseract_ocr"];
  }
  throw new ExtractionError("Supported file types are PDF, DOCX, TXT, MD, PNG, JPG, JPEG, TIFF, and BMP.");
}

function nonempty(pages: ExtractedPage[]): ExtractedPage[] {
  const usable = pages.filter((page) => page.text.trim());
  if (!usable.length) {
    throw new ExtractionError("No machine-readable text was found. Use an OCR-enabled deployment for scanned files.");
  }
  return usable;
}
