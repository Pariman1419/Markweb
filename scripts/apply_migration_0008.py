"""Apply Migration 0008: manual revision index and unread notification deduplication.

Usage:
  # Dry-run (rolls back automatically):
  python scripts/apply_migration_0008.py

  # Commit to live DB:
  python scripts/apply_migration_0008.py --commit

  # Rollback (down migration):
  python scripts/apply_migration_0008.py --down --commit
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
from mark_engine.adapters.env import load_env


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply migration 0008 to mark_web database.")
    parser.add_argument("--commit", action="store_true", help="Commit changes (default is dry-run with rollback)")
    parser.add_argument("--down", action="store_true", help="Run down migration (0008_manual_revision_down.sql)")
    parser.add_argument("--host", default=None, help="PostgreSQL host")
    parser.add_argument("--port", default=5432, type=int, help="PostgreSQL port")
    parser.add_argument("--dbname", default=None, help="Database name")
    parser.add_argument("--user", default=None, help="PostgreSQL user (DBA/owner required for schema changes)")
    parser.add_argument("--password", default=None, help="PostgreSQL password")
    args = parser.parse_args()

    load_env()

    host = args.host or os.getenv("MARK_PG_HOST", "10.151.28.2")
    dbname = args.dbname or os.getenv("MARK_PG_DB", "mark_web")
    user = args.user or os.getenv("MARK_PG_USER", "postgres")
    password = args.password or os.getenv("MARK_PG_PASSWORD", "")

    sql_file = "0008_manual_revision_down.sql" if args.down else "0008_manual_revision.sql"
    sql_path = REPO_ROOT / "migrations" / sql_file

    if not sql_path.is_file():
        print(f"Error: migration file not found: {sql_path}")
        return 1

    sql_content = sql_path.read_text(encoding="utf-8")

    mode_str = "COMMIT" if args.commit else "DRY-RUN (will ROLLBACK)"
    action_str = "DOWN (rollback)" if args.down else "UP (apply)"
    print(f"=== Migration 0008: {action_str} ===")
    print(f"Target DB: postgresql://{user}@{host}:{args.port}/{dbname}")
    print(f"SQL file:  {sql_file}")
    print(f"Mode:      {mode_str}")
    print("-" * 50)

    try:
        conn = psycopg2.connect(
            host=host,
            port=args.port,
            dbname=dbname,
            user=user,
            password=password,
            connect_timeout=10,
        )
    except Exception as exc:
        print(f"Failed to connect to database: {exc}")
        return 1

    try:
        with conn.cursor() as cur:
            print("Executing migration SQL...")
            cur.execute(sql_content)

            # Query verification
            if not args.down:
                cur.execute(
                    """
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE schemaname = 'mark_app'
                      AND tablename IN ('elr_revision', 'notification')
                      AND indexname IN ('elr_revision_fp_auto_unique', 'notification_unread_unique');
                    """
                )
                indexes = cur.fetchall()
                print(f"Verified {len(indexes)} index(es) created in mark_app:")
                for name, defn in indexes:
                    print(f"  - {name}: {defn}")

            if args.commit:
                conn.commit()
                print("\n[SUCCESS] Changes COMMITTED to database.")
            else:
                conn.rollback()
                print("\n[SUCCESS] Dry-run executed successfully. Transaction ROLLED BACK.")
    except Exception as exc:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {exc}")
        return 1
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
