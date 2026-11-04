import type { Config, Context } from "@netlify/functions";
import { handle } from "../../lib/app.js";

// One function serves the whole DocuTrust API (ported from the FastAPI backend).
export default async (req: Request, context: Context) => handle(req, context.ip);

export const config: Config = {
  path: ["/api/*", "/health"],
};
