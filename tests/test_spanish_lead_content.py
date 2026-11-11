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


if __name__ == "__main__":
    unittest.main()
