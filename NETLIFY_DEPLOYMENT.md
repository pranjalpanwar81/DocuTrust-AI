# Netlify Deployment

DocuTrust AI runs entirely on Netlify:

| Piece | Where it lives |
|---|---|
| Frontend | `app/static/` (copied to `web/public/` at build time) |
| API | `web/netlify/functions/api.mts` serving `/api/*` and `/health` |
| Logic | `web/lib/` (TypeScript port of `app/*.py`: retrieval, extraction, auth, synthesis) |
| Database | Netlify Database (Postgres), schema in `web/netlify/database/migrations/` |

`netlify.toml` sets the base directory to `web/`, so the root Python files are ignored by Netlify.
The original FastAPI backend in `app/` still runs locally with `./start.sh` for comparison.

## Deploying

Every push to `main` builds and deploys. Migrations are applied automatically before the deploy is published.

## Environment variables (optional)

Set these under **Project configuration → Environment variables** (scope: Functions), then redeploy.

| Variable | Purpose |
|---|---|
| `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Creates the first admin account when the database has no users. Public registration only creates regular users. |
| `OPENAI_API_KEY` | Enables LLM-written answers. Without it, answers are copied deterministically from the retrieved evidence. |
| `OPENAI_BASE_URL`, `OPENAI_MODEL` | Any OpenAI-compatible endpoint/model (defaults: `https://api.openai.com/v1`, `gpt-4.1-mini`). |
| `JWT_SECRET_KEY` | Optional override. If unset, a random signing key is generated once and stored in the database. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Login session length (default 30). |
| `RETRIEVAL_THRESHOLD` | Minimum confidence for a grounded answer (default 0.12). |
| `MAX_UPLOAD_BYTES` | Upload limit (default 4 MB). |

## Differences from the Render/FastAPI version

- **Upload size:** Netlify Functions accept request bodies up to ~4.5 MB of binary data, so the default limit is 4 MB (was 15 MB).
- **OCR:** images are read with tesseract.js using a bundled English model (same file types as before).
- **Rate limits:** enforced per function instance, so they are best-effort under load.
- **Passwords** are hashed with bcrypt. Accounts from the old Render database were not migrated.

## Local check

```bash
cd web && npm install && npx tsc --noEmit
```

`netlify dev` (Netlify CLI ≥ 26) runs the functions and a local database together.
