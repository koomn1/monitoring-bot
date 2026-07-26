"""
scripts/run_migrations.py

Applies SQL files from bot/db/migrations/ in filename order against the
Supabase project's Postgres database, using a direct connection string
(SUPABASE_DB_URL) rather than the Supabase REST client, since raw DDL
execution is not exposed through supabase-py.

Usage:
    SUPABASE_DB_URL="postgresql://postgres:[password]@[host]:5432/postgres" \
        python scripts/run_migrations.py

See: database/05-database-migrations.md
"""

import os
import pathlib
import sys

import psycopg

MIGRATIONS_DIR = pathlib.Path(__file__).parent.parent / "bot" / "db" / "migrations"


def main() -> None:
    db_url = os.environ.get("SUPABASE_DB_URL")
    if not db_url:
        print("SUPABASE_DB_URL is not set. Get it from Supabase → Project Settings → Database.")
        sys.exit(1)

    migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migration_files:
        print("No migration files found.")
        return

    with psycopg.connect(db_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create table if not exists _migrations (
                    filename text primary key,
                    applied_at timestamptz not null default now()
                );
                """
            )
            cur.execute("select filename from _migrations;")
            applied = {row[0] for row in cur.fetchall()}

            for path in migration_files:
                if path.name in applied:
                    print(f"Skipping {path.name} (already applied)")
                    continue
                print(f"Applying {path.name}...")
                cur.execute(path.read_text())
                cur.execute("insert into _migrations (filename) values (%s);", (path.name,))
        conn.commit()

    print("Migrations complete.")


if __name__ == "__main__":
    main()
