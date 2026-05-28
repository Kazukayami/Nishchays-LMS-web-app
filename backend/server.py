from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Literal, Optional
from urllib.parse import urlparse, urlunparse

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
DATA_FILE = ROOT / "data" / "lms.json"


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(ROOT / ".env")

JWT_SECRET = os.getenv("JWT_SECRET", "change-me-in-production")
JWT_COOKIE_SECURE = os.getenv("JWT_COOKIE_SECURE", "false").lower() == "true"
JWT_COOKIE_SAMESITE = os.getenv("JWT_COOKIE_SAMESITE", "lax").lower()
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5-20250929")
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
Role = Literal["admin", "instructor", "employee"]

try:
    import bcrypt as bcrypt_lib  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    bcrypt_lib = None

try:
    import psycopg2  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    psycopg2 = None


app = FastAPI(title="Employee LMS API")
api = APIRouter(prefix="/api")
store_lock = asyncio.Lock()


def postgres_url() -> str:
    if not DATABASE_URL:
        return ""
    parsed = urlparse(DATABASE_URL)
    if parsed.scheme == "postgres":
        parsed = parsed._replace(scheme="postgresql")
    return urlunparse(parsed)


def get_pg_connection():
    if not DATABASE_URL:
        return None
    if not psycopg2:
        raise RuntimeError("DATABASE_URL is set but psycopg2 is not installed")
    return psycopg2.connect(postgres_url(), sslmode=os.getenv("DB_SSLMODE", "require"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def default_store() -> Dict[str, list]:
    return {
        "users": [],
        "courses": [],
        "enrollments": [],
        "quizzes": [],
        "quiz_attempts": [],
        "certificates": [],
        "assignments": [],
        "assignment_submissions": [],
        "comments": [],
    }


def read_store() -> Dict[str, list]:
    if DATABASE_URL:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lms_store (
                        id integer PRIMARY KEY,
                        data jsonb NOT NULL
                    )
                    """
                )
                cur.execute("SELECT data FROM lms_store WHERE id = 1")
                row = cur.fetchone()
                if not row:
                    return default_store()
                base = default_store()
                base.update(row[0])
                return base
    if not DATA_FILE.exists():
        return default_store()
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    base = default_store()
    base.update(data)
    return base


def write_store(data: Dict[str, list]) -> None:
    if DATABASE_URL:
        with get_pg_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS lms_store (
                        id integer PRIMARY KEY,
                        data jsonb NOT NULL
                    )
                    """
                )
                cur.execute(
                    """
                    INSERT INTO lms_store (id, data)
                    VALUES (1, %s)
                    ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data
                    """,
                    (json.dumps(data),),
                )
        return
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = DATA_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(DATA_FILE)


async def mutate_store(fn: Callable[[Dict[str, list]], Any]) -> Any:
    async with store_lock:
        data = read_store()
        result = fn(data)
        write_store(data)
        return result


async def view_store(fn: Callable[[Dict[str, list]], Any]) -> Any:
    async with store_lock:
        return fn(read_store())


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
        "avatar_color": user.get("avatar_color", "#0A0A0A"),
        "created_at": user.get("created_at"),
    }


def hash_password(password: str) -> str:
    if bcrypt_lib:
        hashed = bcrypt_lib.hashpw(password.encode("utf-8"), bcrypt_lib.gensalt())
        return "bcrypt$" + hashed.decode("utf-8")
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 180000)
    return "pbkdf2_sha256$180000$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("bcrypt$") and bcrypt_lib:
        return bool(bcrypt_lib.checkpw(password.encode("utf-8"), stored[7:].encode("utf-8")))
    if stored.startswith("pbkdf2_sha256$"):
        _, rounds, salt_b64, digest_b64 = stored.split("$", 3)
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(rounds))
        return hmac.compare_digest(actual, expected)
    return False


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_json(data: dict) -> str:
    return b64url(json.dumps(data, separators=(",", ":")).encode("utf-8"))


