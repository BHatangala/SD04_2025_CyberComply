// ─────────────────────────────────────────────────────────────────────────────
// otp-component.js  —  Reusable OTP Verification Component
//
// USAGE ON ANY PAGE:
//   1. Include this script AFTER vue but BEFORE your app script:
//        <script src="otp-component.js"></script>
//
//   2. Register on your Vue app instance before mounting:
//        registerOtpComponent(app);
//        app.mount('#app');
//
//   3. Drop the tag wherever the OTP step should appear:
//        <otp-verification
//            :email="form.email"
//            @verified="handleOtpVerified">
//        </otp-verification>
//
//   4. Define your post-verification handler — this is the ONLY thing
//      that changes per page:
//        const handleOtpVerified = () => {
//            // e.g. advance to next step, redirect, grant access, etc.
//        };
//
// PROPS:
//   email  (String, optional) — passed in so the backend call knows which
//                               account to verify against
//
// EVENTS EMITTED:
//   @verified  — fired after successful OTP verification; no payload
//
// BACKEND INTEGRATION:
//   Find the comment "── BACKEND INTEGRATION POINT ──" below and replace
//   the simulated block with your real fetch() call to Django.
// ─────────────────────────────────────────────────────────────────────────────

const OtpVerification = {
    name: 'OtpVerification',

    props: {
        email: {
            type: String,
            default: ''
        }
    },

    emits: ['verified'],

    template: `
        <div class="otp-wrapper">

            <!-- Inline error / success — only shown after the user interacts -->
            <transition name="otp-fade">
                <div v-if="message.text"
                    :class="['otp-message',
                        message.type === 'error'
                            ? 'otp-message--error'
                            : 'otp-message--success']">
                    {{ message.text }}
                </div>
            </transition>

            <!-- OTP Input -->
            <div class="otp-field">
                <label class="otp-label">Enter OTP</label>
                <input
                    v-model="otp"
                    type="text"
                    inputmode="numeric"
                    maxlength="6"
                    placeholder="******"
                    class="otp-input"
                    :disabled="loading"
                    @keyup.enter="verify"
                />
            </div>

            <!-- Verify Button -->
            <button class="otp-btn" @click="verify" :disabled="loading">
                <span v-if="loading" class="otp-spinner"></span>
                {{ loading ? 'VERIFYING...' : 'VERIFY OTP' }}
            </button>

        </div>
    `,

    data() {
        return {
            otp: '',
            loading: false,
            message: { text: '', type: '' }
        };
    },

    methods: {
        async verify() {
            this.message.text = '';

            // ── Client-side validation ──
            if (!this.otp) {
                this.setMessage('error', 'Please enter the OTP.');
                return;
            }
            if (!/^\d{6}$/.test(this.otp)) {
                this.setMessage('error', 'OTP must be exactly 6 digits.');
                return;
            }

            this.loading = true;

            try {
                // ── BACKEND INTEGRATION POINT ─────────────────────────────────
                // When the Django endpoint is ready, replace the simulation below:
                //
                //   const response = await fetch('/api/verify-otp/', {
                //       method: 'POST',
                //       headers: { 'Content-Type': 'application/json' },
                //       body: JSON.stringify({ email: this.email, otp: this.otp })
                //   });
                //   const data = await response.json();
                //   if (!response.ok) throw new Error(data.detail || 'Invalid OTP.');
                //
                // ── END BACKEND INTEGRATION POINT ─────────────────────────────

                // Simulated delay — any 6-digit number passes for now
                await new Promise(resolve => setTimeout(resolve, 1000));

                // Emit to parent — parent controls what happens next
                this.$emit('verified');

            } catch (err) {
                this.setMessage('error', err.message || 'Verification failed. Please try again.');
            } finally {
                this.loading = false;
            }
        },

        setMessage(type, text) {
            this.message.type = type;
            this.message.text = text;
        }
    }
};

// ─── Auto-injected styles ─────────────────────────────────────────────────────
// Injected once into <head> so no separate CSS file is needed.
// Colours match the existing CyberComply dark-blue palette.
const _otpStyles = `
    .otp-wrapper {
        display: flex;
        flex-direction: column;
        gap: 16px;
    }

    .otp-message {
        font-size: 13px;
        padding: 10px 14px;
        border-radius: 4px;
        text-align: center;
        border: 1px solid transparent;
    }

    .otp-message--error {
        background: #e2e8f0;
        color: #dc2626;
        border-color: #fca5a5;
    }

    .otp-message--success {
        background: #166534;
        color: #ffffff;
        border-color: #4ade80;
    }

    .otp-field {
        display: flex;
        flex-direction: column;
        gap: 6px;
    }

    .otp-label {
        font-size: 11px;
        font-weight: 700;
        letter-spacing: 2px;
        text-transform: uppercase;
        color: #94a3b8;
        margin-left: 2px;
    }

    .otp-input {
        background-color: #0F3456;
        border: 1px solid #2563eb;
        color: #e2e8f0;
        padding: 12px;
        text-align: center;
        font-size: 22px;
        letter-spacing: 10px;
        line-height: 1;
        border-radius: 4px;
        width: 100%;
        transition: border-color 0.3s, box-shadow 0.3s;
    }

    .otp-input::placeholder {
        color: #6b8cba;
        letter-spacing: 10px;
    }

    .otp-input:focus {
        outline: none;
        border-color: #60a5fa;
        box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
    }

    .otp-input:disabled {
        opacity: 0.6;
        cursor: not-allowed;
    }

    .otp-btn {
        background-color: #BEE3F8;
        color: #000;
        font-weight: 700;
        font-size: 13px;
        letter-spacing: 2px;
        text-transform: uppercase;
        padding: 12px;
        margin-top: 12px;
        border: none;
        border-radius: 4px;
        width: 100%;
        cursor: pointer;
        transition: opacity 0.3s;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
    }

    .otp-btn:hover:not(:disabled) { opacity: 0.88; }
    .otp-btn:disabled { opacity: 0.6; cursor: not-allowed; }

    .otp-spinner {
        width: 14px;
        height: 14px;
        border: 2px solid rgba(0,0,0,0.2);
        border-top-color: #000;
        border-radius: 50%;
        animation: otpSpin 0.7s linear infinite;
        flex-shrink: 0;
    }

    @keyframes otpSpin { to { transform: rotate(360deg); } }

    .otp-fade-enter-active,
    .otp-fade-leave-active { transition: opacity 0.3s ease; }
    .otp-fade-enter-from,
    .otp-fade-leave-to { opacity: 0; }
`;

(function injectOtpStyles() {
    if (document.getElementById('otp-component-styles')) return;
    const style = document.createElement('style');
    style.id = 'otp-component-styles';
    style.textContent = _otpStyles;
    document.head.appendChild(style);
})();

// ─── Global registration helper ───────────────────────────────────────────────
// Call this on your Vue app instance before .mount():
//   registerOtpComponent(app);
//
function registerOtpComponent(appInstance) {
    appInstance.component('OtpVerification', OtpVerification);
}