# -*- coding: utf-8 -*-
"""
Короткий тест на уровень — не заменяет полноценное тестирование школы,
а нужен исключительно для того, чтобы выдать подходящую порцию лид-магнита
и создать ощущение вовлечения ("бот меня протестировал, а не просто спросил").

Каждый вопрос размечен уровнем сложности (A1/A2/B1). Итоговый уровень —
самый сложный уровень, на котором пользователь ответил верно на оба вопроса
этого уровня; если ни одного правильного на A2 — остаётся A1, и т.д.
Это грубая, но достаточная для лид-магнита эвристика.
"""

QUESTIONS = [
    {
        "level": "A1",
        "prompt": "1/5. Выбери правильный вариант: 'She ___ a teacher.'",
        "options": ["is", "am", "are"],
        "correct": 0,
    },
    {
        "level": "A1",
        "prompt": "2/5. Как будет 'Мне нравится кофе' по-английски?",
        "options": ["I like coffee", "I likes coffee", "I am like coffee"],
        "correct": 0,
    },
    {
        "level": "A2",
        "prompt": "3/5. 'I ___ to the gym every morning.'",
        "options": ["go", "going", "am go"],
        "correct": 0,
    },
    {
        "level": "A2",
        "prompt": "4/5. Выбери правильный вопрос: 'Куда ты ходил вчера вечером?'",
        "options": ["Where did you go last night?", "Where you went last night?", "Where you go last night?"],
        "correct": 0,
    },
    {
        "level": "B1",
        "prompt": "5/5. 'If I ___ more time, I would learn another language.'",
        "options": ["have", "had", "will have"],
        "correct": 1,
    },
]


def score_to_level(answers: dict[int, int]) -> str:
    """answers: {question_index: chosen_option_index}. Возвращает 'A1' | 'A2' | 'B1'."""
    correct_by_level: dict[str, int] = {"A1": 0, "A2": 0, "B1": 0}
    for idx, q in enumerate(QUESTIONS):
        chosen = answers.get(idx)
        if chosen is not None and chosen == q["correct"]:
            correct_by_level[q["level"]] += 1

    if correct_by_level["B1"] >= 1 and correct_by_level["A2"] >= 1:
        return "B1"
    if correct_by_level["A2"] >= 1:
        return "A2"
    return "A1"
