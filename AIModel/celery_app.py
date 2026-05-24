from celery import Celery

# Redis broker: jobs go in, workers pick them up.
# Result backend: workers write results back so Django can poll.
celery = Celery(
    'cybercomply_ai',
    broker='redis://127.0.0.1:6379/0',
    backend='redis://127.0.0.1:6379/1',
)

celery.conf.update(
    # Fix for empty [tasks] — explicitly register the task module
    imports=['api_server'],
    
    # Serialisation
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],

    # A single analysis job can take up to 20 minutes (68 requirements × batches).
    # Kill it hard after 25 minutes so it never blocks the worker forever.
    task_time_limit=1500,          # hard kill  (seconds)
    task_soft_time_limit=1200,     # SoftTimeLimitExceeded raised first (seconds)

    # Keep results in Redis for 2 hours — long enough for any reasonable poll loop.
    result_expires=7200,

    # One worker process handles one job at a time.
    # This is intentional: each job already saturates OpenRouter's rate limit
    # through its 12-batch internal loop. Running two jobs in parallel would
    # cause 429s. Concurrency=1 serialises jobs cleanly.
    worker_concurrency=1,

    # Fix for Windows PermissionError — use solo pool instead of prefork
    worker_pool='solo',

    # Retry a failed task once after 60 s before marking it FAILURE.
    task_max_retries=1,
    task_default_retry_delay=60,

    # Timezone
    timezone='Asia/Colombo',
    enable_utc=True,
)
