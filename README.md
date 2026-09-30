# Prashna

**Know what to study. Understand it. Recall it. Revise it.** Prashna is a mobile-first UPSC learning platform, with current affairs as one learning module. It uses Supabase Auth for accounts, FastAPI for authenticated APIs, and PostgreSQL for persistent user data. The live current-affairs feed continues to ingest official publisher RSS/Atom items, screen them for UPSC relevance, deduplicate related reports, and generate structured study notes during ingestion. The subject/topic catalog and representative demo lessons are seeded by Alembic; demo learning material is labeled and is not official UPSC content.

## Local setup

Requirements: Node.js 20+, Python 3.11+, and a Supabase project for signup/login and persistent user accounts. The API can use local SQLite for development. No Gemini key is required: the backend automatically uses its mock processor when the key is missing.

1. Copy `.env.example` to `.env` in the project root. From Supabase **Project Settings → API**, copy the project URL and publishable/anon key into `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`. Set `SUPABASE_URL` to the same URL. The publishable/anon key is browser-safe; do not use a service-role or secret key in the frontend.
2. In Supabase **Authentication → URL Configuration**, set the local Site URL to `http://localhost:5173` and add `http://localhost:5173/**` to the redirect URL allow list. Email/password sign-in is enabled by default; configure SMTP/email confirmation there if you want verification emails to be reliably delivered.
3. Install frontend dependencies and start Vite in terminal 1 (from the project root):

   ```bash
   npm install
   npm run dev
   ```

   Open <http://localhost:5173>.

4. Create and activate a Python virtual environment, install backend dependencies, and start FastAPI in terminal 2 (commands below are from the project root):

   ```powershell
   py -3.11 -m venv backend/.venv
   .\backend\.venv\Scripts\Activate.ps1
   python -m pip install -r backend/requirements.txt
   cd backend
   alembic upgrade head
   python -m app.seed
   uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

   On macOS/Linux, activate with `source backend/.venv/bin/activate`, then run the same install command. If your shell is in `backend/`, use `pip install -r requirements.txt` instead. API docs are at <http://localhost:8000/docs>.

5. For actual multi-user persistence locally, use a Supabase PostgreSQL database rather than SQLite. Set the backend-only `DATABASE_URL` to the Supabase **Session pooler** connection URI (copy from **Connect** in the Supabase dashboard; use the URI format accepted by `psycopg`, commonly `postgresql://...`). Then run migrations from `backend/` with `alembic upgrade head`. The migration creates the app tables, links profiles to Supabase Auth users, and enables owner-only RLS policies. Use the database password in the server-only URL; never commit it.

For a no-cloud UI/API smoke run, leave the Supabase client values blank. The app displays the authentication setup screen and the public sample feed API remains accessible, but account-backed learning features require Supabase Auth.

## Environment variables

| Variable | Put it in | Purpose |
| --- | --- | --- |
| `VITE_SUPABASE_URL` | Vercel and local root `.env` | Supabase project URL; browser safe |
| `VITE_SUPABASE_ANON_KEY` | Vercel and local root `.env` | Publishable/anon key; browser safe, protected by Auth/RLS |
| `VITE_API_URL` | Vercel and local root `.env` | Public base URL of the FastAPI service |
| `SUPABASE_URL` | Render/backend only | Supabase issuer used to validate access tokens |
| `DATABASE_URL` | Render/backend only | PostgreSQL connection URI (or local SQLite URI) |
| `CORS_ORIGINS` | Render/backend only | Comma-separated exact frontend origins, including the production Vercel domain |
| `GEMINI_API_KEY` | Optional, Render/backend only | Gemini key used only during content ingestion |
| `LLM_PROVIDER` | Render/backend only | `gemini` (default) or `mock` |
| `CRON_SECRET` | Render/backend and GitHub Actions secret | Shared secret protecting scheduled refresh endpoints; never expose to Vite |
| `NEWS_RSS_FEEDS` | Optional, Render/backend only | Semicolon-separated `Name|https://feed.xml|priority` source overrides |
| `ADMIN_USER_IDS` | Render/backend only | Optional comma-separated Supabase UUIDs permitted to ingest content |
| `SUPABASE_JWT_SECRET` | Optional, backend only | Legacy HS256 JWT verification only; asymmetric JWKS verification is preferred |

