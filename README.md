# ContractIQ — Agentic Contract Review

ContractIQ is a contract-review support application. It parses PDF/DOCX
contracts and reference policies, classifies clauses, compares policy
requirements, flags potential risks, compares contract versions, and stores
reviewer decisions. Automated results are evidence-linked prompts for human
review, not legal advice or a substitute for a qualified legal professional.

## Current capabilities

- PDF and DOCX text extraction with page, paragraph, and table locations.
- Clause classification, rule-based risk flags, and policy-rule extraction.
- Sentence Transformers embeddings with a FAISS similarity index to retrieve
  policy passages (RAG); the source quote and source location remain attached.
- Gemini API evidence review of preliminary findings (Ollama can also be
  selected for local inference). Returned quotations are checked against
  extracted source text before being marked verified; the LLM does not
  replace or override deterministic findings.
- Optional Redis cache for retrieved policy passages.
- Reviewer evidence checks, persistent review history, and recorded decisions.
- Text-level comparison of two PDF/DOCX contract versions with changed lines.
- JWT-protected API and a single reviewer account configured through
  environment variables.
- PDF review report generation.
- PostgreSQL for deployed review records; SQLite is used automatically for
  local development when `DATABASE_URL` is not set.

Policy rules are inferred using transparent text patterns and should be
validated against the uploaded reference policy. The deterministic reviewer
checks whether quoted text is present in extracted source text. When enabled,
the LLM reviewer assesses whether findings are supported by evidence; neither
mechanism establishes legal correctness.

## Run locally (Windows PowerShell)

1. From the project root, create/activate a virtual environment if needed and
   install backend dependencies:

   ```powershell
   .\.venv\Scripts\Activate.ps1
   pip install -r backend\requirements.txt
   ```

2. Copy `backend\.env.example` to `backend\.env`. Set a unique reviewer
   username/password and replace `JWT_SECRET_KEY` with a random secret of at
   least 32 characters. Local runs use SQLite by default. Set `REDIS_URL` only
   when a Redis server is available.

3. Start the API from the project root:

   ```powershell
   .\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload
   ```

   The API is at `http://127.0.0.1:8000`; interactive API docs are at
   `http://127.0.0.1:8000/docs`.

4. In another terminal, copy `frontend\.env.example` to `frontend\.env`, then
   start the frontend:

   ```powershell
   cd frontend
   npm install
   npm run dev
   ```

5. Sign in with the reviewer credentials in `backend\.env`. The
   `sentence-transformers/all-MiniLM-L6-v2` model is loaded on first policy
   comparison and may need to be downloaded once. To use Gemini, create an API
   key in Google AI Studio and set `GEMINI_API_KEY` in `backend\.env` (never
   paste it into chat or commit it). To use local Ollama instead, set
   `LLM_PROVIDER=ollama` and run
   `ollama pull llama3.2`.

## Configuration

| Variable | Purpose |
| --- | --- |
| `REVIEWER_USERNAME`, `REVIEWER_PASSWORD` | Single account allowed to use the API |
| `JWT_SECRET_KEY` | JWT signing key; use a secret value of 32+ characters |
| `JWT_ACCESS_TOKEN_MINUTES` | Token lifetime; defaults to 60 minutes |
| `DATABASE_URL` | PostgreSQL URL in production; omitted means local SQLite |
| `REDIS_URL` | Optional Redis connection used to cache semantic retrieval |
| `REDIS_CACHE_TTL_SECONDS` | Redis cache duration; defaults to 3600 seconds |
| `POLICY_EMBEDDING_MODEL` | Sentence Transformers model identifier or local model path |
| `LLM_PROVIDER` | `gemini`, `ollama`, or `disabled` |
| `GEMINI_API_KEY` | Google Gemini API key (required when provider is `gemini`) |
| `GEMINI_MODEL` | Gemini model; defaults to `gemini-3.8-flash` |
| `OLLAMA_BASE_URL` | Local Ollama endpoint; defaults to `http://127.0.0.1:11434` |
| `OLLAMA_MODEL` | Installed local model; defaults to `llama3.2` |
| `CORS_ORIGINS` | Comma-separated frontend origins allowed by the API |
| `VITE_API_BASE_URL` | Backend URL used by the Vite frontend |

The backend loads `backend\.env` for local development. With
`LLM_PROVIDER=gemini`, relevant contract and policy excerpts are sent to
Google's Gemini API for processing. Gemini API usage has free-tier quotas for
eligible projects/models, but availability and limits can change; usage may
be billable if the project has billing enabled or exceeds free allowances.
Check Google AI Studio/Google Cloud quota and billing for your API key. If
document data must not leave this machine, use `LLM_PROVIDER=ollama` with
Ollama running locally instead. Set `LLM_PROVIDER=disabled` to use deterministic
checks without an LLM assessment.

In production, set reviewer credentials, use a unique generated JWT secret,
provide the managed Redis URL, and restrict `CORS_ORIGINS` to the deployed
frontend origin. PostgreSQL URLs using `postgres://` or `postgresql://` are
normalized to the installed Psycopg 3 driver.

## Deployment

- **Backend (Render):** create a Blueprint from the repository root using
  [`render.yaml`](./render.yaml). It provisions the FastAPI web service and
  PostgreSQL; the database connection string is wired to `DATABASE_URL`, and
  a JWT signing secret is generated. Enter `REVIEWER_USERNAME`,
  `REVIEWER_PASSWORD`, `GEMINI_API_KEY`, `REDIS_URL`, and `CORS_ORIGINS` when
  prompted. The Render backend sends relevant excerpts to Gemini when enabled;
  review provider data handling and quota/billing settings before using real
  contracts. For
  `REDIS_URL`, first create a Render Key Value instance in the same region and
  use its **internal** connection URL. For `CORS_ORIGINS`, provide the exact
  Vercel deployment origin (for example, `https://your-project.vercel.app`).
  Keep reviewer credentials private and use a strong, unique password.
- **Frontend (Vercel):** import the repository and set the project root to
  `frontend`. Use the default Vite build command `npm run build` and output
  directory `dist`; [`vercel.json`](./frontend/vercel.json) configures SPA
  route fallback. Set `VITE_API_BASE_URL` to the deployed Render API origin
  (for example, `https://your-api.onrender.com`), then redeploy the frontend.
- **Deployment order:** create/import the Vercel project first to obtain its
  origin, create the Render Key Value instance, then create the Render
  Blueprint and supply those values. After both deploy, verify login, upload,
  review persistence, and browser CORS behavior. Do not commit `.env` files or
  put secret values in either deployment manifest.

This workspace has not been connected to a GitHub remote or deployment
account, so it does not claim live repository or deployment URLs. After
publishing, add the actual GitHub, Render, and Vercel URLs here.

## Validation

From the project root:

```powershell
.\.venv\Scripts\python.exe -m pytest backend\tests -q
cd frontend
npm run build
npm run lint
```

## API overview

- `POST /api/v1/auth/token` — exchange reviewer credentials for a JWT.
- `POST /api/v1/documents/compare-uploaded-policy` — analyze contract against
  an uploaded policy and persist a review.
- `POST /api/v1/documents/compare-versions` — compare old and new contract
  files, returning changed text and 1-based extracted-text line ranges.
- `GET /api/v1/reviews` and `GET /api/v1/reviews/{analysis_id}` — review
  history.
- `PUT /api/v1/reviews/{analysis_id}/{item_id}` — save a reviewer decision.
- `POST /api/v1/documents/compare-uploaded-policy-report` — download a PDF
  report.

All `/api/v1` routes other than token issuance require
`Authorization: Bearer <token>`. Health and root endpoints remain public.
