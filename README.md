# Employee LMS Web App

A complete local Employee Learning Management System with a FastAPI backend and a no-build browser frontend.

## What Is Included

- JWT-based custom authentication with httpOnly cookies.
- Password hashing with bcrypt when installed, and a PBKDF2 fallback for local machines without bcrypt.
- Role-based access for Admin, Instructor, and Employee users.
- Course catalog, modules, lessons, video/text lesson player, enrollment, progress tracking, and certificates.
- Quiz creation, quiz submission, scoring, and employee-safe quiz fetching that hides correct answers.
- Assignments, submissions, and lesson discussions/comments.
- Instructor studio for course creation and deterministic quiz generation.
- Admin dashboard for stats and user role management.

## Demo Credentials

| Role | Email | Password |
| --- | --- | --- |
| Admin | `admin@lms.com` | `Admin@123` |
| Instructor | `instructor@lms.com` | `Instructor@123` |
| Employee | `employee@lms.com` | `Employee@123` |

## Run Locally

From this folder:

```powershell
.\start_lms.ps1
```

Then open:

```text
http://127.0.0.1:8001
```

## Environment

Backend settings live in `backend/.env`.
Copy `backend/.env.example` to `backend/.env` for local development.

```env
JWT_SECRET="change-this-before-production"
JWT_COOKIE_SECURE=false
CORS_ORIGINS="http://localhost:8001,http://127.0.0.1:8001"
CLAUDE_MODEL="claude-sonnet-4-5-20250929"
```

AI endpoints return deterministic local fallback output so the app remains usable without external services.

## Public Deployment

This repo is ready for split hosting without paid infrastructure:

- Backend API on Render's free web service plan.
- Static frontend on Vercel.
- Persistent data in a free external Postgres database through `DATABASE_URL` such as Neon or Supabase.

### 1. Create a Free Postgres Database

Create a free Postgres project in Neon or Supabase and copy its pooled connection string. Neon connection strings look like:

```text
postgresql://user:password@host/dbname?sslmode=require
```

Use the pooled connection string when available.

### 2. Deploy the Backend on Render

Create a new Render Blueprint from this repository. Render will read `render.yaml` and create the Python web service on the free plan.

Set these Render environment variables before the first production deploy:

```env
ADMIN_PASSWORD="replace-with-a-strong-password"
INSTRUCTOR_PASSWORD="replace-with-a-strong-password"
EMPLOYEE_PASSWORD="replace-with-a-strong-password"
CORS_ORIGINS="https://your-vercel-app.vercel.app"
DATABASE_URL="postgresql://user:password@host/dbname?sslmode=require"
```

Render generates `JWT_SECRET`. The backend start command is:

```bash
uvicorn server:app --host 0.0.0.0 --port $PORT
```

After deployment, copy the Render service URL, for example:

```text
https://nishchays-lms-api.onrender.com
```

### 3. Deploy the Frontend on Vercel

Import this repository in Vercel and use the root project directory.

Set this Vercel environment variable:

```env
LMS_API_URL="https://your-render-service.onrender.com/api"
```

Vercel uses `npm run build`, which copies `frontend/` into `dist/` and writes `dist/config.js` with the API URL.

### 4. Final CORS Update

After Vercel gives you the production URL, update Render's `CORS_ORIGINS` value to the exact Vercel origin:

```env
CORS_ORIGINS="https://your-vercel-app.vercel.app"
```

Redeploy the Render service after changing CORS.