Never prefix server credentials with `VITE_`: Vite publishes those values to every browser. Prashna does not require a Supabase service-role key. If you add one for a separate admin task in the future, keep it server-only and do not add it to this app's client variables.

## Deploy for free: Supabase + Render + Vercel

The services have separate free-plan limits and terms that can change. Render's free web service sleeps after inactivity and has an ephemeral filesystem, so keep the database on Supabase rather than a file or Render's expiring free database. Supabase may pause inactive free projects. See the current provider details: [Supabase free-plan pausing](https://supabase.com/docs/guides/platform/free-project-pausing), [Render free services](https://render.com/docs/free), [Vercel's Vite guide](https://vercel.com/docs/frameworks/frontend/vite), [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing), and [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).

### 1. Supabase project and database

1. Create a Supabase project and save its database password.
2. In **Connect**, copy the Session pooler PostgreSQL URI for the backend `DATABASE_URL`. Supabase pooler connection modes and ports differ; use the URI and mode recommended for a long-running backend service.
3. Copy the Project URL and publishable/anon key from **Project Settings → API**.
4. In **Authentication → URL Configuration**, set the Site URL to your deployed Vercel domain, e.g. `https://your-app.vercel.app`, and add that domain plus `http://localhost:5173/**` to the redirect allow list. If using a custom domain, add it too.
5. Configure email delivery/verification as desired. Supabase's built-in email service is suitable for development; production deliverability may require custom SMTP.

### 2. Deploy the API to Render

1. Push this project to a Git repository and create a **Web Service** in Render from it.
2. Select **Root Directory** `backend`, runtime **Python 3**.
3. Set **Build Command** to `pip install -r requirements.txt`.
4. Set **Start Command** to `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
5. Add backend environment variables in Render: `DATABASE_URL`, `SUPABASE_URL`, `CORS_ORIGINS`, `CRON_SECRET`, `LLM_PROVIDER=gemini`, and optionally `GEMINI_API_KEY` and `ADMIN_USER_IDS`. Use the deployed Vercel origin in `CORS_ORIGINS` (no trailing slash), for example `https://your-app.vercel.app`. Include localhost origins only if needed for local development.
6. Deploy. Check `https://YOUR-RENDER-SERVICE.onrender.com/api/health` returns `{"status":"ok"}`. First deploy runs Alembic migrations. Demo seed records are excluded from the live feed; no seed step is required for current affairs. Trigger the GitHub workflow once after configuring its secrets to populate the feed.

Render's free instance can take a little while to wake after inactivity; this is normal for a free service. Uploaded files/local SQLite are not durable there. Use Supabase PostgreSQL and avoid writing persistent app data to the Render filesystem.

### 3. Deploy the frontend to Vercel

1. Import the same Git repository into Vercel. Use the repository root as **Root Directory** and select the Vite framework (or set the values explicitly): install `npm install`, build `npm run build`, output directory `dist`.
2. Add these Vercel environment variables for Production (and Preview if desired):
   - `VITE_SUPABASE_URL` = Supabase Project URL
   - `VITE_SUPABASE_ANON_KEY` = Supabase publishable/anon key
   - `VITE_API_URL` = `https://YOUR-RENDER-SERVICE.onrender.com`
3. Deploy, then add the resulting Vercel domain to Supabase's Site URL/redirect allow list and to Render's `CORS_ORIGINS`. Redeploy Render after changing its environment variables and redeploy Vercel after changing its build variables.
4. Create a real account, verify email if enabled, complete onboarding, then test save/read/quiz/revision on the deployed app.

`vercel.json` includes an SPA rewrite so deep links serve the React app. When a Vercel preview uses a different domain, add that exact preview origin to Render CORS if you want previews to call the API.

### Scheduled current-affairs refresh

Default feeds are the [Press Information Bureau RSS feed](https://www.pib.gov.in/ViewRss.aspx?lang=1&reg=1) and [Reserve Bank of India RSS feeds](https://www.rbi.org.in/Scripts/rss.aspx). They are fetched over HTTPS as RSS/Atom metadata only; Prashna does not crawl publisher article pages. You can replace or extend them with `NEWS_RSS_FEEDS=Name|https://feed.example/rss|90;Other source|https://other.example/feed.xml|70`. Priority is 0–100; higher values are preferred when multiple sources report the same event.

Each feed item is screened with a deterministic UPSC-topic relevance classifier. Low-relevance items are ignored and never shown to learners. Matching canonical URLs, normalized title/date fingerprints, and close title matches within a two-day window are consolidated, with other publisher links preserved as citations. Only screened items go through the AI processor. Article pages distinguish “what happened” from generated context, significance, Prelims points, Mains angles, facts, terms, and questions. If AI is unavailable, a source-only fallback is used.

The repository includes `.github/workflows/daily-ingestion.yml`, which runs daily at 09:00 IST and can also be started using **Actions → Refresh Prashna current affairs → Run workflow**. Configure these GitHub repository Actions secrets:

- `PRASHNA_API_URL`: backend base URL, such as `https://your-service.onrender.com`.
- `PRASHNA_CRON_SECRET`: the exact same long random value as Render's `CRON_SECRET`.

The workflow calls `POST /api/ingest/run` and polls `GET /api/ingest/runs/{id}` until the run completes. Both endpoints require the `X-Cron-Secret` header. Summaries report source, processed, ignored, duplicate, failed, and queued counts plus sanitized error types. After deployment, start a refresh manually with `workflow_dispatch`. Generate a secret with `python -c "import secrets; print(secrets.token_urlsafe(48))"`; keep it on the backend and in GitHub Actions secrets, never in Vite variables or browser code.

### Optional Gemini processing

Create a Gemini API key and add it only to Render as `GEMINI_API_KEY`. The browser never calls Gemini. Gemini runs during scheduled processing of relevant items (or when an administrator submits source content); the learner feed does not call AI. Without a key, ingestion uses a source-only fallback. Free quotas and model availability vary by account; set `LLM_PROVIDER=mock` to force the fallback.

## Architecture and security

- `src/`: React + TypeScript + Vite UI, Supabase Auth client, authenticated API helper.
- `backend/app/`: FastAPI, JWT validation against Supabase JWKS, SQLAlchemy data access, Gemini/mock ingestion providers.
- `backend/migrations/`: Alembic schema migrations, including PostgreSQL RLS policies on profile and user-owned data tables.
- `subjects`, hierarchical `topics`, and `learning_content` form the extensible study catalog. `user_topic_progress` stores completion against the verified Supabase profile ID. The learning catalog is separate from the current-affairs `articles` ingestion model; this preserves the existing pipeline while allowing future article-to-subject mappings.
- Initial authenticated learning APIs: `GET /api/subjects`, `GET /api/subjects/{slug}`, `GET /api/topics/{slug}`, and `POST /api/topics/{slug}/complete`. Subject/topic responses include progress for the authenticated user only; the API never accepts a user ID from the client.
- Topic MCQs use `questions` and `question_options`; user answers persist in `user_question_attempts`. Unanswered question responses omit the answer key. Attempts are scoped to the verified Supabase user and recorded as learning activity; manual topic completion remains a separate progress signal.
- Practice APIs: `GET /api/topics/{slug}/questions`, `POST /api/questions/{id}/attempt`, and `GET /api/me/question-attempts`. The sample question bank is labeled demo material, not official UPSC content.
- `profiles.id` comes from the verified Supabase token; endpoints do not accept a client-supplied user ID. Bookmarks, quiz history, revisions, activity and statistics are scoped to that identity.
- Streak dates use the timezone sent by the browser. Activity has unique user/type/date constraints and daily quiz completion is unique per user/day.
- Public client credentials are limited to the Supabase publishable/anon key. Database, Gemini and JWT secrets stay on the backend.

## Useful commands

```bash
# Frontend production build
npm run build

# Backend tests (from project root)
cd backend
python -m pytest tests

# Reset neither seed nor user data; this only adds sample content to an empty database
python -m app.seed

# API documentation while the backend is running
# http://localhost:8000/docs
```

## Content ingestion

The source-traceable tables in migration `0007_source_traceable_content` support source documents, extracted chunks, reading cards, reviewable PYQs and publication. Existing demo lessons and sample questions remain in the app and are labelled separately. Run the migration to Alembic head before using these commands.

After migration and catalog setup, seed the idempotent Fundamental Rights example:

```bash
cd backend
python -m app.real_content_seed
```

### Add source files locally

Put original files under the ignored `backend/content/` folder. A subject folder maps to the existing subject slug; a second-level topic folder maps to a topic slug. For example:

```text
backend/content/
  polity/fundamental-rights/ncert-rights.pdf
  history/revolt-of-1857/notes.md
  geography/indian-monsoon/monsoon.txt
```

For reliable attribution, add a sibling metadata file named `ncert-rights.pdf.meta.json`:

```json
{
  "title": "Indian Constitution at Work — Chapter 2",
  "publisher": "National Council of Educational Research and Training",
  "source_type": "NCERT",
  "source_url": "https://www.ncert.nic.in/textbook/pdf/keps202.pdf",
  "subject_slug": "indian-polity",
  "topic_slug": "fundamental-rights",
  "license_notes": "Link to the official publication; do not redistribute the PDF."
}
```

Supported `source_type` values: `NCERT`, `UPSC`, `GOVERNMENT`, `PARLIAMENTARY`, `IGNOU`, `NIOS`, `COACHING`, `NEWS_CURRENT_AFFAIRS`, `OTHER`. Without a sidecar, the filename/folder are used as draft metadata and require review. Do not put copyrighted PDFs in Git.

From the backend directory, scan/register new files and process queued jobs:

```bash
cd backend
python -m app.scripts.process_content_jobs
```

PDF, TXT and Markdown are supported. PDFs retain physical page numbers; TXT/Markdown may use form-feed characters (`\f`) to mark page breaks. Each chunk stores its source document, page and detected section when present. Extraction errors (including scanned PDFs with no text or a missing PDF dependency) leave a failed job with a readable error; after fixing the cause, run `python -m app.scripts.process_content_jobs --retry-failed`. The checksum prevents duplicate registration. Files stay local; the database retains a local identifier, checksum, extracted chunks and attribution metadata.

### Review and publish reading cards

Processing ends in `REVIEW`, never publication. An authenticated admin can inspect extracted pages/text at `GET /api/admin/source-documents/{id}` and the issue summary at `GET /api/admin/content-validation`. Create a Prashna-authored card with the selected chunk IDs at `POST /api/admin/learning-cards`, then publish it only after checking the facts and page attribution with `POST /api/admin/learning-cards/{id}/publish`. The learner topic view returns only published cards, ordered by card order, with publisher, title, section/page and original-source link.

### Import actual UPSC PYQs from JSON

Create a UTF-8 JSON file containing an array. `question_number` may be a string or integer; `correct_option` is **1-based**. Only set `answer_verified: true` after checking the official answer key. If that field is absent/false, the answer is deliberately left unset and the PYQ stays in review.

```json
[
  {
    "year": 2024,
    "exam": "Civil Services Examination",
    "stage": "Prelims",
    "paper": "General Studies Paper I",
    "question_number": 76,
    "question_text": "Exact question text copied from the official paper",
    "options": ["Exact option A", "Exact option B", "Exact option C", "Exact option D"],
    "correct_option": 4,
    "answer_verified": true,
    "explanation": "Explanation kept separate from official question wording.",
    "subject": "indian-polity",
    "topic": "fundamental-rights",
    "official_source_url": "https://www.upsc.gov.in/sites/default/files/QP-CSP-24-GENERAL-STUDIES-PAPER-I-180624.pdf"
  }
]
```

Import it from `backend/`:

```bash
python -m app.scripts.import_pyqs path/to/questions.json
```

The importer checks the schema, existing subject/topic, 2–6 non-empty options and HTTPS UPSC source URL; preserves the supplied wording/options; and skips duplicate year/exam/stage/paper/number or exact same-paper text. New PYQs are `REVIEW` and unpublished. An unverified answer is not stored as correct. Review an item at `GET /api/admin/pyqs/{id}`; if needed, enter the checked 1-based answer with `POST /api/admin/pyqs/{id}/answer`, then explicitly publish with `POST /api/admin/questions/{id}/publish`. These routes require the existing admin role. `GET /api/topics/{slug}/pyqs` and the learner UI expose only published UPSC PYQs; `.../questions` contains sample questions separately. The UI shows “No verified UPSC PYQs…” when there are none; sample items are never substituted or labelled as PYQs.

The starter seed defines a small Indian Polity → Fundamental Rights example linked to the official [NCERT chapter](https://www.ncert.nic.in/textbook/pdf/keps202.pdf) and official UPSC 2024 GS-I paper. Larger source ingestion and answer-key verification remain a human task. Avoid redistributing source books/PDFs; use the source link and concise attributed Prashna summaries. Semantic support and contradictory claims require editorial review. Scanned PDFs need OCR before they can be processed.
