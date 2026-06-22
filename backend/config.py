"""
config.py — Load all environment variables via python-dotenv.
Import `settings` everywhere instead of calling os.getenv() directly.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # ── Vapi ──────────────────────────────────────────────────────
    VAPI_API_KEY: str = os.getenv("VAPI_API_KEY", "")
    VAPI_ASSISTANT_ID: str = os.getenv("VAPI_ASSISTANT_ID", "")
    VAPI_PHONE_NUMBER_ID: str = os.getenv("VAPI_PHONE_NUMBER_ID", "")
    VAPI_PUBLIC_KEY: str = os.getenv("VAPI_PUBLIC_KEY", "")

    # ── LLM (Groq) ────────────────────────────────────────────────
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # ── TTS (ElevenLabs) ──────────────────────────────────────────
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "")

    # ── Supabase ──────────────────────────────────────────────────
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")

    # ── Escalation ────────────────────────────────────────────────
    OWNER_PHONE: str = os.getenv("OWNER_PHONE", "")

    # ── Langfuse Observability ────────────────────────────────────
    LANGFUSE_PUBLIC_KEY: str = os.getenv("LANGFUSE_PUBLIC_KEY", "")
    LANGFUSE_SECRET_KEY: str = os.getenv("LANGFUSE_SECRET_KEY", "")
    LANGFUSE_HOST: str = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com")

    # ── App ───────────────────────────────────────────────────────
    BACKEND_URL: str = os.getenv("BACKEND_URL", "http://localhost:8000")


settings = Settings()
