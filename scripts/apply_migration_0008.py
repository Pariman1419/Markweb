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
from typing import Any

import psycopg2

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "services" / "api"))
from mark_engine.adapters.env import load_env


def cleanup_notifications_in_tx(cur: Any) -> list[dict[str, Any]]:
    """Find and mark as read:
    1. notification_id = 1 (false alarm from missing oracledb fallback)
    2. older duplicate unread notifications (keeping the newest one unread)
    Returns list of modified notification row dicts for display.
    """
    modified_rows: list[dict[str, Any]] = []

    # 1. Check notification 1
    cur.execute(
        """
        SELECT notification_id, elr_no, kind, revision, read_at, created_at, message
        FROM mark_app.notification
        WHERE notification_id = 1 AND read_at IS NULL;
        """
    )
    row1 = cur.fetchone()
    if row1:
        modified_rows.append({
            "id": row1[0],
            "elr_no": row1[1],
            "kind": row1[2],
            "revision": row1[3],
            "reason": "false alarm (oracledb missing fallback)",
            "created_at": str(row1[5]),
            "action": "mark read (read_at=now(), read_by=null)",
        })
        cur.execute(
            "UPDATE mark_app.notification SET read_at = NOW(), read_by = NULL WHERE notification_id = 1;"
        )

    # 2. Check duplicate unread notifications
    cur.execute(
        """
        SELECT notification_id, elr_no, kind, revision, created_at, message,
               ROW_NUMBER() OVER (
                 PARTITION BY elr_no, kind, COALESCE(revision, 0)
                 ORDER BY notification_id DESC
               ) as rn
        FROM mark_app.notification
        WHERE read_at IS NULL AND notification_id <> 1
        ORDER BY elr_no, kind, notification_id ASC;
        """
    )
    dup_rows = cur.fetchall()
    # rn = 1 is the newest row (kept unread). rn > 1 are older duplicate rows (mark read)
    for r in dup_rows:
        notif_id, elr, kind, rev, created, msg, rn = r
        if rn > 1:
            modified_rows.append({
                "id": notif_id,
                "elr_no": elr,
                "kind": kind,
                "revision": rev,
                "reason": f"duplicate unread (kept newer unread row)",
                "created_at": str(created),
                "action": "mark read (read_at=now(), read_by=null)",
            })
            cur.execute(
                "UPDATE mark_app.notification SET read_at = NOW(), read_by = NULL WHERE notification_id = %s;",
                (notif_id,),
            )

    return modified_rows


def check_indexes_exist(conn: Any) -> dict[str, bool]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'mark_app'
              AND indexname IN ('elr_revision_fp_auto_unique', 'notification_unread_unique');
            """
        )
        found = {r[0] for r in cur.fetchall()}
    return {
        "elr_revision_fp_auto_unique": "elr_revision_fp_auto_unique" in found,
        "notification_unread_unique": "notification_unread_unique" in found,
    }


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
    print("-" * 60)

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
            if not args.down:
                print("1. Scanning for notifications to clean up before index creation...")
                cleaned = cleanup_notifications_in_tx(cur)
                if cleaned:
                    print(f"   Found {len(cleaned)} notification row(s) to mark as read:")
                    for c in cleaned:
                        print(f"   - ID {c['id']}: ELR {c['elr_no']} [{c['kind']}] rev={c['revision']} ({c['reason']}) -> {c['action']}")
                else:
                    print("   No duplicate or false-alarm notifications found.")

            print(f"\n2. Executing SQL from {sql_file} in transaction...")
            cur.execute(sql_content)

            # Query verification in transaction
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
                print(f"   In-transaction check: {len(indexes)} index(es) active:")
                for name, defn in indexes:
                    print(f"   - {name}")

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

    # If dry-run, prove on a fresh connection that no index exists and no state was changed
    if not args.commit:
        verify_conn = psycopg2.connect(
            host=host, port=args.port, dbname=dbname, user=user, password=password, connect_timeout=10
        )
        try:
            status = check_indexes_exist(verify_conn)
            with verify_conn.cursor() as cur:
                cur.execute("SELECT notification_id, read_at FROM mark_app.notification WHERE notification_id = 1;")
                r1 = cur.fetchone()
                r1_read = r1[1] if r1 else None

            print("\n=== Post-Rollback DB State Verification ===")
            print(f"  - index elr_revision_fp_auto_unique exists?  {status['elr_revision_fp_auto_unique']} (expected False)")
            print(f"  - index notification_unread_unique exists?   {status['notification_unread_unique']} (expected False)")
            print(f"  - notification_id=1 read_at:                 {r1_read} (expected None)")
            assert not status["elr_revision_fp_auto_unique"], "DRY-RUN LEAK: elr_revision_fp_auto_unique exists!"
            assert not status["notification_unread_unique"], "DRY-RUN LEAK: notification_unread_unique exists!"
            assert r1_read is None, "DRY-RUN LEAK: notification 1 was marked as read!"
            print("  -> Proof verified: Dry-run left zero footprint on database.")
        finally:
            verify_conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
