from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
VENDOR_DIR = BASE_DIR / "vendor"          # KaTeX lives in vendor/katex

# --- fetching ---------------------------------------------------------------
NAV_TIMEOUT_MS = 45_000
SELECTOR_TIMEOUT_MS = 20_000
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
MSG_SEL = "[data-message-author-role]"    # the one selector everything depends on

# --- images -----------------------------------------------------------------
IMAGE_HOST_SUFFIXES = ("oaiusercontent.com", "openai.com", "chatgpt.com", "oaistatic.com")
MAX_IMAGE_BYTES = 15 * 1024 * 1024
MAX_IMAGES = 60
IMAGE_MAX_WIDTH_PX = 1400

# --- service ----------------------------------------------------------------
MAX_CONCURRENT_JOBS = 2
JOB_TIMEOUT_SECONDS = 120
JOB_TTL_SECONDS = 30 * 60
RATE_LIMIT_PER_MINUTE = 6
