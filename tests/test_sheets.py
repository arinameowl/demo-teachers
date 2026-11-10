import unittest
from unittest.mock import patch

from handlers import sheets


class GoogleSheetsRowTest(unittest.TestCase):
    def test_trial_row_matches_current_sheet_columns(self):
        with patch.object(sheets, "_msk_now", return_value="10.11.2026 12:30"):
            row = sheets._build_trial_row(name="Арина Тест", username="arina_test")

        self.assertEqual(len(row), 10)
        self.assertEqual(row, [
            "10.11.2026 12:30",
            "Бот",
            "Арина Тест",
            "@arina_test",
            "",
            "",
            "",
            "",
            "В работе",
            "",
        ])

    def test_trial_row_without_telegram_username(self):
        with patch.object(sheets, "_msk_now", return_value="10.11.2026 12:30"):
            row = sheets._build_trial_row(name="Тест", username=None)

        self.assertEqual(row[3], "—")
        self.assertEqual(row[4], "")
        self.assertEqual(row[8], "В работе")


if __name__ == "__main__":
    unittest.main()
