"""
Outbox policy for outgoing Telegram messages. Pure functions, no aiogram import, so they can be tested
without a bot. It mirrors dental_miniapp/src/lib/outbox.ts; keep the two in step.
"""

from typing import Optional, Tuple

OUTBOX_MAX_ATTEMPTS = 8


def next_delay_seconds(attempts: int) -> int:
    """5 s, 10 s, 20 s ... capped at 30 minutes"""
    base = 5 * (2 ** max(0, attempts - 1))
    return min(base, 1800)


def classify_failure(status: Optional[int]) -> str:
    """429 -> wait for retry_after; 403 -> the patient blocked the bot; 400 -> bad request; else transient"""
    if status == 429:
        return "retry_after"
    if status == 403:
        return "blocked"
    if status == 400:
        return "bad_request"
    return "transient"


def after_failure(attempts_so_far: int, failure: str, retry_after: Optional[int] = None) -> Tuple[str, int]:
    """Returns (new_status, delay_seconds). new_status is 'pending' or 'failed'."""
    attempts = attempts_so_far + 1
    if failure in ("blocked", "bad_request") or attempts >= OUTBOX_MAX_ATTEMPTS:
        return "failed", 0
    if failure == "retry_after" and retry_after:
        return "pending", int(retry_after)
    return "pending", next_delay_seconds(attempts)


def is_group_chat(chat_id: int) -> bool:
    """Group and supergroup ids are negative"""
    return chat_id < 0
