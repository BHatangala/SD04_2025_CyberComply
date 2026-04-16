# Database Backup & Restore

This folder contains scripts to back up and restore your local PostgreSQL database.

---

## Setup (do this once after pulling)

### 1. Install dependencies
```
pip install python-dotenv schedule
```

### 2. Add these variables to your `.env` file in the project root
```
DB_NAME=your_database_name
DB_USER=your_postgres_username
DB_PASSWORD=your_postgres_password
DB_HOST=localhost
DB_PORT=5432

BACKUP_DIR=./backups/dumps
BACKUP_INTERVAL_HOURS=24
```
> Set `BACKUP_INTERVAL_HOURS=1` if you want backups every hour, `24` for once a day, etc.

---

## Running the Scripts

All commands should be run from the **project root** (where `manage.py` is).

### Take a manual backup right now
```
python backups/backup.py
```
This saves a `.dump` file inside `backups/dumps/` on your machine.

### Restore from a backup file
```
python backups/restore.py backups/dumps/<filename>.dump
```
Replace `<filename>` with the actual dump file name you want to restore from.

### Start automatic periodic backups
```
python backups/scheduler.py
```
This runs in the background and takes a backup every X hours based on your `.env`.
Keep this terminal open while you work. Close it to stop the scheduler.

---

## Notes
- Dump files are saved **locally only** and are gitignored — they will NOT be pushed to Bitbucket.
- Each team member's backups are independent of each other.
- If restore fails, make sure the database name in your `.env` matches your actual local PostgreSQL database.