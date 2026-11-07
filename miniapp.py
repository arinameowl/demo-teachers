"""Telegram Mini App API and static frontend for The Teachers lead bot."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qsl

import aiosqlite
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

import config
import database as db

log = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "miniapp"
DATA_DIR = BASE_DIR / "data"

app = FastAPI(title="The Teachers Learning App", docs_url=None, redoc_url=None)

LANGUAGES = {
    "en": {"name": "Английский", "available": True},
    "es": {"name": "Испанский", "available": False},
    "zh": {"name": "Китайский", "available": False},
    "ko": {"name": "Корейский", "available": False},
}

class ProgressUpdate(BaseModel):
    language: str = Field(pattern="^(en|es|zh|ko)$")
    material_id: str = Field(pattern="^(podcast|book|series)$")
    status: str = Field(pattern="^(started|completed)$")


class QuizSubmission(BaseModel):
    material_id: str = Field(pattern="^(podcast|book|series)$")
    answers: list = Field(default_factory=list, max_length=20)


class AppEvent(BaseModel):
    event_name: str = Field(pattern="^(material_opened|exercise_started|book_opened|media_opened)$")
    event_data: str = Field(default="", max_length=120)


def validate_init_data(init_data: str, max_age: int = 86400) -> dict:
    """Validate Telegram WebApp initData using the bot token (Telegram spec)."""
    if not init_data or not config.BOT_TOKEN or config.BOT_TOKEN == "ВАШ_ТОКЕН_ЛИД_БОТА":
        raise HTTPException(status_code=401, detail="Telegram authorization required")
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        received_hash = parsed.pop("hash")
        auth_date = int(parsed.get("auth_date", "0"))
    except (ValueError, KeyError):
        raise HTTPException(status_code=401, detail="Invalid Telegram initData")
    if time.time() - auth_date > max_age or auth_date > time.time() + 60:
        raise HTTPException(status_code=401, detail="Telegram session expired")
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", config.BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise HTTPException(status_code=401, detail="Telegram authorization failed")
    try:
        user = json.loads(parsed["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(status_code=401, detail="Telegram user not found")
    return {"id": user_id, "first_name": user.get("first_name", ""), "username": user.get("username", "")}


async def authorized_user(authorization: str | None = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(status_code=401, detail="Missing Telegram initData")
    return validate_init_data(authorization[4:])



def _task_url(value: str) -> str:
    match = re.search(r"https?://\S+", value or "")
    return match.group(0).rstrip(".,)") if match else ""


def _embed_url(value: str) -> str:
    """Return an embeddable player URL only for known YouTube/Vimeo links."""
    value = value or ""
    yt = re.search(r"(?:youtu\.be/|youtube\.com/watch\?v=)([A-Za-z0-9_-]{6,})", value)
    if yt:
        return f"https://www.youtube-nocookie.com/embed/{yt.group(1)}?playsinline=1&rel=0"
    vm = re.search(r"vimeo\.com/(?:video/)?(\d+)", value)
    if vm:
        return f"https://player.vimeo.com/video/{vm.group(1)}?title=0&byline=0&portrait=0"
    return ""


def _load_exercise_bank() -> dict:
    path = BASE_DIR / "data" / "learning_exercises.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _exercise_key(level: str, material_id: str) -> str:
    return f"en_{level}_{material_id}"

def _load_book_exercises(level: str) -> dict:
    if level not in {"A1", "A2", "B1"}:
        return {}
    path = DATA_DIR / f"book_{level.lower()}_exercises.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Не удалось загрузить интерактивные упражнения к книге %s", level)
        return {}


def _material_cards(level: str | None) -> list[dict]:
    if level not in {"A1", "A2", "B1"}:
        return []
    try:
        data = json.loads(Path(config.MATERIALS_PATH).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    source = data.get(level, {})
    cards = []
    podcast = source.get("podcast", {})
    if podcast:
        media_url = podcast.get("file_url", "")
        cards.append({"id": "podcast", "type": "audio", "title": podcast.get("title", "Подкаст"),
                      "description": podcast.get("text", ""), "media_url": media_url,
                      "embed_url": _embed_url(media_url),
                      "has_exercises": bool(_load_exercise_bank().get(_exercise_key(level, "podcast"))), "available": True})
    series = source.get("series", {})
    episode = series.get("episode", {})
    if episode:
        media_url = episode.get("file_url", "")
        cards.append({"id": "series", "type": "video", "title": f"{series.get('show', 'Сериал')} — {episode.get('title', '')}",
                      "description": episode.get("about", ""), "media_url": media_url,
                      "embed_url": _embed_url(media_url),
                      "has_exercises": bool(_load_exercise_bank().get(_exercise_key(level, "series"))), "available": True})
    return cards


@app.get("/")
async def index():
    return FileResponse(APP_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/app/bootstrap")
async def bootstrap(user: dict = Depends(authorized_user)):
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user["id"],))
        row = await cur.fetchone()
        if not row:
            await conn.execute(
                "INSERT INTO users (user_id, username, first_name, stage, created_at, source, last_active_at) VALUES (?, ?, ?, 'new', datetime('now'), 'miniapp', datetime('now'))",
                (user["id"], user.get("username", ""), user.get("first_name", "")),
            )
            await conn.commit()
            cur = await conn.execute("SELECT * FROM users WHERE user_id = ?", (user["id"],))
            row = await cur.fetchone()
        profile = dict(row)
        cur = await conn.execute(
            "SELECT language, material_id, status, updated_at FROM learning_progress WHERE user_id = ?",
            (user["id"],),
        )
        progress = [dict(r) for r in await cur.fetchall()]
    if profile.get("level") in {"A1", "A2", "B1"}:
        if profile.get("stage") not in {"nurtured", "trial_requested"}:
            await db.update_user(user["id"], stage="learning_space_opened")
        await db.log_funnel_event(user["id"], "learning_space_opened")
    return {
        "profile": {"first_name": profile.get("first_name"), "goal": profile.get("goal"),
                    "level": profile.get("level"), "level_source": profile.get("level_source")},
        "bot_username": config.BOT_USERNAME,
        "languages": LANGUAGES,
        "selected_language": "en",
        "materials": _material_cards(profile.get("level")),
        "progress": progress,
        "notice": "",
    }


@app.post("/api/app/event")
async def track_app_event(payload: AppEvent, user: dict = Depends(authorized_user)):
    """Track meaningful Mini App actions without accepting arbitrary event names."""
    await db.log_funnel_event(user["id"], payload.event_name, payload.event_data)
    return {"ok": True}


@app.get("/api/app/books/{level}")
async def get_book_fragment(level: str, user: dict = Depends(authorized_user)):
    if level not in {"A1", "A2", "B1"}:
        raise HTTPException(status_code=404, detail="Фрагмент для этого уровня не найден")
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute("SELECT level FROM users WHERE user_id = ?", (user["id"],))
        row = await cur.fetchone()
    if not row or row[0] != level:
        raise HTTPException(status_code=403, detail="Можно открыть книгу только для своего уровня")
    path = DATA_DIR / "book_fragments.json"
    try:
        books = json.loads(path.read_text(encoding="utf-8"))
        book = books[level]
    except (OSError, json.JSONDecodeError, KeyError):
        raise HTTPException(status_code=500, detail="Не удалось загрузить фрагмент книги")
    return book



@app.get("/api/app/library")
async def get_learning_library(user: dict = Depends(authorized_user)):
    """Return the text-based book available for the learner's current level."""
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT level FROM users WHERE user_id = ?", (user["id"],))
        row = await cur.fetchone()
    level = row["level"] if row else None
    if level not in {"A1", "A2", "B1"}:
        raise HTTPException(status_code=409, detail="Сначала определите уровень в боте")
    try:
        fragments = json.loads((DATA_DIR / "book_fragments.json").read_text(encoding="utf-8"))
        book = fragments[level]
        exercises_path = DATA_DIR / f"book_{level.lower()}_exercises.json"
        exercises = json.loads(exercises_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError):
        raise HTTPException(status_code=500, detail="Не удалось загрузить книгу и упражнения")
    return {
        "level": level,
        "books": [{
            "id": book.get("id", f"book_{level.lower()}"),
            "level": level,
            "title": book.get("title", "Книга"),
            "author": book.get("author", ""),
            "has_exercises": bool(exercises.get("questions")),
        }],
        "worksheets": [],
    }


