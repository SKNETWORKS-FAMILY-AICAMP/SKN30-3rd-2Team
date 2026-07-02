"""OpenAI 호환 Chat Completions provider — openai SDK 하나로 openai/gemini/custom 처리."""
from .base import AssistantTurn, ProviderConfig, ToolCall
from openai import OpenAI


class OpenAICompatProvider:
    """base_url 만 바꿔 OpenAI·Gemini(OpenAI 호환)·자체 vLLM 서빙을 동일 코드로 호출."""

    def __init__(self, config: ProviderConfig):
        if not config.model:
            raise ValueError(f"[{config.name}] 모델명이 비어 있습니다 — 환경변수(*_MODEL)를 확인하세요.")
        self.config = config
        kwargs = {}
        if config.api_key:
            kwargs["api_key"] = config.api_key
        if config.base_url:
            kwargs["base_url"] = config.base_url
        self._client = OpenAI(**kwargs)

    def complete(self, messages, tools=None, temperature=0.2) -> AssistantTurn:
        params = {"model": self.config.model, "messages": messages, "temperature": temperature}
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
        resp = self._client.chat.completions.create(**params)
        msg = resp.choices[0].message
        calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=tc.function.arguments or "{}")
            for tc in (msg.tool_calls or [])
        ]
        return AssistantTurn(content=msg.content, tool_calls=calls, raw=msg)

    def stream(self, messages, temperature=0.2):
        """content 델타를 순차 yield (요약 스트리밍용, 도구 미사용)."""
        resp = self._client.chat.completions.create(
            model=self.config.model, messages=messages, temperature=temperature, stream=True,
        )
        for chunk in resp:
            if not chunk.choices:
                continue
            piece = getattr(chunk.choices[0].delta, "content", None)
            if piece:
                yield piece
