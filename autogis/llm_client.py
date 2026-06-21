from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
        "api_key_env": "DEEPSEEK_API_KEY",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
        "api_key_env": "OPENAI_API_KEY",
    },
}


@dataclass
class LLMConfig:
    provider: str
    base_url: str
    model: str
    api_key_env: str
    has_key: bool

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "has_key": self.has_key,
        }


def get_llm_config(provider: str = "deepseek", model: str | None = None) -> LLMConfig:
    defaults = PROVIDERS.get(provider, PROVIDERS["deepseek"])
    api_key_env = defaults["api_key_env"]
    return LLMConfig(
        provider=provider,
        base_url=os.environ.get(f"{provider.upper()}_BASE_URL", defaults["base_url"]),
        model=model or os.environ.get(f"{provider.upper()}_MODEL", defaults["model"]),
        api_key_env=api_key_env,
        has_key=bool(os.environ.get(api_key_env)),
    )


def chat_json(
    messages: list[dict[str, str]],
    provider: str = "deepseek",
    model: str | None = None,
    temperature: float = 0.1,
    max_tokens: int = 1800,
) -> dict[str, Any]:
    config = get_llm_config(provider, model)
    api_key = os.environ.get(config.api_key_env)
    if not api_key:
        raise RuntimeError(f"Missing API key. Set environment variable {config.api_key_env}.")

    url = config.base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": config.model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "response_format": {"type": "json_object"},
    }
    if provider == "deepseek" and config.model.startswith("deepseek-v4"):
        body["thinking"] = {"type": "disabled"}

    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM HTTP error {exc.code}: {detail}") from exc

    content = payload["choices"][0]["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model did not return valid JSON: {content[:500]}") from exc

