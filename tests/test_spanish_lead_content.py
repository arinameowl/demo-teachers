import unittest

from spanish_lead_content import load_spanish_lead, load_spanish_media, questions_for, strip_answers


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
        expected = {"es_es": ("A1", 4), "es_mx": ("A1 (publisher-labelled)", 2)}
        for variant, (level, count) in expected.items():
            with self.subTest(variant=variant):
                data = load_spanish_lead(variant)
                self.assertEqual(data["video"]["level"], level)
                self.assertEqual(len(questions_for(data["video"], "after_watching")), count)
                self.assertEqual(questions_for(data["video"], "before_watching"), [])
                self.assertEqual(questions_for(data["video"], "while_watching"), [])

    def test_podcast_and_series_are_region_specific(self):
        spain = load_spanish_lead("es_es")
        mexico = load_spanish_lead("es_mx")
        self.assertTrue(spain["podcast"]["url"].startswith("https://"))
        self.assertTrue(mexico["podcast"]["url"].startswith("https://"))
        self.assertIsNone(spain["series"])
        self.assertEqual(mexico["series"]["level"], "Beginner / A1")
        self.assertTrue(mexico["series"]["youtube_url"].startswith("https://www.youtube.com/"))

    def test_existing_media_is_returned_by_level_and_dialect(self):
        spain_a1 = load_spanish_media("A1", "es_es")
        mexico_a1 = load_spanish_media("A1", "es_mx")
        self.assertTrue(spain_a1["podcast"]["url"].startswith("https://"))
        self.assertTrue(mexico_a1["podcast"]["url"].startswith("https://"))
        self.assertIsNone(spain_a1["series"])
        self.assertIsNotNone(mexico_a1["series"])
        self.assertIsNotNone(spain_a1["video"])
        self.assertIsNotNone(mexico_a1["video"])

        spain_a2 = load_spanish_media("A2", "es_es")
        mexico_a2 = load_spanish_media("A2", "es_mx")
        spain_b1 = load_spanish_media("B1", "es_es")
        mexico_b1 = load_spanish_media("B1", "es_mx")
        self.assertTrue(spain_a2["videos"])
        self.assertTrue(mexico_a2["videos"])
        self.assertTrue(spain_b1["videos"])
        self.assertEqual(mexico_b1["videos"], [])
        self.assertTrue(all("Spain" in item["region"] for item in spain_a2["videos"] + spain_b1["videos"]))
        self.assertTrue(all("Mexico" in item["region"] for item in mexico_a2["videos"]))

    def test_a1_podcasts_have_internal_players_and_post_listening_tasks(self):
        for variant in ("es_es", "es_mx"):
            with self.subTest(variant=variant):
                podcast = load_spanish_lead(variant)["podcast"]
                self.assertTrue(podcast["player_url"].startswith("https://"))
                self.assertEqual(podcast["player_type"], "audio" if variant == "es_es" else "youtube")
                questions = questions_for(podcast, "after_listening")
                self.assertEqual(len(questions), 3)
                self.assertTrue(all(q.get("explanation") for q in questions))
                self.assertEqual(questions_for(podcast, "before_listening"), [])
                self.assertEqual(questions_for(podcast, "while_listening"), [])

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

    def test_media_exercises_are_available_only_after_viewing(self):
        for variant in ("es_es", "es_mx"):
            data = load_spanish_lead(variant)
            self.assertEqual(questions_for(data["video"], "before_watching"), [])
            self.assertEqual(questions_for(data["video"], "while_watching"), [])
            self.assertTrue(questions_for(data["video"], "after_watching"))
        mexico = load_spanish_lead("es_mx")
        self.assertEqual(len(questions_for(mexico["series"], "after_watching")), 3)
        self.assertEqual(questions_for(mexico["series"], "before_watching"), [])
        self.assertEqual(questions_for(mexico["series"], "while_watching"), [])


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
                            self.assertEqual(
                                len(exercise["options"]),
                                len(set(exercise["options"])),
                                f"{exercise.get('id')} has duplicate answer options",
                            )
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
                        self.assertTrue(
                            all(topic.get("title_ru") for topic in unit.get("grammar", [])),
                            f"{unit['id']} has a grammar topic without a learner-facing Russian title",
                        )
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

    def test_a1_two_blank_exercises_offer_complete_answer_pairs(self):
        from spanish_lead_content import load_spanish_level_units

        units = load_spanish_level_units("A1", "es_es") + load_spanish_level_units("A1", "es_mx")
        by_id = {
            exercise["id"]: exercise
            for unit in units
            for exercise in unit["variant"].get("exercises", [])
        }
        expected = {
            "es_es_u3_e4": ["me levanto / me ducho", "se levanta / se ducha", "te levantas / te duchas"],
            "es_mx_u3_e4": ["me despierto / me acuesto", "se despierta / se acuesta", "te despiertas / te acuestas"],
        }
        for exercise_id, options in expected.items():
            with self.subTest(exercise=exercise_id):
                self.assertEqual(by_id[exercise_id]["options"], options)
                self.assertIn("/", options[by_id[exercise_id]["answer"]])

    def test_a1_book_questions_have_unique_options_and_explanations(self):
        for variant in ("es_es", "es_mx"):
            with self.subTest(variant=variant):
                book = load_spanish_lead(variant)["book"]["books"][0]
                for question in book["questions"]:
                    self.assertEqual(len(question["options"]), len(set(question["options"])))
                    self.assertTrue(question.get("explanation"))
                    self.assertGreaterEqual(question["answer"], 0)
                    self.assertLess(question["answer"], len(question["options"]))

    def test_spanish_placement_quiz_is_original_and_covers_all_three_levels(self):
        import quiz
        from spanish_lead_content import load_spanish_level_units

        for variant in ("es_es", "es_mx"):
            with self.subTest(variant=variant):
                questions = quiz.spanish_questions(variant)
                self.assertEqual(len(questions), 9)
                self.assertEqual([q["level"] for q in questions], ["A1"] * 3 + ["A2"] * 3 + ["B1"] * 3)
                curriculum_prompts = {
                    exercise["prompt"]
                    for level in ("A1", "A2", "B1")
                    for unit in load_spanish_level_units(level, variant)
                    for exercise in unit["variant"].get("exercises", [])
                }
                for question in questions:
                    self.assertGreaterEqual(len(question["options"]), 2)
                    self.assertIsInstance(question["correct"], int)
                    self.assertGreaterEqual(question["correct"], 0)
                    self.assertLess(question["correct"], len(question["options"]))
                    self.assertTrue(question["explanation"])
                    self.assertNotIn(question["prompt"].split(". ", 1)[-1], curriculum_prompts)

    def test_spanish_placement_scoring_uses_passed_question_bank(self):
        import quiz

        questions = quiz.spanish_questions("es_es")
        answers = {index: question["correct"] for index, question in enumerate(questions)}
        self.assertEqual(quiz.score_to_level(answers, questions), "B1")
        answers.pop(8)
        self.assertEqual(quiz.score_to_level(answers, questions), "A2")
        answers.pop(5)
        self.assertEqual(quiz.score_to_level(answers, questions), "A1")


if __name__ == "__main__":
    unittest.main()
