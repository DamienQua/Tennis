"""Module strategy : détection Alpha 5+, Kelly, règlement et notifications SMTP."""

from .alpha_strategy import (
    calculate_kelly_stake,
    evaluate_alpha_strategy,
    format_alpha_summary,
)
from .alpha_tracker import record_alpha_selection, HEADERS
from .email_notifier import send_daily_email
from .generate_match_xlsx import generate_match_xlsx
from .result_settler import update_pending_results

__all__ = [
    "calculate_kelly_stake",
    "evaluate_alpha_strategy",
    "format_alpha_summary",
    "record_alpha_selection",
    "HEADERS",
    "send_daily_email",
    "generate_match_xlsx",
    "update_pending_results",
]