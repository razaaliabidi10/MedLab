"""
database/apply_migration.py
============================
Applies migration_v2.sql and seed_v2.sql to medlab_db.
Uses the mysql CLI client directly for full native compatibility with DELIMITER,
triggers, stored procedures, and PREPARE statements.

Usage (from project root, with venv active):
    python database/apply_migration.py
"""

import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

DB_HOST     = os.environ.get("DB_HOST",     "127.0.0.1")
DB_PORT     = os.environ.get("DB_PORT",     "3306")
DB_USER     = os.environ.get("DB_USER",     "root")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME     = os.environ.get("DB_NAME",     "medlab_db")


def run_sql_file(filepath: str, label: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  Applying: {label}")
    print(f"{'='*60}")

    if not os.path.exists(filepath):
        print(f"  [ERROR] File not found: {filepath}")
        return False

    mysql_exe = shutil.which("mysql")
    if not mysql_exe:
        print("  [ERROR] 'mysql' CLI executable not found on system PATH.")
        return False

    cmd = [
        mysql_exe,
        f"--host={DB_HOST}",
        f"--port={DB_PORT}",
        f"--user={DB_USER}",
        f"--default-character-set=utf8mb4",
        DB_NAME,
    ]
    if DB_PASSWORD:
        cmd.insert(4, f"--password={DB_PASSWORD}")

    with open(filepath, "rb") as f:
        res = subprocess.run(cmd, stdin=f, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if res.returncode != 0:
        print(f"  [FAILED with code {res.returncode}]")
        if res.stderr:
            print(res.stderr.strip())
        return False

    if res.stdout:
        print(res.stdout.strip())
    print(f"  [SUCCESS] {label} applied cleanly.")
    return True


def main():
    print(f"Applying database updates for {DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME} ...")
    base = os.path.dirname(__file__)

    # 1. Migration schema changes
    mig = os.path.join(base, "migration_v2.sql")
    if not run_sql_file(mig, "migration_v2.sql"):
        sys.exit(1)

    # 2. Seed data
    seed = os.path.join(base, "seed_v2.sql")
    if os.path.exists(seed):
        if not run_sql_file(seed, "seed_v2.sql"):
            sys.exit(1)
    else:
        print("\n[WARNING] seed_v2.sql not found. Run generate_seed_hashes.py first.")

    print("\n✅ All migrations and seeds applied successfully!")


if __name__ == "__main__":
    main()
