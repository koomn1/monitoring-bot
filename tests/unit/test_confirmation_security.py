from __future__ import annotations

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
