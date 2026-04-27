# CyberComply — Project Setup Guide

## Overview

CyberComply is a full-stack regulatory compliance management system. This guide covers the complete setup for all modules across all branches.

**System Architecture:**
- **Web Interface:** Django (Port 8000) — `SD04_2025/Database/DjangoManager/`
- **AI Engine:** Flask + Celery (Port 5000) — `SD04_2025/AIModel/`
- **Task Queue:** Celery + Redis
- **Database:** PostgreSQL
- **File Storage:** AWS S3
- **Email / OTP Delivery:** AWS SES
- **Malware Scanning:** ClamAV (via Docker)
- **AI Model:** DeepSeek R1 Distill Qwen 32B (via OpenRouter API)

---

## Prerequisites

### Hardware
- RAM: Minimum 16GB

### Software
Ensure the following are installed before proceeding:
- Python 3.10 or higher
- PostgreSQL (v14 recommended)
- Git
- Docker Desktop
- Redis (see Section 4)

---

## 1. Clone the Repository

```bash
git clone <repository-url>
cd SD04_2025
```

---

## 2. Virtual Environment

Create and activate the virtual environment from the **SD04_2025 root**.

```bash
python -m venv venv
```

**Activate — Windows (PowerShell):**
```powershell
.\venv\Scripts\activate
```

If activation fails due to execution policy:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
```

**Activate — macOS/Linux:**
```bash
source venv/bin/activate
```

---

## 3. Install Python Dependencies

With the virtual environment activated, install all dependencies:

```bash
pip install -r requirements.txt
```

---

## 4. Redis Installation

Redis is required for the Celery task queue and must be running before starting the AI engine.

**Option A — Via WSL (Windows):**
```bash
wsl
sudo apt update
sudo apt install redis-server
```

Verify:
```bash
redis-cli ping
```
Expected: `PONG`

**Option B — Via Memurai (Windows, no WSL required):**

Download and install from https://www.memurai.com/get-memurai. Memurai installs as a Windows service and starts automatically.

Verify:
```bash
memurai-cli ping
```
Expected: `PONG`

**macOS:**
```bash
brew install redis
brew services start redis
```

> Redis must be running before starting the Celery worker or the Flask AI server.

---

## 5. PostgreSQL Database Setup

### Create the Database

```bash
psql -U postgres
```

Inside `psql`, run:

```sql
CREATE DATABASE cybercomply_db;
CREATE USER cybercomply_user WITH PASSWORD 'your_secure_password';
ALTER USER cybercomply_user CREATEDB;
GRANT ALL PRIVILEGES ON DATABASE cybercomply_db TO cybercomply_user;
ALTER DATABASE cybercomply_db OWNER TO cybercomply_user;
\q
```

---

## 6. Environment Configuration

Create a `.env` file inside the **DjangoManager** folder (same level as `manage.py`). Use `.env.example` as the template:

```bash
cp .env.example .env
```

Then fill in the values as described below.

### Django

```
SECRET_KEY=
DEBUG=True
```

### Database

```
DB_NAME=cybercomply_db
DB_USER=cybercomply_user
DB_PASSWORD=your_secure_password
DB_HOST=127.0.0.1
DB_PORT=5432
```

### AI Engine

```
OPENROUTER_API_KEY=your_api_key_here
```

Get your key from https://openrouter.ai/

### AWS (S3 and SES)

```
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key_here
AWS_STORAGE_BUCKET_NAME=
AWS_REGION=
AWS_SHARED_REPORTS_BUCKET_NAME=
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=
```

Only fill in `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` with your own credentials. Leave the remaining values unchanged unless instructed otherwise by the team.

### Database Backups

```
BACKUP_DIR=./backups/dumps
BACKUP_INTERVAL_HOURS=24
```

Set `BACKUP_INTERVAL_HOURS=1` for hourly backups, `24` for once a day.

> The actual `.env` file must never be committed to Bitbucket. It is already listed in `.gitignore`.

---

## 7. Apply Database Migrations

```bash
cd Database/DjangoManager
python manage.py migrate
```

### Create a Superuser (optional, for admin panel access)

```bash
python manage.py createsuperuser
```

---

## 8. ClamAV Setup (Docker)

ClamAV handles malware scanning for uploaded files. Docker Desktop must be running before starting the Django server.

**First-time setup:**
```bash
docker pull clamav/clamav:latest
docker run -d --name clamav -p 3310:3310 clamav/clamav:latest
```

**Subsequent runs:**
```bash
docker start clamav
```

**Verify the container is healthy:**
```bash
docker ps
```

The `STATUS` column should show `healthy` next to the `clamav` container. If it shows `starting`, wait 1–2 minutes and check again.

---

## 9. Running the Full System

The system requires **four terminal windows**. Start them in the order listed below.

> **Resuming after a previous session?** Clear any leftover jobs from Redis first to avoid stale tasks:
> ```bash
> redis-cli FLUSHDB
> ```

### Terminal A — Redis Server

Only required if using WSL. Skip if using Memurai (it runs automatically).

```bash
wsl
redis-server
```

Leave this terminal running.

### Terminal B — AI Engine (Flask)

```bash
cd SD04_2025
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # macOS/Linux
cd AIModel
python api_server.py
```

Wait for: `Running on http://127.0.0.1:5000`

