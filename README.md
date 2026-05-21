# Employee LMS Web App

A complete local Employee Learning Management System with a FastAPI backend and a no-build browser frontend.

## What Is Included

- JWT-based custom authentication with httpOnly cookies.
- Password hashing with bcrypt when installed, and a PBKDF2 fallback for local machines without bcrypt.
- Role-based access for Admin, Instructor, and Employee users.
- Course catalog, modules, lessons, video/text lesson player, enrollment, progress tracking, and certificates.
- Quiz creation, quiz submission, scoring, and employee-safe quiz fetching that hides correct answers.
- Assignments, submissions, and lesson discussions/comments.
- Instructor studio for course creation and AI quiz generation.
- Admin dashboard for stats and user role management.
- Optional Claude Sonnet integration through `EMERGENT_LLM_KEY` using the `emergentintegrations` package.

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
EMERGENT_LLM_KEY=""
CLAUDE_MODEL="claude-sonnet-4-5-20250929"
```

When `EMERGENT_LLM_KEY` is empty or `emergentintegrations` is not installed, AI endpoints return deterministic local fallback output so the app remains usable.
