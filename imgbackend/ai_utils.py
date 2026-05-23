"""
Compatibility layer for Gemini client usage across the backend.

Exports `genai` and `types` so existing imports continue to work, while
defaulting API key auth to environment variables from `.env`.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai as _genai
from google.genai import types

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env", override=False)


class genai:
    @staticmethod
    def Client(*args, **kwargs):
        if not kwargs.get("api_key"):
            api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
            kwargs["api_key"] = (api_key or "").strip()
        return _genai.Client(*args, **kwargs)


__all__ = ["genai", "types"]