@app.get("/api/app/book-exercises/{level}")
async def get_book_exercises(level: str, user: dict = Depends(authorized_user)):
    """Return the reading worksheet for the learner's own level."""
    if level not in {"A1", "A2", "B1"}:
        raise HTTPException(status_code=404, detail="Упражнения для этого уровня не найдены")
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute("SELECT level FROM users WHERE user_id = ?", (user["id"],))
        row = await cur.fetchone()
    if not row or row[0] != level:
        raise HTTPException(status_code=403, detail="Можно открыть упражнения только для своего уровня")
    exercises = _load_book_exercises(level)
    questions = exercises.get("questions", [])
    if not questions:
        raise HTTPException(status_code=404, detail="Интерактивные упражнения к книге пока не настроены")
    return {
        "id": exercises.get("id", f"book_{level.lower()}_exercises"),
        "level": level,
        "title": exercises.get("title", "Упражнения к книге"),
        "questions": [{k: v for k, v in question.items() if k != "answer"} for question in questions],
    }

@app.get("/api/app/exercises/{material_id}")
async def get_exercises(material_id: str, user: dict = Depends(authorized_user)):
    if material_id not in {"podcast", "book", "series"}:
        raise HTTPException(status_code=404, detail="Упражнения не найдены")
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT level FROM users WHERE user_id = ?", (user["id"],))
        row = await cur.fetchone()
    level = row["level"] if row else None
    if level not in {"A1", "A2", "B1"}:
        raise HTTPException(status_code=409, detail="Сначала определите уровень в боте")
    if material_id == "book":
        questions = _load_book_exercises(level).get("questions", [])
    else:
        questions = _load_exercise_bank().get(_exercise_key(level, material_id))
    if not questions:
        raise HTTPException(status_code=404, detail="Для этого материала упражнения пока не перенесены")
    safe_questions = []
    for q in questions:
        safe_questions.append({k: v for k, v in q.items() if k != "answer"})
    return {"level": level, "material_id": material_id, "questions": safe_questions}


