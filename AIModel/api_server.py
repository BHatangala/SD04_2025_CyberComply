from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import tempfile
import time
from werkzeug.utils import secure_filename
from src.compliance_analyser import ComplianceAnalyzer
from celery_app import celery
from celery.exceptions import SoftTimeLimitExceeded
# from src.risk_assessor import RiskAssessor
# from src.recommendation_generator import RecommendationGenerator

app = Flask(__name__)
CORS(app)

# Limit upload size to 16MB to protect RAM/VRAM
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

# ── Queue depth limit ──────────────────────────────────────────────────────────
# If this many jobs are already waiting, reject new submissions immediately.
# Prevents unbounded queue growth when OpenRouter daily cap is exhausted.
MAX_QUEUED_JOBS = 5

# Initialize components (Singleton model loading)
analyzer = ComplianceAnalyzer(
    requirements_path=os.path.join(os.path.dirname(__file__), 'data', 'pdpa_requirements_full.json')
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_queue_depth() -> int:
    """Return number of jobs waiting in the Celery queue via Redis directly."""
    try:
        import redis
        r = redis.Redis(host='127.0.0.1', port=6379, db=0)
        return r.llen('celery')  # type: ignore[return-value]
    except Exception:
        return 0

# ── Celery task ────────────────────────────────────────────────────────────────

@celery.task(bind=True, name='run_compliance_analysis', max_retries=1)
def run_compliance_analysis(self, file_bytes_hex: str, original_filename: str,
                            company_name: str, department: str) -> dict:
    """
    Celery task that runs the full compliance analysis.

    Accepts file bytes as a hex string (JSON-safe; avoids base64 padding issues).
    Writes bytes to a temp file, runs analysis, cleans up, returns the result dict.

    Raises SoftTimeLimitExceeded if the job exceeds task_soft_time_limit (1200 s).
    The hard task_time_limit (1500 s) will SIGKILL the worker process if that fires.
    """
    _, extension = os.path.splitext(original_filename)
    temp_path = None

    try:
        file_bytes = bytes.fromhex(file_bytes_hex)

        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as tmp:
            tmp.write(file_bytes)
            temp_path = tmp.name

        print(f"[TASK] Processing: {company_name} | Dept: {department or 'N/A'} | File: {original_filename}")

        compliance_result = analyzer.analyze_document(
            temp_path,
            org_name=company_name,
            department=department,
        )

        # Placeholder logic — unchanged from original api_server.py
        risk_assessment = {"status": "low", "factors": ["Data encryption detected"]}
        recommendations = {"top_action": "Update privacy policy with Section 10 wording."}

        return {
            "compliance": compliance_result,
            "risks": risk_assessment,
            "recommendations": recommendations,
            "metadata": {
                "company": company_name,
                "department": department,
                "file_analyzed": original_filename,
            },
        }

    except SoftTimeLimitExceeded:
        # Analysis took longer than 20 minutes — return a graceful timeout payload
        # instead of crashing so Django can surface a meaningful error to the user.
        print(f"[TASK] Soft time limit exceeded for {original_filename}")
        return {
            "error": "Analysis timed out. The document may be too large or the AI service is overloaded.",
            "timed_out": True,
        }

    except Exception as exc:
        print(f"[TASK] CRITICAL ERROR for {original_filename}: {exc}")
        # Retry once after 60 s (configured in celery_app.py).
        # If the retry also fails, Celery marks the task FAILURE and stores the
        # exception so /api/job-status/<id> can return it to Django.
        raise self.retry(exc=exc)

    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)


# ── Original synchronous endpoint (kept intact) ────────────────────────────────

@app.route('/health', methods=['GET'])
def health_check():
    """Confirms the server and DeepSeek model are ready. Also exposes queue depth."""
    queue_depth = _get_queue_depth()
    return jsonify({
        "status": "healthy",
        "model": "DeepSeek-R1-Distill-7B",
        "device": "Open Router API (via Celery worker)",
        "queue_depth": queue_depth,
        "queue_at_limit": queue_depth >= MAX_QUEUED_JOBS,
        "max_queued_jobs":    MAX_QUEUED_JOBS,
        "worker_concurrency": 1,
        "rate_limit_note": (
            "OpenRouter free tier: 20 req/min. Each analysis job uses ~12 batch calls. "
            "Worker dispatches at max 1 job per 4 s stagger to stay within limits."),
    })

