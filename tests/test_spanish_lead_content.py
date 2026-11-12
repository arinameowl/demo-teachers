import unittest

from spanish_lead_content import load_spanish_lead, questions_for, strip_answers


class SpanishLeadContentTest(unittest.TestCase):
    def test_each_variant_has_one_a1_book(self):
        for variant in ("es_es", "es_mx"):
            with self.subTest(variant=variant):
                data = load_spanish_lead(variant)
                books = data["book"]["books"]
                self.assertEqual(len(books), 1)
                self.assertEqual(books[0]["level"], "A1")
                self.assertTrue(books[0]["pages"])
                self.assertEqual(len(books[0]["questions"]), 5)

    def test_video_levels_and_listening_question_counts(self):
        expected = {"es_es": ("A1", 9), "es_mx": ("A2 (publisher-labelled)", 5)}
        for variant, (level, count) in expected.items():
            with self.subTest(variant=variant):
                data = load_spanish_lead(variant)
                self.assertEqual(data["video"]["level"], level)
                self.assertEqual(len(questions_for(data["video"], "while_watching")), count)

    def test_each_variant_includes_the_a1_series(self):
        for variant in ("es_es", "es_mx"):
            with self.subTest(variant=variant):
                data = load_spanish_lead(variant)
                self.assertEqual(data["series"]["level"], "Beginner / A1")
                self.assertTrue(data["series"]["youtube_url"].startswith("https://www.youtube.com/"))

    def test_public_payload_does_not_expose_answer_keys(self):
        public = strip_answers(load_spanish_lead("es_es"))

        def assert_no_keys(value):
            if isinstance(value, dict):
                self.assertNotIn("answer", value)
                self.assertNotIn("answer_key", value)
                for child in value.values():
                    assert_no_keys(child)
            elif isinstance(value, list):
                for child in value:
                    assert_no_keys(child)

        assert_no_keys(public)

    def test_task_sections_flatten_into_closed_questions(self):
        data = load_spanish_lead("es_es")
        expected = {
            ("video", "before_watching"): 1,
            ("video", "while_watching"): 9,
            ("video", "after_watching"): 4,
            ("series", "before_watching"): 5,
            ("series", "while_watching"): 7,
            ("series", "after_watching"): 3,
        }
        for (resource, section), count in expected.items():
            with self.subTest(resource=resource, section=section):
                self.assertEqual(len(questions_for(data[resource], section)), count)


class SpanishCurriculumTest(unittest.TestCase):
    def test_each_cefr_level_loads_separately_for_both_variants(self):
        from spanish_lead_content import load_spanish_level_units

        for level in ("A1", "A2", "B1"):
            for variant in ("es_es", "es_mx"):
                with self.subTest(level=level, variant=variant):
                    units = load_spanish_level_units(level, variant)
                    self.assertEqual(len(units), 6, f"Expected six {level} units for {variant}")
                    self.assertTrue(all(unit["level"] == level for unit in units))
                    self.assertEqual(len({unit["id"] for unit in units}), len(units))
                    self.assertEqual(sum(len(unit["variant"].get("exercises", [])) for unit in units), 30)
                    for unit in units:
                        exercises = [e for e in unit["variant"].get("exercises", []) if e.get("type") == "choice"]
                        self.assertEqual(len(exercises), 5, f"{unit['id']} must contain five exercises for {variant}")
                        exercise_ids = [e.get("id") for e in exercises]
                        self.assertTrue(all(exercise_ids), f"{unit['id']} has an exercise without an ID")
                        self.assertEqual(len(set(exercise_ids)), len(exercise_ids), f"Duplicate exercise IDs in {unit['id']}")

    def test_curriculum_choice_exercises_have_valid_answer_keys(self):
        from spanish_lead_content import load_spanish_level_units

        for level in ("A1", "A2", "B1"):
            for variant in ("es_es", "es_mx"):
                with self.subTest(level=level, variant=variant):
                    units = load_spanish_level_units(level, variant)
                    for unit in units:
                        exercises = unit["variant"].get("exercises", [])
                        for exercise in exercises:
                            if exercise.get("type") != "choice":
                                continue
                            self.assertGreaterEqual(len(exercise.get("options", [])), 2)
                            self.assertIsInstance(exercise.get("answer"), int)
                            self.assertGreaterEqual(exercise["answer"], 0)
                            self.assertLess(exercise["answer"], len(exercise["options"]))
                            self.assertTrue(exercise.get("explanation"))

    def test_dialogue_reading_and_grammar_structure_matches_level(self):
        from spanish_lead_content import load_spanish_level_units

        for level in ("A1", "A2", "B1"):
            for variant in ("es_es", "es_mx"):
                with self.subTest(level=level, variant=variant):
                    units = load_spanish_level_units(level, variant)
                    for unit in units:
                        dialogue_turns = len(unit["variant"].get("dialogue", []))
                        grammar_topics = len(unit.get("grammar", []))
                        if level == "A1":
                            self.assertGreaterEqual(dialogue_turns, 8)
                            self.assertLessEqual(dialogue_turns, 10)
                            self.assertGreaterEqual(grammar_topics, 5)
                            self.assertLessEqual(grammar_topics, 6)
                            self.assertFalse(unit["variant"].get("reading"))
                        else:
                            self.assertEqual(dialogue_turns, 12)
                            self.assertTrue(unit["variant"].get("reading"))
                            if level == "A2":
                                self.assertGreaterEqual(grammar_topics, 3)
                                self.assertLessEqual(grammar_topics, 4)
                            else:
                                self.assertEqual(grammar_topics, 3)

    def test_spanish_placement_quiz_covers_all_three_levels(self):
        import quiz

        for variant in ("es_es", "es_mx"):
            with self.subTest(variant=variant):
                questions = quiz.spanish_questions(variant)
                self.assertEqual(len(questions), 6)
                self.assertEqual([q["level"] for q in questions], ["A1", "A1", "A2", "A2", "B1", "B1"])
                for question in questions:
                    self.assertGreaterEqual(len(question["options"]), 2)
                    self.assertIsInstance(question["correct"], int)
                    self.assertGreaterEqual(question["correct"], 0)
                    self.assertLess(question["correct"], len(question["options"]))
                    self.assertTrue(question["explanation"])

    def test_spanish_placement_scoring_uses_passed_question_bank(self):
        import quiz

        questions = quiz.spanish_questions("es_es")
        answers = {index: question["correct"] for index, question in enumerate(questions)}
        self.assertEqual(quiz.score_to_level(answers, questions), "B1")
        answers.pop(5)
        self.assertEqual(quiz.score_to_level(answers, questions), "A2")
        answers.pop(3)
        self.assertEqual(quiz.score_to_level(answers, questions), "A1")


if __name__ == "__main__":
    unittest.main()
