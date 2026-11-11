"""Load and validate the compact Spanish lead-magnet content."""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "data"


def _read(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


def load_spanish_lead(variant: str) -> dict:
    if variant not in {"es_es", "es_mx"}:
        raise ValueError("Unknown Spanish variant")
    books = _read("spanish_a1_books.json")
    tasks = _read("spanish_lead_video_tasks.json")
    book_variant = next((x for x in books["variants"] if x["id"] == variant), None)
    if not book_variant:
        raise ValueError("Spanish book variant not found")
    resources = tasks["resources"]
    return {
        "variant": variant,
        "book": book_variant,
        "video": resources[variant],
        "series": resources["series"],
    }


def questions_for(resource: dict, section: str) -> list[dict]:
    """Flatten only closed multiple-choice questions in a task section."""
    tasks = resource.get("tasks", {}).get(section, [])
    result = []
    for task in tasks:
        if task.get("type") not in {"multiple_choice", "choice"}:
            continue
        if isinstance(task.get("questions"), list):
            result.extend(q for q in task["questions"] if q.get("options") and "answer" in q)
        elif task.get("options") and "answer" in task:
            result.append(task)
    return result


def public_questions(resource: dict, section: str) -> list[dict]:
    return [
        {key: value for key, value in q.items() if key not in {"answer", "answer_key"}}
        for q in questions_for(resource, section)
    ]


def strip_answers(value):
    if isinstance(value, list):
        return [strip_answers(item) for item in value]
    if isinstance(value, dict):
        return {
            key: strip_answers(item)
            for key, item in value.items()
            if key not in {"answer", "answer_key"}
        }
    return value