@app.route('/api/analyze', methods=['POST'])
def analyze_document():
    """
    Main endpoint to process PDPA compliance.
    Unchanged from original — kept for direct/synchronous callers.
    """
    try:
        # 1. Validation: Check if file exists in request
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']

        # 2. Fix for splitext/Pylance error: Explicitly check filename
        if file.filename is None or file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        # Create a safe version of the filename
        original_filename = secure_filename(file.filename)
        company_name = request.form.get('company_name', 'Unknown Organization')
        department   = request.form.get('department', '')

        # Extract extension safely for temp file creation
        _, extension = os.path.splitext(original_filename)

        # 3. Memory-Safe Temporary Storage
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            file.save(temp_file.name)
            temp_path = temp_file.name

        print(f"--- Processing started for: {company_name} | Dept: {department or 'N/A'} ---")

        # 4. Run Analysis (DeepSeek Logic)
        # org_name and department are forwarded so the analyser can tailor
        # risk severity and reasoning to the organisation's sector.
        compliance_result = analyzer.analyze_document(
            temp_path,
            org_name=company_name,
            department=department,
        )

        # Placeholder logic for risks and recommendations
        risk_assessment = {"status": "low", "factors": ["Data encryption detected"]}
        recommendations = {"top_action": "Update privacy policy with Section 10 wording."}

        # 5. Cleanup: Always remove temp files to save disk space
        if os.path.exists(temp_path):
            os.remove(temp_path)

        return jsonify({
            "compliance": compliance_result,
            "risks": risk_assessment,
            "recommendations": recommendations,
            "metadata": {
                "company": company_name,
                "department": department,
                "file_analyzed": original_filename
            }
        })

    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        return jsonify({
            "error": "The AI model encountered an issue or the file was too complex.",
            "details": str(e)
        }), 500


# ── New queued endpoint ────────────────────────────────────────────────────────

@app.route('/api/analyze-queued', methods=['POST'])
def analyze_document_queued():
    """
    Accepts a file, checks the queue depth, and submits a Celery task.
    Returns a job_id immediately — caller must poll /api/job-status/<job_id>.

    Request: multipart/form-data — same fields as /api/analyze.
    Response 202: { "job_id": "<celery-task-id>", "status": "queued" }
    Response 503: { "error": "...", "queue_depth": N }  — when queue is full
    """
    try:
        # ── Queue depth guard ──────────────────────────────────────────────────
        depth = _get_queue_depth()
        if depth >= MAX_QUEUED_JOBS:
            return jsonify({
                "error": "The AI service is currently at capacity. Please try again in a few minutes.",
                "queue_depth": depth,
            }), 503

        # ── Validate file ──────────────────────────────────────────────────────
        if 'file' not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files['file']
        if file.filename is None or file.filename == '':
            return jsonify({"error": "No selected file"}), 400

        original_filename = secure_filename(file.filename)
        company_name = request.form.get('company_name', 'Unknown Organization')
        department   = request.form.get('department', '')

        # ── Serialise file bytes as hex for Celery (JSON-safe) ─────────────────
        file_bytes     = file.read()
        file_bytes_hex = file_bytes.hex()

        # ── Submit task ────────────────────────────────────────────────────────
        task = run_compliance_analysis.apply_async( # type: ignore[attr-defined]
            args=[file_bytes_hex, original_filename, company_name, department],
            # Rate-limit: at most 1 task dispatched to OpenRouter per 4 seconds.
            countdown=depth * 4,
        )

        print(f"[QUEUE] Job {task.id} queued — depth was {depth} | {company_name} | {original_filename}")

        return jsonify({
            "job_id": task.id,
            "status": "queued",
            "queue_position": depth + 1,
        }), 202

    except Exception as e:
        print(f"[QUEUE] Submission error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/job-status/<job_id>', methods=['GET'])
def job_status(job_id: str):
    """
    Poll the status of a queued analysis job.

    Possible responses:
        { "status": "pending"  }                          — waiting in queue
        { "status": "started"  }                          — worker is running it
        { "status": "success",  "result": { ... } }       — finished, result attached
        { "status": "failure",  "error":  "..." }         — task failed after retries
        { "status": "timeout"                   }         — soft time limit hit
        { "status": "unknown"                   }         — job_id not found in Redis
    """
    try:
        result = celery.AsyncResult(job_id)
        state  = result.state   # PENDING | STARTED | SUCCESS | FAILURE | RETRY

        if state == 'PENDING':
            return jsonify({"status": "pending"})

        if state == 'STARTED':
            return jsonify({"status": "started"})

        if state == 'SUCCESS':
            payload = result.result or {}
            # Handle the graceful timeout path from run_compliance_analysis
            if payload.get("timed_out"):
                return jsonify({"status": "timeout"})
            return jsonify({"status": "success", "result": payload})

        if state in ('FAILURE', 'REVOKED'):
            error_msg = str(result.result) if result.result else "Unknown error"
            return jsonify({"status": "failure", "error": error_msg})

        # RETRY or any other transient state
        return jsonify({"status": "pending"})

    except Exception as e:
        return jsonify({"status": "unknown", "error": str(e)}), 404


if __name__ == '__main__':
    print("Starting AI Compliance Server...")
    # use_reloader=False prevents double-loading the 5GB model into your 16GB RAM
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)