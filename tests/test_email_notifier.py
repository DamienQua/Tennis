import unittest
from unittest.mock import patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from strategy.email_notifier import (
    _is_config_valid,
    _build_subject,
    _build_html_content,
    _attach_excel,
    send_daily_email
)
from email.mime.multipart import MIMEMultipart

class TestEmailNotifier(unittest.TestCase):
    """Unit tests for email notification configuration and dispatch."""
    def test_is_config_valid(self):
        valid = {"user": "user@gmail.com", "password": "app_password", "recipient": "rec@gmail.com"}
        self.assertTrue(_is_config_valid(valid))

        invalid_no_pass = {"user": "user@gmail.com", "password": "", "recipient": "rec@gmail.com"}
        self.assertFalse(_is_config_valid(invalid_no_pass))

        invalid_no_user = {"user": "", "password": "app_password", "recipient": "rec@gmail.com"}
        self.assertFalse(_is_config_valid(invalid_no_user))

    def test_build_subject(self):
        sub_bets = _build_subject(3, "11/11/2026")
        self.assertIn("3 Pari(s) Alpha 5+", sub_bets)
        self.assertIn("11/11/2026", sub_bets)

        sub_no_bets = _build_subject(0, "11/11/2026")
        self.assertIn("0 pari", sub_no_bets)

    def test_build_html_content_with_bets(self):
        bets = [{
            "tournament": "Roland Garros",
            "surface": "Clay",
            "player1": "Carlos Alcaraz",
            "player2": "Fabio Fognini",
            "selected_player": "Carlos Alcaraz",
            "book_odds": 1.65,
            "model_odds": 1.25,
            "model_prob": 0.78,
            "ev_percent": 8.5,
            "elo_diff": 195.0
        }]
        html = _build_html_content(bets, total_matches=5, date_str="11/11/2026")
        self.assertIn("Carlos Alcaraz", html)
        self.assertIn("Roland Garros", html)
        self.assertIn("+8.5%", html)

    def test_build_html_content_without_bets(self):
        html = _build_html_content([], total_matches=10, date_str="11/11/2026")
        self.assertIn("Aucun pari qualifié", html)
        self.assertIn("10", html)

    def test_send_email_no_config_returns_false(self):
        mock_cfg = {"user": "", "password": "", "recipient": ""}
        result = send_daily_email([], total_matches=0, config=mock_cfg)
        self.assertFalse(result)

    def test_attach_excel_missing_file_safe(self):
        msg = MIMEMultipart()
        _attach_excel(msg, "non_existent_file_xyz.xlsx")
        self.assertEqual(len(msg.get_payload()), 0)

    @patch("smtplib.SMTP")
    def test_send_email_mock_success(self, mock_smtp):
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        mock_cfg = {
            "host": "smtp.gmail.com",
            "port": "587",
            "user": "test@gmail.com",
            "password": "secret_password",
            "recipient": "dest@gmail.com"
        }

        bets = [{
            "tournament": "Australian Open",
            "surface": "Hard",
            "player1": "Jannik Sinner",
            "player2": "Daniil Medvedev",
            "selected_player": "Jannik Sinner",
            "book_odds": 1.50,
            "model_odds": 1.20,
            "model_prob": 0.80,
            "ev_percent": 12.0,
            "elo_diff": 210.0
        }]

        success = send_daily_email(bets, total_matches=1, config=mock_cfg)
        self.assertTrue(success)
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("test@gmail.com", "secret_password")
        mock_instance.send_message.assert_called_once()

if __name__ == "__main__":
    unittest.main()
