"""Create an API token for Mark Web (mark_app.api_token)."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import secrets
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import psycopg2

from mark_engine.adapters.env import load_env


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Create an API token.")
    parser.add_argument("name", help="Name or purpose of the API token")
    parser.add_argument("--scope", default="metrics:read", help="Scope(s) comma-separated (e.g. metrics:read)")
    parser.add_argument("--days", type=int, default=90, help="Token validity in days (default: 90)")
    parser.add_argument("--user", default=None, help="Username of the creator (defaults to first admin/user)")
    parser.add_argument("--host", default=os.getenv("MARK_PG_HOST", "10.151.28.2"))
    parser.add_argument("--db", default=os.getenv("MARK_PG_DB", "mark_web"))
    parser.add_argument("--db-user", default=os.getenv("MARK_PG_USER", "postgres"))
    args = parser.parse_args()

    scopes = [s.strip() for s in args.scope.split(",") if s.strip()]
    raw_token = f"mkt_{secrets.token_urlsafe(32)}"
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=args.days) if args.days > 0 else None

    password_db = os.environ.get("MARK_PG_PASSWORD", "")
    conn = psycopg2.connect(
        host=args.host,
        port=5432,
        dbname=args.db,
        user=args.db_user,
        password=password_db,
        connect_timeout=8,
    )
    try:
        with conn.cursor() as cur:
            if args.user:
                cur.execute("select user_id from mark_app.app_user where lower(username) = %s", (args.user.strip().lower(),))
                res = cur.fetchone()
                if not res:
                    print(f"Error: Creator user '{args.user}' not found.", file=sys.stderr)
                    sys.exit(1)
                creator_id = res[0]
            else:
                cur.execute("select user_id from mark_app.app_user order by user_id asc limit 1")
                res = cur.fetchone()
                if not res:
                    print("Error: No users in mark_app.app_user. Create an app user first.", file=sys.stderr)
                    sys.exit(1)
                creator_id = res[0]

            cur.execute(
                """
                insert into mark_app.api_token (name, token_hash, scopes, created_by, expires_at)
                values (%s, %s, %s, %s, %s)
                returning token_id
                """,
                (args.name.strip(), token_hash, scopes, creator_id, expires_at),
            )
            token_id = cur.fetchone()[0]
            conn.commit()

            print("=" * 60)
            print(f"API Token Created: {args.name} (token_id={token_id})")
            print(f"Scopes: {scopes}")
            print(f"Expires: {expires_at}")
            print("Token (Save this now! It cannot be retrieved again):")
            print(raw_token)
            print("=" * 60)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
