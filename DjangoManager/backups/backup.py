import os
import subprocess
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
BACKUP_DIR = os.getenv("BACKUP_DIR", "./backups/dumps")

def run_backup():
    os.makedirs(BACKUP_DIR, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{DB_NAME}_backup_{timestamp}.dump"
    filepath = os.path.join(BACKUP_DIR, filename)

    env = os.environ.copy()
    env["PGPASSWORD"] = DB_PASSWORD

    command = [
        "pg_dump",
        "-h", DB_HOST,
        "-p", DB_PORT,
        "-U", DB_USER,
        "-F", "c",          # custom compressed format
        "-f", filepath,
        DB_NAME
    ]

    print(f"Starting backup: {filename}")
    result = subprocess.run(command, env=env)

    if result.returncode == 0:
        print(f"Backup successful: {filepath}")
    else:
        print("Backup failed.")

if __name__ == "__main__":
    run_backup()