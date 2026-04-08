import os
import schedule
import time
from dotenv import load_dotenv
from backup import run_backup

load_dotenv()

# Set BACKUP_INTERVAL_HOURS=24 in your .env for daily, 1 for every hour, etc.
BACKUP_INTERVAL_HOURS = int(os.getenv("BACKUP_INTERVAL_HOURS", "24"))

def start_scheduler():
    print(f"Scheduler started. Running backup every {BACKUP_INTERVAL_HOURS} hour(s).")
    print("Running an initial backup now...")
    run_backup()

    schedule.every(BACKUP_INTERVAL_HOURS).hours.do(run_backup)

    while True:
        schedule.run_pending()
        time.sleep(60)  # checks every minute if a backup is due

if __name__ == "__main__":
    start_scheduler()