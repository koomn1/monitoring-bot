"""
scripts/seed_admin.py

One-time local script to register the first OWNER of the bot in the
bot_users table, for audit visibility (the actual permission grant is
via OWNER_USER_IDS in the environment — this script just records it).
Run locally: `python scripts/seed_admin.py <telegram_user_id> <username>`
"""

import asyncio
import sys

from bot.db.repositories.users_repo import upsert_bot_user


async def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/seed_admin.py <telegram_user_id> [username]")
        sys.exit(1)

    user_id = int(sys.argv[1])
    username = sys.argv[2] if len(sys.argv) > 2 else None
    await upsert_bot_user(user_id=user_id, username=username, role="OWNER")
    print(f"Registered {user_id} ({username}) as OWNER in bot_users.")


if __name__ == "__main__":
    asyncio.run(main())
