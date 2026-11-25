from types import SimpleNamespace

from bot.modules.telegram_commands.handlers import _integration_readiness


def _settings(**overrides):
    defaults = {
        "telegram_bot_token": "token",
        "supabase_url": "url",
        "supabase_service_role_key": "service-key",
        "github_token": "gh-token",
        "github_repo": "owner/repo",
        "github_webhook_secret": "gh-secret",
        "cloudflare_api_token": "cf-token",
        "cloudflare_account_id": "account",
        "cloudflare_project_name": "project",
        "sentry_auth_token": "sentry-token",
        "sentry_org_slug": "org",
        "sentry_project_slug": "project",
        "umami_api_url": "https://umami.example",
        "umami_api_key": "umami-key",
        "umami_website_id": "website",
        "firebase_project_id": "firebase",
        "firebase_service_account_json": '{"type":"service_account"}',
        "ai_api_key": "ai-key",
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_integration_readiness_requires_every_variable_in_group():
    readiness = {
        name: (ready, missing)
        for name, ready, missing in _integration_readiness(
            _settings(cloudflare_account_id=None, umami_website_id=None)
        )
    }

    assert readiness["GitHub Actions"] == (True, [])
    assert readiness["Cloudflare"] == (False, ["CLOUDFLARE_ACCOUNT_ID"])
    assert readiness["Umami"] == (False, ["UMAMI_WEBSITE_ID"])


def test_integration_readiness_reports_missing_names_not_secret_values():
    readiness = _integration_readiness(_settings(sentry_auth_token=None))
    sentry = next(item for item in readiness if item[0] == "Sentry")

    assert sentry == ( "Sentry", False, ["SENTRY_AUTH_TOKEN"])
    assert "sentry-token" not in repr(readiness)
