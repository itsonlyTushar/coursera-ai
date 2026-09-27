"""Applies the app's Supabase schema directly from your machine, without a manual
copy/paste into the Supabase SQL Editor.

Runs the three SQL files in backend/database/sql/ against your project's
Postgres database, in the required order: schema -> dashboard views -> RLS.
This is a one-time setup step per Supabase project.

Prerequisites
-------------
Add SUPABASE_DB_URL to backend/.env (not the SUPABASE_URL/SUPABASE_SECRET_KEY
you already have, since those are the REST API and can't run DDL). Get the
direct Postgres connection string from:

    Supabase Dashboard -> Project Settings -> Database -> Connection string
    -> URI  (use the "Session pooler" URI if your network blocks direct
    connections, e.g. IPv6-only or you're behind a strict firewall)

It looks like:
    postgresql://postgres:[YOUR-PASSWORD]@db.<project-ref>.supabase.co:5432/postgres

Replace [YOUR-PASSWORD] with your actual database password (set at project
creation, resettable in the same Database settings page), then add it to
backend/.env as a single line:

    SUPABASE_DB_URL=postgresql://postgres:your-real-password@db.xxxx.supabase.co:5432/postgres

Usage
-----
    python scripts/apply_supabase_sql.py
    python scripts/apply_supabase_sql.py --dry-run   # just checks the connection
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = BACKEND_ROOT / "database" / "sql"

# Order matters: views depend on tables, RLS policies depend on tables.
SQL_FILES = [
    "supabase_schema.sql",
    "supabase_dashboard_views.sql",
    "supabase_rls.sql",
]


def main() -> int:
    # Connects to Supabase Postgres directly and runs each schema file in order.
    parser = argparse.ArgumentParser(description="Apply the Supabase schema locally.")
    parser.add_argument("--dry-run", action="store_true", help="only test the connection, run nothing")
    args = parser.parse_args()

    load_dotenv(BACKEND_ROOT / ".env")
    db_url = os.getenv("SUPABASE_DB_URL")
    if not db_url:
        print(
            "ERROR: SUPABASE_DB_URL is not set in backend/.env.\n"
            "Get it from Supabase Dashboard -> Project Settings -> Database -> Connection string.\n"
            "See the top of this script for the exact format."
        )
        return 2

    try:
        conn = psycopg2.connect(db_url)
    except psycopg2.OperationalError as exc:
        print(f"ERROR: could not connect to Supabase Postgres: {exc}")
        return 2

    print("Connected to Supabase Postgres.")
    if args.dry_run:
        print("Dry run: connection OK, no SQL executed.")
        conn.close()
        return 0

    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            for filename in SQL_FILES:
                path = SQL_DIR / filename
                if not path.exists():
                    print(f"ERROR: missing SQL file: {path}")
                    return 2

                sql = path.read_text(encoding="utf-8")
                print(f"Applying {filename} ...")
                cur.execute(sql)
                conn.commit()
                print(f"  OK: {filename}")
    except Exception as exc:
        conn.rollback()
        print(f"ERROR while applying schema: {exc}")
        print("Rolled back the failing file's changes. Earlier files already committed remain applied.")
        return 1
    finally:
        conn.close()

    print("\nAll three SQL files applied successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
