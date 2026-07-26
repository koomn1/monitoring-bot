"""
scripts/local_dev_runner.py

Convenience entrypoint for local development: loads .env via
python-dotenv (production relies on real environment variables /
GitHub Actions secrets — see docs/04-environment-variables.md) then
starts the bot in polling mode.
"""

from dotenv import load_dotenv

load_dotenv()

from bot.main import main  # noqa: E402

if __name__ == "__main__":
    main()
