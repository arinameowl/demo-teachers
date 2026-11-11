# -*- coding: utf-8 -*-
"""
Короткий тест на уровень — не заменяет полноценное тестирование школы,
а нужен исключительно для того, чтобы выдать подходящую подборку материалов
и создать ощущение вовлечения ("бот меня протестировал, а не просто спросил").

Каждый вопрос размечен уровнем сложности (A1/A2/B1). Итоговый уровень —
самый сложный уровень, для которого пользователь верно ответил на все вопросы
этого и предыдущих уровней. Для A1/A2 предусмотрено по два вопроса, для B1 — три.
Это грубая, но достаточная для лид-магнита эвристика.
"""

QUESTIONS = [
    {
        "level": "A1",
        "prompt": "1/7. Выберите правильный вариант: 'She ___ a teacher.'",
        "options": ["is", "am", "are"],
        "correct": 0,
    },
    {
        "level": "A1",
        "prompt": "2/7. Как будет 'Мне нравится кофе' по-английски?",
        "options": ["I like coffee", "I likes coffee", "I am like coffee"],
        "correct": 0,
    },
    {
        "level": "A2",
        "prompt": "3/7. 'I ___ to the gym every morning.'",
        "options": ["go", "going", "am go"],
        "correct": 0,
    },
    {
        "level": "A2",
        "prompt": "4/7. Выберите правильный вопрос: «Куда вы ходили вчера вечером?»",
        "options": ["Where did you go last night?", "Where you went last night?", "Where you go last night?"],
        "correct": 0,
    },
    {
        "level": "B1",
        "prompt": "5/7. 'If I ___ more time, I would learn another language.'",
        "options": ["have", "had", "will have"],
        "correct": 1,
    },
    {
        "level": "B1",
        "prompt": "6/7. 'The report ___ by the finance team last week.'",
        "options": ["was prepared", "prepared", "has prepared"],
        "correct": 0,
    },
    {
        "level": "B1",
        "prompt": "7/7. 'I wish I ___ more time to practise speaking.'",
        "options": ["have", "had", "would have"],
        "correct": 1,
    },
]


def spanish_questions(variant: str = "es_es") -> list[dict]:
    """Build a six-question placement test from approved A1–B1 unit exercises."""
    if variant not in {"es_es", "es_mx"}:
        variant = "es_es"
    root = Path(__file__).resolve().parent / "data"
    questions = []
    for level in ("A1", "A2", "B1"):
        catalog = json.loads((root / f"spanish_{level.lower()}_catalog.json").read_text(encoding="utf-8"))
        units = sorted(catalog.get("units", []), key=lambda item: item.get("order", 0))
        level_questions = []
        for unit in units:
            data = json.loads((Path(__file__).resolve().parent / unit["path"]).read_text(encoding="utf-8"))
            dialect = next((item for item in data.get("variants", []) if item.get("id") == variant), None)
            if not dialect:
                continue
            for item in dialect.get("exercises", []):
                if item.get("type") == "choice" and len(item.get("options", [])) >= 2 and isinstance(item.get("answer"), int):
                    level_questions.append({
                        "level": level,
                        "prompt": item["prompt"],
                        "options": item["options"],
                        "correct": item["answer"],
                        "explanation": item.get("explanation", ""),
                    })
        # Two items per CEFR band, selected from different units where possible.
        if level_questions:
            questions.extend(level_questions[:1])
            if len(level_questions) > 1:
                questions.append(level_questions[min(5, len(level_questions)-1)])
    for index, question in enumerate(questions, 1):
        question["prompt"] = f"{index}/{len(questions)}. {question['prompt']}"
    return questions


def score_to_level(answers: dict[int, int], questions: list[dict] | None = None) -> str:
    """answers: {question_index: chosen_option_index}. Возвращает 'A1' | 'A2' | 'B1'."""
    questions = questions or QUESTIONS
    correct_by_level: dict[str, int] = {"A1": 0, "A2": 0, "B1": 0}
    for idx, q in enumerate(questions):
        chosen = answers.get(idx)
        if chosen is not None and chosen == q["correct"]:
            correct_by_level[q["level"]] += 1

    questions_by_level = {
        level: sum(1 for q in questions if q["level"] == level)
        for level in correct_by_level
    }

    # Переход на следующий уровень возможен только после прохождения
    # всех вопросов текущего и предыдущих уровней.
    a1_complete = correct_by_level["A1"] == questions_by_level["A1"]
    a2_complete = correct_by_level["A2"] == questions_by_level["A2"]
    b1_complete = correct_by_level["B1"] == questions_by_level["B1"]

    if a1_complete and a2_complete and b1_complete:
        return "B1"
    if a1_complete and a2_complete:
        return "A2"
    return "A1"
