import pytest

from spanish_lead_content import load_spanish_lead, questions_for, strip_answers


@pytest.mark.parametrize("variant", ["es_es", "es_mx"])
def test_spanish_variant_has_one_a1_book(variant):
    data = load_spanish_lead(variant)
    books = data["book"]["books"]
    assert len(books) == 1
    assert books[0]["level"] == "A1"
    assert books[0]["pages"]
    assert len(books[0]["questions"]) == 5


@pytest.mark.parametrize(
    ("variant", "video_level", "video_while_count"),
    [("es_es", "A1", 9), ("es_mx", "A2 (publisher-labelled)", 5)],
)
def test_video_level_and_closed_listening_tasks(variant, video_level, video_while_count):
    data = load_spanish_lead(variant)
    assert data["video"]["level"] == video_level
    assert len(questions_for(data["video"], "while_watching")) == video_while_count


@pytest.mark.parametrize("variant", ["es_es", "es_mx"])
def test_each_variant_includes_the_same_a1_series(variant):
    data = load_spanish_lead(variant)
    assert data["series"]["level"] == "Beginner / A1"
    assert data["series"]["youtube_url"].startswith("https://www.youtube.com/")


def test_public_payload_does_not_expose_answer_keys():
    data = load_spanish_lead("es_es")
    public = strip_answers(data)
    
    def assert_no_keys(value):
        if isinstance(value, dict):
            assert "answer" not in value
            assert "answer_key" not in value
            for child in value.values():
                assert_no_keys(child)
        elif isinstance(value, list):
            for child in value:
                assert_no_keys(child)

    assert_no_keys(public)


@pytest.mark.parametrize(
    ("resource_key", "section", "expected_count"),
    [
        ("video", "before_watching", 1),
        ("video", "while_watching", 9),
        ("video", "after_watching", 4),
        ("series", "before_watching", 5),
        ("series", "while_watching", 7),
        ("series", "after_watching", 3),
    ],
)
def test_spanish_tasks_flatten_into_closed_questions(resource_key, section, expected_count):
    data = load_spanish_lead("es_es")
    assert len(questions_for(data[resource_key], section)) == expected_count
