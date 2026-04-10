"""Centralized configuration for the APEX backend.

All hardcoded values and environment-variable defaults live here so they are
easy to find, audit, and override.
"""

import os

# ── Upload ────────────────────────────────────────────────────────────
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
CHUNK_SIZE: int = int(os.getenv("UPLOAD_CHUNK_SIZE", str(2 * 1024 * 1024)))  # 2 MB
CHUNK_SIZE_BYTES: int = CHUNK_SIZE  # alias used by validation code
SESSION_TTL: int = int(os.getenv("UPLOAD_SESSION_TTL", "1800"))  # 30 minutes
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_MB", "2048")) * 1024 * 1024
ALLOWED_EXTENSIONS: set[str] = {
    "pdf", "docx", "doc", "xlsx", "xls", "csv", "est", "txt", "rtf",
}

# ── LLM defaults ─────────────────────────────────────────────────────
DEFAULT_LLM_PROVIDER: str = os.getenv("DEFAULT_LLM_PROVIDER", os.getenv("LLM_PROVIDER", "ollama"))
DEFAULT_LLM_MODEL: str = os.getenv("DEFAULT_LLM_MODEL", "")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

# ── Server ────────────────────────────────────────────────────────────
PORT: int = int(os.getenv("PORT", "8000"))
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
APEX_DEV_MODE: bool = os.getenv("APEX_DEV_MODE", "").lower() in ("true", "1", "yes")

_cors_env = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
CORS_ORIGINS: list[str] = [o.strip() for o in _cors_env.split(",") if o.strip()]
# Auto-add Railway public domain if provided
_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
if _railway_domain:
    CORS_ORIGINS.append(f"https://{_railway_domain}")

# ── Rate limiting ─────────────────────────────────────────────────────
GLOBAL_RATE_LIMIT: str = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
AUTH_LOGIN_RATE_LIMIT: str = os.getenv("RATE_LIMIT_LOGIN", "5/minute")
AUTH_REGISTER_RATE_LIMIT: str = os.getenv("RATE_LIMIT_REGISTER", "3/minute")
PIPELINE_RATE_LIMIT: str = os.getenv("RATE_LIMIT_PIPELINE", "10/minute")

# ── Email / SMTP ──────────────────────────────────────────────────────
SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM: str = os.getenv("EMAIL_FROM", "noreply@apex-platform.com")
EMAIL_ENABLED: bool = bool(SMTP_HOST and SMTP_USER)
