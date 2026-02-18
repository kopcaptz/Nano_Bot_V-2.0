"""LiteLLM Router provider with heuristic-based model selection."""

from __future__ import annotations

import json
import os
from typing import Any

from litellm import Router, acompletion

from nanobot.agent.model_router import get_model_for_request
from nanobot.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from nanobot.providers.registry import find_by_model, find_gateway


class LiteLLMRouterProvider(LLMProvider):
    """
    LLM provider using LiteLLM Router with heuristic-based model selection.
    
    Selects model per request based on:
    - is_background -> free-model (Aurora)
    - keywords (code, debug, etc.) -> smart-model (Claude)
    - short query -> cheap-model (Qwen)
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "anthropic/claude-opus-4-5",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
        model_router_config: "ModelRouterConfig | None" = None,
    ):
        from nanobot.config.schema import ModelRouterConfig

        super().__init__(api_key, api_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}
        self._model_router_config = model_router_config or ModelRouterConfig()
        self._gateway = find_gateway(provider_name, api_key, api_base)

        if api_key:
            self._setup_env(api_key, api_base, default_model)

        self._router: Router | None = None
        if self._model_router_config.enabled and self._model_router_config.models:
            self._router = self._build_router(api_key, api_base)

    def _setup_env(self, api_key: str, api_base: str | None, model: str) -> None:
        """Set environment variables for LiteLLM."""
        spec = self._gateway or find_by_model(model)
        if not spec:
            return
        if self._gateway:
            os.environ[spec.env_key] = api_key
        else:
            os.environ.setdefault(spec.env_key, api_key)
        effective_base = api_base or spec.default_api_base
        for env_name, env_val in spec.env_extras:
            resolved = env_val.replace("{api_key}", api_key)
            resolved = resolved.replace("{api_base}", effective_base or "")
            os.environ.setdefault(env_name, resolved)

    def _build_router(self, api_key: str | None, api_base: str | None) -> Router:
        """Build LiteLLM Router from model_router config."""
        model_list = []
        for m in self._model_router_config.models:
            params = dict(m.litellm_params)
            if api_key and "api_key" not in params:
                params["api_key"] = api_key
            if api_base and "api_base" not in params:
                params["api_base"] = api_base
            if self.extra_headers and "extra_headers" not in params:
                params["extra_headers"] = self.extra_headers
            model_list.append({
                "model_name": m.model_name,
                "litellm_params": params,
                "model_info": {"max_tokens": 4096},
            })

        fallbacks_flat: list[dict[str, str]] = []
        for fb in self._model_router_config.fallbacks:
            for src, dst in fb.items():
                if isinstance(dst, list):
                    for d in dst:
                        fallbacks_flat.append({src: d})
                else:
                    fallbacks_flat.append({src: dst})

        return Router(
            model_list=model_list,
            routing_strategy=self._model_router_config.routing_strategy or "cost-based-routing",
            fallbacks=fallbacks_flat if fallbacks_flat else [],
        )

    def _extract_query(self, messages: list[dict[str, Any]]) -> str:
        """Extract the last user message as query for heuristics."""
        for m in reversed(messages):
            role = m.get("role", "")
            content = m.get("content", "")
            if role == "user" and content:
                if isinstance(content, list):
                    parts = [p.get("text", "") for p in content if isinstance(p, dict) and "text" in p]
                    return " ".join(parts) if parts else ""
                return str(content)
        return ""

    def get_default_model(self) -> str:
        """Default model when router is disabled or no models configured."""
        if self._model_router_config.enabled and self._model_router_config.models:
            return self._model_router_config.models[0].model_name
        return self.default_model

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        metadata: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Send chat via LiteLLM Router with heuristic model selection."""
        metadata = metadata or {}
        is_background = metadata.get("is_background", False)

        if self._router:
            query = self._extract_query(messages)
            chosen = get_model_for_request(
                query=query,
                is_background=is_background,
                config=self._model_router_config,
            )
            model = chosen or model or self.get_default_model()
        else:
            model = model or self.get_default_model()

        kwargs_dict: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "timeout": 120,
        }
        if tools:
            kwargs_dict["tools"] = tools
            kwargs_dict["tool_choice"] = "auto"
        if self.api_key:
            kwargs_dict["api_key"] = self.api_key
        if self.api_base:
            kwargs_dict["api_base"] = self.api_base
        if self.extra_headers:
            kwargs_dict["extra_headers"] = self.extra_headers

        completion_fn = self._router.acompletion if self._router else acompletion

        try:
            response = await completion_fn(**kwargs_dict)
            return self._parse_response(response)
        except Exception as e:
            return LLMResponse(
                content=f"Error calling LLM: {str(e)}",
                finish_reason="error",
            )

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse LiteLLM response into LLMResponse."""
        choice = response.choices[0]
        message = choice.message
        tool_calls = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {"raw": args}
                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))
        usage = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
        reasoning_content = getattr(message, "reasoning_content", None)
        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
        )
