# DjangoManager/middleware/performance.py
import time
import json
import logging
from django.db import connection

logger = logging.getLogger(__name__)

# SRS §1.5.1 thresholds — used for severity tagging
THRESHOLD_WARNING_MS  = 3000   # warn at 3s
THRESHOLD_ERROR_MS    = 5000   # SRS hard limit: all interactions < 5s
THRESHOLD_CRITICAL_MS = 10000  # AI analysis paths only


class PerformanceLoggingMiddleware:
    """
    Records API response time, HTTP status, and error rate per request.
    Logs structured JSON to Django's logger which feeds into CloudWatch Logs
    via the existing AWS setup (same credentials as S3/SSM in views.py).

    Severity tagging matches architecture §2.2.5:
      info     — response within SRS threshold
      warning  — response between 3s–5s
      error    — response exceeded 5s SRS limit
      critical — response exceeded 10s (AI analysis paths)
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start_time = time.time()

        # Reset per-request DB query tracking
        if hasattr(connection, "queries_log"):
            connection.queries_log.clear()        

        response = self.get_response(request)

        duration_ms = round((time.time() - start_time) * 1000, 2)

        # Capture DB metrics
        db_queries = connection.queries
        db_query_count = len(db_queries)
        db_latency_ms = round(
            sum(float(q.get("time", 0)) for q in db_queries) * 1000,
            2
        )

        # Assign severity based on SRS thresholds
        if duration_ms < THRESHOLD_WARNING_MS:
            severity = 'info'
        elif duration_ms < THRESHOLD_ERROR_MS:
            severity = 'warning'
        elif duration_ms < THRESHOLD_CRITICAL_MS:
            severity = 'error'
        else:
            severity = 'critical'

        # Escalate severity if DB latency is high
        if db_latency_ms > 2000:
            severity = 'critical'
        elif db_latency_ms > 1000 and severity != 'critical':
            severity = 'error'
        elif db_latency_ms > 500 and severity == 'info':
            severity = 'warning'

        log_entry = {
            'path':             request.path,
            'view':             request.resolver_match.view_name if request.resolver_match else 'unknown',
            'method':           request.method,
            'status':           response.status_code,
            'duration_ms':      duration_ms,
            'db_query_count':   db_query_count,
            'db_latency_ms':    db_latency_ms,            
            'severity':         severity,
        }

        # Log at the appropriate level so CloudWatch filters work correctly
        if severity == 'info':
            logger.info(json.dumps(log_entry))
        elif severity == 'warning':
            logger.warning(json.dumps(log_entry))
        else:
            logger.error(json.dumps(log_entry))

        return response