Leave this terminal running.

### Terminal C — Celery Worker

```bash
cd SD04_2025
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # macOS/Linux
cd AIModel
celery -A celery_app.celery worker --loglevel=info
```

Wait for: `celery@<hostname> ready.` and confirm `run_compliance_analysis` appears under `[tasks]`.

Leave this terminal running.

### Terminal D — Web Interface (Django)

```bash
cd SD04_2025
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # macOS/Linux
cd Database/DjangoManager
python manage.py runserver
```

Access the application at: `http://127.0.0.1:8000`

### Accessing the Application (Live Server)

Install the **Live Server** extension in VS Code if you haven't already:
- Open VS Code → Extensions (`Ctrl + Shift + X`) → search **Live Server** → Install

Then open the `SD04_2025/frontend/` folder in VS Code, right-click `welcome.html` and select **Open with Live Server**.

Access the application at: `http://127.0.0.1:5500`

---

## 10. Verifying All Services

Once all terminals are running, open a browser and go to:

```
http://127.0.0.1:5000/health
```

If `status` is `healthy` and `queue_depth` is `0`, all services (Redis, Flask, Celery) are connected and ready.

---

## 11. Database Backups

All backup scripts are located in `Database/DjangoManager/backups/`. Run all commands from the `Database/DjangoManager/` directory.

### Take a Manual Backup
```bash
python backups/backup.py
```

Saves a `.dump` file to `backups/dumps/` on your local machine.

### Restore from a Backup
```bash
python backups/restore.py backups/dumps/<filename>.dump
```

Replace `<filename>` with the actual dump file name.

### Start Automatic Periodic Backups
```bash
python backups/scheduler.py
```

Runs in the background and takes a backup every X hours based on `BACKUP_INTERVAL_HOURS` in your `.env`. Keep this terminal open while working.

> Dump files are saved locally only and are gitignored — they will not be pushed to Bitbucket. Each team member's backups are independent.

---

## 12. PostgreSQL Verification

Connect to the database directly:

```bash
psql -U cybercomply_user -d cybercomply_db
```

List all tables:
```sql
\dt
```

Inspect a table:
```sql
\d organization
\d user_profile
```

Run sample queries:
```sql
SELECT * FROM organization;
SELECT * FROM user_profile;
```

Exit:
```sql
\q
```

---

## 13. Running Tests

```bash
cd Database/DjangoManager
python manage.py test core
```

---

## 14. Before Pushing to Bitbucket

- Ensure `.env` is not staged or committed
- If new packages were installed, update the requirements file:
```bash
pip freeze > requirements.txt
```
- All model changes must include corresponding migration files
- All changes must pass unit tests before committing
- Do not commit sensitive files (`.env`, dump files)

---

## 15. AWS SES — Testing Notes

AWS SES is currently in sandbox mode. Only verified email addresses can receive emails. Use a verified email address when testing OTP functionality.

**Supported file upload formats:** `.pdf`, `.docx`, `.txt`  
**Maximum file size:** 50MB — all files are scanned with ClamAV before processing.

---

## Appendix A — Admin Panel

Access the Django admin panel at:
```
http://127.0.0.1:8000/admin
```

---

## Appendix B — Query Performance Monitoring (pg_stat_statements)

### Step 1: Enable the Extension in PostgreSQL Config

**macOS:**
```bash
nano /usr/local/var/postgresql@14/postgresql.conf
```

**Windows:** Open `C:\Program Files\PostgreSQL\14\data\postgresql.conf`

Find and update (remove the `#` to uncomment):
```
shared_preload_libraries = 'pg_stat_statements'
```

**Restart PostgreSQL:**

macOS:
```bash
brew services restart postgresql@14
```

Windows (run Command Prompt as Administrator):
```bash
net stop postgresql-x64-14
net start postgresql-x64-14
```

### Step 2: Enable the Extension in the Database

```bash
psql -U postgres
```

```sql
\c cybercomply_db
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
GRANT pg_read_all_stats TO cybercomply_user;
\q
```

### Step 3: Generate System Activity

Run the application and perform key workflows — login, file upload, analysis, viewing results, generating and downloading reports — so that relevant queries are captured.

### Step 4: Run the Demo Evidence Script

```bash
psql -U cybercomply_user -d cybercomply_db
```

```sql
\i demo_evidence_m2.sql
```

This will display slow queries (if any exceed ~10ms) and the most frequently executed queries, demonstrating real-time performance monitoring.