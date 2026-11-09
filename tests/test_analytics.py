import os
import tempfile
import unittest
from datetime import datetime, timedelta

import aiosqlite

import database as db


class AnalyticsQueriesTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "analytics-test.sqlite3")
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.executescript("""
                CREATE TABLE users (
                    user_id INTEGER PRIMARY KEY,
                    source TEXT,
                    created_at TEXT NOT NULL,
                    unsubscribed INTEGER DEFAULT 0,
                    blocked INTEGER DEFAULT 0
                );
                CREATE TABLE funnel_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    event_name TEXT NOT NULL,
                    event_data TEXT,
                    created_at TEXT NOT NULL
                );
            """)
            await conn.commit()
        self.base = datetime.utcnow().replace(microsecond=0)

    async def asyncTearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp.cleanup()

    def stamp(self, minutes):
        return (self.base + timedelta(minutes=minutes)).isoformat()

    async def add_user(self, user_id, source="instagram"):
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO users(user_id, source, created_at) VALUES (?, ?, ?)",
                (user_id, source, self.stamp(-10)),
            )
            await conn.commit()

    async def add_event(self, user_id, name, minute, data=""):
        async with aiosqlite.connect(db.DB_PATH) as conn:
            await conn.execute(
                "INSERT INTO funnel_events(user_id, event_name, event_data, created_at) VALUES (?, ?, ?, ?)",
                (user_id, name, data, self.stamp(minute)),
            )
            await conn.commit()

    async def test_funnel_requires_events_in_order(self):
        await self.add_user(1)
        ordered = [
            "start", "goal_selected", "level_selected", "learning_space_opened",
            "material_opened", "trial_cta_clicked", "trial_contact_submitted",
        ]
        for minute, event in enumerate(ordered):
            await self.add_event(1, event, minute)

        await self.add_user(2)
        # CTA/application before opening Learning Space must not count as a completed path.
        for minute, event in enumerate([
            "start", "goal_selected", "level_selected", "trial_cta_clicked",
            "trial_contact_submitted", "learning_space_opened", "material_opened",
        ]):
            await self.add_event(2, event, minute)

        result = await db.get_funnel_conversion(30)
        self.assertEqual(
            [(step["from"], step["to"]) for step in result["bot_steps"]],
            [(2, 2), (2, 2), (2, 2)],
        )
        self.assertEqual(
            [(step["from"], step["to"]) for step in result["learning_steps"]],
            [(2, 2), (2, 0), (0, 0)],
        )
        self.assertEqual(
            [(step["from"], step["to"]) for step in result["trial_steps"]],
            [(2, 2)],
        )

    async def test_funnel_uses_next_valid_event_not_only_first_event_of_each_type(self):
        await self.add_user(3)
        # Earlier out-of-order events must not hide a later valid sequence.
        events = [
            ("goal_selected", -2), ("level_selected", -1),
            ("start", 0), ("goal_selected", 1),
            ("level_selected", 2), ("learning_space_opened", 3),
            ("material_opened", 4), ("trial_cta_clicked", 5),
            ("trial_contact_submitted", 6),
        ]
        for name, minute in events:
            await self.add_event(3, name, minute)
        result = await db.get_funnel_conversion(30)
        self.assertEqual(
            [(step["from"], step["to"]) for step in result["bot_steps"]],
            [(1, 1), (1, 1), (1, 1)],
        )
        self.assertEqual(
            [(step["from"], step["to"]) for step in result["learning_steps"]],
            [(1, 1), (1, 0), (0, 0)],
        )
        self.assertEqual(
            [(step["from"], step["to"]) for step in result["trial_steps"]],
            [(1, 1)],
        )


    async def test_tracking_coverage_separates_bot_starts_and_miniapp_accounts(self):
        await self.add_user(1, "instagram")
        await self.add_event(1, "start", 0)
        await self.add_user(2, "miniapp")
        await self.add_event(2, "learning_space_opened", 1)
        await self.add_user(3, "instagram")

        result = await db.get_funnel_conversion(30)
        coverage = result["coverage"]
        self.assertEqual(coverage["registered"], 3)
        self.assertEqual(coverage["with_start_event"], 1)
        self.assertEqual(coverage["with_any_event"], 2)
        self.assertEqual(coverage["miniapp_created"], 1)
        self.assertEqual(coverage["without_any_event"], 1)
        self.assertAlmostEqual(coverage["start_rate"], 100 / 3)
        self.assertAlmostEqual(coverage["any_event_rate"], 200 / 3)

    async def test_material_engagement_requires_open_before_start_and_completion(self):
        await self.add_user(1)
        await self.add_event(1, "material_opened", 0)
        await self.add_event(1, "exercise_started", 1)
        await self.add_event(1, "exercise_submitted", 2)

        await self.add_user(2)
        await self.add_event(2, "exercise_started", 0)
        await self.add_event(2, "material_opened", 1)
        await self.add_event(2, "exercise_submitted", 2)

        result = await db.get_material_engagement_summary(30)
        self.assertEqual((result["opened"], result["started"], result["completed"]), (2, 1, 1))
        self.assertEqual(result["open_to_start"], 50.0)
        self.assertEqual(result["start_to_complete"], 100.0)

    async def test_notification_attribution_stops_at_next_automated_message(self):
        await self.add_user(1)
        await self.add_event(1, "nurture_day1_sent", 0)
        await self.add_event(1, "nurture_day2_sent", 5)
        await self.add_event(1, "trial_cta_clicked", 6)
        await self.add_event(1, "trial_contact_submitted", 7)

        result = await db.get_notification_stats(30)
        day1 = result["conversion"]["nurture_day1_sent"]
        day2 = result["conversion"]["nurture_day2_sent"]
        self.assertEqual((day1["recipients"], day1["clicked"], day1["submitted"]), (1, 0, 0))
        self.assertEqual((day2["recipients"], day2["clicked"], day2["submitted"]), (1, 1, 1))

    async def test_source_stats_separates_app_open_from_later_application(self):
        await self.add_user(1, "instagram")
        await self.add_event(1, "trial_contact_submitted", 0)
        await self.add_event(1, "learning_space_opened", 1)
        await self.add_user(2, "instagram")
        await self.add_event(2, "learning_space_opened", 0)
        await self.add_event(2, "trial_contact_submitted", 1)

        result = await db.get_source_stats()
        instagram = next(row for row in result if row["src"] == "instagram")
        self.assertEqual(instagram["users"], 2)
        self.assertEqual(instagram["trial_people"], 2)
        self.assertEqual(instagram["app_to_trial_people"], 1)
        self.assertEqual(instagram["app_to_trial_rate"], 50.0)


if __name__ == "__main__":
    unittest.main()


class QuizStatePersistenceTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db_path = db.DB_PATH
        db.DB_PATH = os.path.join(self.temp.name, "quiz-state.sqlite3")
        await db.init_db()
        await db.create_user_if_missing(101, "tester", "Test")

    async def asyncTearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp.cleanup()

    async def test_quiz_state_survives_database_reopen(self):
        expected = {"current": 3, "answers": {"0": 0, "1": 2, "2": 1}}
        await db.set_quiz_state(101, expected)
        self.assertEqual(await db.get_quiz_state(101), expected)

    async def test_clearing_quiz_state_removes_saved_progress(self):
        await db.set_quiz_state(101, {"current": 1, "answers": {"0": 0}})
        await db.clear_quiz_state(101)
        self.assertIsNone(await db.get_quiz_state(101))
