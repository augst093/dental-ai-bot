"""Unit tests for the outbox retry policy (no Telegram, no database). Run: python scripts/test_outbox_policy.py"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from services.outbox_policy import (  # noqa: E402
    OUTBOX_MAX_ATTEMPTS,
    after_failure,
    classify_failure,
    is_group_chat,
    next_delay_seconds,
)


def test_backoff_grows_and_caps():
    assert next_delay_seconds(1) == 5
    assert next_delay_seconds(2) == 10
    assert next_delay_seconds(3) == 20
    assert next_delay_seconds(20) == 1800


def test_429_waits_for_telegram_retry_after():
    assert classify_failure(429) == "retry_after"
    assert after_failure(0, "retry_after", 37) == ("pending", 37)


def test_403_is_final():
    assert classify_failure(403) == "blocked"
    assert after_failure(0, "blocked") == ("failed", 0)


def test_400_is_final():
    assert after_failure(0, classify_failure(400))[0] == "failed"


def test_network_errors_retry_with_backoff():
    assert classify_failure(None) == "transient"
    assert classify_failure(502) == "transient"
    assert after_failure(2, "transient") == ("pending", 20)


def test_gives_up_after_max_attempts():
    assert after_failure(OUTBOX_MAX_ATTEMPTS - 1, "transient")[0] == "failed"
    assert after_failure(OUTBOX_MAX_ATTEMPTS - 2, "transient")[0] == "pending"


def test_group_chats_have_negative_ids():
    assert is_group_chat(-1001234567890) is True
    assert is_group_chat(123456789) is False


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    for fn in tests:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")
