/**
 * session-manager.js
 * ──────────────────────────────────────────────────────────────────────
 * CyberComply – Shared session timeout manager
 *
 * USAGE IN EVERY AUTHENTICATED PAGE
 * ───────────────────────────────────
 * 1. Include this script in <head> after sidebar_component.js:
 *      <script src="session-manager.js"></script>
 *
 * 2. After the auth guard passes (inside mounted() or onMounted()),
 *    call the one-liner:
 *      SessionManager.init({ timeoutMs: 1800000 });  // 30 min (home/analysis)
 *      SessionManager.init({ timeoutMs: 1200000 });  // 20 min (all other pages)
 *
 * BEHAVIOUR
 * ──────────
 * - Tracks user activity (mouse, keyboard, scroll, touch) and resets the
 *   inactivity timer on each event (debounced to once per second).
 * - Shows a warning modal 2 minutes before the timeout fires.
 * - While the warning modal is visible, activity alone does NOT reset the
 *   timer — the user must click "Stay Logged In" to confirm intent.
 * - On timeout (or "Log Out Now"): clears sessionStorage and redirects to
 *   login.html?expired=1, which displays a session-expired banner.
 */

const SessionManager = (() => {

    // ── Internal state ─────────────────────────────────────────────────────
    let _timeoutMs        = 1200000; // default 20 min
    let _warningMs        = 120000;  // default 2 min warning
    let _timer            = null;    // logout timer handle
    let _warnTimer        = null;    // warning timer handle
    let _countdownInterval = null;   // countdown tick handle
    let _modalEl          = null;    // injected overlay element
    let _initialized      = false;   // guard against double-init

    // ── Internal helpers ────────────────────────────────────────────────────

    function _clearAll() {
        clearTimeout(_timer);
        clearTimeout(_warnTimer);
        clearInterval(_countdownInterval);
    }

    function _logout() {
        _clearAll();
        sessionStorage.clear();
        window.location.href = 'login.html?expired=1';
    }

    // ── Modal injection ─────────────────────────────────────────────────────
    // Called once during init(). Appends a hidden overlay <div> and scoped
    // <style> to document.body. The overlay is shown/hidden via the
    // .sm-visible class rather than display toggling.

    function _injectModal() {
        if (_modalEl) return;

        const style = document.createElement('style');
        style.textContent = `
            #sm-overlay {
                display: none;
                position: fixed;
                inset: 0;
                z-index: 9999;
                background: rgba(0, 0, 0, 0.72);
                justify-content: center;
                align-items: center;
            }
            #sm-overlay.sm-visible {
                display: flex;
                animation: smFadeIn 0.25s ease;
            }
            @keyframes smFadeIn {
                from { opacity: 0; }
                to   { opacity: 1; }
            }
            #sm-box {
                background: #234561;
                color: #f0f4ff;
                border: 1px solid #90a0b5;
                border-radius: 10px;
                padding: 32px 28px;
                width: 100%;
                max-width: 400px;
                text-align: center;
                box-shadow: 0 18px 40px rgba(0, 0, 0, 0.45);
                animation: smPopIn 0.25s ease;
            }
            @keyframes smPopIn {
                from { transform: scale(0.92); opacity: 0; }
                to   { transform: scale(1);    opacity: 1; }
            }
            #sm-box h3 {
                margin: 0 0 12px;
                font-size: 20px;
                font-weight: 700;
                color: #ffffff;
                letter-spacing: 0.01em;
            }
            #sm-box p {
                font-size: 14px;
                color: #c8d8ea;
                line-height: 1.6;
                margin: 0 0 24px;
            }
            #sm-box p strong {
                color: #ffffff;
                font-weight: 700;
            }
            #sm-countdown-wrap {
                display: inline-block;
                background: rgba(255,255,255,0.08);
                border-radius: 6px;
                padding: 2px 10px;
                margin: 0 2px;
                font-variant-numeric: tabular-nums;
            }
            .sm-btn-row {
                display: flex;
                gap: 12px;
                justify-content: center;
            }
            .sm-btn {
                padding: 10px 22px;
                border: none;
                border-radius: 6px;
                font-weight: 700;
                cursor: pointer;
                font-size: 14px;
                transition: opacity 0.18s, transform 0.18s;
                letter-spacing: 0.02em;
            }
            .sm-btn:hover {
                opacity: 0.88;
                transform: translateY(-1px);
            }
            .sm-btn:active {
                transform: translateY(0);
            }
            #sm-stay-btn {
                background: #a2b8c8;
                color: #0d2035;
            }
            #sm-logout-btn {
                background: #3a5070;
                color: #e2e8f0;
            }
        `;
        document.head.appendChild(style);

        const overlay = document.createElement('div');
        overlay.id = 'sm-overlay';
        overlay.innerHTML = `
            <div id="sm-box">
                <h3>Session Expiring Soon</h3>
                <p>
                    Due to inactivity, you will be logged out in<br>
                    <span id="sm-countdown-wrap">
                        <strong><span id="sm-countdown">120</span> seconds</strong>
                    </span>.
                </p>
                <div class="sm-btn-row">
                    <button id="sm-stay-btn"   class="sm-btn">Stay Logged In</button>
                    <button id="sm-logout-btn" class="sm-btn">Log Out Now</button>
                </div>
            </div>
        `;
        document.body.appendChild(overlay);
        _modalEl = overlay;

        document.getElementById('sm-stay-btn').addEventListener('click', _resetTimers);
        document.getElementById('sm-logout-btn').addEventListener('click', _logout);
    }

    // ── Warning modal controls ───────────────────────────────────────────────

    function _startCountdown(seconds) {
        const el = document.getElementById('sm-countdown');
        if (el) el.textContent = seconds;

        _countdownInterval = setInterval(() => {
            seconds--;
            if (el) el.textContent = Math.max(0, seconds);
            if (seconds <= 0) clearInterval(_countdownInterval);
        }, 1000);
    }

    function _showWarning() {
        if (!_modalEl) return;
        _modalEl.classList.add('sm-visible');
        _startCountdown(Math.floor(_warningMs / 1000));
    }

    function _hideWarning() {
        if (!_modalEl) return;
        _modalEl.classList.remove('sm-visible');
        clearInterval(_countdownInterval);
    }

    // ── Timer management ────────────────────────────────────────────────────

    function _resetTimers() {
        _hideWarning();
        _clearAll();

        // Fire warning at (timeoutMs - warningMs) from now
        _warnTimer = setTimeout(_showWarning, _timeoutMs - _warningMs);

        // Fire logout at timeoutMs from now
        _timer = setTimeout(_logout, _timeoutMs);
    }

    // ── Activity tracking ───────────────────────────────────────────────────
    // Debounced to at most once per second to avoid timer-reset storms.
    // While the warning modal is visible the user must explicitly click
    // "Stay Logged In" — passive activity is not enough.

    let _lastActivity = 0;

    function _onActivity() {
        const now = Date.now();
        if (now - _lastActivity < 1000) return;
        _lastActivity = now;
        if (_modalEl && _modalEl.classList.contains('sm-visible')) return;
        _resetTimers();
    }

    function _attachActivityListeners() {
        ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart']
            .forEach(evt => document.addEventListener(evt, _onActivity, { passive: true }));
    }

    // ── Public API ──────────────────────────────────────────────────────────

    /**
     * Initialise the session manager.
     *
     * @param {object} options
     * @param {number} options.timeoutMs  Inactivity timeout in milliseconds.
     *                                    30 min (1800000) for home / document_analysis.
     *                                    20 min (1200000) for all other pages.
     * @param {number} [options.warningMs=120000]  Warning lead time in ms (default 2 min).
     */
    function init(options) {
        if (_initialized) return;
        _initialized = true;

        _timeoutMs = (options && options.timeoutMs) ? options.timeoutMs : 1200000;
        _warningMs = (options && options.warningMs) ? options.warningMs : 120000;

        // Safety: warning must be shorter than the full timeout
        if (_warningMs >= _timeoutMs) {
            _warningMs = Math.floor(_timeoutMs / 6);
        }

        _injectModal();
        _attachActivityListeners();
        _resetTimers();
    }

    return { init };

})();
