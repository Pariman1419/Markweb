"""Create or reset an application user for Mark Web (mark_app.app_user)."""
import argparse
import getpass
from http.cookiejar import CookieJar
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from argon2 import PasswordHasher
import psycopg2

from mark_engine.adapters.env import load_env


def reset_via_api(base_url: str, username: str, new_password: str,
                  admin_username: str, admin_password: str) -> int:
    """Reset through the API so session-cache invalidation is serialized."""
    cookies = CookieJar()
    opener = build_opener(HTTPCookieProcessor(cookies))
    base_url = base_url.rstrip("/")

    def request(path, payload=None, csrf=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data else {}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        req = Request(base_url + path, data=data, headers=headers)
        try:
            with opener.open(req, timeout=10) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(f"API request failed (HTTP {exc.code})") from exc
        except URLError as exc:
            raise RuntimeError("API unavailable") from exc

    request("/api/auth/login", {"username": admin_username, "password": admin_password})
    csrf = next((cookie.value for cookie in cookies if cookie.name in ("mark_csrf", "__Host-mark_csrf")), None)
    if not csrf:
        raise RuntimeError("API did not issue a CSRF cookie")
    users = request("/api/admin/users")
    target = next((user for user in users if user.get("username", "").lower() == username.lower()), None)
    if target is None:
        raise RuntimeError("Target user not found")
    user_id = int(target["user_id"])
    request(f"/api/admin/users/{user_id}/password", {"password": new_password}, csrf)
    try:
        request("/api/auth/logout", {}, csrf)
    except RuntimeError:
        # Resetting the current admin account also revokes the current session.
        pass
    return user_id


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="Create or reset an application user.")
    parser.add_argument("username", help="Unique username (case-insensitive)")
    parser.add_argument("--name", dest="display_name", help="Display name of user", default="")
    parser.add_argument("--role", choices=["engineer", "mark_eng_approver", "admin"], default="engineer")
    parser.add_argument("--reset", action="store_true", help="Reset password and clear account lock")
    parser.add_argument("--api-url", default=os.getenv("MARK_API_URL"), help="API base URL (required for --reset)")
    parser.add_argument("--host", default=os.getenv("MARK_PG_HOST", "10.151.28.2"))
    parser.add_argument("--db", default=os.getenv("MARK_PG_DB", "mark_web"))
    parser.add_argument("--user", default=os.getenv("MARK_PG_USER", "postgres"))
    args = parser.parse_args()

    username = args.username.strip().lower()
    if not username:
        print("Error: Username cannot be empty.", file=sys.stderr)
        sys.exit(1)

    if args.reset and not args.api_url:
        parser.error("--reset requires --api-url or MARK_API_URL so active sessions can be revoked safely")

    password = getpass.getpass("Enter password (min 12 chars): ")
    if len(password) < 12:
        print("Error: Password must be at least 12 characters.", file=sys.stderr)
        sys.exit(1)

    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Error: Passwords do not match.", file=sys.stderr)
        sys.exit(1)

    if args.reset:
        admin_username = input("Admin username: ").strip()
        admin_password = getpass.getpass("Admin password: ")
        try:
            user_id = reset_via_api(args.api_url, username, password, admin_username, admin_password)
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"Password reset and sessions revoked for user '{username}' (user_id={user_id}).")
        return

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
