"""Module strategy : détection Alpha 5+, suivi Excel et notifications SMTP."""

from .alpha_strategy import evaluate_alpha_strategy, format_alpha_summary
from .alpha_tracker import record_alpha_selection, get_session_bets, HEADERS
from .email_notifier import send_daily_email
from .generate_match_xlsx import generate_match_xlsx

__all__ = [
    "evaluate_alpha_strategy",
    "format_alpha_summary",
    "record_alpha_selection",
    "get_session_bets",
    "HEADERS",
    "send_daily_email",
    "generate_match_xlsx",
]