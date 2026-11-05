"""Create or reset an application user for Mark Web (mark_app.app_user)."""
import argparse
import getpass
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from argon2 import PasswordHasher
import psycopg2

from mark_engine.adapters.env import load_env


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Create or reset an application user.")
    parser.add_argument("username", help="Unique username (case-insensitive)")
    parser.add_argument("--name", dest="display_name", help="Display name of user", default="")
    parser.add_argument("--role", choices=["engineer", "mark_eng_approver", "admin"], default="engineer")
    parser.add_argument("--reset", action="store_true", help="Reset password and clear account lock")
    parser.add_argument("--host", default=os.getenv("MARK_PG_HOST", "10.151.28.2"))
    parser.add_argument("--db", default=os.getenv("MARK_PG_DB", "mark_web"))
    parser.add_argument("--user", default=os.getenv("MARK_PG_USER", "postgres"))
    args = parser.parse_args()

    username = args.username.strip().lower()
    if not username:
        print("Error: Username cannot be empty.", file=sys.stderr)
        sys.exit(1)

    password = getpass.getpass("Enter password (min 12 chars): ")
    if len(password) < 12:
        print("Error: Password must be at least 12 characters.", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    ph = PasswordHasher()
    pwd_hash = ph.hash(password)

    password_db = os.environ.get("MARK_PG_PASSWORD", "")
    conn = psycopg2.connect(
        host=args.host,
        port=5432,
        dbname=args.db,
        user=args.user,
        password=password_db,
        connect_timeout=8,
    )
    try:
        with conn.cursor() as cur:
            if args.reset:
                cur.execute(
                    """
                    update mark_app.app_user
                    set password_hash = %s,
                        failed_count = 0,
                        locked_until = null
                    where lower(username) = %s
                    returning user_id
                    """,
                    (pwd_hash, username),
                )
                res = cur.fetchone()
                if not res:
                    print(f"Error: User '{username}' not found for reset.", file=sys.stderr)
                    conn.rollback()
                    sys.exit(1)
                user_id = res[0]
                cur.execute("delete from mark_app.user_session where user_id = %s", (user_id,))
                conn.commit()
                print(f"Password reset and lock cleared for user '{username}' (user_id={user_id}).")
            else:
                display_name = args.display_name.strip() or username
                cur.execute(
                    """
                    insert into mark_app.app_user (username, display_name, role, password_hash)
                    values (%s, %s, %s, %s)
                    returning user_id
                    """,
                    (username, display_name, args.role, pwd_hash),
                )
                user_id = cur.fetchone()[0]
                conn.commit()
                print(f"Created user '{username}' (role={args.role}, user_id={user_id}).")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
