"""환경변수 기반 provider 선택/구성."""
import os
from typing import Optional

import config
from .base import ProviderConfig
from .providers import OpenAICompatProvider

_SUPPORTED = ("openai", "gemini", "custom")


def _config_for(name: Optional[str] = None) -> ProviderConfig:
    name = (name or config.LLM_PROVIDER).lower()
    if name == "openai":
        return ProviderConfig("openai", model=config.OPENAI_MODEL, api_key=config.OPENAI_API_KEY)
    if name == "gemini":
        return ProviderConfig("gemini", model=config.GEMINI_MODEL,
                              base_url=config.GEMINI_BASE_URL, api_key=config.GEMINI_API_KEY)
    if name == "custom":
        return ProviderConfig("custom", model=config.CUSTOM_LLM_MODEL,
                              base_url=config.CUSTOM_LLM_BASE_URL, api_key=config.CUSTOM_LLM_API_KEY)
    raise ValueError(f"지원하지 않는 LLM_PROVIDER: {name!r} (가능: {_SUPPORTED})")


def build_provider(name: Optional[str] = None) -> OpenAICompatProvider:
    return OpenAICompatProvider(_config_for(name))


def available_providers() -> tuple:
    return _SUPPORTED


def is_configured(name: Optional[str] = None) -> bool:
    """선택된 provider가 호출 가능한 최소 설정(키/베이스URL/모델)을 갖췄는지 확인."""
    try:
        cfg = _config_for(name)
    except ValueError:
        return False
    if cfg.name == "openai":
        return bool(cfg.api_key or os.getenv("OPENAI_API_KEY"))
    if cfg.name == "gemini":
        return bool(cfg.api_key and cfg.model)
    if cfg.name == "custom":
        return bool(cfg.base_url and cfg.model)
    return False
