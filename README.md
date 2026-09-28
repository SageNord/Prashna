# Prashna

**Know what's happening. Know why it matters.** A mobile-first current-affairs learning app for UPSC aspirants. Prashna uses Supabase Auth for accounts, FastAPI for authenticated APIs, and PostgreSQL for persistent user data. The existing editorial sample feed remains available as a learning sample; it is not a live news feed.

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
5. Add backend environment variables in Render: `DATABASE_URL`, `SUPABASE_URL`, `CORS_ORIGINS`, `LLM_PROVIDER=gemini`, and optionally `GEMINI_API_KEY` and `ADMIN_USER_IDS`. Use the deployed Vercel origin in `CORS_ORIGINS` (no trailing slash), for example `https://your-app.vercel.app`. Include localhost origins only if needed for local development.
6. Deploy. Check `https://YOUR-RENDER-SERVICE.onrender.com/api/health` returns `{"status":"ok"}`. First deploy runs Alembic migrations. Run `python -m app.seed` once from the Render Shell to install the sample articles. The seed command is idempotent and leaves existing articles and user activity untouched.

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

### Optional Gemini processing

Create a Gemini API key and add it only to Render as `GEMINI_API_KEY`. The browser never calls Gemini. Gemini is used only when an administrator submits source content to `POST /api/ingest`; processed output is stored in PostgreSQL, and the user-facing feed does not call AI. Without a key, ingestion uses a labeled mock processor. Free quotas and model availability vary by account and may change; check Google's live pricing/limits before relying on automated ingestion. Set `LLM_PROVIDER=mock` to force the fallback.

## Architecture and security

- `src/`: React + TypeScript + Vite UI, Supabase Auth client, authenticated API helper.
- `backend/app/`: FastAPI, JWT validation against Supabase JWKS, SQLAlchemy data access, Gemini/mock ingestion providers.
- `backend/migrations/`: Alembic schema migrations, including PostgreSQL RLS policies on profile and user-owned data tables.
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

