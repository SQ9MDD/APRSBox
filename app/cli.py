from __future__ import annotations

import argparse
import getpass
import sys

from app.auth import create_user, ensure_admin_user, update_user_password
from app.db import fetch_one, init_db


def init_db_command(_: argparse.Namespace) -> int:
    init_db()
    print("Database initialized.")
    return 0


def create_admin_command(args: argparse.Namespace) -> int:
    init_db()
    username = args.username or input("Initial admin username: ").strip()
    password = args.password or getpass.getpass("Initial admin password: ")
    created = ensure_admin_user(username=username, password=password)
    print("Admin user created." if created else "Admin user already exists.")
    return 0


def create_user_command(args: argparse.Namespace) -> int:
    init_db()
    password = args.password or getpass.getpass(f"Password for {args.username}: ")
    create_user(args.username, password, args.role, is_active=not args.inactive)
    print(f"User {args.username} created.")
    return 0


def set_password_command(args: argparse.Namespace) -> int:
    init_db()
    password = args.password or getpass.getpass(f"New password for {args.username}: ")
    update_user_password(args.username, password)
    print(f"Password updated for {args.username}.")
    return 0


def admin_exists_command(_: argparse.Namespace) -> int:
    init_db()
    row = fetch_one("SELECT COUNT(*) AS total FROM users WHERE role = 'admin' AND is_active = 1")
    return 0 if row and row["total"] > 0 else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="APRSBox administration helper.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init-db", help="Initialize the SQLite database")
    init_parser.set_defaults(func=init_db_command)

    admin_parser = subparsers.add_parser("create-admin", help="Create the initial admin user")
    admin_parser.add_argument("--username")
    admin_parser.add_argument("--password")
    admin_parser.set_defaults(func=create_admin_command)

    user_parser = subparsers.add_parser("create-user", help="Create a user")
    user_parser.add_argument("--username", required=True)
    user_parser.add_argument("--role", required=True, choices=["admin", "operator", "viewer"])
    user_parser.add_argument("--password")
    user_parser.add_argument("--inactive", action="store_true")
    user_parser.set_defaults(func=create_user_command)

    password_parser = subparsers.add_parser("set-password", help="Set or rotate a user password")
    password_parser.add_argument("--username", required=True)
    password_parser.add_argument("--password")
    password_parser.set_defaults(func=set_password_command)

    exists_parser = subparsers.add_parser("admin-exists", help="Exit 0 when an active admin user exists")
    exists_parser.set_defaults(func=admin_exists_command)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
