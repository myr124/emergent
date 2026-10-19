import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# How long a finished simulation's results stay readable.
SIM_RESULT_TTL = int(os.getenv("SIM_RESULT_TTL", str(24 * 3600)))
# How long a cached persona response is reused for an identical plan.
PERSONA_CACHE_TTL = int(os.getenv("PERSONA_CACHE_TTL", str(7 * 24 * 3600)))
# Bump to invalidate every cached persona response (e.g. after a schema change).
CACHE_VERSION = os.getenv("PERSONA_CACHE_VERSION", "1")

# Pool shape: WORKER_PROCESSES processes, each running WORKER_CONCURRENCY jobs at once.
WORKER_PROCESSES = int(os.getenv("WORKER_PROCESSES", "2"))
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "8"))

JOB_MAX_ATTEMPTS = int(os.getenv("JOB_MAX_ATTEMPTS", "3"))
JOB_TIMEOUT = float(os.getenv("JOB_TIMEOUT", "180"))
# Retry n waits RETRY_BACKOFF_SECONDS * 2^(n-1), capped at 30s.
RETRY_BACKOFF_SECONDS = float(os.getenv("JOB_RETRY_BACKOFF_SECONDS", "2"))

HEARTBEAT_INTERVAL = float(os.getenv("WORKER_HEARTBEAT_INTERVAL", "5"))
HEARTBEAT_TTL = int(os.getenv("WORKER_HEARTBEAT_TTL", "20"))
REAP_INTERVAL = float(os.getenv("WORKER_REAP_INTERVAL", "10"))

MAX_PROMPT_BYTES = 256 * 1024
