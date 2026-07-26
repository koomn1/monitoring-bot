"""
bot/core/exceptions.py

Shared exception hierarchy used across all modules. Central so that the
router / middleware can catch known exception types and respond
appropriately, instead of every module inventing its own error shape.

See: docs/03-system-architecture.md (Error Handling)
"""


class QuizSpaceBotError(Exception):
    """Base class for all Bot-raised exceptions."""


class UnauthorizedError(QuizSpaceBotError):
    """Raised when a Telegram user is not recognized by the Bot at all."""


class ForbiddenError(QuizSpaceBotError):
    """Raised when a recognized user lacks the role required for an action."""


class ConfirmationRequiredError(QuizSpaceBotError):
    """
    Raised by destructive actions (deploy, rollback, restore, backup)
    when the caller has not yet supplied an explicit confirmation.
    The router catches this, builds a Confirm/Cancel inline keyboard via
    bot/utils/keyboards.py:confirmation_buttons(command, extra_args), and
    re-prompts the user instead of executing the action. `extra_args`
    preserves any parameters (e.g. environment, backup_id) so the
    eventual "Confirm" tap can re-invoke the command with them intact.
    """

    def __init__(self, command: str, message: str, extra_args: list[str] | None = None):
        self.command = command
        self.extra_args = extra_args or []
        super().__init__(message)


class ExternalServiceError(QuizSpaceBotError):
    """
    Raised by integrations/* clients when a third-party free-tier service
    (Supabase, GitHub, Cloudflare, Firebase, Sentry, Analytics, Telegram)
    fails, times out, or returns an unexpected response.
    """

    def __init__(self, service: str, message: str, *, status_code: int | None = None):
        self.service = service
        self.status_code = status_code
        super().__init__(f"[{service}] {message}")


class ConfigurationError(QuizSpaceBotError):
    """Raised when a module is invoked but its required configuration/
    credentials are missing (e.g. Firebase module called without
    FIREBASE_SERVICE_ACCOUNT_JSON configured)."""


class RateLimitedError(QuizSpaceBotError):
    """Raised when a command or job is throttled to protect free-tier quotas."""
