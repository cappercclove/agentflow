"""Access control for the one case the desktop build never had: this app sitting on
a public address, where any visitor can spend the owner's model quota.

Everything here is inert unless AGENTFLOW_ACCESS_CODE is set, so running from source
or from the Electron package behaves exactly as it always did.
"""

import base64
import hashlib
import hmac
import os
import time
from threading import Lock

SESSION_COOKIE = "af_session"
SESSION_TTL = 12 * 3600

# One code guards the whole site, so a guessed code is the only way in. Attempts get
# their own much tighter budget than the workloads do.
DEFAULT_LIMITS = {
    "login": (10, 600),
    "execute": (30, 3600),
    "decompose": (10, 3600),
    "node": (20, 3600),
}

DAILY_RUNS_KEY = "daily_runs"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _now() -> float:
    """Session clocks go through here so their expiry can be pinned in tests."""
    return time.time()


def access_code() -> str:
    return os.getenv("AGENTFLOW_ACCESS_CODE", "").strip()


def auth_enabled() -> bool:
    return bool(access_code())


def trust_proxy() -> bool:
    return os.getenv("AGENTFLOW_TRUST_PROXY", "").strip() in ("1", "true", "yes")


def cookie_secure() -> bool:
    """Set on when TLS terminates at the reverse proxy, so the cookie never leaves
    the browser over a plain connection."""
    return os.getenv("AGENTFLOW_COOKIE_SECURE", "").strip() in ("1", "true", "yes")


def _secret() -> bytes:
    configured = os.getenv("AGENTFLOW_SESSION_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    # Deriving from the access code keeps a restart from invalidating every session,
    # without asking anyone to generate a second random string.
    return hashlib.sha256(f"agentflow:{access_code()}".encode("utf-8")).digest()


def _sign(payload: bytes) -> str:
    return base64.urlsafe_b64encode(hmac.new(_secret(), payload, hashlib.sha256).digest()).decode("ascii").rstrip("=")


def issue_session() -> str:
    expires = int(_now()) + SESSION_TTL
    payload = str(expires).encode("ascii")
    return f"{expires}.{_sign(payload)}"


def valid_session(token) -> bool:
    if not token or not auth_enabled():
        return False
    try:
        expires_text, signature = token.split(".", 1)
        expires = int(expires_text)
    except (ValueError, AttributeError):
        return False
    if expires < _now():
        return False
    expected = _sign(str(expires).encode("ascii"))
    return hmac.compare_digest(signature, expected)


def code_matches(submitted) -> bool:
    if not isinstance(submitted, str):
        return False
    return hmac.compare_digest(submitted.strip().encode("utf-8"), access_code().encode("utf-8"))


def client_ip(request) -> str:
    if trust_proxy():
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return getattr(client, "host", None) or "unknown"


class Window:
    """Fixed-window counter per key. Cheap, and good enough to stop a runaway script."""

    def __init__(self, limit: int, seconds: int):
        self.limit = limit
        self.seconds = seconds
        self._hits: dict[str, tuple[int, int]] = {}
        self._lock = Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        now = int(time.time())
        bucket = now // self.seconds
        with self._lock:
            if len(self._hits) > 4096:
                self._hits = {k: v for k, v in self._hits.items() if v[0] == bucket}
            used, stored = self._hits.get(key, (0, bucket))
            if stored != bucket:
                used, stored = 0, bucket
            if used >= self.limit:
                return False, (bucket + 1) * self.seconds - now
            self._hits[key] = (used + 1, stored)
            return True, 0

    def reset(self):
        with self._lock:
            self._hits.clear()


LIMITS = {name: Window(*DEFAULT_LIMITS[name]) for name in DEFAULT_LIMITS}


def limit_for(name: str) -> Window:
    limit, seconds = DEFAULT_LIMITS[name]
    window = LIMITS[name]
    window.limit = _env_int(f"AGENTFLOW_LIMIT_{name.upper()}", limit)
    return window


class DailyBudget:
    """Site-wide cap on started runs, so one open afternoon cannot empty a coupon."""

    def __init__(self, hard_max: int):
        self.hard_max = hard_max
        self._day = None
        self._used = 0
        self._lock = Lock()

    def _today(self) -> str:
        return time.strftime("%Y-%m-%d", time.gmtime())

    def consume(self) -> tuple[bool, int]:
        with self._lock:
            today = self._today()
            if today != self._day:
                self._day, self._used = today, 0
            if self._used >= self.hard_max:
                return False, self.hard_max
            self._used += 1
            return True, self.hard_max

    @property
    def remaining(self) -> int:
        with self._lock:
            today = self._today()
            if today != self._day:
                return self.hard_max
            return max(0, self.hard_max - self._used)

    def reset(self):
        with self._lock:
            self._day = None
            self._used = 0


DAILY_RUNS = DailyBudget(_env_int("AGENTFLOW_DAILY_RUNS", 200))


def deny_message(name: str, retry_after: int) -> str:
    if name == "login":
        return "口令尝试次数过多，请稍后再试"
    minutes = max(1, int(retry_after // 60))
    return f"这个操作太频繁了，请 {minutes} 分钟后再试"


def budget_message(hard_max: int) -> str:
    return f"今天的运行次数已经用完（上限 {hard_max} 次），明天再来"
