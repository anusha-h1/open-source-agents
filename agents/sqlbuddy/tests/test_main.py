
import unittest
from unittest.mock import patch

import main


class TestSQLBuddy(unittest.TestCase):

    def test_menu_displays_four_options(self):
        with patch("builtins.print") as mock_print:
            main.show_menu()

        printed_text = " ".join(
            str(call) for call in mock_print.call_args_list
        )

        self.assertIn("Convert English to SQL", printed_text)
        self.assertIn("Explain an SQL query", printed_text)
        self.assertIn("Help with an SQL error", printed_text)
        self.assertIn("Exit", printed_text)

    def test_missing_api_key_message(self):
        with patch.object(main, "API_KEY", None):
            result = main.ask_gemini("Generate a SQL query")

        self.assertIn("API key not configured", result)

    def test_api_key_placeholder_message(self):
        with patch.object(main, "API_KEY", "your_api_key_here"):
            result = main.ask_gemini("Generate a SQL query")

        self.assertIn("API key not configured", result)


if __name__ == "__main__":
    unittest.main()
