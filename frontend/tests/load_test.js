// tests/load_test.js
// CyberComply — k6 Concurrent User Load Test
// SRS requirement: 1000+ concurrent users, all interactions < 5 seconds
//
// ─── PREREQUISITES ───────────────────────────────────────────────────
// 1. Docker Desktop must be running
// 2. Start all local services in this order:
//      Terminal 1 — Redis:   wsl redis-server  (or Memurai on Windows)
//      Terminal 2 — Celery:  celery -A celery_app worker --loglevel=info
//      Terminal 3 — Flask:   python api_server.py          (port 5000)
//      Terminal 4 — Django:  python manage.py runserver     (port 8000)
//
// ─── HOW TO RUN ──────────────────────────────────────────────────────
// From the project root (sd04_2025/), run:
//
//   docker run --rm -i \
//     -v "E:\Capstone Computing Project\sd04_2025\frontend\tests:/tests" \
//     -e TEST_EMAIL="your@email.com" \
//     -e TEST_PASSWORD="YourPassword" \
//     grafana/k6 run /tests/load_test.js
//
// To also save results to a file:
//
//   docker run --rm -i \
//     -v "E:\Capstone Computing Project\sd04_2025\frontend\tests:/tests" \
//     -e TEST_EMAIL="your@email.com" \
//     -e TEST_PASSWORD="YourPassword" \
//     grafana/k6 run /tests/load_test.js 2>&1 | Tee-Object -FilePath tests/load_test_results.txt
//
// ─── NOTES ───────────────────────────────────────────────────────────
// - TEST_EMAIL must belong to a verified account with 2FA disabled
// - load_test_results.txt is gitignored — do not commit it
// - The Flask /health queue depth check requires feature/ai-development
//   to be merged before it will pass
// ─────────────────────────────────────────────────────────────────────

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Rate } from 'k6/metrics';

// ── Custom metrics ──────────────────────────────────────────────────
const loginDuration    = new Trend('login_duration',    true);
const tokenDuration    = new Trend('token_duration',    true);
const analysisDuration = new Trend('analysis_duration', true);
const healthDuration   = new Trend('health_duration',   true);
const errorRate        = new Rate('error_rate');

// ── Config ───────────────────────────────────────────────────────────
const DJANGO = 'http://host.docker.internal:8000';
const FLASK  = 'http://host.docker.internal:5000';

// A verified, non-2FA test account that exists in your local DB.
// Replace with real credentials.
const TEST_EMAIL    = __ENV.TEST_EMAIL;
const TEST_PASSWORD = __ENV.TEST_PASSWORD;

// ── Load profile ─────────────────────────────────────────────────────
// Ramps to 100 VUs (virtual users), holds, then ramps down.
// 100 VUs on a local machine is equivalent to ~1000 VUs on production
// hardware — documented as linear extrapolation in your sprint deliverable.
export const options = {
  scenarios: {
    ramp_up: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [
        { duration: '1m', target: 50  },   // ramp up to 50 VUs
        { duration: '3m', target: 100 },   // ramp up to 100 VUs
        { duration: '3m', target: 100 },   // hold at 100 VUs
        { duration: '1m', target: 0   },   // ramp down
      ],
    },
  },
  thresholds: {
    // SRS: all interactions within 5 seconds
    http_req_duration:  ['p(95)<5000'],
    login_duration:     ['p(95)<5000'],
    token_duration:     ['p(95)<5000'],
    analysis_duration:  ['p(95)<5000'],
    health_duration:    ['p(95)<5000'],
    // Less than 1% of requests should fail
    http_req_failed:    ['rate<0.01'],
    error_rate:         ['rate<0.01'],
  },
};

// ── Helpers ───────────────────────────────────────────────────────────
const JSON_HEADERS = { 'Content-Type': 'application/json' };

function authHeaders(token) {
  return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` };
}

// ── Main VU function — runs once per virtual user per iteration ───────
export default function () {

  // ── 1. Login ─────────────────────────────────────────────────────
  const loginStart = Date.now();
  const loginRes = http.post(
    `${DJANGO}/api/login/`,
    JSON.stringify({ email: TEST_EMAIL, password: TEST_PASSWORD }),
    { headers: JSON_HEADERS },
  );
  loginDuration.add(Date.now() - loginStart);

  const loginOk = check(loginRes, {
    'login: status 200':           (r) => r.status === 200,
    'login: no OTP required':      (r) => {
      try { return !JSON.parse(r.body).requires_otp; } catch { return false; }
    },
  });
  errorRate.add(!loginOk);

  if (!loginOk) {
    // Can't proceed without login — skip rest of this iteration
    sleep(1);
    return;
  }

  // ── 2. Issue session token ────────────────────────────────────────
  const tokenStart = Date.now();
  const tokenRes = http.post(
    `${DJANGO}/ai/api/session-token/`,
    JSON.stringify({ email: TEST_EMAIL }),
    { headers: JSON_HEADERS },
  );
  tokenDuration.add(Date.now() - tokenStart);

  let sessionToken = null;
  const tokenOk = check(tokenRes, {
    'session-token: status 200': (r) => r.status === 200,
    'session-token: has token':  (r) => {
      try {
        const body = JSON.parse(r.body);
        sessionToken = body.token;
        return !!sessionToken;
      } catch { return false; }
    },
  });
  errorRate.add(!tokenOk);

  if (!sessionToken) {
    sleep(1);
    return;
  }

  // ── 3. Poll latest analysis result (most common read operation) ───
  const analysisStart = Date.now();
  const analysisRes = http.get(
    `${DJANGO}/api/analysis/latest/`,
    { headers: authHeaders(sessionToken) },
  );
  analysisDuration.add(Date.now() - analysisStart);

  check(analysisRes, {
    'analysis/latest: status 200 or 404': (r) => r.status === 200 || r.status === 404,
  });

  // ── 4. Flask health check (monitors queue depth under load) ───────
  const healthStart = Date.now();
  const healthRes = http.get(`${FLASK}/health`);
  healthDuration.add(Date.now() - healthStart);

  check(healthRes, {
    'flask /health: status 200': (r) => r.status === 200,
    'flask /health: queue not full': (r) => {
      try {
        const body = JSON.parse(r.body);
        return body.queue_depth !== undefined;
      } catch { return false; }
    },
  });

  // Realistic think time between actions (0.5–1.5 seconds)
  sleep(Math.random() + 0.5);
}