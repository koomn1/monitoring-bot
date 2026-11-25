from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from bot.utils import keyboards


def test_confirmation_token_is_bound_to_user_and_chat_and_expires(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(keyboards.time, "monotonic", lambda: now[0])

    buttons = keyboards.confirmation_buttons(
        "restore", ["backup-123"], user_id=111, chat_id=222
    )
    token = buttons[0][0]["callback_data"].split("|", 1)[1]

    assert keyboards.resolve_confirmation_token(token, user_id=999, chat_id=222) is None
    assert keyboards.resolve_confirmation_token(token, user_id=111, chat_id=999) is None
    assert keyboards.resolve_confirmation_token(token, user_id=111, chat_id=222) == (
        "restore",
        ["backup-123"],
    )
    assert keyboards.resolve_confirmation_token(token, user_id=111, chat_id=222) is None

    expiring = keyboards.confirmation_buttons(
        "rollback", ["production"], user_id=111, chat_id=222
    )[0][0]["callback_data"].split("|", 1)[1]
    now[0] += keyboards._CONFIRMATION_TTL_SECONDS + 1
    assert keyboards.resolve_confirmation_token(expiring, user_id=111, chat_id=222) is None


def test_confirmation_cancel_callback_contains_token_and_invalidates_it():
    buttons = keyboards.confirmation_buttons("deletequiz", ["quiz-1"], user_id=111, chat_id=222)
    confirm_data = buttons[0][0]["callback_data"]
    cancel_data = buttons[0][1]["callback_data"]
    confirm_token = confirm_data.split("|", 1)[1]
    cancel_token = cancel_data.split("|", 1)[1]

    assert confirm_data.startswith("confirm_tok|")
    assert cancel_data.startswith("cancel_tok|")
    assert cancel_token == confirm_token
    assert keyboards.resolve_confirmation_token(cancel_token, user_id=111, chat_id=222) == (
        "deletequiz",
        ["quiz-1"],
    )
    assert keyboards.resolve_confirmation_token(confirm_token, user_id=111, chat_id=222) is None


def test_confirmation_token_is_consumed_by_only_one_concurrent_caller():
    buttons = keyboards.confirmation_buttons("restore", ["backup-1"], user_id=111, chat_id=222)
    token = buttons[0][0]["callback_data"].split("|", 1)[1]

    def consume():
        return keyboards.resolve_confirmation_token(token, user_id=111, chat_id=222)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: consume(), range(32)))

    successful = [result for result in results if result is not None]
    assert successful == [("restore", ["backup-1"])]