@app.post("/api/app/exercises/submit")
async def submit_exercises(payload: QuizSubmission, user: dict = Depends(authorized_user)):
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        cur = await conn.execute("SELECT level FROM users WHERE user_id = ?", (user["id"],))
        row = await cur.fetchone()
    level = row["level"] if row else None
    if level not in {"A1", "A2", "B1"}:
        raise HTTPException(status_code=409, detail="Сначала определите уровень в боте")
    if payload.material_id == "book":
        questions = _load_book_exercises(level).get("questions", [])
    else:
        questions = _load_exercise_bank().get(_exercise_key(level, payload.material_id))
    if not questions:
        raise HTTPException(status_code=404, detail="Упражнения не найдены")
    if len(payload.answers) != len(questions):
        raise HTTPException(status_code=422, detail="Ответьте на все задания")
    results = []
    correct = 0
    for i, q in enumerate(questions):
        given = payload.answers[i]
        expected = q.get("answer")
        # Bound free-text submissions before comparing or echoing them in results.
        if isinstance(given, str) and len(given) > 500:
            given = given[:500]
        if q["type"] == "choice":
            ok = isinstance(given, int) and not isinstance(given, bool) and 0 <= given < len(q.get("options", [])) and given == expected
            expected_display = q["options"][expected]
        elif q["type"] == "text":
            accepted = q.get("accepted", [expected])
            ok = isinstance(given, str) and given.strip().casefold() in [str(x).strip().casefold() for x in accepted]
            expected_display = expected
        else:
            ok = False
            expected_display = ""
        correct += int(ok)
        results.append({
            "index": i,
            "correct": ok,
            "expected": expected_display,
            "given": given if given is not None else "",
            "explanation": q.get("explanation", ""),
        })
    total = len(questions)
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO funnel_events (user_id, event_name, event_data, created_at) VALUES (?, 'exercise_submitted', ?, datetime('now'))",
            (user["id"], f"en:{payload.material_id}:{correct}/{total}"),
        )
        await conn.commit()
    if correct == total:
        async with aiosqlite.connect(config.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO learning_progress (user_id, language, material_id, status, updated_at) VALUES (?, 'en', ?, 'completed', datetime('now')) "
                "ON CONFLICT(user_id, language, material_id) DO UPDATE SET status='completed', updated_at=datetime('now')",
                (user["id"], payload.material_id),
            )
            await conn.execute(
                "INSERT INTO funnel_events (user_id, event_name, event_data, created_at) VALUES (?, 'miniapp_exercise_completed', ?, datetime('now'))",
                (user["id"], f"en:{payload.material_id}:{correct}/{total}"),
            )
            await conn.commit()
    return {"correct": correct, "total": total, "results": results, "completed": correct == total}


@app.post("/api/app/progress")
async def save_progress(payload: ProgressUpdate, user: dict = Depends(authorized_user)):
    if payload.language != "en":
        raise HTTPException(status_code=409, detail="Материалы этого языка ещё не загружены")
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO learning_progress (user_id, language, material_id, status, updated_at) VALUES (?, ?, ?, ?, datetime('now')) "
            "ON CONFLICT(user_id, language, material_id) DO UPDATE SET "
            "status=CASE WHEN learning_progress.status='completed' AND excluded.status='started' "
            "THEN 'completed' ELSE excluded.status END, updated_at=excluded.updated_at",
            (user["id"], payload.language, payload.material_id, payload.status),
        )
        await conn.execute(
            "INSERT INTO funnel_events (user_id, event_name, event_data, created_at) VALUES (?, 'miniapp_progress', ?, datetime('now'))",
            (user["id"], f"{payload.language}:{payload.material_id}:{payload.status}"),
        )
        await conn.commit()
    return {"ok": True}
