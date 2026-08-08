# -*- coding: utf-8 -*-
"""LLM 模块 — OpenAI 兼容多提供方客户端

provider="openai": OpenAI 兼容 API，POST {endpoint}{chat_path}
（DeepSeek、OpenAI、通义、vLLM、Ollama 等）
"""
import requests

from core.config import is_llm_configured, resolve_llm_profile
from core.logger import logger


class LLMClient:
    """LLM 客户端（OpenAI 兼容多提供方）"""

    def __init__(self):
        self.profile_name, p = resolve_llm_profile()
        self.provider = p.get("provider", "openai")
        self.endpoint = p.get("endpoint", "")
        self.api_key = p.get("api_key", "")
        self.model = p.get("model", "")
        self.vision_model = p.get("vision_model", "") or self.model
        self.chat_path = p.get("chat_path", "/v1/chat/completions")
        self.max_tokens = p.get("max_tokens", 4096)
        self.temperature = p.get("temperature", 0.7)
        self.timeout = p.get("timeout", 60)

        if self.profile_name:
            logger.info("LLM profile '{}'（provider={}, model={}）",
                        self.profile_name, self.provider, self.model)

    def available(self) -> bool:
        return is_llm_configured()

    def _call(self, messages: list, model: str = "") -> str:
        """调用 OpenAI 兼容 chat completions，返回 assistant 文本。"""
        url = f"{self.endpoint.rstrip('/')}{self.chat_path}"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {
            "model": model or self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "stream": False,
        }
        resp = requests.post(url, json=body, headers=headers, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    def chat(self, system: str, user: str, model: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": user})
        return self._call(messages, model)


# 全局单例
_llm: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm
    if _llm is None:
        _llm = LLMClient()
    return _llm
