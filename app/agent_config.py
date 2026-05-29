from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

AGENT_RATE_LIMIT_PER_MINUTE = int(os.getenv("AGENT_RATE_LIMIT_PER_MINUTE", "30"))
AGENT_SESSION_MAX_MESSAGES = int(os.getenv("AGENT_SESSION_MAX_MESSAGES", "100"))
AGENT_CONTEXT_MESSAGE_LIMIT = int(os.getenv("AGENT_CONTEXT_MESSAGE_LIMIT", "8"))
AGENT_LLM_ENABLED = os.getenv("AGENT_LLM_ENABLED", "false").lower() in ("1", "true", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
