import os
import subprocess
import sys
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

def run_restore(dump_file):
    if not os.path.exists(dump_file):
        print(f"File not found: {dump_file}")
        sys.exit(1)

    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD

    command = [
        "pg_restore",
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "-d", DB_NAME,
        "--clean",          # drops existing tables before restoring
        "--if-exists",      # avoids errors if tables don't exist yet
        dump_file
    ]

    print(f"Restoring from: {dump_file}")
    result = subprocess.run(command, env=env)

    if result.returncode == 0:
        print("Restore successful.")
    else:
        print("Restore failed.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python restore.py <path_to_dump_file>")
        print("Example: python restore.py backups/dumps/mydb_backup_20250101_120000.dump")
        sys.exit(1)

    run_restore(sys.argv[1])