The feature/aws branch integrates the following into the Django backend:

AWS S3 – file storage
AWS SES – email and OTP delivery
ClamAV – malware scanning (via Docker)
This README explains how to set up and run the project locally.

Prerequisites
The following must be installed on the local machine before getting started.
    1. [Python 3.x](https://www.python.org/downloads/)
    2. [Docker Desktop](https://www.docker.com/products/docker-desktop/)
    3. Git

1. Check out the branch
git clone <repository-url>
cd sd04_2025
git checkout feature/aws
cd DjangoManager

2. Set up a virtual environment
A virtual environment must be created and activated on each machine.
The venv/ folder is not committed to Bitbucket.

Create the virtual environment
python -m venv venv

Activate the virtual environment
On Windows:
venv\Scripts\activate

On macOS/Linux:
source venv/bin/activate

PowerShell execution policy error (Windows only)
Run this once if activation fails:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

3. Install Dependencies
All required python packages:
pip install -r requirements.txt

4. Environment Variables (.env file)
A .env.example file is included as a template.
The actual .env file is ignored by Git and must never be pushed.

Create your .env file
cp .env.example .env

Required values:
Only fill in your AWS Access Key ID and AWS Secret Access Key
Leave all other values unchanged unless instructed otherwise

5. ClamAV Setup (with Docker)
ClamAV runs in a Docker container for malware scanning.
Make sure Docker Desktop is running before starting the server.

First-time setup
docker pull clamav/clamav:lastest
docker run -d --name clamav -p 3310:3310 clamav/clamav:latest

Subsequent runs:
docker start clamav

Verify container status:
docker ps

The status column should show healthy next to the clamav container. If it shows starting, wait 1–2 minutes and check again.

6. Running the server

Make sure the venv is activated and ClamAV is running:

Start the server
python manage.py runserver

You may see a warning about unapplied migrations — this is handled by the database team and can be ignored for now.

7. Testing Notes
SES sandbox mode
AWS SES is currently in sandbox mode.
Only verified email addresses can receive emails
Use a verified email when testing OTP functionality

File uploads
Supported formats: .pdf, .docx, .txt
Maximum file size: 50 MB
All files are scanned with ClamAV before processing

8. Before pushing to Bitbucket
Ensure .env is not staged or committed.
Run 'pip freeze > requirements.txt' if any new packages were installed.