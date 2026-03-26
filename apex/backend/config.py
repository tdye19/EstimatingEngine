"""Centralized configuration for the APEX backend.

All hardcoded values and environment-variable defaults live here so they are
easy to find, audit, and override.
"""

import os

# ── Upload ────────────────────────────────────────────────────────────
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
CHUNK_SIZE: int = int(os.getenv("UPLOAD_CHUNK_SIZE", str(1024 * 1024)))  # 1 MB
SESSION_TTL: int = int(os.getenv("UPLOAD_SESSION_TTL", "1800"))  # 30 minutes
MAX_UPLOAD_BYTES: int = int(os.getenv("MAX_UPLOAD_MB", "50")) * 1024 * 1024
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
CORS_ORIGINS: list[str] = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

# ── Rate limiting ─────────────────────────────────────────────────────
GLOBAL_RATE_LIMIT: str = os.getenv("RATE_LIMIT_DEFAULT", "120/minute")
AUTH_LOGIN_RATE_LIMIT: str = os.getenv("RATE_LIMIT_LOGIN", "10/minute")
AUTH_REGISTER_RATE_LIMIT: str = os.getenv("RATE_LIMIT_REGISTER", "5/minute")
