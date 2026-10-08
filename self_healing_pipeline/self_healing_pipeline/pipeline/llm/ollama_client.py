"""
OllamaClient — thin wrapper around the Ollama HTTP /api/generate endpoint.

Uses the `format: "json"` parameter to force structured JSON output.
Includes retry logic and a fallback JSON extractor for when the model
occasionally wraps the JSON in markdown code fences.
"""

import json
import logging
import re
import time
from typing import Optional

import requests

from ..config import OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_TEMPERATURE

logger = logging.getLogger(__name__)

_GENERATE_URL = f"{OLLAMA_BASE_URL}/api/generate"


def _repair_json(text: str) -> Optional[dict]:
    """
    Best-effort repair of truncated JSON.
    Closes any open string, then appends missing ] and } characters.
    Returns a dict if repair succeeds, else None.
    """
    s = text.rstrip()

    # If truncated mid-string, close the string
    # Count unescaped quotes to determine if we're inside a string
    in_string = False
    i = 0
    while i < len(s):
        c = s[i]
        if c == '\\' and in_string:
            i += 2
            continue
        if c == '"':
            in_string = not in_string
        i += 1
    if in_string:
        s += '"'

    # Remove trailing comma (invalid before closing brackets)
    s = re.sub(r",\s*$", "", s)

    # Count unclosed brackets and braces
    depth_brace  = s.count("{") - s.count("}")
    depth_bracket = s.count("[") - s.count("]")

    # Close in LIFO order — approximate since we don't track the actual stack
    s += "]" * max(depth_bracket, 0) + "}" * max(depth_brace, 0)

    try:
        result = json.loads(s)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass
    return None
_DEFAULT_SYSTEM = (
    "You are a cloud infrastructure expert specialising in AIOps, SRE, and "
    "autonomous monitoring systems. You analyse cloud telemetry and provide "
    "precise, actionable recommendations. Always respond with valid JSON only."
)


class OllamaClient:
    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        base_url: str = OLLAMA_BASE_URL,
        timeout: int = OLLAMA_TIMEOUT,
        temperature: float = OLLAMA_TEMPERATURE,
    ):
        self.model       = model
        self.base_url    = base_url
        self.timeout     = timeout
        self.temperature = temperature
        self._session    = requests.Session()

    def generate(self, prompt: str, max_retries: int = 2) -> Optional[dict]:
        """
        Send prompt to Ollama; return parsed JSON dict or None on failure.
        """
        payload = {
            "model":  self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": self.temperature,
                "num_predict": 2048,
                "think":       False,   # disable qwen3 thinking — saves tokens for actual JSON
            },
        }

        for attempt in range(max_retries + 1):
            try:
                resp = self._session.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                raw_text = data.get("response", "")
                parsed = self._parse_json(raw_text)
                if parsed is not None:
                    return parsed
                logger.warning("Ollama response was not valid JSON (attempt %d)", attempt + 1)
            except requests.exceptions.Timeout:
                logger.warning("Ollama timeout (attempt %d/%d)", attempt + 1, max_retries + 1)
            except requests.exceptions.ConnectionError:
                logger.error("Cannot reach Ollama at %s", self.base_url)
                return None
            except Exception as exc:
                logger.warning("Ollama error (attempt %d): %s", attempt + 1, exc)

            if attempt < max_retries:
                time.sleep(2 ** attempt)  # exponential back-off: 1s, 2s

        return None

    def health_check(self) -> bool:
        """Returns True if Ollama is reachable and the model is loaded."""
        try:
            resp = self._session.get(f"{self.base_url}/api/tags", timeout=5)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            # Accept prefix match so "qwen3:8b" matches "qwen3:8b-instruct" etc.
            model_base = self.model.split(":")[0]
            return any(m.startswith(model_base) or m == self.model for m in models)
        except Exception:
            return False

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        """
        Parse JSON from Ollama response. Handles:
          - qwen3 <think>…</think> blocks (stripped before parsing)
          - Markdown code fences (```json … ```)
          - Truncated JSON (closes dangling braces/brackets as best-effort)
        """
        # Strip qwen3 thinking blocks — they appear before the JSON even with format:json
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()

        # Direct parse
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        # Extract from ```json … ``` or ``` … ```
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if m:
            try:
                result = json.loads(m.group(1))
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass

        # Find the first { … } block (may be truncated)
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            candidate = m.group(0)
            try:
                result = json.loads(candidate)
                if isinstance(result, dict):
                    return result
            except json.JSONDecodeError:
                pass
            # Attempt to repair truncated JSON by closing open braces/brackets
            repaired = _repair_json(candidate)
            if repaired:
                return repaired

        return None
