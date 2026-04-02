# CyberComply — Playwright E2E Test Suite

End-to-end integration tests for the CyberComply authentication flow, built with [Playwright](https://playwright.dev/).

---

## What Is Tested

The tests cover the full user journey from the landing page through to the home page:

```
welcome.html → signup.html → login.html ↔ forgot_password.html → home.html
```

---

## Prerequisites

Before setting up the tests, make sure the following are already installed and running:

- [Node.js](https://nodejs.org/) v18 or higher
- Python virtual environment for the Django backend (already set up in this project)
- Django backend running on `http://127.0.0.1:8000`
- VS Code Live Server extension serving the frontend on `http://localhost:5500`

---

## Installation

### 1. Install Playwright and browsers

Checkout and run a pull request in the `test` branch.
Then Navigate to the `frontend` folder (where `package.json` lives) and run:

```bash
cd frontend
npm install
npx playwright install
```

This installs Playwright and downloads the Chromium, Firefox, and WebKit browser binaries.

---

## Configuration

### 2. Configure `playwright.config.js`

(DO NOT MAKE ANY CHANGES TO THIS FILE, UNLESS YOU RUN INTO AN ERROR ON FIRST TIME RUNNING)
Located at `frontend/playwright.config.js`. The key settings are:

```js
testDir: './tests/e2e', //Ensure this folder actually exists under frontend sub directory
baseURL: 'http://localhost:5500/frontend/',   // This URL must match your Live Server URL, may need updates based on your Liver Server Settings
```

> **Important:** The `baseURL` must end with a trailing slash (`/frontend/`) and all
> `page.goto()` calls in the spec files use `./pagename.html` (with `./`) so that
> Playwright resolves them relative to the full base URL correctly.

### 3. Configure `otpSeeder.js and verificationHelper.js`

Located at `frontend/tests/e2e/helpers/otpSeeder.js` and `frontend/tests/e2e/helpers/verificationHelper.js`. Edit the python binary line of both files to match your project:

```js
const PYTHON_BIN             = 'E:/Capstone Computing Project/sd04_2025/AIModel/venv/Scripts/python';
//The file path needs updates based on your python.exe location. The above file path given, is based on my environment setup.
```
- To find where the python.exe is located, press `Ctrl + Shift + P` in VSCode. 
- In the search bar, type out `Python: Select Interpreter` and click on the option that appears with that name. 
- Once you click that, the file path of the selected interpreter that is currently used in your project will appear at the top. 
- Update the `otpSeeder.js` file based on this file path. 

### 4. Configure `frontend/tests/e2e/helpers/helper_login.js`

There is a credential section at the top of this file which needs to be updated based on the actual email and password registered in your local database. 

```bash
const GENERAL_EMAIL = '21804005@student.curtin.edu.au';
const GENERAL_PASS  = 'Curtin1781*';
const ADMIN_EMAIL   = 'edirisinghev82oth@gmail.com';
const ADMIN_PASS    = 'Curtin1781*';
```

Ensure that you have both an admin level account and a general user account created under 2 email addresses and then add these credentials to this file which currently shows the accounts in my local database. 




## Folder Structure

```
sd04_2025/
├── DjangoManager/
│   ├── core/                         ← Django app (models.py, views.py, urls.py)
│   ├── DjangoManager/                ← Django settings folder
│   ├── manage.py
│   └── seed_test_otp.py              ← Django helper: injects known OTP into DB for tests
│
└── frontend/
    ├── playwright.config.js          ← Playwright configuration
    ├── package.json                  ← NPM configuration
    ├── welcome.html
    ├── login.html
    ├── home.html
    ├── otp_component.js             
    │
    └── tests/
        └── e2e/
            ├── helpers/
            │   ├── helper_login.js   ← Shared login functions (Which need to be updated)
            │   └── otpSeeder.js      ← Calls seed_test_otp.py to inject OTP into DB
            │
            ├── 1_welcome.spec.js     ← Landing page: rendering + navigation
            ├── 2_signup.spec.js      ← Registration: field validation + happy path
            ├── 3_login.spec.js       ← Login: validation, wrong creds, lockout, OTP flows
            ├── 4_forgot_password.spec.js  ← Password reset: all 3 steps + OTP edge cases
            └── 5_home.spec.js        ← Home page: access guard + session/role checks
```

Files are numbered `1_` through `5_` to reflect the natural user journey order and to control execution sequence when running in single-worker mode.

---

## Running the Tests

### Before every test run

Make sure all 3 servers are running:

**Terminal 1 — AI Flask Server:**
```bash
.venv\Scripts\activate
cd AIModel
python api_server.py
```

**Terminal 2 — Django backend:**
```bash
.venv\Scripts\activate
cd DjangoManager
python manage.py runserver
```

**VS Code — Live Server:**
Open VS Code at the `sd04_2025` root, then click **Go Live** in the bottom-right status bar.
Verify the frontend loads at: `http://localhost:5500/frontend/welcome.html`

---

### Run commands

All commands are run from the `frontend` folder:

```bash
cd "sd04_2025\frontend"
```

| Command | What it does |
|---|---|
| `npx playwright test --project=chromium` | Run all tests in Chromium only |
| `npx playwright test 1_welcome.spec.js --project=chromium --headed` | Run a single spec file |
| `npx playwright test --project=chromium --headed --workers=1` | Run sequentially (one at a time) |
| `npx playwright test` | Run across all browsers (Chromium, Firefox, WebKit, Edge) |
| `npx playwright show-report` | Open the HTML test report after a run |


**Recommended first run** — run one file at a time to verify everything is working:

```bash
npx playwright test tests/e2e/1_welcome.spec.js --project=chromium --headed
npx playwright test tests/e2e/2_signup.spec.js --project=chromium --headed
npx playwright test tests/e2e/5_home.spec.js --project=chromium --headed
```

---

## How OTP Testing Works

Real OTPs are delivered via AWS SES to actual email inboxes — the tests cannot read those.
Instead, the `seedOtp()` helper injects a **known fixed OTP (`123456`)** directly into the
`otp_verification` database table before each OTP test runs.

**Flow:**
1. Test calls `seedOtp(email, purpose)` in the spec file
2. `otpSeeder.js` shells out to `seed_test_otp.py` via Node's `execSync`
3. `seed_test_otp.py` invalidates any existing live OTP and writes a new row with hash of `123456`
4. The test types `123456` into the OTP input field (`input.otp-input`)
5. The backend validates it against the hash — passes normally

**OTP purposes used:**

| Purpose | Used in |
|---|---|
| `FIRST_LOGIN` | First-time login email verification |
| `LOGIN_2FA` | Login with 2FA enabled |
| `RESET_PASSWORD` | Forgot password OTP step |

---

## Test Accounts

| Role | Email | Password |
|---|---|---|
| General User | `21804005@student.curtin.edu.au` | `Curtin1781*` |
| Admin User | `edirisinghev82oth@gmail.com` | `Curtin1781*` |

> - These test account credentials might be differnet based on your local database state. 
> - The happy-path signup test generates a unique `playwright_<timestamp>@example.com`
> address each run. Clean these up periodically via the Django admin panel or shell.

---

## Notes

- **Lockout tests** use `page.route()` to mock the backend response instead of actually
  triggering 5 failed logins — this protects the real test accounts from being locked.
- **Wrong OTP tests** hit the real backend (which returns `401` naturally for wrong codes).
- **Expired / brute-force OTP tests** use mocked responses to avoid waiting for real expiry.
- Screenshots and videos are saved automatically for any failed test inside
  `frontend/test-results/` (ignored by `.gitignore`).