def sign_token(payload: dict) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    head = b64url_json(header)
    body = b64url_json(payload)
    sig = hmac.new(JWT_SECRET.encode("utf-8"), f"{head}.{body}".encode("ascii"), hashlib.sha256).digest()
    return f"{head}.{body}.{b64url(sig)}"


def decode_token(token: str) -> dict:
    try:
        head, body, sig = token.split(".")
        expected = hmac.new(JWT_SECRET.encode("utf-8"), f"{head}.{body}".encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(b64url(expected), sig):
            raise ValueError("bad signature")
        padded = body + "=" * (-len(body) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        if payload.get("exp", 0) < int(time.time()):
            raise ValueError("expired")
        return payload
    except Exception:
        raise HTTPException(401, "Invalid or expired token")


def create_access_token(user: dict) -> str:
    return sign_token(
        {
            "sub": user["id"],
            "email": user["email"],
            "role": user["role"],
            "type": "access",
            "exp": int(time.time()) + 60 * 60 * 12,
        }
    )


def set_auth_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "access_token",
        token,
        httponly=True,
        secure=JWT_COOKIE_SECURE,
        samesite=JWT_COOKIE_SAMESITE,
        max_age=60 * 60 * 12,
        path="/",
    )


async def current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    auth = request.headers.get("Authorization", "")
    if not token and auth.startswith("Bearer "):
        token = auth[7:]
    if not token:
        raise HTTPException(401, "Not authenticated")
    payload = decode_token(token)
    user = await view_store(lambda db: next((u for u in db["users"] if u["id"] == payload["sub"]), None))
    if not user:
        raise HTTPException(401, "User not found")
    return user


def require_role(*allowed: str):
    async def checker(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(403, "Forbidden")
        return user

    return checker


class RegisterIn(BaseModel):
    name: str
    email: str
    password: str = Field(min_length=6)
    role: Role = "employee"


class LoginIn(BaseModel):
    email: str
    password: str


class LessonIn(BaseModel):
    title: str
    content_type: Literal["video", "text"] = "text"
    video_url: str = ""
    body: str = ""
    duration_min: int = 5


class ModuleIn(BaseModel):
    title: str
    lessons: List[LessonIn] = []


class CourseIn(BaseModel):
    title: str
    description: str
    category: str = "General"
    level: Literal["Beginner", "Intermediate", "Advanced"] = "Beginner"
    cover_url: str = ""
    modules: List[ModuleIn] = []
    published: bool = True


class QuizQuestionIn(BaseModel):
    question: str
    options: List[str]
    correct_index: int
    explanation: str = ""


class QuizIn(BaseModel):
    course_id: str
    title: str
    passing_score: int = 70
    questions: List[QuizQuestionIn]


class QuizSubmitIn(BaseModel):
    answers: List[int]


class AssignmentIn(BaseModel):
    course_id: str
    title: str
    description: str
    due_date: str = ""


class AssignmentSubmissionIn(BaseModel):
    submission_text: str


class CommentIn(BaseModel):
    lesson_id: str
    course_id: str
    text: str


class AIQuizGenIn(BaseModel):
    course_id: str
    topic: str
    num_questions: int = 5


def course_lesson_count(modules: List[dict]) -> int:
    return sum(len(m.get("lessons", [])) for m in modules)


def make_course(body: CourseIn, user: dict) -> dict:
    modules = []
    for module in body.modules:
        lessons = [{"id": new_id(), **lesson.model_dump()} for lesson in module.lessons]
        modules.append({"id": new_id(), "title": module.title, "lessons": lessons})
    return {
        "id": new_id(),
        "title": body.title,
        "description": body.description,
        "category": body.category,
        "level": body.level,
        "cover_url": body.cover_url,
        "modules": modules,
        "total_lessons": course_lesson_count(modules),
        "published": body.published,
        "instructor_id": user["id"],
        "instructor_name": user["name"],
        "created_at": now_iso(),
    }


@api.get("/")
async def root():
    return {"service": "Employee LMS", "ok": True}


@api.post("/auth/register")
async def register(body: RegisterIn, response: Response):
    email = body.email.lower().strip()
    if "@" not in email:
        raise HTTPException(400, "Enter a valid email address")

    def create(db: Dict[str, list]) -> dict:
        if any(u["email"] == email for u in db["users"]):
            raise HTTPException(400, "Email already registered")
        role = body.role if body.role in ("employee", "instructor") else "employee"
        user = {
            "id": new_id(),
            "name": body.name.strip(),
            "email": email,
            "password_hash": hash_password(body.password),
            "role": role,
            "avatar_color": "#FF3B30" if role == "instructor" else "#06402B",
            "created_at": now_iso(),
        }
        db["users"].append(user)
        return user

    user = await mutate_store(create)
    set_auth_cookie(response, create_access_token(user))
    return public_user(user)


@api.post("/auth/login")
async def login(body: LoginIn, response: Response):
    email = body.email.lower().strip()
    user = await view_store(lambda db: next((u for u in db["users"] if u["email"] == email), None))
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
    set_auth_cookie(response, create_access_token(user))
    return public_user(user)


@api.post("/auth/logout")
async def logout(response: Response):
    response.delete_cookie("access_token", path="/", secure=JWT_COOKIE_SECURE, samesite=JWT_COOKIE_SAMESITE)
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return public_user(user)


@api.get("/users")
async def list_users(_: dict = Depends(require_role("admin"))):
    return await view_store(lambda db: [public_user(u) for u in db["users"]])


@api.patch("/users/{user_id}/role")
async def change_role(user_id: str, body: Dict[str, str], _: dict = Depends(require_role("admin"))):
    role = body.get("role")
    if role not in ("admin", "instructor", "employee"):
        raise HTTPException(400, "Invalid role")

    def update(db: Dict[str, list]) -> dict:
        user = next((u for u in db["users"] if u["id"] == user_id), None)
        if not user:
            raise HTTPException(404, "User not found")
        user["role"] = role
        return public_user(user)

    return await mutate_store(update)


@api.get("/courses")
async def list_courses(category: str = "All", level: str = "All", q: str = ""):
    def query(db: Dict[str, list]) -> list:
        courses = [c for c in db["courses"] if c.get("published", True)]
        if category != "All":
            courses = [c for c in courses if c["category"] == category]
        if level != "All":
            courses = [c for c in courses if c["level"] == level]
        if q:
            needle = q.lower()
            courses = [c for c in courses if needle in c["title"].lower() or needle in c["description"].lower()]
        return deepcopy(courses)

    return await view_store(query)


@api.get("/courses/categories")
async def categories():
    return await view_store(lambda db: sorted({c["category"] for c in db["courses"]}))


@api.get("/courses/{course_id}")
async def get_course(course_id: str):
    course = await view_store(lambda db: deepcopy(next((c for c in db["courses"] if c["id"] == course_id), None)))
    if not course:
        raise HTTPException(404, "Course not found")
    return course


@api.post("/courses")
async def create_course(body: CourseIn, user: dict = Depends(require_role("admin", "instructor"))):
    course = make_course(body, user)
    await mutate_store(lambda db: db["courses"].append(course))
    return course


@api.delete("/courses/{course_id}")
async def delete_course(course_id: str, user: dict = Depends(require_role("admin", "instructor"))):
    def remove(db: Dict[str, list]) -> dict:
        course = next((c for c in db["courses"] if c["id"] == course_id), None)
        if not course:
            raise HTTPException(404, "Course not found")
        if user["role"] != "admin" and course["instructor_id"] != user["id"]:
            raise HTTPException(403, "Only the owner or an admin can delete this course")
        db["courses"] = [c for c in db["courses"] if c["id"] != course_id]
        db["quizzes"] = [q for q in db["quizzes"] if q["course_id"] != course_id]
        db["enrollments"] = [e for e in db["enrollments"] if e["course_id"] != course_id]
        return {"ok": True}

    return await mutate_store(remove)


@api.post("/enrollments/{course_id}")
async def enroll(course_id: str, user: dict = Depends(current_user)):
    def create(db: Dict[str, list]) -> dict:
        course = next((c for c in db["courses"] if c["id"] == course_id), None)
        if not course:
            raise HTTPException(404, "Course not found")
        existing = next((e for e in db["enrollments"] if e["course_id"] == course_id and e["user_id"] == user["id"]), None)
        if existing:
            return deepcopy(existing)
        enrollment = {
            "id": new_id(),
            "user_id": user["id"],
            "course_id": course_id,
            "completed_lessons": [],
            "progress": 0,
            "completed": False,
            "enrolled_at": now_iso(),
            "completed_at": "",
            "certificate_id": "",
        }
        db["enrollments"].append(enrollment)
        return deepcopy(enrollment)

    return await mutate_store(create)


@api.get("/enrollments")
async def my_enrollments(user: dict = Depends(current_user)):
    def query(db: Dict[str, list]) -> list:
        courses = {c["id"]: c for c in db["courses"]}
        rows = []
        for enrollment in db["enrollments"]:
            if enrollment["user_id"] == user["id"]:
                row = deepcopy(enrollment)
                row["course"] = deepcopy(courses.get(enrollment["course_id"]))
                rows.append(row)
        return rows

    return await view_store(query)


@api.post("/enrollments/{course_id}/lesson/{lesson_id}/complete")
async def complete_lesson(course_id: str, lesson_id: str, user: dict = Depends(current_user)):
    def update(db: Dict[str, list]) -> dict:
        course = next((c for c in db["courses"] if c["id"] == course_id), None)
        if not course:
            raise HTTPException(404, "Course not found")
        enrollment = next((e for e in db["enrollments"] if e["course_id"] == course_id and e["user_id"] == user["id"]), None)
        if not enrollment:
            raise HTTPException(400, "Enroll before completing lessons")
        lessons = {l["id"] for m in course["modules"] for l in m["lessons"]}
        if lesson_id not in lessons:
            raise HTTPException(404, "Lesson not found")
        completed = set(enrollment.get("completed_lessons", []))
        completed.add(lesson_id)
        total = max(1, course.get("total_lessons") or course_lesson_count(course["modules"]))
        progress = int((len(completed) / total) * 100)
        enrollment["completed_lessons"] = sorted(completed)
        enrollment["progress"] = min(100, progress)
        enrollment["completed"] = enrollment["progress"] >= 100
        if enrollment["completed"] and not enrollment.get("certificate_id"):
            cert = {
                "id": new_id(),
                "user_id": user["id"],
                "user_name": user["name"],
                "course_id": course_id,
                "course_title": course["title"],
                "issued_at": now_iso(),
            }
            db["certificates"].append(cert)
            enrollment["certificate_id"] = cert["id"]
            enrollment["completed_at"] = cert["issued_at"]
        return deepcopy(enrollment)

    return await mutate_store(update)


@api.get("/certificates")
async def my_certificates(user: dict = Depends(current_user)):
    return await view_store(lambda db: deepcopy([c for c in db["certificates"] if c["user_id"] == user["id"]]))


@api.get("/certificates/{cert_id}")
async def get_certificate(cert_id: str):
    cert = await view_store(lambda db: deepcopy(next((c for c in db["certificates"] if c["id"] == cert_id), None)))
    if not cert:
        raise HTTPException(404, "Certificate not found")
    return cert


@api.get("/quizzes/course/{course_id}")
async def quizzes_for_course(course_id: str):
    return await view_store(lambda db: deepcopy([q for q in db["quizzes"] if q["course_id"] == course_id]))


@api.get("/quizzes/{quiz_id}")
async def get_quiz(quiz_id: str, user: dict = Depends(current_user)):
    quiz = await view_store(lambda db: deepcopy(next((q for q in db["quizzes"] if q["id"] == quiz_id), None)))
    if not quiz:
        raise HTTPException(404, "Quiz not found")
    if user["role"] == "employee":
        for question in quiz["questions"]:
            question.pop("correct_index", None)
            question.pop("explanation", None)
    return quiz


@api.post("/quizzes")
async def create_quiz(body: QuizIn, _: dict = Depends(require_role("admin", "instructor"))):
    quiz = {
        "id": new_id(),
        "course_id": body.course_id,
        "title": body.title,
        "passing_score": body.passing_score,
        "questions": [{"id": new_id(), **q.model_dump()} for q in body.questions],
        "created_at": now_iso(),
    }
    await mutate_store(lambda db: db["quizzes"].append(quiz))
    return quiz


@api.post("/quizzes/{quiz_id}/submit")
async def submit_quiz(quiz_id: str, body: QuizSubmitIn, user: dict = Depends(current_user)):
    def grade(db: Dict[str, list]) -> dict:
        quiz = next((q for q in db["quizzes"] if q["id"] == quiz_id), None)
        if not quiz:
            raise HTTPException(404, "Quiz not found")
        total = len(quiz["questions"])
        correct = 0
        detail = []
        for i, question in enumerate(quiz["questions"]):
            answer = body.answers[i] if i < len(body.answers) else -1
            ok = answer == question["correct_index"]
            correct += int(ok)
            detail.append(
                {
                    "question": question["question"],
                    "user_answer": answer,
                    "correct_index": question["correct_index"],
                    "is_correct": ok,
                    "explanation": question.get("explanation", ""),
                }
            )
        score = int((correct / total) * 100) if total else 0
        attempt = {
            "id": new_id(),
            "user_id": user["id"],
            "quiz_id": quiz_id,
            "course_id": quiz["course_id"],
            "score": score,
            "passed": score >= quiz.get("passing_score", 70),
            "submitted_at": now_iso(),
        }
        db["quiz_attempts"].append(attempt)
        return {"score": score, "passed": attempt["passed"], "passing_score": quiz.get("passing_score", 70), "detail": detail}

    return await mutate_store(grade)


@api.post("/assignments")
async def create_assignment(body: AssignmentIn, user: dict = Depends(require_role("admin", "instructor"))):
    assignment = {"id": new_id(), **body.model_dump(), "created_by": user["id"], "created_at": now_iso()}
    await mutate_store(lambda db: db["assignments"].append(assignment))
    return assignment


@api.get("/assignments/course/{course_id}")
async def assignments_for_course(course_id: str):
    return await view_store(lambda db: deepcopy([a for a in db["assignments"] if a["course_id"] == course_id]))


@api.post("/assignments/{assignment_id}/submit")
async def submit_assignment(assignment_id: str, body: AssignmentSubmissionIn, user: dict = Depends(current_user)):
    def create(db: Dict[str, list]) -> dict:
        assignment = next((a for a in db["assignments"] if a["id"] == assignment_id), None)
        if not assignment:
            raise HTTPException(404, "Assignment not found")
        submission = {
            "id": new_id(),
            "assignment_id": assignment_id,
            "user_id": user["id"],
            "user_name": user["name"],
            "submission_text": body.submission_text,
            "submitted_at": now_iso(),
            "graded": False,
            "grade": None,
        }
        db["assignment_submissions"].append(submission)
        return submission

    return await mutate_store(create)


@api.get("/assignments/{assignment_id}/submissions")
async def list_assignment_submissions(assignment_id: str, _: dict = Depends(require_role("admin", "instructor"))):
    return await view_store(lambda db: deepcopy([s for s in db["assignment_submissions"] if s["assignment_id"] == assignment_id]))


@api.post("/comments")
async def post_comment(body: CommentIn, user: dict = Depends(current_user)):
    comment = {
        "id": new_id(),
        "lesson_id": body.lesson_id,
        "course_id": body.course_id,
        "user_id": user["id"],
        "user_name": user["name"],
        "user_role": user["role"],
        "text": body.text,
        "created_at": now_iso(),
    }
    await mutate_store(lambda db: db["comments"].append(comment))
    return comment


@api.get("/comments/lesson/{lesson_id}")
async def comments_for_lesson(lesson_id: str):
    return await view_store(lambda db: deepcopy([c for c in reversed(db["comments"]) if c["lesson_id"] == lesson_id]))


async def ask_claude(system: str, prompt: str) -> Optional[str]:
    return None


def extract_json(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def fallback_questions(topic: str, count: int) -> list:
    seeds = [
        ("Which statement best describes {topic}?", ["A practical capability", "A random policy", "A one-time event", "A software bug"], 0),
        ("What is the first step when applying {topic}?", ["Observe the current situation", "Skip planning", "Ignore feedback", "Wait for approval"], 0),
        ("Why does {topic} matter at work?", ["It improves decisions and outcomes", "It replaces collaboration", "It removes all risk", "It only helps managers"], 0),
        ("Which habit supports {topic}?", ["Reflect, practice, and ask for feedback", "Memorize terms only", "Avoid measurement", "Work in isolation"], 0),
        ("How should progress in {topic} be checked?", ["With evidence and learner feedback", "By guessing", "By seniority", "Only at year end"], 0),
    ]
    questions = []
    for idx in range(max(1, min(count, 10))):
        text, options, answer = seeds[idx % len(seeds)]
        questions.append(
            {
                "question": text.format(topic=topic),
                "options": options,
                "correct_index": answer,
                "explanation": "This answer supports measurable learning and workplace transfer.",
            }
        )
    return questions


@api.post("/ai/generate-quiz")
async def ai_generate_quiz(body: AIQuizGenIn, _: dict = Depends(require_role("admin", "instructor"))):
    course = await view_store(lambda db: next((c for c in db["courses"] if c["id"] == body.course_id), None))
    if not course:
        raise HTTPException(404, "Course not found")
    lesson_text = " ".join(l.get("body", "") for m in course["modules"] for l in m["lessons"])[:4000]
    system = (
        "You are an instructional designer. Return strict JSON only with schema "
        '{"questions":[{"question":string,"options":[string,string,string,string],"correct_index":number,"explanation":string}]}.'
    )
    prompt = f"Course: {course['title']}\nTopic: {body.topic}\nCourse content: {lesson_text}\nGenerate {body.num_questions} questions."
    parsed = extract_json(await ask_claude(system, prompt))
    questions = parsed.get("questions", []) if parsed else []
    clean = []
    for item in questions:
        opts = item.get("options", [])
        if item.get("question") and isinstance(opts, list) and len(opts) >= 2:
            clean.append(
                {
                    "question": str(item["question"]),
                    "options": [str(o) for o in opts[:4]],
                    "correct_index": int(item.get("correct_index", 0)),
                    "explanation": str(item.get("explanation", "")),
                }
            )
    return {"questions": clean or fallback_questions(body.topic, body.num_questions), "model": CLAUDE_MODEL if parsed else "local-fallback"}


@api.get("/ai/recommendations")
async def ai_recommendations(user: dict = Depends(current_user)):
    data = await view_store(lambda db: deepcopy(db))
    enrolled = [e for e in data["enrollments"] if e["user_id"] == user["id"]]
    enrolled_ids = {e["course_id"] for e in enrolled}
    candidates = [c for c in data["courses"] if c["id"] not in enrolled_ids and c.get("published", True)]
    if not candidates:
        return {"recommendations": [], "reason": "You are enrolled in every available course."}
    system = 'You recommend employee learning paths. Return JSON only: {"course_ids":[string],"reason":string}.'
    catalog = [{"id": c["id"], "title": c["title"], "category": c["category"], "level": c["level"]} for c in candidates]
    prompt = f"User: {public_user(user)}\nEnrollments: {enrolled}\nCatalog: {catalog}\nPick at most 3 course_ids."
    parsed = extract_json(await ask_claude(system, prompt))
    picked = parsed.get("course_ids", [])[:3] if parsed else []
    by_id = {c["id"]: c for c in candidates}
    recs = [by_id[i] for i in picked if i in by_id]
    if not recs:
        recs = sorted(candidates, key=lambda c: (c["level"] != "Beginner", c["title"]))[:3]
    reason = parsed.get("reason") if parsed else "Recommended from your open learning path and current catalog."
    return {"recommendations": recs, "reason": reason, "model": CLAUDE_MODEL if parsed else "local-fallback"}


@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(require_role("admin"))):
    def stats(db: Dict[str, list]) -> dict:
        by_role = {"admin": 0, "instructor": 0, "employee": 0}
        for user in db["users"]:
            by_role[user["role"]] += 1
        return {
            "users": len(db["users"]),
            "courses": len(db["courses"]),
            "enrollments": len(db["enrollments"]),
            "completions": len([e for e in db["enrollments"] if e.get("completed")]),
            "certificates": len(db["certificates"]),
            "by_role": by_role,
        }

    return await view_store(stats)


def seed_user(db: Dict[str, list], email: str, password: str, name: str, role: Role, color: str) -> dict:
    existing = next((u for u in db["users"] if u["email"] == email), None)
    if existing:
        return existing
    user = {
        "id": new_id(),
        "name": name,
        "email": email,
        "password_hash": hash_password(password),
        "role": role,
        "avatar_color": color,
        "created_at": now_iso(),
    }
    db["users"].append(user)
    return user


def seed_course(db: Dict[str, list], instructor: dict, title: str, description: str, category: str, level: str, cover_url: str, modules: list) -> dict:
    course = {
        "id": new_id(),
        "title": title,
        "description": description,
        "category": category,
        "level": level,
        "cover_url": cover_url,
        "modules": modules,
        "total_lessons": course_lesson_count(modules),
        "published": True,
        "instructor_id": instructor["id"],
        "instructor_name": instructor["name"],
        "created_at": now_iso(),
    }
    db["courses"].append(course)
    return course


def make_modules(seed: list) -> list:
    modules = []
    for module_title, lessons in seed:
        modules.append(
            {
                "id": new_id(),
                "title": module_title,
                "lessons": [
                    {
                        "id": new_id(),
                        "title": lesson["title"],
                        "content_type": lesson.get("content_type", "text"),
                        "video_url": lesson.get("video_url", ""),
                        "body": lesson.get("body", ""),
                        "duration_min": lesson.get("duration_min", 6),
                    }
                    for lesson in lessons
                ],
            }
        )
    return modules


async def seed_data() -> None:
    def seed(db: Dict[str, list]) -> None:
        admin = seed_user(db, os.getenv("ADMIN_EMAIL", "admin@lms.com"), os.getenv("ADMIN_PASSWORD", "Admin@123"), "Atlas Admin", "admin", "#0A0A0A")
        instructor = seed_user(
            db,
            os.getenv("INSTRUCTOR_EMAIL", "instructor@lms.com"),
            os.getenv("INSTRUCTOR_PASSWORD", "Instructor@123"),
            "Iris Instructor",
            "instructor",
            "#FF3B30",
        )
        seed_user(db, os.getenv("EMPLOYEE_EMAIL", "employee@lms.com"), os.getenv("EMPLOYEE_PASSWORD", "Employee@123"), "Eli Employee", "employee", "#06402B")
        if db["courses"]:
            return
        leadership = seed_course(
            db,
            instructor,
            "Leadership in the Modern Workplace",
            "Build communication, trust, and practical decision-making for high-performing teams.",
            "Leadership",
            "Intermediate",
            "https://images.unsplash.com/photo-1556761175-b413da4baf72?w=1200",
            make_modules(
                [
                    (
                        "Foundations",
                        [
                            {"title": "Leadership is influence", "body": "Leadership is influence, not authority. Strong leaders build trust, clarify context, and make room for ownership.", "duration_min": 8},
                            {"title": "Communication that lands", "content_type": "video", "video_url": "https://www.youtube.com/embed/eIho2S0ZahI", "duration_min": 12},
                        ],
                    ),
                    (
                        "Team Practice",
                        [
                            {"title": "Psychological safety", "body": "Teams perform better when people can speak up, share risks, and learn without fear. Use Signal, Ask, Frame, and Empower.", "duration_min": 10}
                        ],
                    ),
                ]
            ),
        )
        seed_course(
            db,
            instructor,
            "Creative Thinking and Design Fundamentals",
            "Learn visual hierarchy, ideation, and the design principles behind credible workplace output.",
            "Creative",
            "Beginner",
            "https://images.unsplash.com/photo-1518005020951-eccb494ad742?w=1200",
            make_modules(
                [
                    (
                        "Visual Systems",
                        [
                            {"title": "Composition basics", "body": "Hierarchy turns chaos into clarity. Use scale, contrast, alignment, and whitespace with intent.", "duration_min": 7},
                            {"title": "Typography that breathes", "body": "Type carries most of the message. Pair fonts carefully and give content enough room to read.", "duration_min": 9},
                        ],
                    )
                ]
            ),
        )
        seed_course(
            db,
            instructor,
            "Data-Driven Decision Making",
            "Translate dashboards and spreadsheets into confident business decisions.",
            "Analytics",
            "Intermediate",
            "https://images.unsplash.com/photo-1551288049-bebda4e38f71?w=1200",
            make_modules(
                [
                    (
                        "Reading Data",
                        [
                            {"title": "Descriptive vs predictive", "body": "Descriptive analytics explain what happened. Predictive analytics estimate what might happen next.", "duration_min": 6}
                        ],
                    )
                ]
            ),
        )
        seed_course(
            db,
            instructor,
            "Cybersecurity Essentials for Every Employee",
            "A practical guide to safer passwords, phishing detection, and everyday security habits.",
            "Compliance",
            "Beginner",
            "https://images.unsplash.com/photo-1516321318423-f06f85e504b3?w=1200",
            make_modules(
                [
                    (
                        "Phishing",
                        [
                            {"title": "Spotting a suspicious message", "body": "Pause before clicking. Check urgency, sender domain, unexpected attachments, and link destinations.", "duration_min": 5}
                        ],
                    )
                ]
            ),
        )
        db["quizzes"].append(
            {
                "id": new_id(),
                "course_id": leadership["id"],
                "title": "Leadership Fundamentals Quiz",
                "passing_score": 70,
                "questions": [
                    {"id": new_id(), "question": "Leadership is best defined as:", "options": ["Authority over others", "Influence and direction", "Owning the org chart", "Giving orders"], "correct_index": 1, "explanation": "Leadership is influence, not authority."},
                    {"id": new_id(), "question": "Psychological safety means:", "options": ["No conflict ever", "People can speak up without fear", "Strict hierarchy", "Anonymous feedback only"], "correct_index": 1, "explanation": "It is the freedom to take interpersonal risks."},
                    {"id": new_id(), "question": "The SAFE framework starts with:", "options": ["Strategy", "Signal openness", "Speed", "Status"], "correct_index": 1, "explanation": "Signal, Ask, Frame, Empower."},
                ],
                "created_at": now_iso(),
            }
        )
        db["assignments"].append(
            {
                "id": new_id(),
                "course_id": leadership["id"],
                "title": "Team Leadership Reflection",
                "description": "Write a short reflection on one meeting where psychological safety changed the quality of discussion.",
                "due_date": "",
                "created_by": admin["id"],
                "created_at": now_iso(),
            }
        )

    await mutate_store(seed)


@app.on_event("startup")
async def startup() -> None:
    await seed_data()


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:8001,http://127.0.0.1:8001").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
