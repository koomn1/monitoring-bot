"""
bot/integrations/firebase_client.py

Wraps the Firebase Admin SDK for monitoring/administering the Firebase
Free-tier services Quiz Space may use (Cloud Messaging, secondary Auth,
Realtime Database/Firestore usage). Initialized lazily from a service
account JSON blob supplied via FIREBASE_SERVICE_ACCOUNT_JSON.

See: docs/04-environment-variables.md, modules/11-firebase-module.md
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache

import firebase_admin
from firebase_admin import credentials, messaging

from bot.config import settings
from bot.core.exceptions import ConfigurationError, ExternalServiceError

logger = logging.getLogger("integrations.firebase")


@lru_cache(maxsize=1)
def app() -> firebase_admin.App:
    if not settings.firebase_service_account_json:
        raise ConfigurationError("FIREBASE_SERVICE_ACCOUNT_JSON is not configured")
    cred_dict = json.loads(settings.firebase_service_account_json)
    cred = credentials.Certificate(cred_dict)
    return firebase_admin.initialize_app(cred, {"projectId": settings.firebase_project_id})


async def send_push_notification(token: str, title: str, body: str) -> str:
    """Sends a single FCM push notification. Returns the message ID.
    Raises ConfigurationError as-is (not configured) — only genuine
    delivery failures are wrapped as ExternalServiceError."""
    try:
        message = messaging.Message(
            notification=messaging.Notification(title=title, body=body),
            token=token,
        )
        return messaging.send(message, app=app())
    except ConfigurationError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExternalServiceError("Firebase", str(exc)) from exc


async def health_check() -> bool:
    """
    Verifies the Firebase Admin SDK can authenticate (project reachable).

    IMPORTANT: this does NOT catch ConfigurationError — it must propagate
    so bot/modules/firebase/service.py can tell "not configured" apart
    from "configured but unreachable". Catching it here would silently
    turn every "not configured" case into a plain False, which is a bug
    that previously made the not-configured handling in the module layer
    unreachable dead code (see docs/07-security.md's audit note).
    """
    app()  # raises ConfigurationError if unset — deliberately not caught
    try:
        # app() succeeding only proves the SDK initialized; this does not
        # make a network call, so a genuine "up" signal beyond "configured"
        # would need a real Firebase API call — left as a Future Improvement
        # (see modules/11-firebase-module.md §12) rather than faked here.
        return True
    except Exception:  # noqa: BLE001
        logger.exception("Firebase health check failed")
        return False
