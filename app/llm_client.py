"""
LLM Client for Checkpoint 10.
Interfaces with local Ollama or compatible LLM API endpoints.
Enforces JSON formatting, handles timeouts, and provides retry capabilities.
"""

import json
import logging
from typing import Optional, Dict, Any
import requests

from app.config import OLLAMA_BASE_URL, LLM_MODEL, setup_logger

logger = setup_logger("llm_client")


class LLMClient:
    """
    Client for interacting with local Ollama or compatible OpenAI/Gemini endpoints.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = 300,
    ):
        self.base_url = (base_url or OLLAMA_BASE_URL).rstrip("/")
        self.model = model or LLM_MODEL
        self.timeout = timeout

    def _request_raw(self, payload: Dict[str, Any]) -> str:
        """Sends the HTTP request to the LLM backend and returns the raw response string."""
        endpoint = f"{self.base_url}/api/generate"
        response = requests.post(
            endpoint,
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()

    def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.0,
        max_retries: int = 2,
    ) -> Dict[str, Any]:
        """
        Calls the LLM with format="json" and returns the parsed dictionary.
        Retries up to max_retries on transient failure or invalid JSON.
        """
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": system_prompt or "",
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
            },
        }

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    f"Calling LLM model '{self.model}' (attempt {attempt}/{max_retries})..."
                )
                response_text = self._request_raw(payload)

                if not response_text:
                    raise ValueError("LLM returned an empty response.")

                # Parse JSON with robust fallback
                try:
                    parsed_json = json.loads(response_text)
                except json.JSONDecodeError:
                    import re
                    cleaned = response_text.strip()
                    if cleaned.startswith("```json"):
                        cleaned = cleaned[7:]
                    elif cleaned.startswith("```"):
                        cleaned = cleaned[3:]
                    if cleaned.endswith("```"):
                        cleaned = cleaned[:-3]
                    cleaned = cleaned.strip()
                    try:
                        parsed_json = json.loads(cleaned)
                    except json.JSONDecodeError:
                        m = re.search(r"(\{.*\})", cleaned, re.DOTALL)
                        if m:
                            cand = m.group(1)
                            try:
                                parsed_json = json.loads(cand)
                            except json.JSONDecodeError:
                                # Replace inner quotes or trailing broken strings
                                fixed = re.sub(r'([^\\])"([^:,\]\}]+)"([^\\])', r"\1'\2'\3", cand)
                                try:
                                    parsed_json = json.loads(fixed)
                                except Exception:
                                    # Fallback: extract eligibility and exclusion items via regex
                                    elig_items = []
                                    excl_items = []
                                    for r_match in re.finditer(r'\{[^{}]*"rule"\s*:\s*"([^"]+)"[^{}]*\}', cand):
                                        item_str = r_match.group(0)
                                        rule_m = re.search(r'"rule"\s*:\s*"([^"]+)"', item_str)
                                        type_m = re.search(r'"type"\s*:\s*"([^"]+)"', item_str)
                                        ev_m = re.search(r'"evidence"\s*:\s*"([^"]+)"', item_str)
                                        if rule_m:
                                            r_data = {
                                                "rule": rule_m.group(1),
                                                "type": type_m.group(1) if type_m else "eligibility",
                                                "evidence": ev_m.group(1) if ev_m else ""
                                            }
                                            if r_data["type"] == "exclusion" or "excl" in item_str:
                                                excl_items.append(r_data)
                                            else:
                                                elig_items.append(r_data)
                                    parsed_json = {
                                        "eligibility_rules": elig_items,
                                        "exclusion_rules": excl_items
                                    }
                        else:
                            raise
                logger.info(f"LLM response successfully received and parsed ({len(response_text)} chars).")
                return parsed_json

            except (requests.RequestException, json.JSONDecodeError, ValueError) as e:
                last_error = e
                logger.warning(
                    f"LLM call failed on attempt {attempt}/{max_retries}: {type(e).__name__} - {e}"
                )
                if attempt < max_retries:
                    continue

        raise RuntimeError(
            f"Failed to generate valid JSON from LLM '{self.model}' after {max_retries} attempts: {last_error}"
        )

    def is_available(self) -> bool:
        """Checks whether the Ollama server and configured model are accessible."""
        try:
            res = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if res.status_code == 200:
                tags_data = res.json()
                models = [m.get("name") for m in tags_data.get("models", [])]
                # Check exact or prefix match (e.g. qwen2.5:7b matches qwen2.5:7b-instruct)
                has_model = any(self.model in m or m in self.model for m in models)
                return has_model
            return False
        except Exception:
            return False
