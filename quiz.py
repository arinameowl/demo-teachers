# -*- coding: utf-8 -*-

import json
from pathlib import Path
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
    """Return an original Spanish placement bank, independent from library exercises.

    The same CEFR grammar and comprehension targets are used for both regional
    tracks; the test does not recycle questions from the learning materials.
    """
    # Regional variant is accepted for a stable onboarding API. These diagnostic
    # items use broadly shared Spanish and avoid region-specific vocabulary.
    if variant not in {"es_es", "es_mx"}:
        variant = "es_es"
    bank = [
        {
            "level": "A1",
            "prompt": "Completa: «¿Cómo ___ llamas?»",
            "options": ["te", "se", "me"],
            "correct": 0,
            "explanation": "Для обращения на tú используется форма te: ¿Cómo te llamas?"
        },
        {
            "level": "A1",
            "prompt": "Elige la frase correcta.",
            "options": ["Ana vive en Madrid.", "Ana vivo en Madrid.", "Ana vivir en Madrid."],
            "correct": 0,
            "explanation": "С местоимением ella / Ana глагол vivir в настоящем времени имеет форму vive."
        },
        {
            "level": "A1",
            "prompt": "¿De dónde ___ ustedes?",
            "options": ["son", "están", "tienen"],
            "correct": 0,
            "explanation": "Происхождение спрашивают с ser: ¿De dónde son ustedes?"
        },
        {
            "level": "A2",
            "prompt": "Ayer nosotros ___ al cine después del trabajo.",
            "options": ["vamos", "fuimos", "íbamos a ir"],
            "correct": 1,
            "explanation": "Ayer указывает на завершенное событие в прошлом; для ir используется форма fuimos."
        },
        {
            "level": "A2",
            "prompt": "Todavía no he ___ el correo electrónico.",
            "options": ["leído", "leer", "leyendo"],
            "correct": 0,
            "explanation": "В pretérito perfecto используется haber + причастие: he leído."
        },
        {
            "level": "A2",
            "prompt": "Si mañana hace buen tiempo, ___ a la playa.",
            "options": ["fuimos", "iremos", "íbamos"],
            "correct": 1,
            "explanation": "Реальное условие о будущем строится с si + presente и futuro simple."
        },
        {
            "level": "B1",
            "prompt": "Si tuviera más tiempo, ___ un curso de fotografía.",
            "options": ["hago", "haré", "haría"],
            "correct": 2,
            "explanation": "Гипотеза с si + imperfecto de subjuntivo требует condicional: haría."
        },
        {
            "level": "B1",
            "prompt": "No creo que Marta ___ la respuesta.",
            "options": ["sabe", "sepa", "sabrá"],
            "correct": 1,
            "explanation": "После выражения сомнения no creo que обычно используется presente de subjuntivo: sepa."
        },
        {
            "level": "B1",
            "prompt": "Cuando llegué a la estación, el tren ya ___.",
            "options": ["salía", "ha salido", "había salido"],
            "correct": 2,
            "explanation": "Событие, завершившееся до другого момента в прошлом, выражается pluscuamperfecto: había salido."
        },
    ]
    questions = [dict(question) for question in bank]
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
